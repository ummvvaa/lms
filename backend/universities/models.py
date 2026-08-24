"""Справочник вузов и заявки учеников.

Инвариант №4: дедлайн принадлежит вузу, а не ученику — он живёт
в `AdmissionRound` и меняется один раз для всех, кто туда подаётся.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.archivable import Archivable
from students.models import Student

#: Текст плашки над непроверенной записью справочника (инвариант №14).
UNVERIFIED_NOTE = "Данные не подтверждены, проверьте на сайте вуза"


class CatalogSource(models.TextChoices):
    """Откуда взялась запись справочника.

    Отличать нужно ради инварианта №14: всё, что пришло не от сотрудника
    школы и не с официального сайта, показывается только с плашкой.
    """

    SCHOOL = "school", "Заведено школой"
    SEED = "seed", "Стартовый справочник"
    IMPORT = "import", "Импорт файла"
    SYNC = "sync", "Фоновая сверка"
    #: разобрано моделью по названию или ссылке — такие записи всегда
    #: заводятся неподтверждёнными и сверяются человеком (инвариант №14)
    AI = "ai", "Разобрано помощником"


class VerifiableRecord(models.Model):
    """Запись справочника с признаком «данные подтверждены» (инвариант №14).

    Снять признак вправе только директор по поступлению — руками или через
    сверку с официальным сайтом. До этого запись живёт с оранжевой плашкой,
    и ученику она показывается только вместе с ней.
    """

    data_source = models.CharField(
        "Источник записи", max_length=16, choices=CatalogSource.choices, default=CatalogSource.SCHOOL
    )
    is_verified = models.BooleanField("Данные подтверждены", default=True)
    verified_at = models.DateTimeField("Когда подтверждено", null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто подтвердил",
        related_name="verified_%(class)s_set",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True

    @property
    def verification_note(self) -> str:
        """Текст плашки. Пустая строка — плашки нет."""
        return "" if self.is_verified else UNVERIFIED_NOTE


class University(VerifiableRecord):
    """Вуз."""

    name = models.CharField("Название", max_length=250, unique=True)
    country = models.CharField("Страна", max_length=100)
    website = models.URLField("Сайт", blank=True)
    domain = models.CharField(
        "Домен для сверки", max_length=100, blank=True, help_text="Например utoronto.ca — по нему сверяются источники"
    )
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Вуз"
        verbose_name_plural = "Вузы"
        ordering = ("name",)
        indexes = [models.Index(fields=("country",))]

    def __str__(self) -> str:
        return self.name


class ProgramLevel(models.TextChoices):
    BACHELOR = "bachelor", "Бакалавриат"
    MASTER = "master", "Магистратура"
    FOUNDATION = "foundation", "Foundation"


class Program(VerifiableRecord):
    """Программа обучения в вузе."""

    university = models.ForeignKey(University, verbose_name="Вуз", related_name="programs", on_delete=models.CASCADE)
    name = models.CharField("Специальность", max_length=250)
    level = models.CharField("Уровень", max_length=16, choices=ProgramLevel.choices, default=ProgramLevel.BACHELOR)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Программа"
        verbose_name_plural = "Программы"
        ordering = ("university__name", "name")
        constraints = [
            models.UniqueConstraint(fields=("university", "name", "level"), name="uniq_program_per_university")
        ]

    def __str__(self) -> str:
        return f"{self.university.name} — {self.name}"


class RoundType(models.TextChoices):
    ED = "ED", "Early Decision"
    EA = "EA", "Early Action"
    RD = "RD", "Regular Decision"
    ROLLING = "Rolling", "Rolling"


class AdmissionRound(VerifiableRecord):
    """Раунд подачи с дедлайном. Дедлайн — здесь и только здесь."""

    program = models.ForeignKey(Program, verbose_name="Программа", related_name="rounds", on_delete=models.CASCADE)
    round_type = models.CharField("Тип раунда", max_length=8, choices=RoundType.choices)
    deadline = models.DateField("Дедлайн")
    source_url = models.URLField("Источник", blank=True)
    checked_at = models.DateTimeField("Последняя сверка", null=True, blank=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Раунд подачи"
        verbose_name_plural = "Раунды подачи"
        ordering = ("deadline",)
        constraints = [
            models.UniqueConstraint(fields=("program", "round_type"), name="uniq_round_per_program"),
        ]
        indexes = [models.Index(fields=("deadline",))]

    def __str__(self) -> str:
        return f"{self.program} · {self.round_type} до {self.deadline}"


class Tier(models.TextChoices):
    REACH = "reach", "Reach"
    TARGET = "target", "Target"
    SAFETY = "safety", "Safety"


class ApplicationStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Не начата"
    IN_PROGRESS = "in_progress", "В работе"
    READY = "ready", "Готова"
    SUBMITTED = "submitted", "Подана"
    ACCEPTED = "accepted", "Принят"
    REJECTED = "rejected", "Отказ"
    WAITLIST = "waitlist", "Лист ожидания"


class AddedBy(models.TextChoices):
    """Кто положил программу в список ученика."""

    DIRECTOR = "director", "Директор по поступлению"
    STUDENT = "student", "Ученик"
    IMPORT = "import", "Импорт"


class StudentUniversity(Archivable):
    """Программа в списке ученика. Владелец — домен `admission`.

    Ученик может добавить программу себе сам — такая запись помечается
    `added_by=student` и ждёт подтверждения директора. Удалить он может
    только то, что добавил сам: чужое решение снимает тот, кто его принял.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="universities", on_delete=models.CASCADE)
    program = models.ForeignKey(Program, verbose_name="Программа", related_name="applicants", on_delete=models.PROTECT)
    admission_round = models.ForeignKey(
        AdmissionRound,
        verbose_name="Раунд",
        related_name="applicants",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    tier = models.CharField("Категория", max_length=8, choices=Tier.choices, default=Tier.TARGET)
    application_status = models.CharField(
        "Статус заявки", max_length=16, choices=ApplicationStatus.choices, default=ApplicationStatus.NOT_STARTED
    )
    note = models.CharField("Примечание", max_length=250, blank=True)
    added_by = models.CharField("Кто добавил", max_length=16, choices=AddedBy.choices, default=AddedBy.DIRECTOR)
    #: подтверждение директора нужно только тому, что добавил ученик
    is_confirmed = models.BooleanField("Подтверждено директором", default=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Вуз ученика"
        verbose_name_plural = "Вузы учеников"
        ordering = ("student", "tier")
        constraints = [
            # архивную запись ученик не видит, и она не должна мешать
            # добавить ту же программу заново
            models.UniqueConstraint(
                fields=("student", "program"),
                condition=models.Q(archived_at__isnull=True),
                name="uniq_student_program",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} → {self.program}"

    @property
    def deadline(self):
        """Дедлайн берётся из раунда вуза, у ученика своего дедлайна нет."""
        return self.admission_round.deadline if self.admission_round_id else None


class AdmissionRequirement(VerifiableRecord):
    """Требования программы к абитуриенту.

    Ровно те таблицы, которые директор по поступлению ведёт в своих файлах.
    Владелец — домен `admission`. Пороги хранятся типизированными колонками
    (инвариант №6): по ним считается соответствие и строятся подборки.

    Пустой порог означает «требования нет», а не «ноль».
    """

    program = models.OneToOneField(
        Program, verbose_name="Программа", related_name="requirement", on_delete=models.CASCADE
    )
    min_gpa = models.DecimalField("Минимальный GPA", max_digits=4, decimal_places=2, null=True, blank=True)
    min_ielts = models.DecimalField("Минимальный IELTS", max_digits=3, decimal_places=1, null=True, blank=True)
    min_toefl = models.PositiveSmallIntegerField("Минимальный TOEFL", null=True, blank=True)
    min_sat = models.PositiveSmallIntegerField("Минимальный SAT", null=True, blank=True)
    min_act = models.PositiveSmallIntegerField("Минимальный ACT", null=True, blank=True)
    required_subjects = models.CharField("Требуемые предметы", max_length=300, blank=True, help_text="Через запятую")
    portfolio_required = models.BooleanField("Нужно портфолио", default=False)
    portfolio_note = models.CharField("Требования к портфолио", max_length=300, blank=True)
    notes = models.TextField("Примечания", blank=True)
    source_url = models.URLField("Источник", blank=True)
    checked_at = models.DateTimeField("Дата актуализации", null=True, blank=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Требования программы"
        verbose_name_plural = "Требования программ"
        ordering = ("program__university__name", "program__name")

    def __str__(self) -> str:
        return f"Требования: {self.program}"

    @property
    def subjects_list(self) -> list[str]:
        return [x.strip() for x in self.required_subjects.split(",") if x.strip()]
