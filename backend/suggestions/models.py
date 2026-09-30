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
from django.utils.translation import gettext, gettext_lazy

from students.models import Student


class SuggestionSource(models.TextChoices):
    """Откуда пришло предложение."""

    PASTE = "paste", gettext_lazy("Вставленный текст")
    FILE = "file", gettext_lazy("Файл")
    IMAGE = "image", gettext_lazy("Изображение")
    WEB_SYNC = "web_sync", gettext_lazy("Фоновая сверка")
    MANUAL = "manual", gettext_lazy("Заведено руками")
    #: ученик внёс данные о себе (фаза 37) — решение принимает владелец домена
    STUDENT = "student", gettext_lazy("Внёс ученик")
    #: сгенерированные задачи плана по вузу (фаза 41) — применяет сам ученик
    PLAN = "plan", gettext_lazy("План по вузу")
    #: ученик загрузил документ (фаза 62) — строка очереди домена «Документы»;
    #: решение подтверждает или отклоняет сам документ
    DOCUMENT = "document", gettext_lazy("Загрузил документ")
    #: помощник собрал предложение моделью: разбор вуза, разбор активности,
    #: задачи ученикам — в журнал применение идёт с источником «ИИ»
    ASSISTANT = "assistant", gettext_lazy("Собрал помощник")


class SuggestionStatus(models.TextChoices):
    DRAFT = "draft", gettext_lazy("Черновик")
    PENDING = "pending", gettext_lazy("Ждёт решения")
    APPLIED = "applied", gettext_lazy("Применено")
    PARTIALLY_APPLIED = "partially_applied", gettext_lazy("Применено частично")
    REJECTED = "rejected", gettext_lazy("Отклонено")
    REVERTED = "reverted", gettext_lazy("Откачено")
    #: куратор внёс значение сам, пока предложение ученика ждало решения.
    #: Не «отклонено»: причины нет, просто внесли за него
    SUPERSEDED = "superseded", gettext_lazy("Перекрыто записью куратора")


