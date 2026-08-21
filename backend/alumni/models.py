"""Выпускники, менторство и архив эссе.

Ключевое правило менторства: запрос ученика проходит через сотрудника
школы, а не напрямую к выпускнику. Выпускник — не служба поддержки,
и школа отвечает за то, кого к нему направляют.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from students.models import Student
from universities.models import Program, University


class Alumnus(models.Model):
    """Выпускник.

    Профиль на момент поступления сохраняется отдельными колонками:
    он не должен меняться вслед за правками ученической карточки —
    это исторический срез, по нему нынешние ученики сверяются с реальностью.
    """

    student = models.OneToOneField(Student, verbose_name="Ученик", related_name="alumnus", on_delete=models.CASCADE)
    graduation_year = models.PositiveSmallIntegerField("Год выпуска")

    university = models.ForeignKey(
        University,
        verbose_name="Вуз",
        related_name="alumni",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    program = models.ForeignKey(
        Program,
        verbose_name="Программа",
        related_name="alumni",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    country = models.CharField("Страна", max_length=100, blank=True)
    current_occupation = models.CharField("Чем занимается сейчас", max_length=250, blank=True)

    # --- профиль на момент поступления: исторический срез ---
    admission_gpa = models.DecimalField("GPA при поступлении", max_digits=4, decimal_places=2, null=True, blank=True)
    admission_ielts = models.DecimalField(
        "IELTS при поступлении", max_digits=3, decimal_places=1, null=True, blank=True
    )
    admission_sat = models.PositiveSmallIntegerField("SAT при поступлении", null=True, blank=True)
    admission_activities = models.PositiveSmallIntegerField("Активностей при поступлении", default=0)

    # --- менторство ---
    mentorship_consent = models.BooleanField("Согласие на менторство", default=False)
    contact_email = models.EmailField("Контактная почта", blank=True)
    note = models.TextField("Заметка школы", blank=True)

    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Выпускник"
        verbose_name_plural = "Выпускники"
        ordering = ("-graduation_year", "student__last_name")
        indexes = [
            models.Index(fields=("graduation_year",)),
            models.Index(fields=("country",)),
            models.Index(fields=("mentorship_consent",)),
        ]

    def __str__(self) -> str:
        return f"{self.student} ({self.graduation_year})"

    @property
    def full_name(self) -> str:
        return self.student.full_name


class ApplicationOutcome(models.TextChoices):
    ADMITTED = "admitted", "Поступил"
    REJECTED = "rejected", "Отказ"
    WAITLIST = "waitlist", "Лист ожидания"
    WITHDRAWN = "withdrawn", "Отозвал"
    ENROLLED = "enrolled", "Учится"


class AlumnusApplication(models.Model):
    """Результат по каждой заявке выпускника (инвариант №5)."""

    alumnus = models.ForeignKey(
        Alumnus, verbose_name="Выпускник", related_name="applications", on_delete=models.CASCADE
    )
    program = models.ForeignKey(
        Program, verbose_name="Программа", related_name="alumni_applications", on_delete=models.PROTECT
    )
    outcome = models.CharField("Результат", max_length=16, choices=ApplicationOutcome.choices)
    scholarship = models.CharField("Стипендия", max_length=200, blank=True)
    note = models.CharField("Примечание", max_length=250, blank=True)

    class Meta:
        verbose_name = "Заявка выпускника"
        verbose_name_plural = "Заявки выпускников"
        constraints = [
            models.UniqueConstraint(fields=("alumnus", "program"), name="uniq_alumnus_program"),
        ]

    def __str__(self) -> str:
        return f"{self.alumnus} → {self.program}: {self.get_outcome_display()}"


class MentorshipStatus(models.TextChoices):
    """Запрос идёт через школу, поэтому статусов больше, чем «да/нет»."""

    REQUESTED = "requested", "Запрошено учеником"
    APPROVED = "approved", "Одобрено школой"
    DECLINED = "declined", "Отклонено школой"
    SENT = "sent", "Передано выпускнику"
    ACCEPTED = "accepted", "Выпускник согласился"
    REFUSED = "refused", "Выпускник отказался"
    COMPLETED = "completed", "Завершено"


class MentorshipRequest(models.Model):
    """Запрос ученика на менторство.

    Пока сотрудник не одобрил, выпускник о запросе не знает: поле
    `is_visible_to_alumnus` выставляется только на переходе в `sent`.
    """

    student = models.ForeignKey(
        Student, verbose_name="Ученик", related_name="mentorship_requests", on_delete=models.CASCADE
    )
    alumnus = models.ForeignKey(
        Alumnus, verbose_name="Выпускник", related_name="mentorship_requests", on_delete=models.CASCADE
    )
    topic = models.CharField("Тема", max_length=250)
    message = models.TextField("Сообщение", blank=True)
    status = models.CharField(
        "Статус", max_length=16, choices=MentorshipStatus.choices, default=MentorshipStatus.REQUESTED
    )
    #: становится True только после одобрения сотрудником
    is_visible_to_alumnus = models.BooleanField("Видно выпускнику", default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто рассмотрел",
        related_name="reviewed_mentorships",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    review_note = models.CharField("Решение сотрудника", max_length=250, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Запрос на менторство"
        verbose_name_plural = "Запросы на менторство"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("status", "-created_at"))]

    def __str__(self) -> str:
        return f"{self.student} → {self.alumnus}: {self.get_status_display()}"


class MentorshipMeeting(models.Model):
    """История встреч по запросу (инвариант №5)."""

    request = models.ForeignKey(
        MentorshipRequest, verbose_name="Запрос", related_name="meetings", on_delete=models.CASCADE
    )
    date = models.DateField("Дата")
    duration_minutes = models.PositiveSmallIntegerField("Длительность, мин", null=True, blank=True)
    summary = models.TextField("О чём говорили", blank=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Встреча"
        verbose_name_plural = "Встречи"
        ordering = ("-date",)

    def __str__(self) -> str:
        return f"Встреча {self.date} по запросу {self.request_id}"


class ArchivedEssay(models.Model):
    """Эссе выпускника в архиве — только с явного согласия.

    Обязательно указано, куда человек поступил: без этого эссе теряет
    смысл как образец.
    """

    alumnus = models.ForeignKey(
        Alumnus, verbose_name="Выпускник", related_name="archived_essays", on_delete=models.CASCADE
    )
    essay = models.ForeignKey(
        "roadmap.Essay",
        verbose_name="Исходное эссе",
        related_name="archive_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    program = models.ForeignKey(
        Program, verbose_name="Куда поступил", related_name="archived_essays", on_delete=models.PROTECT
    )
    essay_type = models.CharField("Тип", max_length=24)
    title = models.CharField("Название", max_length=250)
    text = models.TextField("Текст")
    #: без явного согласия эссе не показывается никому, кроме сотрудников
    consent_given = models.BooleanField("Согласие на публикацию", default=False)
    consent_at = models.DateTimeField("Когда дано согласие", null=True, blank=True)
    is_anonymous = models.BooleanField("Скрыть имя автора", default=False)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Эссе в архиве"
        verbose_name_plural = "Архив эссе"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("consent_given",))]

    def __str__(self) -> str:
        return f"{self.title} ({self.alumnus})"

    @property
    def author_label(self) -> str:
        """Как подписывать эссе для читателя."""
        if self.is_anonymous:
            return f"Выпуск {self.alumnus.graduation_year}"
        return f"{self.alumnus.full_name}, выпуск {self.alumnus.graduation_year}"
