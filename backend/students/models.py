"""Ученики, учебные группы, пять профильных таблиц и история достижений.

Инвариант №5: всё, что имеет историю (моки, активности, соревнования),
живёт строками в дочерних таблицах, а не полями профиля.
Инвариант №6: никакого JSONB — только типизированные колонки.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils.translation import gettext, gettext_lazy

from core.archivable import Archivable


class GroupLanguage(models.TextChoices):
    """Язык группы (фаза 66): на нём составляются письма родителям и ученикам."""

    RU = "ru", gettext_lazy("Русский")
    KK = "kk", gettext_lazy("Казахский")


class Parallel(models.IntegerChoices):
    """Параллель группы: школа ведёт 8–11, поступление — только у 11.

    Параллель есть только у группы. Ученику она не выбирается и не вводится:
    его параллель — параллель его группы (`core.parallels.parallel_of`).
    Что какая параллель видит — один реестр, `core/parallels.py`.
    """

    EIGHTH = 8, "8"
    NINTH = 9, "9"
    TENTH = 10, "10"
    ELEVENTH = 11, "11"


#: параллель выпускников: у неё поступление, и её ведёт Асем
GRADUATE_PARALLEL = Parallel.ELEVENTH


class StudyGroup(Archivable):
    """Учебная группа — единица контроля, 15–20 учеников.

    Куратора у группы держит назначение с датой (`accounts.CuratorAssignment`),
    а не поле с именем: по имени нельзя ни войти, ни проверить право.
    Текстовое поле было до фазы 61 и удалено вместе с переходом на роль.
    """

    #: уникален только среди действующих групп: выпускная группа уходит
    #: в архив, и её город можно снова дать новой восьмой
    code = models.CharField(gettext_lazy("Код"), max_length=16)
    parallel = models.PositiveSmallIntegerField(
        gettext_lazy("Параллель"), choices=Parallel.choices, default=GRADUATE_PARALLEL
    )
    #: язык, на котором школа пишет этой группе (фаза 66). Нужен письмам:
    #: шаблон подставляется на языке группы, а не на языке того, кто пишет
    language = models.CharField(
        gettext_lazy("Язык группы"), max_length=2, choices=GroupLanguage.choices, default=GroupLanguage.RU
    )
    #: литера класса по списку школы: «А», «Ә», «Б»
    letter = models.CharField(gettext_lazy("Литера"), max_length=4, blank=True)
    #: кабинет, где группа сидит по умолчанию; может быть пустым
    home_room = models.CharField(gettext_lazy("Домашний кабинет"), max_length=40, blank=True)
    is_active = models.BooleanField(gettext_lazy("Активна"), default=True)

    class Meta:
        verbose_name = gettext_lazy("Учебная группа")
        verbose_name_plural = gettext_lazy("Учебные группы")
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(
                fields=("code",), condition=models.Q(archived_at__isnull=True), name="group_code_unique_among_active"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class Student(Archivable):
    """Ученик. Реестровая запись школы, к пяти доменам не относится."""

    last_name = models.CharField(gettext_lazy("Фамилия"), max_length=100)
    first_name = models.CharField(gettext_lazy("Имя"), max_length=100)
    middle_name = models.CharField(gettext_lazy("Отчество"), max_length=100, blank=True)
    #: почта школы — необязательна: у 8–10 её нет, они входят по логину
    #: учётной записи (`accounts.User.login`)
    email = models.EmailField("Email", unique=True, null=True, blank=True)
    group = models.ForeignKey(
        StudyGroup,
        verbose_name=gettext_lazy("Группа"),
        related_name="students",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Учётная запись"),
        related_name="student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    graduation_year = models.PositiveSmallIntegerField(gettext_lazy("Год выпуска"))
    is_active = models.BooleanField(gettext_lazy("Учится"), default=True)
    #: отбор в олимпиадную группу. Признак ставит только директор талантов;
    #: ученик вне группы не видит раздел материалов вовсе — ни в меню,
    #: ни по прямой ссылке, ни в API (фаза 19)
    in_olympiad_group = models.BooleanField(gettext_lazy("В олимпиадной группе"), default=False)
    #: вымышленный ученик — посев прогона или пилотная карточка (фаза 64).
    #: Ставится явно: посевом или командой `mark_fictional`, а не угадывается
    #: по почте. По нему `preflight` ищет, что осталось, а `purge_fictional`
    #: вычищает перед живыми учениками
    is_fictional = models.BooleanField(gettext_lazy("Вымышленный"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Ученик")
        verbose_name_plural = gettext_lazy("Ученики")
        # id в конце — тезки в школе есть, а без уникального ключа порядок
        # между страницами не гарантирован и строки перескакивают
        ordering = ("last_name", "first_name", "id")
        indexes = [
            models.Index(fields=("graduation_year",)),
            models.Index(fields=("in_olympiad_group",)),
        ]

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        return " ".join(x for x in (self.last_name, self.first_name, self.middle_name) if x)


# --- Домен behavior (Салтанат) -----------------------------------------


class BehaviorStatus(models.TextChoices):
    """Внутренний ярлык дисциплины — ученику не показывается (инвариант №7)."""

    CAN_EXECUTE = "can_execute", gettext_lazy("Работает самостоятельно")
    NEEDS_SUPERVISION = "needs_supervision", gettext_lazy("Нужен контроль")
    CRITICAL = "critical", gettext_lazy("Ежедневный контроль")


class BehaviorProfile(Archivable):
    """Профиль и дисциплина. Владелец — домен `behavior`."""

    student = models.OneToOneField(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="behavior", on_delete=models.CASCADE
    )
    attendance_percent = models.PositiveSmallIntegerField(gettext_lazy("Посещаемость, %"), null=True, blank=True)
    remarks_count = models.PositiveSmallIntegerField(gettext_lazy("Замечания"), default=0)
    status = models.CharField(gettext_lazy("Статус"), max_length=32, choices=BehaviorStatus.choices, blank=True)
    comment = models.TextField(gettext_lazy("Комментарий куратора"), blank=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Профиль: дисциплина")
        verbose_name_plural = gettext_lazy("Профили: дисциплина")

    def __str__(self) -> str:
        return gettext("Дисциплина: {student}").format(student=self.student)


class AttendanceDay(models.Model):
    """Один учебный день одного ученика: был или не был (фаза 66).

    До фазы 66 посещаемость была одним числом в профиле, и его вносили
    руками. Число отвечает на вопрос «сколько», но не на вопрос «когда»,
    а разговор с родителем начинается со второго. Поэтому день — строка
    (инвариант №5), а процент в профиле пересчитывается из строк.

    Прямой ввод процента у директора школы остаётся: за время до системы
    дней в базе нет, и стирать историю ради стройности нельзя. Как только
    у ученика появляется хоть один день, процент считается по дням.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="attendance", on_delete=models.CASCADE
    )
    date = models.DateField(gettext_lazy("Дата"))
    present = models.BooleanField(gettext_lazy("Присутствовал"), default=True)
    #: причина отсутствия — по желанию: «болел», «на олимпиаде»
    reason = models.CharField(gettext_lazy("Причина"), max_length=200, blank=True)
    noted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто отметил"),
        related_name="attendance_marks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Отмечен"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Изменён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("День посещаемости")
        verbose_name_plural = gettext_lazy("Дни посещаемости")
        ordering = ("-date",)
        constraints = [models.UniqueConstraint(fields=("student", "date"), name="unique_attendance_day")]
        indexes = [models.Index(fields=("student", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.date} · {gettext('был') if self.present else gettext('не был')}"


class BehaviorRemark(Archivable):
    """Замечание ученику: текст, дата, кто записал (фаза 66).

    Счётчик замечаний в профиле остался, но считается теперь из этих
    строк: «три замечания» без слов через месяц не помнит никто, а именно
    словами разговаривают с родителем. Текст видят сотрудники; ученику
    замечание не показывается — как и прежде (инвариант №7).
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="remarks", on_delete=models.CASCADE
    )
    date = models.DateField(gettext_lazy("Дата"))
    text = models.CharField(gettext_lazy("Замечание"), max_length=500)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто записал"),
        related_name="behavior_remarks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    author_role = models.CharField(gettext_lazy("Роль автора"), max_length=32, blank=True)
    #: след автора, если его учётную запись удалили навсегда (фаза 67):
    #: имя, почта и дата удаления строкой. Пока запись жива, поле пустое
    #: и имя берётся у неё — второго источника правды не заводим
    author_title = models.CharField(gettext_lazy("Автор на момент удаления"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Записано"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Замечание")
        verbose_name_plural = gettext_lazy("Замечания")
        ordering = ("-date", "-created_at")
        indexes = [models.Index(fields=("student", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.date}: {self.text[:40]}"


# --- Домен admission (Асем) --------------------------------------------


class AdmissionStatus(models.TextChoices):
    """Внутренний ярлык готовности к подаче — ученику не показывается."""

    A = "A", gettext_lazy("A — готов к подаче")
    B = "B", gettext_lazy("B — требует подготовки")
    C = "C", gettext_lazy("C — критический")


class TargetLevel(models.TextChoices):
    """Уровень обучения, на который целится ученик (фаза 38)."""

    FOUNDATION = "foundation", gettext_lazy("Foundation / подготовительный")
    BACHELOR = "bachelor", gettext_lazy("Бакалавриат")
    MASTER = "master", gettext_lazy("Магистратура")


class AdmissionProfile(Archivable):
    """Поступление. Владелец — домен `admission`."""

    student = models.OneToOneField(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="admission", on_delete=models.CASCADE
    )
    target_country = models.CharField(gettext_lazy("Целевая страна"), max_length=100, blank=True)
    target_major = models.CharField(gettext_lazy("Специальность"), max_length=150, blank=True)
    target_level = models.CharField(
        gettext_lazy("Уровень цели"), max_length=16, choices=TargetLevel.choices, blank=True
    )
    # год поступления и комментарий удалены в фазе 68 по решению владельца:
    # все ученики одного выпуска, а комментарий не читал никто. Приоритет
    # стоимости — в фазе 70: его спрашивала анкета, считал счётчик
    # заполненности, и не читал никто — ни подбор, ни стипендии
    has_common_app = models.BooleanField(gettext_lazy("Common App заведён"), default=False)
    has_application_account = models.BooleanField(gettext_lazy("Кабинет подачи заведён"), default=False)
    status = models.CharField(gettext_lazy("Статус"), max_length=1, choices=AdmissionStatus.choices, blank=True)
    #: данные из таблицы Асем (фаза 65): телефон ученика — здесь, а не в
    #: `Student`, потому что его ведёт домен поступления; почта Common App
    #: и папка на Диске — ссылки, по которым Асем подаёт документы
    student_phone = models.CharField(gettext_lazy("Телефон ученика"), max_length=20, blank=True)
    common_app_email = models.EmailField(gettext_lazy("Почта Common App"), blank=True)
    drive_folder_url = models.URLField(gettext_lazy("Папка на Диске"), max_length=500, blank=True)
    #: личная почта из таблицы Асем (фаза 71) — текст в карточке, к входу
    #: в систему отношения не имеет и с логином не сверяется
    personal_email = models.CharField(gettext_lazy("Электронный адрес"), max_length=254, blank=True)
    #: срок паспорта — своё поле, а не свойство документа (фаза 71): ссылки
    #: на паспорт в таблице может не быть, а срок в ней есть
    passport_expires_at = models.DateField(gettext_lazy("Срок годности паспорта"), null=True, blank=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Профиль: поступление")
        verbose_name_plural = gettext_lazy("Профили: поступление")

    def __str__(self) -> str:
        return gettext("Поступление: {student}").format(student=self.student)


# --- Домен exam (Кымбат) -----------------------------------------------


class ExamProfile(Archivable):
    """Экзамены. Владелец — домен `exam`."""

    student = models.OneToOneField(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="exam", on_delete=models.CASCADE
    )
    ielts_current = models.DecimalField(
        gettext_lazy("IELTS текущий"), max_digits=3, decimal_places=1, null=True, blank=True
    )
    ielts_target = models.DecimalField(
        gettext_lazy("IELTS цель"), max_digits=3, decimal_places=1, null=True, blank=True
    )
    sat_current = models.PositiveSmallIntegerField(gettext_lazy("SAT текущий"), null=True, blank=True)
    sat_target = models.PositiveSmallIntegerField(gettext_lazy("SAT цель"), null=True, blank=True)
    hours_per_week = models.PositiveSmallIntegerField(gettext_lazy("Часов в неделю"), null=True, blank=True)
    teacher = models.CharField(gettext_lazy("Преподаватель"), max_length=150, blank=True)
    gpa = models.DecimalField("GPA", max_digits=4, decimal_places=2, null=True, blank=True)
    next_mock_date = models.DateField(gettext_lazy("Следующий Mock Test"), null=True, blank=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Профиль: экзамены")
        verbose_name_plural = gettext_lazy("Профили: экзамены")

    def __str__(self) -> str:
        return gettext("Экзамены: {student}").format(student=self.student)


class ExamType(models.TextChoices):
    IELTS = "IELTS", "IELTS"
    TOEFL = "TOEFL", "TOEFL"
    SAT = "SAT", "SAT"
    ACT = "ACT", "ACT"
    #: национальный экзамен убран насовсем в фазе 59: школа готовит за рубеж
    #: и в НУ; строки с его кодом остались в базе архивными, в перечне его нет
    #: центр подготовки держит банк шести экзаменов (фаза 42)
    DUOLINGO = "Duolingo", "Duolingo"
    HSK = "HSK", "HSK"


class AttemptFormat(models.TextChoices):
    MOCK = "mock", gettext_lazy("Mock Test")
    OFFICIAL = "official", gettext_lazy("Официальный")


class AttemptSource(models.TextChoices):
    """Откуда взялся результат.

    Мок, пройденный на платформе, надо отличать и от официальной сдачи,
    и от внесённого руками: доверие к ним разное.
    """

    MANUAL = "manual", gettext_lazy("Внесён руками")
    IMPORT = "import", gettext_lazy("Импорт")
    #: таблица поступления Асем (фаза 65): официальные сдачи без даты
    ADMISSION_IMPORT = "admission_import", gettext_lazy("Импорт Асем")
    PLATFORM = "platform", gettext_lazy("Пройден на платформе")
    #: прочитано со скриншота помощником и принято человеком — доверие
    #: к такому баллу ниже, чем к внесённому руками с бумаги
    AI = "ai", gettext_lazy("Распознано со скриншота")


#: Секции IELTS. Порядок тот же, что в бланке и в файле учителя.
IELTS_SECTIONS: tuple[str, ...] = ("listening", "reading", "writing", "speaking")

#: Шкалы баллов живут в реестре доменов (`core.domains.SCALES`, фаза 64):
#: одно место, откуда читают разбор файла, сериализатор и валидатор.


def mock_upload_to(instance: MockImport, filename: str) -> str:
    """Путь внутри закрытого хранилища — рядом с документами учеников."""
    return f"mocks/{instance.group_id}/{filename}"


def _mock_storage():
    """То же закрытое хранилище, что у документов: вне корня веб-сервера."""
    from materials.storage import private_storage

    return private_storage()


class MockImport(Archivable):
    """Одна загрузка пробника файлом (фаза 63).

    Пробник проводит учитель, а учётной записи у него нет: таблицу
    с результатами загружает куратор группы или академический директор.
    Строка нужна, чтобы у каждого балла было видно происхождение — какой
    файл, чей пробник, кто загрузил, — и чтобы всю загрузку можно было
    убрать одним движением: архив уносит с собой её попытки (каскад),
    у учеников баллы этого пробника пропадают, а возврат поднимает всё
    обратно тем же номером удаления.
    """

    exam_type = models.CharField(gettext_lazy("Экзамен"), max_length=8, choices=ExamType.choices)
    group = models.ForeignKey(
        StudyGroup, verbose_name=gettext_lazy("Группа"), related_name="mock_imports", on_delete=models.CASCADE
    )
    date = models.DateField(gettext_lazy("Дата Mock Test"))
    teacher = models.CharField(gettext_lazy("Кто проверял"), max_length=200, blank=True)
    file = models.FileField(gettext_lazy("Файл"), upload_to=mock_upload_to, storage=_mock_storage, max_length=300)
    file_name = models.CharField(gettext_lazy("Имя файла"), max_length=250, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто загрузил"),
        related_name="mock_imports",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: след загрузившего, если его запись удалили навсегда (фаза 67)
    uploaded_by_title = models.CharField(gettext_lazy("Кто загрузил, на момент удаления"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Когда загружен"), auto_now_add=True)
    rows_total = models.PositiveIntegerField(gettext_lazy("Строк в файле"), default=0)
    rows_applied = models.PositiveIntegerField(gettext_lazy("Записано результатов"), default=0)
    rows_skipped = models.PositiveIntegerField(gettext_lazy("Пропущено строк"), default=0)
    #: что пропустили и почему — по строке на пропуск, читается на странице
    #: результатов. Текстом, а не JSON: это отчёт для человека, и хранить
    #: его блоком было бы вторым источником правды о попытках (инвариант №6)
    skipped_report = models.TextField(gettext_lazy("Пропущенные строки"), blank=True)

    class Meta:
        verbose_name = gettext_lazy("Загрузка Mock Test")
        verbose_name_plural = gettext_lazy("Загрузки Mock Test")
        ordering = ("-date", "-created_at")
        constraints = [
            # один пробник одного экзамена на группу и дату: повторная загрузка
            # того же файла не должна удваивать баллы у половины класса
            models.UniqueConstraint(
                fields=("exam_type", "group", "date"),
                condition=models.Q(archived_at__isnull=True),
                name="unique_active_mock_import",
            )
        ]

    def __str__(self) -> str:
        return f"{self.exam_type} · {self.group.code} · {self.date}"

    @property
    def status(self) -> str:
        return "archived" if self.is_archived else "applied"

    @property
    def status_title(self) -> str:
        return gettext("В архиве") if self.is_archived else gettext("Применён")


class ExamAttempt(Archivable):
    """Одна попытка экзамена — мок или официальная сдача (инвариант №5).

    С фазы 63 у мок-попытки из файла есть ссылка на загрузку: по ней видно,
    чей это пробник и кто его залил, и по ней же загрузка уходит в архив
    целиком. Официальную попытку вносит ученик предложением, подтверждает
    владелец домена; текущий балл профиля считается только по официальным —
    пробник его не подменяет ни из файла, ни с платформы.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="exam_attempts", on_delete=models.CASCADE
    )
    exam_type = models.CharField(gettext_lazy("Экзамен"), max_length=8, choices=ExamType.choices)
    attempt_format = models.CharField(gettext_lazy("Формат"), max_length=8, choices=AttemptFormat.choices)
    source = models.CharField(
        gettext_lazy("Источник"), max_length=16, choices=AttemptSource.choices, default=AttemptSource.MANUAL
    )
    date = models.DateField(gettext_lazy("Дата"))
    #: дата не указана в источнике (таблица Асем): стоит день импорта,
    #: карточка показывает «дата уточняется», ученик предлагает настоящую
    date_unknown = models.BooleanField(gettext_lazy("Дата не указана"), default=False)
    total_score = models.DecimalField(gettext_lazy("Общий балл"), max_digits=6, decimal_places=1, null=True, blank=True)
    # секции IELTS / TOEFL
    listening = models.DecimalField("Listening", max_digits=4, decimal_places=1, null=True, blank=True)
    reading = models.DecimalField("Reading", max_digits=4, decimal_places=1, null=True, blank=True)
    writing = models.DecimalField("Writing", max_digits=4, decimal_places=1, null=True, blank=True)
    speaking = models.DecimalField("Speaking", max_digits=4, decimal_places=1, null=True, blank=True)
    # секции SAT / ACT
    math = models.PositiveSmallIntegerField("Math", null=True, blank=True)
    verbal = models.PositiveSmallIntegerField("Verbal", null=True, blank=True)
    #: загрузка, из которой пришёл результат (фаза 63); у официальных пусто
    mock_import = models.ForeignKey(
        MockImport,
        verbose_name=gettext_lazy("Загрузка Mock Test"),
        related_name="attempts",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Создана"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Попытка экзамена")
        verbose_name_plural = gettext_lazy("Попытки экзаменов")
        ordering = ("-date",)
        indexes = [models.Index(fields=("student", "exam_type", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.exam_type} {self.attempt_format} {self.date}"


# --- Домен talent (Арман) ----------------------------------------------


class TalentTrack(models.TextChoices):
    """Шесть треков усиления."""

    OLYMPIAD = "olympiad", gettext_lazy("Олимпиады")
    RESEARCH = "research", gettext_lazy("Исследования")
    STARTUP = "startup", gettext_lazy("Стартап")
    LEADERSHIP = "leadership", gettext_lazy("Лидерство")
    VOLUNTEERING = "volunteering", gettext_lazy("Волонтёрство")
    COMPETITION = "competition", gettext_lazy("Конкурсы")


class PortfolioStatus(models.TextChoices):
    """Внутренний ярлык портфолио — ученику не показывается."""

    STRONG = "strong", gettext_lazy("Сильное")
    MEDIUM = "medium", gettext_lazy("Среднее")
    WEAK = "weak", gettext_lazy("Слабое")


class TalentProfile(Archivable):
    """Таланты. Владелец — домен `talent`."""

    student = models.OneToOneField(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="talent", on_delete=models.CASCADE
    )
    main_track = models.CharField(gettext_lazy("Основной трек"), max_length=32, choices=TalentTrack.choices, blank=True)
    portfolio_status = models.CharField(
        gettext_lazy("Статус портфолио"), max_length=16, choices=PortfolioStatus.choices, blank=True
    )
    comment = models.TextField(gettext_lazy("Комментарий"), blank=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Профиль: таланты")
        verbose_name_plural = gettext_lazy("Профили: таланты")

    def __str__(self) -> str:
        return gettext("Таланты: {student}").format(student=self.student)


class ActivityCategory(models.TextChoices):
    OLYMPIAD = "olympiad", gettext_lazy("Олимпиада")
    PROJECT = "project", gettext_lazy("Проект")
    RESEARCH = "research", gettext_lazy("Исследование")
    STARTUP = "startup", gettext_lazy("Стартап")
    LEADERSHIP = "leadership", gettext_lazy("Лидерство")
    VOLUNTEERING = "volunteering", gettext_lazy("Волонтёрство")
    COMPETITION = "competition", gettext_lazy("Конкурс")
    AWARD = "award", gettext_lazy("Награда")


class Activity(Archivable):
    """Одна активность портфолио (инвариант №5)."""

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="activities", on_delete=models.CASCADE
    )
    category = models.CharField(gettext_lazy("Категория"), max_length=16, choices=ActivityCategory.choices)
    #: предмет из справочника — заполняется у олимпиад, у волонтёрства пусто.
    #: PROTECT: удалить предмет, на который ссылается активность, нельзя —
    #: сначала его заменяют или прячут из списка выбора
    subject = models.ForeignKey(
        "directories.OlympiadSubject",
        verbose_name=gettext_lazy("Предмет"),
        related_name="activities",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    title = models.CharField(gettext_lazy("Название"), max_length=250)
    date = models.DateField(gettext_lazy("Дата"), null=True, blank=True)
    description = models.TextField(gettext_lazy("Описание"), blank=True)
    proof_url = models.URLField(gettext_lazy("Подтверждение"), blank=True)
    is_confirmed = models.BooleanField(gettext_lazy("Подтверждено"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Создана"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Активность")
        verbose_name_plural = gettext_lazy("Активности")
        ordering = ("-date", "-id")
        indexes = [models.Index(fields=("student", "category")), models.Index(fields=("subject",))]

    def __str__(self) -> str:
        return f"{self.student} · {self.title}"


# --- Домен sport (Нурлыбек) --------------------------------------------


class SportLevel(models.TextChoices):
    SCHOOL = "school", gettext_lazy("Школьный")
    CITY = "city", gettext_lazy("Городской")
    REGIONAL = "regional", gettext_lazy("Областной")
    NATIONAL = "national", gettext_lazy("Республиканский")
    INTERNATIONAL = "international", gettext_lazy("Международный")


class SportProfile(Archivable):
    """Спорт. Владелец — домен `sport`."""

    student = models.OneToOneField(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="sport", on_delete=models.CASCADE
    )
    #: вид спорта из справочника вместо свободного текста: «Футбол»,
    #: «футбол» и «Футб.» иначе оказывались тремя разными видами
    sport_type = models.ForeignKey(
        "directories.SportType",
        verbose_name=gettext_lazy("Вид спорта"),
        related_name="profiles",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    level = models.CharField(gettext_lazy("Уровень"), max_length=16, choices=SportLevel.choices, blank=True)
    rank = models.CharField(gettext_lazy("Разряд"), max_length=50, blank=True)
    leadership_role = models.CharField(gettext_lazy("Лидерская роль"), max_length=100, blank=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Профиль: спорт")
        verbose_name_plural = gettext_lazy("Профили: спорт")

    def __str__(self) -> str:
        return gettext("Спорт: {student}").format(student=self.student)


class Competition(Archivable):
    """Одно соревнование (инвариант №5).

    Строка на ученика, а не на старт: у одного соревнования бывает
    несколько участников, и у каждого свой результат. Экран заводит
    сразу все строки одной формой — соревнование вносится один раз,
    а участники отмечаются списком.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="competitions", on_delete=models.CASCADE
    )
    name = models.CharField(gettext_lazy("Соревнование"), max_length=250)
    #: вид спорта из справочника — тот же, что и в профиле: иначе
    #: «Футбол» и «футбол» окажутся разными видами (фаза 18)
    sport_type = models.ForeignKey(
        "directories.SportType",
        verbose_name=gettext_lazy("Вид спорта"),
        related_name="competitions",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    level = models.CharField(gettext_lazy("Уровень"), max_length=16, choices=SportLevel.choices, blank=True)
    date = models.DateField(gettext_lazy("Дата"), null=True, blank=True)
    result = models.CharField(gettext_lazy("Результат"), max_length=150, blank=True)
    has_certificate = models.BooleanField(gettext_lazy("Сертификат есть"), default=False)
    proof_url = models.URLField(gettext_lazy("Ссылка на подтверждение"), blank=True)
    #: значимо для поступления: отмеченные видны в карточке ученика у всех
    #: ролей и в CV, остальные — только во вкладке «Портфолио» и у директора
    #: спорта. Школьный турнир и чемпионат страны — разный вес для заявки,
    #: а решает это человек, а не уровень соревнования
    show_in_card = models.BooleanField(gettext_lazy("Показывать в карточке ученика"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Создано"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Соревнование")
        verbose_name_plural = gettext_lazy("Соревнования")
        ordering = ("-date", "-id")
        indexes = [models.Index(fields=("student", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.name}"


# --- Домен behavior: контакты родителей ---------------------------------


class ContactRelation(models.TextChoices):
    """Кем контакт приходится ученику."""

    MOTHER = "mother", gettext_lazy("Мама")
    FATHER = "father", gettext_lazy("Папа")
    GUARDIAN = "guardian", gettext_lazy("Опекун")
    GRANDPARENT = "grandparent", gettext_lazy("Бабушка или дедушка")
    RELATIVE = "relative", gettext_lazy("Другой родственник")
    OTHER = "other", gettext_lazy("Другое")


class ContactChannel(models.TextChoices):
    """Как с человеком удобнее связаться."""

    PHONE = "phone", gettext_lazy("Звонок")
    WHATSAPP = "whatsapp", "WhatsApp"
    TELEGRAM = "telegram", "Telegram"
    EMAIL = "email", gettext_lazy("Почта")


class ParentContact(Archivable):
    """Родитель или опекун ученика. Владелец — домен `behavior`.

    Инвариант №5: контактов у ученика бывает несколько, поэтому они лежат
    строками, а не тремя колонками в профиле. Один помечается основным —
    его и набирают первым, когда надо дозвониться сегодня.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="contacts", on_delete=models.CASCADE
    )
    full_name = models.CharField(gettext_lazy("ФИО"), max_length=200)
    relation = models.CharField(gettext_lazy("Кем приходится"), max_length=16, choices=ContactRelation.choices)
    phone = models.CharField(gettext_lazy("Телефон"), max_length=32, blank=True)
    email = models.EmailField(gettext_lazy("Почта"), blank=True)
    preferred_channel = models.CharField(
        gettext_lazy("Предпочтительный способ связи"), max_length=16, choices=ContactChannel.choices, blank=True
    )
    note = models.TextField(gettext_lazy("Примечание"), blank=True)
    is_primary = models.BooleanField(gettext_lazy("Основной контакт"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Контакт родителя")
        verbose_name_plural = gettext_lazy("Контакты родителей")
        ordering = ("-is_primary", "full_name", "id")
        indexes = [models.Index(fields=("student", "-is_primary"))]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.get_relation_display()})"

    def save(self, *args, **kwargs):
        """Основной контакт у ученика один.

        Снимаем признак у остальных здесь, а не во вьюхе: контакт заводят
        и правят из API, из импорта и из админки, и в каждом месте помнить
        об этом никто не будет — второй «основной» появился бы молча.

        Телефон приводится к виду `+7XXXXXXXXXX` здесь же: по нему набирают
        и копируют в мессенджер, и два вида одного номера ни к чему.
        """
        from students.phones import normalize_kz

        self.phone = normalize_kz(self.phone)[:32]
        super().save(*args, **kwargs)
        if self.is_primary:
            ParentContact.all_objects.filter(student_id=self.student_id, is_primary=True).exclude(pk=self.pk).update(
                is_primary=False
            )


# --- Документы портфолио (фаза 38) --------------------------------------


class DocumentType(models.TextChoices):
    """Типы документов чек-листа готовности."""

    ATTESTAT = "attestat", gettext_lazy("Аттестат")
    TRANSCRIPT = "transcript", gettext_lazy("Транскрипт")
    EXAM_CERTIFICATE = "exam_certificate", gettext_lazy("Сертификат экзамена")
    RECOMMENDATION = "recommendation", gettext_lazy("Рекомендательное письмо")
    PASSPORT = "passport", gettext_lazy("Паспорт")
    OTHER = "other", gettext_lazy("Прочее")


def document_upload_to(instance: StudentDocument, filename: str) -> str:
    """Путь внутри закрытого хранилища; имя файла своё, не пользовательское."""
    return f"documents/{instance.student_id}/{filename}"


def _document_storage():
    """То же закрытое хранилище, что у материалов: вне корня веб-сервера."""
    from materials.storage import private_storage

    return private_storage()


class DocumentStatus(models.TextChoices):
    """Проверка документа (фаза 62): загружен → подтверждён или отклонён с причиной.

    «Истекает» — не статус, а вычисляемый признак подтверждённого документа
    со сроком действия ближе настройки школы «Документ истекает».
    """

    PENDING = "pending", gettext_lazy("Ждёт проверки")
    CONFIRMED = "confirmed", gettext_lazy("Подтверждён")
    REJECTED = "rejected", gettext_lazy("Отклонён")
    #: куратор загрузил документ того же типа, пока этот ждал проверки.
    #: Не «отклонён»: причины нет, просто внесли за ученика
    SUPERSEDED = "superseded", gettext_lazy("Заменён документом куратора")


#: Типы документов со сроком действия: паспорт и сертификаты экзаменов.
#: Транскрипту и рекомендации срок не нужен — поле у них не спрашивается.
EXPIRING_TYPES: tuple[str, ...] = (DocumentType.PASSPORT, DocumentType.EXAM_CERTIFICATE)


class StudentDocument(Archivable):
    """Документ ученика: аттестат, транскрипт, сертификат, письмо, паспорт.

    Файл лежит вне корня веб-сервера — как материалы олимпиадников —
    и отдаётся только после проверки прав: ученик видит свои, сотрудники —
    документы любого ученика. Загружает ученик сам: это его документы,
    а не табличные данные, которые с фазы 35 грузит администратор.

    С фазы 62 документ проверяется: загрузка даёт «ждёт проверки» и строку
    в очереди домена «Документы»; куратор группы или владелец домена
    подтверждает либо отклоняет с причиной. Отклонённый не удаляется —
    ученик загружает заново, и прежний файл остаётся историей.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="documents", on_delete=models.CASCADE
    )
    doc_type = models.CharField(gettext_lazy("Тип документа"), max_length=24, choices=DocumentType.choices)
    title = models.CharField(gettext_lazy("Название"), max_length=200, blank=True)
    file = models.FileField(
        gettext_lazy("Файл"), upload_to=document_upload_to, storage=_document_storage, max_length=300, blank=True
    )
    #: документ-ссылка (фаза 65): вместо файла — адрес на Диске из таблицы
    #: Асем. Проверяется той же очередью, в матрице своя иконка, предпросмотр
    #: открывает ссылку в новой вкладке. У документа либо файл, либо ссылка
    external_url = models.URLField(gettext_lazy("Внешняя ссылка"), max_length=500, blank=True)
    content_type = models.CharField(gettext_lazy("Тип содержимого"), max_length=64, blank=True)
    size = models.PositiveIntegerField(gettext_lazy("Размер, байт"), default=0)
    issued_date = models.DateField(gettext_lazy("Дата выдачи"), null=True, blank=True)
    expires_at = models.DateField(gettext_lazy("Действует до"), null=True, blank=True)
    note = models.CharField(gettext_lazy("Примечание"), max_length=250, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто загрузил"),
        related_name="uploaded_documents",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(
        gettext_lazy("Проверка"), max_length=16, choices=DocumentStatus.choices, default=DocumentStatus.PENDING
    )
    #: причина отклонения — её читает ученик; имя проверившего ему не отдаётся
    reject_reason = models.CharField(gettext_lazy("Причина отклонения"), max_length=250, blank=True)
    reviewed_at = models.DateTimeField(gettext_lazy("Проверен"), null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто проверил"),
        related_name="reviewed_documents",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Загружен"), auto_now_add=True)

    def expiring_within(self, days: int | None = None) -> bool:
        """Подтверждён, а срок действия ближе `days` дней.

        `days` — настройка школы «Документ истекает»; список документов читает
        её один раз и передаёт сюда, одиночный документ читает сам.
        """
        from django.utils import timezone

        if self.status != DocumentStatus.CONFIRMED or self.expires_at is None:
            return False
        if days is None:
            from core import school_rules

            days = school_rules.value(school_rules.DOCUMENT_EXPIRING_DAYS)
        today = timezone.localdate()
        return today <= self.expires_at <= today + timedelta(days=days)

    @property
    def is_expiring(self) -> bool:
        """Подтверждён, а срок действия уже близко (порог — настройка школы)."""
        return self.expiring_within()

    def state_within(self, days: int | None = None) -> str:
        """Состояние для матрицы: `expiring` поверх `confirmed`, остальное — статус."""
        return "expiring" if self.expiring_within(days) else str(self.status)

    @property
    def state(self) -> str:
        return self.state_within()

    @property
    def is_link(self) -> bool:
        """Документ задан ссылкой, а не файлом."""
        return bool(self.external_url) and not self.file

    class Meta:
        verbose_name = gettext_lazy("Документ ученика")
        verbose_name_plural = gettext_lazy("Документы учеников")
        ordering = ("doc_type", "-created_at")
        indexes = [models.Index(fields=("student", "doc_type"))]

    def __str__(self) -> str:
        return f"{self.get_doc_type_display()}: {self.student}"


# --- Цели по экзаменам (фаза 39) ------------------------------------------


class ExamGoal(Archivable):
    """Цель по экзамену: целевой балл, дата экзамена и дата регистрации.

    Ставит ученик (предложением, фаза 37), подтверждает академический
    директор. От дат растут календарь, напоминания и автозадачи
    о регистрации; задача ссылается на цель, а не копирует дату
    (инвариант №4): сдвинулась дата — сдвинулся срок.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="exam_goals", on_delete=models.CASCADE
    )
    exam = models.ForeignKey(
        "directories.ExamKind",
        verbose_name=gettext_lazy("Экзамен"),
        related_name="goals",
        on_delete=models.PROTECT,
    )
    target_score = models.DecimalField(
        gettext_lazy("Целевой балл"), max_digits=6, decimal_places=1, null=True, blank=True
    )
    exam_date = models.DateField(gettext_lazy("Дата экзамена"), null=True, blank=True)
    registration_date = models.DateField(gettext_lazy("Дата регистрации"), null=True, blank=True)
    note = models.CharField(gettext_lazy("Примечание"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Создана"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлена"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Цель по экзамену")
        verbose_name_plural = gettext_lazy("Цели по экзаменам")
        ordering = ("exam_date", "exam__sort_order", "id")
        constraints = [
            # одна живая цель на экзамен; архивная не закрывает дорогу новой
            models.UniqueConstraint(
                fields=("student", "exam"),
                condition=models.Q(archived_at__isnull=True),
                name="unique_active_exam_goal",
            )
        ]
        indexes = [models.Index(fields=("exam_date",))]

    def __str__(self) -> str:
        return f"{self.student} · {self.exam} → {self.target_score or '—'}"


class CuratorNote(Archivable):
    """Внутренняя заметка о ученике (фаза 62).

    Пишет куратор группы; читают куратор, академический директор и директор
    школы — список читателей задан в одном месте (`students.notes.NOTE_READERS`),
    чтобы добавить роль одной правкой. Ученику заметка не отдаётся никогда:
    это инвариант, а не настройка. Удаление мягкое — в архив, как у всего,
    что имеет историю (инвариант №13).
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="curator_notes", on_delete=models.CASCADE
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Автор"),
        related_name="curator_notes",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: роль автора снимком: человек сменит роль, а подпись под заметкой — нет
    author_role = models.CharField(gettext_lazy("Роль автора"), max_length=32, blank=True)
    #: след автора, если его учётную запись удалили навсегда (фаза 67)
    author_title = models.CharField(gettext_lazy("Автор на момент удаления"), max_length=250, blank=True)
    text = models.TextField(gettext_lazy("Текст"))
    created_at = models.DateTimeField(gettext_lazy("Создана"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Заметка куратора")
        verbose_name_plural = gettext_lazy("Заметки куратора")
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.student}: {self.text[:40]}"


# --- Пароли учеников и таблица поступления (фаза 65) ------------------------


class CredentialKind(models.TextChoices):
    """Чей пароль хранится: почты или кабинета Common App."""

    EMAIL = "email", gettext_lazy("Пароль от почты")
    COMMON_APP = "common_app", gettext_lazy("Пароль Common App")


class StudentCredential(models.Model):
    """Пароль ученика от почты или Common App — только шифртекстом (фаза 65).

    Это единственные данные в системе, которые открывают чужие аккаунты.
    В колонке лежит шифртекст Fernet под ключом `CREDENTIALS_KEY` из
    окружения; открытый текст выдаёт один маршрут «показать», и каждый
    показ пишется в журнал (кто, чей, когда). В списках, выгрузках, поиске
    и любых других ответах API пароля нет ни открытым текстом, ни
    шифртекстом — это стережёт тест-сторож.

    Пароль — не история, а текущее значение: перезаписывается на месте,
    физически удаляется вместе с учеником.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="credentials", on_delete=models.CASCADE
    )
    kind = models.CharField(gettext_lazy("Что за пароль"), max_length=16, choices=CredentialKind.choices)
    #: только шифртекст; открытый текст в базе не появляется никогда
    ciphertext = models.TextField(gettext_lazy("Шифртекст"))
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто записал"),
        related_name="saved_credentials",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Пароль ученика")
        verbose_name_plural = gettext_lazy("Пароли учеников")
        constraints = [models.UniqueConstraint(fields=("student", "kind"), name="unique_student_credential")]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.student}"


class AdmissionImport(models.Model):
    """Загрузка таблицы поступления Асем (фаза 65) — отчёт, что вышло.

    Таблица грузится один раз, но повторная загрузка обновляет, а не
    дублирует: строка нужна как след — кто, когда, какой файл, сколько
    учеников обновлено и что пропущено. Отчёт хранится текстом по строке
    на событие (лист, строка, ученик, что случилось) и выгружается XLSX.
    """

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто загрузил"),
        related_name="admission_imports",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: след загрузившего, если его запись удалили навсегда (`core.purge`)
    uploaded_by_title = models.CharField(gettext_lazy("Кто загрузил, на момент удаления"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True)
    file_name = models.CharField(gettext_lazy("Имя файла"), max_length=250, blank=True)
    #: какие домены заполнялись (фаза 71): коды через запятую — след того,
    #: что человек выбрал, а не того, что было в файле
    domains = models.CharField(gettext_lazy("Домены"), max_length=120, blank=True)
    sheets = models.PositiveSmallIntegerField(gettext_lazy("Листов"), default=0)
    students_updated = models.PositiveIntegerField(gettext_lazy("Учеников обновлено"), default=0)
    attempts_created = models.PositiveIntegerField(gettext_lazy("Попыток создано"), default=0)
    documents_created = models.PositiveIntegerField(gettext_lazy("Документов-ссылок"), default=0)
    credentials_saved = models.PositiveIntegerField(gettext_lazy("Паролей записано"), default=0)
    rows_skipped = models.PositiveIntegerField(gettext_lazy("Строк пропущено"), default=0)
    #: по строке на событие: «лист\tстрока\tученик\tвид\tтекст»; текстом, не
    #: JSON — это отчёт для человека (инвариант №6)
    report = models.TextField(gettext_lazy("Отчёт"), blank=True)

    class Meta:
        verbose_name = gettext_lazy("Загрузка таблицы поступления")
        verbose_name_plural = gettext_lazy("Загрузки таблицы поступления")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return gettext("Таблица поступления {moment}").format(moment=f"{self.created_at:%d.%m.%Y %H:%M}")


class YearTransfer(models.Model):
    """Перевод школы на следующий учебный год — одна запись на учебный год.

    8→9, 9→10, 10→11 — группа остаётся той же, меняется параллель;
    11 — выпуск: группа и ученики уходят в архив, вход закрывается.
    Учебный год считается по дате Алматы, сентябрь–август
    (`students.year_transfer.school_year`). Уникальность года и есть
    запрет повторного запуска: второй перевод в том же году отбивает база.
    """

    school_year = models.CharField(gettext_lazy("Учебный год"), max_length=9, unique=True)
    done_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто перевёл"),
        related_name="year_transfers",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: текстовый след автора: учётную запись могут удалить (инвариант №13)
    actor_title = models.CharField(gettext_lazy("Кто перевёл, текстом"), max_length=200, blank=True)
    groups_moved = models.PositiveSmallIntegerField(gettext_lazy("Групп переведено"), default=0)
    students_moved = models.PositiveIntegerField(gettext_lazy("Учеников переведено"), default=0)
    groups_graduated = models.PositiveSmallIntegerField(gettext_lazy("Групп выпущено"), default=0)
    students_graduated = models.PositiveIntegerField(gettext_lazy("Учеников выпущено"), default=0)

    class Meta:
        verbose_name = gettext_lazy("Перевод на следующий год")
        verbose_name_plural = gettext_lazy("Переводы на следующий год")
        ordering = ("-done_at",)

    def __str__(self) -> str:
        return gettext("Перевод {school_year}").format(school_year=self.school_year)