class Suggestion(models.Model):
    """Пакет предложенных изменений — единица предпросмотра и применения."""

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Автор"),
        related_name="suggestions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    role = models.CharField(gettext_lazy("Роль автора"), max_length=32)
    domain_code = models.CharField(gettext_lazy("Домен"), max_length=32)
    command = models.CharField(gettext_lazy("Команда"), max_length=64, blank=True)
    source_type = models.CharField(gettext_lazy("Тип источника"), max_length=16, choices=SuggestionSource.choices)
    source_ref = models.CharField(gettext_lazy("Ссылка на источник"), max_length=500, blank=True)
    status = models.CharField(
        gettext_lazy("Статус"), max_length=24, choices=SuggestionStatus.choices, default=SuggestionStatus.DRAFT
    )
    #: причина отклонения — ученик читает её и вносит заново (фаза 37)
    reject_reason = models.CharField(gettext_lazy("Причина отклонения"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Создано"), auto_now_add=True)
    resolved_at = models.DateTimeField(gettext_lazy("Решено"), null=True, blank=True)
    #: кто решил и в какой роли (фаза 60): очередь общая у владельца домена
    #: и куратора группы, и второму система отвечает «уже подтверждено,
    #: кем и когда». Роль — снимком: сменится у человека, а в журнале нет
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто решил"),
        related_name="resolved_suggestions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    resolved_role = models.CharField(gettext_lazy("Роль решившего"), max_length=32, blank=True)
    #: след решившего, если его учётную запись удалили навсегда (фаза 67):
    #: «кем подтверждено» должно читаться и через год после ухода человека
    resolved_by_title = models.CharField(gettext_lazy("Кто решил, на момент удаления"), max_length=250, blank=True)
    #: передано владельцу домена (фаза 62): куратор не решает сам, а отдаёт
    #: строку с комментарием Кымбат или Асем — тому, чей домен у строки.
    #: Пока владелец не решил, куратор может вернуть строку себе
    escalated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто передал"),
        related_name="escalated_suggestions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    escalated_at = models.DateTimeField(gettext_lazy("Когда передано"), null=True, blank=True)
    escalation_comment = models.CharField(gettext_lazy("Комментарий при передаче"), max_length=500, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Предложение")
        verbose_name_plural = gettext_lazy("Предложения")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("domain_code", "status", "-created_at"))]

    def __str__(self) -> str:
        return gettext("Предложение #{number} ({status})").format(number=self.pk, status=self.get_status_display())

    @property
    def is_escalated(self) -> bool:
        return self.escalated_by_id is not None and self.status == SuggestionStatus.PENDING


class SuggestionChange(models.Model):
    """Одна строка предложения: поле одного ученика."""

    suggestion = models.ForeignKey(
        Suggestion, verbose_name=gettext_lazy("Предложение"), related_name="changes", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        Student,
        verbose_name=gettext_lazy("Ученик"),
        related_name="suggested_changes",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    model_label = models.CharField(gettext_lazy("Модель"), max_length=100)
    object_id = models.CharField(gettext_lazy("Объект"), max_length=64, blank=True)
    #: непустой ключ означает «это часть новой записи, а не правка старой».
    #: Строки с одним ключом складываются в один объект при применении —
    #: так массовая постановка задач проходит через предложение, а не мимо
    #: него (инвариант №3)
    new_object_key = models.CharField(gettext_lazy("Новая запись"), max_length=64, blank=True)
    field_name = models.CharField(gettext_lazy("Поле"), max_length=100)
    old_value = models.TextField(gettext_lazy("Было"), blank=True)
    new_value = models.TextField(gettext_lazy("Стало"), blank=True)
    confidence = models.DecimalField(gettext_lazy("Уверенность"), max_digits=4, decimal_places=3, default=1)
    source_ref = models.CharField(gettext_lazy("Ссылка на источник"), max_length=500, blank=True)
    source_quote = models.TextField(gettext_lazy("Фрагмент источника"), blank=True)
    is_accepted = models.BooleanField(gettext_lazy("Принято"), default=False)
    is_applied = models.BooleanField(gettext_lazy("Применено"), default=False)
    conflict = models.CharField(gettext_lazy("Конфликт"), max_length=250, blank=True)
    #: что внёс куратор, перекрыв эту строку: ученик читает «куратор внёс
    #: значение X». Пусто у всех остальных строк
    superseded_value = models.TextField(gettext_lazy("Внесено куратором"), blank=True)

    class Meta:
        verbose_name = gettext_lazy("Изменение в предложении")
        verbose_name_plural = gettext_lazy("Изменения в предложениях")
        ordering = ("confidence", "id")

    def __str__(self) -> str:
        return f"{self.model_label}.{self.field_name} → {self.new_value}"


class LLMCall(models.Model):
    """Журнал обращений к модели: кто, когда, какая операция, сколько стоило.

    Хранится отдельно от AuditLog: там доменные изменения, здесь — следы
    работы с провайдером. Нужен, чтобы можно было разобрать любой спорный
    случай постфактум и чтобы месячный счёт не оказался сюрпризом.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто вызвал"),
        related_name="llm_calls",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: роль на момент вызова: учётную запись могли переназначить,
    #: а расходы по ролям считать всё равно нужно
    role = models.CharField(gettext_lazy("Роль"), max_length=32, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True)
    purpose = models.CharField(gettext_lazy("Операция"), max_length=64)
    provider = models.CharField(gettext_lazy("Провайдер"), max_length=32, blank=True)
    model = models.CharField(gettext_lazy("Модель"), max_length=100, blank=True)
    external_id = models.CharField(gettext_lazy("Идентификатор вызова"), max_length=100, blank=True)
    request_payload = models.TextField(gettext_lazy("Отправлено"), blank=True)
    response_payload = models.TextField(gettext_lazy("Получено"), blank=True)
    tokens_in = models.PositiveIntegerField(gettext_lazy("Токенов на входе"), default=0)
    tokens_out = models.PositiveIntegerField(gettext_lazy("Токенов на выходе"), default=0)
    #: поиск в интернете оплачивается запросами, а не токенами
    searches = models.PositiveIntegerField(gettext_lazy("Поисковых запросов"), default=0)
    #: считается по прейскуранту из настроек: провайдер цену в ответе не шлёт
    cost = models.DecimalField(gettext_lazy("Стоимость, $"), max_digits=9, decimal_places=5, default=0)
    duration_ms = models.PositiveIntegerField(gettext_lazy("Длительность, мс"), default=0)
    is_ok = models.BooleanField(gettext_lazy("Успешно"), default=True)
    error = models.CharField(gettext_lazy("Что пошло не так"), max_length=250, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Вызов модели")
        verbose_name_plural = gettext_lazy("Журнал вызовов модели")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("-created_at",)),
            models.Index(fields=("purpose",)),
            models.Index(fields=("role", "-created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.purpose} · {self.created_at:%Y-%m-%d %H:%M}"


class EssayAssistLog(models.Model):
    """Активность ученика с ИИ по эссе — целиком видна куратору.

    ИИ не пишет и не переписывает текст: разрешено только задавать вопросы,
    помогающие раскрыть историю. Что спросили и что ответил ИИ — здесь.
    """

    essay = models.ForeignKey(
        "roadmap.Essay", verbose_name=gettext_lazy("Эссе"), related_name="assist_logs", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        "students.Student", verbose_name=gettext_lazy("Ученик"), related_name="essay_assists", on_delete=models.CASCADE
    )
    prompt = models.TextField(gettext_lazy("Запрос ученика"))
    questions = models.TextField(gettext_lazy("Вопросы от ИИ"))
    created_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Работа с ИИ по эссе")
        verbose_name_plural = gettext_lazy("Работа с ИИ по эссе")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return gettext("Эссе {essay} · {date}").format(essay=self.essay_id, date=f"{self.created_at:%Y-%m-%d}")


class AssistantThread(models.Model):
    """Диалог помощника в углу. Каждый видит только свои диалоги."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Владелец"),
        related_name="assistant_threads",
        on_delete=models.CASCADE,
    )
    title = models.CharField(gettext_lazy("Название"), max_length=200, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Диалог помощника")
        verbose_name_plural = gettext_lazy("Диалоги помощника")
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return self.title or gettext("Диалог #{number}").format(number=self.pk)


class AssistantMessage(models.Model):
    """Сообщение диалога. Типизированные колонки, без JSONB (инвариант №6)."""

    class Author(models.TextChoices):
        USER = "user", gettext_lazy("Человек")
        ASSISTANT = "assistant", gettext_lazy("Помощник")

    thread = models.ForeignKey(
        AssistantThread, verbose_name=gettext_lazy("Диалог"), related_name="messages", on_delete=models.CASCADE
    )
    author = models.CharField(gettext_lazy("Кто"), max_length=12, choices=Author.choices)
    text = models.TextField(gettext_lazy("Текст"))
    #: строки-списки ответа, по одной на строку
    lines = models.TextField(gettext_lazy("Строки"), blank=True)
    #: код быстрой кнопки, если сообщение — её вызов
    command = models.CharField(gettext_lazy("Команда"), max_length=64, blank=True)
    #: предложение, созданное этим ответом, — карточка предпросмотра в панели
    suggestion = models.ForeignKey(
        Suggestion,
        verbose_name=gettext_lazy("Предложение"),
        related_name="assistant_messages",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: собран правилами (модели не было или она не понадобилась)
    offline = models.BooleanField(gettext_lazy("Собрано правилами"), default=True)
    #: к скольким ученикам применится создаваемое предложение
    affected = models.PositiveIntegerField(gettext_lazy("Затронет учеников"), default=0)
    created_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Сообщение помощника")
        verbose_name_plural = gettext_lazy("Сообщения помощника")
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"{self.get_author_display()}: {self.text[:40]}"
