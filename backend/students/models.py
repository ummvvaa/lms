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


class AdmissionProfile(Archivable):
    """Поступление. Владелец — домен `admission`."""

    student = models.OneToOneField(Student, verbose_name="Ученик", related_name="admission", on_delete=models.CASCADE)
    target_country = models.CharField("Целевая страна", max_length=100, blank=True)
    target_major = models.CharField("Специальность", max_length=150, blank=True)
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
        indexes = [models.Index(fields=("student", "category"))]

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
    sport_kind = models.CharField("Вид спорта", max_length=100, blank=True)
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
    """Одно соревнование (инвариант №5)."""

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="competitions", on_delete=models.CASCADE)
    name = models.CharField("Соревнование", max_length=250)
    date = models.DateField("Дата", null=True, blank=True)
    result = models.CharField("Результат", max_length=150, blank=True)
    has_certificate = models.BooleanField("Сертификат есть", default=False)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Соревнование"
        verbose_name_plural = "Соревнования"
        ordering = ("-date", "-id")
        indexes = [models.Index(fields=("student", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.name}"
