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
    source = models.CharField("Источник", max_length=16, choices=Source.CHOICES, default=Source.MANUAL)
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
