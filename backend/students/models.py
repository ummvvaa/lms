"""Ученики, учебные группы, пять профильных таблиц и история достижений.

Инвариант №5: всё, что имеет историю (моки, активности, соревнования),
живёт строками в дочерних таблицах, а не полями профиля.
Инвариант №6: никакого JSONB — только типизированные колонки.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.archivable import Archivable


class StudyGroup(Archivable):
    """Учебная группа — единица контроля, 15–20 учеников."""

    code = models.CharField("Код", max_length=16, unique=True)
    grade = models.PositiveSmallIntegerField("Класс")
    curator = models.CharField("Куратор", max_length=200, blank=True)
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
    #: для казахстанской школы ЕНТ — не второстепенный экзамен: часть
    #: учеников сдаёт и его, и международные (фаза 38)
    ENT = "ENT", "ЕНТ"


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
    PLATFORM = "platform", "Пройден на платформе"
    #: прочитано со скриншота помощником и принято человеком — доверие
    #: к такому баллу ниже, чем к внесённому руками с бумаги
    AI = "ai", "Распознано со скриншота"


class ExamAttempt(Archivable):
    """Одна попытка экзамена — мок или официальная сдача (инвариант №5)."""

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="exam_attempts", on_delete=models.CASCADE)
    exam_type = models.CharField("Экзамен", max_length=8, choices=ExamType.choices)
    attempt_format = models.CharField("Формат", max_length=8, choices=AttemptFormat.choices)
    source = models.CharField("Источник", max_length=16, choices=AttemptSource.choices, default=AttemptSource.MANUAL)
    date = models.DateField("Дата")
    total_score = models.DecimalField("Общий балл", max_digits=6, decimal_places=1, null=True, blank=True)
    # секции IELTS / TOEFL
    listening = models.DecimalField("Listening", max_digits=4, decimal_places=1, null=True, blank=True)
    reading = models.DecimalField("Reading", max_digits=4, decimal_places=1, null=True, blank=True)
    writing = models.DecimalField("Writing", max_digits=4, decimal_places=1, null=True, blank=True)
    speaking = models.DecimalField("Speaking", max_digits=4, decimal_places=1, null=True, blank=True)
    # секции SAT / ACT
    math = models.PositiveSmallIntegerField("Math", null=True, blank=True)
    verbal = models.PositiveSmallIntegerField("Verbal", null=True, blank=True)
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


class StudentDocument(Archivable):
    """Документ ученика: аттестат, транскрипт, сертификат, письмо, паспорт.

    Файл лежит вне корня веб-сервера — как материалы олимпиадников —
    и отдаётся только после проверки прав: ученик видит свои, сотрудники —
    документы любого ученика. Загружает ученик сам: это его документы,
    а не табличные данные, которые с фазы 35 грузит администратор.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="documents", on_delete=models.CASCADE)
    doc_type = models.CharField("Тип документа", max_length=24, choices=DocumentType.choices)
    title = models.CharField("Название", max_length=200, blank=True)
    file = models.FileField("Файл", upload_to=document_upload_to, storage=_document_storage, max_length=300)
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
    created_at = models.DateTimeField("Загружен", auto_now_add=True)

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
