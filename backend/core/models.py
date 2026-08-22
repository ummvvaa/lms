"""Журнал изменений доменных полей (инвариант №9)."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.domains import Source


class AuditLog(models.Model):
    """Одна запись: кто, когда, какое поле какого объекта и откуда изменил.

    Значения хранятся строками — универсально для любых типов колонок
    и читаемо во вкладке истории на карточке ученика.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто изменил",
        related_name="audit_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Когда", auto_now_add=True)
    model_label = models.CharField("Модель", max_length=100)
    object_id = models.CharField("Объект", max_length=64)
    student_id = models.BigIntegerField("Ученик", null=True, blank=True, db_index=True)
    field_name = models.CharField("Поле", max_length=100)
    domain_code = models.CharField("Домен", max_length=32, blank=True)
    old_value = models.TextField("Было", blank=True)
    new_value = models.TextField("Стало", blank=True)
    # 32 символа: «student_onboarding» в 16 не помещается
    source = models.CharField("Источник", max_length=32, choices=Source.CHOICES, default=Source.MANUAL)
    suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        verbose_name="Предложение",
        related_name="audit_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Запись аудита"
        verbose_name_plural = "Журнал изменений"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("model_label", "object_id")),
            models.Index(fields=("-created_at",)),
            models.Index(fields=("domain_code", "-created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.model_label}#{self.object_id}.{self.field_name}: {self.old_value} → {self.new_value}"


class ReadinessSnapshot(models.Model):
    """Еженедельный срез готовности — для графиков динамики.

    Сам Readiness Score вычисляемый и не хранится; здесь лежат только
    снимки на дату, чтобы было что рисовать в динамике.
    """

    student = models.ForeignKey(
        "students.Student", verbose_name="Ученик", related_name="readiness_snapshots", on_delete=models.CASCADE
    )
    date = models.DateField("Дата среза")
    score = models.PositiveSmallIntegerField("Готовность, %")
    exam = models.DecimalField("Экзамены", max_digits=5, decimal_places=1, null=True, blank=True)
    admission = models.DecimalField("Поступление", max_digits=5, decimal_places=1, null=True, blank=True)
    talent = models.DecimalField("Портфолио", max_digits=5, decimal_places=1, null=True, blank=True)
    behavior = models.DecimalField("Дисциплина", max_digits=5, decimal_places=1, null=True, blank=True)
    sport = models.DecimalField("Спорт", max_digits=5, decimal_places=1, null=True, blank=True)
    weakest = models.CharField("Слабое звено", max_length=32, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Срез готовности"
        verbose_name_plural = "Срезы готовности"
        ordering = ("-date",)
        constraints = [
            models.UniqueConstraint(fields=("student", "date"), name="uniq_readiness_snapshot_per_day"),
        ]
        indexes = [models.Index(fields=("student", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.date}: {self.score}%"
