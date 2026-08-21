"""Предложения изменений.

Схема заводится в Фазе 1 вместе с остальной базой, потому что `AuditLog`
обязан ссылаться на предложение (инвариант №9). Движок применения, отката,
валидации и разбора появляется в Фазе 5.

Инвариант №3: ИИ никогда не пишет в основные таблицы — только сюда.
Применяет изменения человек.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from students.models import Student


class SuggestionSource(models.TextChoices):
    """Откуда пришло предложение."""

    PASTE = "paste", "Вставленный текст"
    FILE = "file", "Файл"
    IMAGE = "image", "Изображение"
    WEB_SYNC = "web_sync", "Фоновая сверка"
    MANUAL = "manual", "Заведено руками"


class SuggestionStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    PENDING = "pending", "Ждёт решения"
    APPLIED = "applied", "Применено"
    PARTIALLY_APPLIED = "partially_applied", "Применено частично"
    REJECTED = "rejected", "Отклонено"
    REVERTED = "reverted", "Откачено"


class Suggestion(models.Model):
    """Пакет предложенных изменений — единица предпросмотра и применения."""

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор",
        related_name="suggestions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    role = models.CharField("Роль автора", max_length=32)
    domain_code = models.CharField("Домен", max_length=32)
    command = models.CharField("Команда", max_length=64, blank=True)
    source_type = models.CharField("Тип источника", max_length=16, choices=SuggestionSource.choices)
    source_ref = models.CharField("Ссылка на источник", max_length=500, blank=True)
    status = models.CharField("Статус", max_length=24, choices=SuggestionStatus.choices, default=SuggestionStatus.DRAFT)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    resolved_at = models.DateTimeField("Решено", null=True, blank=True)

    class Meta:
        verbose_name = "Предложение"
        verbose_name_plural = "Предложения"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("domain_code", "status", "-created_at"))]

    def __str__(self) -> str:
        return f"Предложение #{self.pk} ({self.get_status_display()})"


class SuggestionChange(models.Model):
    """Одна строка предложения: поле одного ученика."""

    suggestion = models.ForeignKey(
        Suggestion, verbose_name="Предложение", related_name="changes", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        Student,
        verbose_name="Ученик",
        related_name="suggested_changes",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    model_label = models.CharField("Модель", max_length=100)
    object_id = models.CharField("Объект", max_length=64, blank=True)
    field_name = models.CharField("Поле", max_length=100)
    old_value = models.TextField("Было", blank=True)
    new_value = models.TextField("Стало", blank=True)
    confidence = models.DecimalField("Уверенность", max_digits=4, decimal_places=3, default=1)
    source_ref = models.CharField("Ссылка на источник", max_length=500, blank=True)
    source_quote = models.TextField("Фрагмент источника", blank=True)
    is_accepted = models.BooleanField("Принято", default=False)
    is_applied = models.BooleanField("Применено", default=False)
    conflict = models.CharField("Конфликт", max_length=250, blank=True)

    class Meta:
        verbose_name = "Изменение в предложении"
        verbose_name_plural = "Изменения в предложениях"
        ordering = ("confidence", "id")

    def __str__(self) -> str:
        return f"{self.model_label}.{self.field_name} → {self.new_value}"


class LLMCall(models.Model):
    """Журнал обращений к модели: кто, что отправлено, что вернулось.

    Хранится отдельно от AuditLog: там доменные изменения, здесь — следы
    работы с провайдером. Нужен, чтобы можно было разобрать любой спорный
    случай постфактум.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто вызвал",
        related_name="llm_calls",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Когда", auto_now_add=True)
    purpose = models.CharField("Назначение", max_length=64)
    model = models.CharField("Модель", max_length=100, blank=True)
    external_id = models.CharField("Идентификатор вызова", max_length=100, blank=True)
    request_payload = models.TextField("Отправлено", blank=True)
    response_payload = models.TextField("Получено", blank=True)

    class Meta:
        verbose_name = "Вызов модели"
        verbose_name_plural = "Журнал вызовов модели"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("-created_at",)), models.Index(fields=("purpose",))]

    def __str__(self) -> str:
        return f"{self.purpose} · {self.created_at:%Y-%m-%d %H:%M}"


class EssayAssistLog(models.Model):
    """Активность ученика с ИИ по эссе — целиком видна куратору.

    ИИ не пишет и не переписывает текст: разрешено только задавать вопросы,
    помогающие раскрыть историю. Что спросили и что ответил ИИ — здесь.
    """

    essay = models.ForeignKey(
        "roadmap.Essay", verbose_name="Эссе", related_name="assist_logs", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        "students.Student", verbose_name="Ученик", related_name="essay_assists", on_delete=models.CASCADE
    )
    prompt = models.TextField("Запрос ученика")
    questions = models.TextField("Вопросы от ИИ")
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "Работа с ИИ по эссе"
        verbose_name_plural = "Работа с ИИ по эссе"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Эссе {self.essay_id} · {self.created_at:%Y-%m-%d}"
