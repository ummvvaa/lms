"""Ученики, учебные группы, пять профильных таблиц и история достижений.

Инвариант №5: всё, что имеет историю (моки, активности, соревнования),
живёт строками в дочерних таблицах, а не полями профиля.
Инвариант №6: никакого JSONB — только типизированные колонки.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models

from core.archivable import Archivable


class GroupLanguage(models.TextChoices):
    """Язык группы (фаза 66): на нём составляются письма родителям и ученикам."""

    RU = "ru", "Русский"
    KK = "kk", "Казахский"


class StudyGroup(Archivable):
    """Учебная группа — единица контроля, 15–20 учеников.

    Куратора у группы держит назначение с датой (`accounts.CuratorAssignment`),
    а не поле с именем: по имени нельзя ни войти, ни проверить право.
    Текстовое поле было до фазы 61 и удалено вместе с переходом на роль.
    """

    code = models.CharField("Код", max_length=16, unique=True)
    grade = models.PositiveSmallIntegerField("Класс")
    #: язык, на котором школа пишет этой группе (фаза 66). Нужен письмам:
    #: шаблон подставляется на языке группы, а не на языке того, кто пишет
    language = models.CharField("Язык группы", max_length=2, choices=GroupLanguage.choices, default=GroupLanguage.RU)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Учебная группа"
        verbose_name_plural = "Учебные группы"
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} ({self.grade} класс)"


class Student(Archivable):
    """Ученик. Реестровая запись школы, к пяти доменам не относится."""

    last_name = models.CharField("Фамилия", max_length=100)
    first_name = models.CharField("Имя", max_length=100)
    middle_name = models.CharField("Отчество", max_length=100, blank=True)
    email = models.EmailField("Email", unique=True)
    grade = models.PositiveSmallIntegerField("Класс")
    group = models.ForeignKey(
        StudyGroup, verbose_name="Группа", related_name="students", on_delete=models.PROTECT, null=True, blank=True
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Учётная запись",
        related_name="student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    graduation_year = models.PositiveSmallIntegerField("Год выпуска")
    is_active = models.BooleanField("Учится", default=True)
    #: отбор в олимпиадную группу. Признак ставит только директор талантов;
    #: ученик вне группы не видит раздел материалов вовсе — ни в меню,
    #: ни по прямой ссылке, ни в API (фаза 19)
    in_olympiad_group = models.BooleanField("В олимпиадной группе", default=False)
    #: вымышленный ученик — посев прогона или пилотная карточка (фаза 64).
    #: Ставится явно: посевом или командой `mark_fictional`, а не угадывается
    #: по почте. По нему `preflight` ищет, что осталось, а `purge_fictional`
    #: вычищает перед живыми учениками
    is_fictional = models.BooleanField("Вымышленный", default=False)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Ученик"
        verbose_name_plural = "Ученики"
        # id в конце — тезки в школе есть, а без уникального ключа порядок
        # между страницами не гарантирован и строки перескакивают
        ordering = ("last_name", "first_name", "id")
        indexes = [
            models.Index(fields=("grade",)),
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

    CAN_EXECUTE = "can_execute", "Работает самостоятельно"
    NEEDS_SUPERVISION = "needs_supervision", "Нужен контроль"
    CRITICAL = "critical", "Ежедневный контроль"


class BehaviorProfile(Archivable):
    """Профиль и дисциплина. Владелец — домен `behavior`."""

    student = models.OneToOneField(Student, verbose_name="Ученик", related_name="behavior", on_delete=models.CASCADE)
    attendance_percent = models.PositiveSmallIntegerField("Посещаемость, %", null=True, blank=True)
    remarks_count = models.PositiveSmallIntegerField("Замечания", default=0)
    homework_percent = models.PositiveSmallIntegerField("Выполнение заданий, %", null=True, blank=True)
    status = models.CharField("Статус", max_length=32, choices=BehaviorStatus.choices, blank=True)
    comment = models.TextField("Комментарий куратора", blank=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Профиль: дисциплина"
        verbose_name_plural = "Профили: дисциплина"

    def __str__(self) -> str:
        return f"Дисциплина: {self.student}"


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

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="attendance", on_delete=models.CASCADE)
    date = models.DateField("Дата")
    present = models.BooleanField("Присутствовал", default=True)
    #: причина отсутствия — по желанию: «болел», «на олимпиаде»
    reason = models.CharField("Причина", max_length=200, blank=True)
    noted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто отметил",
        related_name="attendance_marks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Отмечен", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    class Meta:
        verbose_name = "День посещаемости"
        verbose_name_plural = "Дни посещаемости"
        ordering = ("-date",)
        constraints = [models.UniqueConstraint(fields=("student", "date"), name="unique_attendance_day")]
        indexes = [models.Index(fields=("student", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.date} · {'был' if self.present else 'не был'}"


class BehaviorRemark(Archivable):
    """Замечание ученику: текст, дата, кто записал (фаза 66).

    Счётчик замечаний в профиле остался, но считается теперь из этих
    строк: «три замечания» без слов через месяц не помнит никто, а именно
    словами разговаривают с родителем. Текст видят сотрудники; ученику
    замечание не показывается — как и прежде (инвариант №7).
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="remarks", on_delete=models.CASCADE)
    date = models.DateField("Дата")
    text = models.CharField("Замечание", max_length=500)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто записал",
        related_name="behavior_remarks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    author_role = models.CharField("Роль автора", max_length=32, blank=True)
    #: след автора, если его учётную запись удалили навсегда (фаза 67):
    #: имя, почта и дата удаления строкой. Пока запись жива, поле пустое
    #: и имя берётся у неё — второго источника правды не заводим
    author_title = models.CharField("Автор на момент удаления", max_length=250, blank=True)
    created_at = models.DateTimeField("Записано", auto_now_add=True)

    class Meta:
        verbose_name = "Замечание"
        verbose_name_plural = "Замечания"
        ordering = ("-date", "-created_at")
        indexes = [models.Index(fields=("student", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.date}: {self.text[:40]}"


# --- Домен admission (Асем) --------------------------------------------


class AdmissionStatus(models.TextChoices):
    """Внутренний ярлык готовности к подаче — ученику не показывается."""

    A = "A", "A — готов к подаче"
    B = "B", "B — требует подготовки"
    C = "C", "C — критический"


class CostPriority(models.TextChoices):
    """Насколько семье важна стоимость обучения — «бюджет» профиля поступления."""

    SCHOLARSHIP = "scholarship", "Нужна стипендия или грант"
    MODERATE = "moderate", "Готовы платить умеренно"
    ANY = "any", "Стоимость не главное"
    UNKNOWN = "unknown", "Ещё не обсуждали"


class TargetLevel(models.TextChoices):
    """Уровень обучения, на который целится ученик (фаза 38)."""

    FOUNDATION = "foundation", "Foundation / подготовительный"
    BACHELOR = "bachelor", "Бакалавриат"
    MASTER = "master", "Магистратура"


class AdmissionProfile(Archivable):
    """Поступление. Владелец — домен `admission`."""

    student = models.OneToOneField(Student, verbose_name="Ученик", related_name="admission", on_delete=models.CASCADE)
    target_country = models.CharField("Целевая страна", max_length=100, blank=True)
    target_major = models.CharField("Специальность", max_length=150, blank=True)
    cost_priority = models.CharField("Приоритет стоимости", max_length=16, choices=CostPriority.choices, blank=True)
    target_level = models.CharField("Уровень цели", max_length=16, choices=TargetLevel.choices, blank=True)
    target_year = models.PositiveSmallIntegerField("Год поступления", null=True, blank=True)
    has_common_app = models.BooleanField("Common App заведён", default=False)
    has_application_account = models.BooleanField("Кабинет подачи заведён", default=False)
    status = models.CharField("Статус", max_length=1, choices=AdmissionStatus.choices, blank=True)
    comment = models.TextField("Комментарий", blank=True)
    #: данные из таблицы Асем (фаза 65): телефон ученика — здесь, а не в
    #: `Student`, потому что его ведёт домен поступления; почта Common App
    #: и папка на Диске — ссылки, по которым Асем подаёт документы
    student_phone = models.CharField("Телефон ученика", max_length=20, blank=True)
    common_app_email = models.EmailField("Почта Common App", blank=True)
    drive_folder_url = models.URLField("Папка на Диске", max_length=500, blank=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Профиль: поступление"
        verbose_name_plural = "Профили: поступление"

    def __str__(self) -> str:
        return f"Поступление: {self.student}"


# --- Домен exam (Кымбат) -----------------------------------------------


class ExamProfile(Archivable):
    """Экзамены. Владелец — домен `exam`."""

    student = models.OneToOneField(Student, verbose_name="Ученик", related_name="exam", on_delete=models.CASCADE)
    ielts_current = models.DecimalField("IELTS текущий", max_digits=3, decimal_places=1, null=True, blank=True)
    ielts_target = models.DecimalField("IELTS цель", max_digits=3, decimal_places=1, null=True, blank=True)
    sat_current = models.PositiveSmallIntegerField("SAT текущий", null=True, blank=True)
    sat_target = models.PositiveSmallIntegerField("SAT цель", null=True, blank=True)
    hours_per_week = models.PositiveSmallIntegerField("Часов в неделю", null=True, blank=True)
    teacher = models.CharField("Преподаватель", max_length=150, blank=True)
    gpa = models.DecimalField("GPA", max_digits=4, decimal_places=2, null=True, blank=True)
    next_mock_date = models.DateField("Следующий мок", null=True, blank=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Профиль: экзамены"
        verbose_name_plural = "Профили: экзамены"

    def __str__(self) -> str:
        return f"Экзамены: {self.student}"


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
    MOCK = "mock", "Мок"
    OFFICIAL = "official", "Официальный"


class AttemptSource(models.TextChoices):
    """Откуда взялся результат.

    Мок, пройденный на платформе, надо отличать и от официальной сдачи,
    и от внесённого руками: доверие к ним разное.
    """

    MANUAL = "manual", "Внесён руками"
    IMPORT = "import", "Импорт"
    #: таблица поступления Асем (фаза 65): официальные сдачи без даты
    ADMISSION_IMPORT = "admission_import", "Импорт Асем"
    PLATFORM = "platform", "Пройден на платформе"
    #: прочитано со скриншота помощником и принято человеком — доверие
    #: к такому баллу ниже, чем к внесённому руками с бумаги
    AI = "ai", "Распознано со скриншота"


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

    exam_type = models.CharField("Экзамен", max_length=8, choices=ExamType.choices)
    group = models.ForeignKey(StudyGroup, verbose_name="Группа", related_name="mock_imports", on_delete=models.CASCADE)
    date = models.DateField("Дата пробника")
    teacher = models.CharField("Кто проверял", max_length=200, blank=True)
    file = models.FileField("Файл", upload_to=mock_upload_to, storage=_mock_storage, max_length=300)
    file_name = models.CharField("Имя файла", max_length=250, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто загрузил",
        related_name="mock_imports",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: след загрузившего, если его запись удалили навсегда (фаза 67)
    uploaded_by_title = models.CharField("Кто загрузил, на момент удаления", max_length=250, blank=True)
    created_at = models.DateTimeField("Когда загружен", auto_now_add=True)
    rows_total = models.PositiveIntegerField("Строк в файле", default=0)
    rows_applied = models.PositiveIntegerField("Записано результатов", default=0)
    rows_skipped = models.PositiveIntegerField("Пропущено строк", default=0)
    #: что пропустили и почему — по строке на пропуск, читается на странице
    #: результатов. Текстом, а не JSON: это отчёт для человека, и хранить
    #: его блоком было бы вторым источником правды о попытках (инвариант №6)
    skipped_report = models.TextField("Пропущенные строки", blank=True)

    class Meta:
        verbose_name = "Загрузка пробника"
        verbose_name_plural = "Загрузки пробников"
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
        return "В архиве" if self.is_archived else "Применён"


class ExamAttempt(Archivable):
    """Одна попытка экзамена — мок или официальная сдача (инвариант №5).

    С фазы 63 у мок-попытки из файла есть ссылка на загрузку: по ней видно,
    чей это пробник и кто его залил, и по ней же загрузка уходит в архив
    целиком. Официальную попытку вносит ученик предложением, подтверждает
    владелец домена; текущий балл профиля считается только по официальным —
    пробник его не подменяет ни из файла, ни с платформы.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="exam_attempts", on_delete=models.CASCADE)
    exam_type = models.CharField("Экзамен", max_length=8, choices=ExamType.choices)
    attempt_format = models.CharField("Формат", max_length=8, choices=AttemptFormat.choices)
    source = models.CharField("Источник", max_length=16, choices=AttemptSource.choices, default=AttemptSource.MANUAL)
    date = models.DateField("Дата")
    #: дата не указана в источнике (таблица Асем): стоит день импорта,
    #: карточка показывает «дата уточняется», ученик предлагает настоящую
    date_unknown = models.BooleanField("Дата не указана", default=False)
    total_score = models.DecimalField("Общий балл", max_digits=6, decimal_places=1, null=True, blank=True)
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
        verbose_name="Загрузка пробника",
        related_name="attempts",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Попытка экзамена"
        verbose_name_plural = "Попытки экзаменов"
        ordering = ("-date",)
        indexes = [models.Index(fields=("student", "exam_type", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.exam_type} {self.attempt_format} {self.date}"


# --- Домен talent (Арман) ----------------------------------------------


class TalentTrack(models.TextChoices):
    """Шесть треков усиления."""

    OLYMPIAD = "olympiad", "Олимпиады"
    RESEARCH = "research", "Исследования"
    STARTUP = "startup", "Стартап"
    LEADERSHIP = "leadership", "Лидерство"
    VOLUNTEERING = "volunteering", "Волонтёрство"
    COMPETITION = "competition", "Конкурсы"


class PortfolioStatus(models.TextChoices):
    """Внутренний ярлык портфолио — ученику не показывается."""

    STRONG = "strong", "Сильное"
    MEDIUM = "medium", "Среднее"
    WEAK = "weak", "Слабое"


class TalentProfile(Archivable):
    """Таланты. Владелец — домен `talent`."""

    student = models.OneToOneField(Student, verbose_name="Ученик", related_name="talent", on_delete=models.CASCADE)
    main_track = models.CharField("Основной трек", max_length=32, choices=TalentTrack.choices, blank=True)
    portfolio_status = models.CharField("Статус портфолио", max_length=16, choices=PortfolioStatus.choices, blank=True)
    comment = models.TextField("Комментарий", blank=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Профиль: таланты"
        verbose_name_plural = "Профили: таланты"

    def __str__(self) -> str:
        return f"Таланты: {self.student}"


class ActivityCategory(models.TextChoices):
    OLYMPIAD = "olympiad", "Олимпиада"
    PROJECT = "project", "Проект"
    RESEARCH = "research", "Исследование"
    STARTUP = "startup", "Стартап"
    LEADERSHIP = "leadership", "Лидерство"
    VOLUNTEERING = "volunteering", "Волонтёрство"
    COMPETITION = "competition", "Конкурс"
    AWARD = "award", "Награда"


class Activity(Archivable):
    """Одна активность портфолио (инвариант №5)."""

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="activities", on_delete=models.CASCADE)
    category = models.CharField("Категория", max_length=16, choices=ActivityCategory.choices)
    #: предмет из справочника — заполняется у олимпиад, у волонтёрства пусто.
    #: PROTECT: удалить предмет, на который ссылается активность, нельзя —
    #: сначала его заменяют или прячут из списка выбора
    subject = models.ForeignKey(
        "directories.OlympiadSubject",
        verbose_name="Предмет",
        related_name="activities",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    title = models.CharField("Название", max_length=250)
    date = models.DateField("Дата", null=True, blank=True)
    description = models.TextField("Описание", blank=True)
    proof_url = models.URLField("Подтверждение", blank=True)
    is_confirmed = models.BooleanField("Подтверждено", default=False)
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Активность"
        verbose_name_plural = "Активности"
        ordering = ("-date", "-id")
        indexes = [models.Index(fields=("student", "category")), models.Index(fields=("subject",))]

    def __str__(self) -> str:
        return f"{self.student} · {self.title}"


# --- Домен sport (Нурлыбек) --------------------------------------------


class SportLevel(models.TextChoices):
    SCHOOL = "school", "Школьный"
    CITY = "city", "Городской"
    REGIONAL = "regional", "Областной"
    NATIONAL = "national", "Республиканский"
    INTERNATIONAL = "international", "Международный"


class SportProfile(Archivable):
    """Спорт. Владелец — домен `sport`."""

    student = models.OneToOneField(Student, verbose_name="Ученик", related_name="sport", on_delete=models.CASCADE)
    #: вид спорта из справочника вместо свободного текста: «Футбол»,
    #: «футбол» и «Футб.» иначе оказывались тремя разными видами
    sport_type = models.ForeignKey(
        "directories.SportType",
        verbose_name="Вид спорта",
        related_name="profiles",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    level = models.CharField("Уровень", max_length=16, choices=SportLevel.choices, blank=True)
    rank = models.CharField("Разряд", max_length=50, blank=True)
    leadership_role = models.CharField("Лидерская роль", max_length=100, blank=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Профиль: спорт"
        verbose_name_plural = "Профили: спорт"

    def __str__(self) -> str:
        return f"Спорт: {self.student}"


class Competition(Archivable):
    """Одно соревнование (инвариант №5).

    Строка на ученика, а не на старт: у одного соревнования бывает
    несколько участников, и у каждого свой результат. Экран заводит
    сразу все строки одной формой — соревнование вносится один раз,
    а участники отмечаются списком.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="competitions", on_delete=models.CASCADE)
    name = models.CharField("Соревнование", max_length=250)
    #: вид спорта из справочника — тот же, что и в профиле: иначе
    #: «Футбол» и «футбол» окажутся разными видами (фаза 18)
    sport_type = models.ForeignKey(
        "directories.SportType",
        verbose_name="Вид спорта",
        related_name="competitions",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    level = models.CharField("Уровень", max_length=16, choices=SportLevel.choices, blank=True)
    date = models.DateField("Дата", null=True, blank=True)
    result = models.CharField("Результат", max_length=150, blank=True)
    has_certificate = models.BooleanField("Сертификат есть", default=False)
    proof_url = models.URLField("Ссылка на подтверждение", blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Соревнование"
        verbose_name_plural = "Соревнования"
        ordering = ("-date", "-id")
        indexes = [models.Index(fields=("student", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.name}"


# --- Домен behavior: контакты родителей ---------------------------------


class ContactRelation(models.TextChoices):
    """Кем контакт приходится ученику."""

    MOTHER = "mother", "Мама"
    FATHER = "father", "Папа"
    GUARDIAN = "guardian", "Опекун"
    GRANDPARENT = "grandparent", "Бабушка или дедушка"
    RELATIVE = "relative", "Другой родственник"
    OTHER = "other", "Другое"


class ContactChannel(models.TextChoices):
    """Как с человеком удобнее связаться."""

    PHONE = "phone", "Звонок"
    WHATSAPP = "whatsapp", "WhatsApp"
    TELEGRAM = "telegram", "Telegram"
    EMAIL = "email", "Почта"


class ParentContact(Archivable):
    """Родитель или опекун ученика. Владелец — домен `behavior`.

    Инвариант №5: контактов у ученика бывает несколько, поэтому они лежат
    строками, а не тремя колонками в профиле. Один помечается основным —
    его и набирают первым, когда надо дозвониться сегодня.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="contacts", on_delete=models.CASCADE)
    full_name = models.CharField("ФИО", max_length=200)
    relation = models.CharField("Кем приходится", max_length=16, choices=ContactRelation.choices)
    phone = models.CharField("Телефон", max_length=32, blank=True)
    email = models.EmailField("Почта", blank=True)
    preferred_channel = models.CharField(
        "Предпочтительный способ связи", max_length=16, choices=ContactChannel.choices, blank=True
    )
    note = models.TextField("Примечание", blank=True)
    is_primary = models.BooleanField("Основной контакт", default=False)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Контакт родителя"
        verbose_name_plural = "Контакты родителей"
        ordering = ("-is_primary", "full_name", "id")
        indexes = [models.Index(fields=("student", "-is_primary"))]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.get_relation_display()})"

    def save(self, *args, **kwargs):
        """Основной контакт у ученика один.

        Снимаем признак у остальных здесь, а не во вьюхе: контакт заводят
        и правят из API, из импорта и из админки, и в каждом месте помнить
        об этом никто не будет — второй «основной» появился бы молча.
        """
        super().save(*args, **kwargs)
        if self.is_primary:
            ParentContact.all_objects.filter(student_id=self.student_id, is_primary=True).exclude(pk=self.pk).update(
                is_primary=False
            )


# --- Документы портфолио (фаза 38) --------------------------------------


class DocumentType(models.TextChoices):
    """Типы документов чек-листа готовности."""

    ATTESTAT = "attestat", "Аттестат"
    TRANSCRIPT = "transcript", "Транскрипт"
    EXAM_CERTIFICATE = "exam_certificate", "Сертификат экзамена"
    RECOMMENDATION = "recommendation", "Рекомендательное письмо"
    PASSPORT = "passport", "Паспорт"
    OTHER = "other", "Прочее"


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
    со сроком действия ближе `CURATOR_RULES["DOCUMENT_EXPIRING_DAYS"]`.
    """

    PENDING = "pending", "Ждёт проверки"
    CONFIRMED = "confirmed", "Подтверждён"
    REJECTED = "rejected", "Отклонён"


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

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="documents", on_delete=models.CASCADE)
    doc_type = models.CharField("Тип документа", max_length=24, choices=DocumentType.choices)
    title = models.CharField("Название", max_length=200, blank=True)
    file = models.FileField("Файл", upload_to=document_upload_to, storage=_document_storage, max_length=300, blank=True)
    #: документ-ссылка (фаза 65): вместо файла — адрес на Диске из таблицы
    #: Асем. Проверяется той же очередью, в матрице своя иконка, предпросмотр
    #: открывает ссылку в новой вкладке. У документа либо файл, либо ссылка
    external_url = models.URLField("Внешняя ссылка", max_length=500, blank=True)
    content_type = models.CharField("Тип содержимого", max_length=64, blank=True)
    size = models.PositiveIntegerField("Размер, байт", default=0)
    issued_date = models.DateField("Дата выдачи", null=True, blank=True)
    expires_at = models.DateField("Действует до", null=True, blank=True)
    note = models.CharField("Примечание", max_length=250, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто загрузил",
        related_name="uploaded_documents",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField("Проверка", max_length=16, choices=DocumentStatus.choices, default=DocumentStatus.PENDING)
    #: причина отклонения — её читает ученик; имя проверившего ему не отдаётся
    reject_reason = models.CharField("Причина отклонения", max_length=250, blank=True)
    reviewed_at = models.DateTimeField("Проверен", null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто проверил",
        related_name="reviewed_documents",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Загружен", auto_now_add=True)

    @property
    def is_expiring(self) -> bool:
        """Подтверждён, а срок действия уже близко (порог — в настройках)."""
        from django.conf import settings as conf
        from django.utils import timezone

        if self.status != DocumentStatus.CONFIRMED or self.expires_at is None:
            return False
        today = timezone.localdate()
        return today <= self.expires_at <= today + timedelta(days=conf.CURATOR_RULES["DOCUMENT_EXPIRING_DAYS"])

    @property
    def state(self) -> str:
        """Состояние для матрицы: `expiring` поверх `confirmed`, остальное — статус."""
        return "expiring" if self.is_expiring else str(self.status)

    @property
    def is_link(self) -> bool:
        """Документ задан ссылкой, а не файлом."""
        return bool(self.external_url) and not self.file

    class Meta:
        verbose_name = "Документ ученика"
        verbose_name_plural = "Документы учеников"
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

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="exam_goals", on_delete=models.CASCADE)
    exam = models.ForeignKey(
        "directories.ExamKind",
        verbose_name="Экзамен",
        related_name="goals",
        on_delete=models.PROTECT,
    )
    target_score = models.DecimalField("Целевой балл", max_digits=6, decimal_places=1, null=True, blank=True)
    exam_date = models.DateField("Дата экзамена", null=True, blank=True)
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)
    note = models.CharField("Примечание", max_length=250, blank=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Цель по экзамену"
        verbose_name_plural = "Цели по экзаменам"
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

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="curator_notes", on_delete=models.CASCADE)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор",
        related_name="curator_notes",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: роль автора снимком: человек сменит роль, а подпись под заметкой — нет
    author_role = models.CharField("Роль автора", max_length=32, blank=True)
    #: след автора, если его учётную запись удалили навсегда (фаза 67)
    author_title = models.CharField("Автор на момент удаления", max_length=250, blank=True)
    text = models.TextField("Текст")
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Заметка куратора"
        verbose_name_plural = "Заметки куратора"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.student}: {self.text[:40]}"


# --- Пароли учеников и таблица поступления (фаза 65) ------------------------


class CredentialKind(models.TextChoices):
    """Чей пароль хранится: почты или кабинета Common App."""

    EMAIL = "email", "Пароль от почты"
    COMMON_APP = "common_app", "Пароль Common App"


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

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="credentials", on_delete=models.CASCADE)
    kind = models.CharField("Что за пароль", max_length=16, choices=CredentialKind.choices)
    #: только шифртекст; открытый текст в базе не появляется никогда
    ciphertext = models.TextField("Шифртекст")
    updated_at = models.DateTimeField("Обновлён", auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто записал",
        related_name="saved_credentials",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Пароль ученика"
        verbose_name_plural = "Пароли учеников"
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
        verbose_name="Кто загрузил",
        related_name="admission_imports",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Когда", auto_now_add=True)
    file_name = models.CharField("Имя файла", max_length=250, blank=True)
    sheets = models.PositiveSmallIntegerField("Листов", default=0)
    students_updated = models.PositiveIntegerField("Учеников обновлено", default=0)
    attempts_created = models.PositiveIntegerField("Попыток создано", default=0)
    documents_created = models.PositiveIntegerField("Документов-ссылок", default=0)
    credentials_saved = models.PositiveIntegerField("Паролей записано", default=0)
    rows_skipped = models.PositiveIntegerField("Строк пропущено", default=0)
    #: по строке на событие: «лист\tстрока\tученик\tвид\tтекст»; текстом, не
    #: JSON — это отчёт для человека (инвариант №6)
    report = models.TextField("Отчёт", blank=True)

    class Meta:
        verbose_name = "Загрузка таблицы поступления"
        verbose_name_plural = "Загрузки таблицы поступления"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Таблица поступления {self.created_at:%d.%m.%Y %H:%M}"
