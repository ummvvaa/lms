"""Журнал изменений доменных полей (инвариант №9), архив и история загрузок."""

from __future__ import annotations

import uuid

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
    #: подпись автора на случай, если самой записи больше нет: учётные
    #: записи людей не удаляются никогда, а одноразовые записи прогона —
    #: всегда, и строка журнала после этого не должна читаться как «система»
    actor_title = models.CharField("Автор на момент удаления", max_length=250, blank=True)
    created_at = models.DateTimeField("Когда", auto_now_add=True)
    model_label = models.CharField("Модель", max_length=100)
    object_id = models.CharField("Объект", max_length=64)
    student_id = models.BigIntegerField("Ученик", null=True, blank=True, db_index=True)
    field_name = models.CharField("Поле", max_length=100)
    domain_code = models.CharField("Домен", max_length=32, blank=True)
    #: домен, за который действовал автор, когда это не его домен.
    #: Администратор грузит файлы и вставляет текст по всем пяти доменам
    #: (фаза 35) — и владелец домена должен видеть в истории не просто
    #: «изменил администратор», а «изменил администратор за домен
    #: «Экзамены»»: иначе откуда взялось значение, которое он не вносил,
    #: не понять. У правки владельца домена поле пустое
    acting_for = models.CharField("За домен", max_length=32, blank=True)
    old_value = models.TextField("Было", blank=True)
    new_value = models.TextField("Стало", blank=True)
    # 32 символа: «student_onboarding» в 16 не помещается
    source = models.CharField("Источник", max_length=32, choices=Source.CHOICES, default=Source.MANUAL)
    #: объект, к которому относится запись, удалён из базы. Запись остаётся:
    #: журнал не должен ссылаться в пустоту, но и вести на несуществующую
    #: карточку интерфейс не должен
    object_deleted = models.BooleanField("Объект удалён", default=False)
    #: имя объекта на момент удаления. Без него запись про удалённого
    #: насовсем ученика читалась бы как «students.Student#57» — то есть
    #: никак: спросить, чьё это изменение, было бы уже не у кого
    object_title = models.CharField("Имя на момент удаления", max_length=250, blank=True)
    #: удалён безвозвратно, а не просто убран из интерфейса: возвращать
    #: нечего, и предлагать восстановление нельзя
    object_purged = models.BooleanField("Удалён безвозвратно", default=False)
    #: номер удаления, которым объект вычистили из архива. По нему журнал
    #: читается после того, как самой карточки уже нет
    archive_batch = models.UUIDField("Номер удаления", null=True, blank=True, db_index=True)
    suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        verbose_name="Предложение",
        related_name="audit_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: загрузка, в составе которой прошло изменение. По ней откатывается
    #: импорт целиком — тем же способом, что и предложение
    import_batch = models.ForeignKey(
        "core.ImportBatch",
        verbose_name="Загрузка",
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
            models.Index(fields=("import_batch", "-created_at")),
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


class ImportBatch(models.Model):
    """Одна загрузка файла: кто, когда, что и с каким результатом.

    Нужна, чтобы загрузку можно было отменить целиком. Механика та же,
    что у отката предложений: обратный набор изменений через журнал.
    """

    class Kind(models.TextChoices):
        STUDENTS = "students", "Данные учеников"
        REQUIREMENTS = "requirements", "Требования вузов"
        QUESTIONS = "questions", "Банк заданий"
        SCHOLARSHIPS = "scholarships", "Стипендии"

    class Status(models.TextChoices):
        APPLIED = "applied", "Применена"
        REVERTED = "reverted", "Отменена"
        PARTIAL = "partial", "Отменена частично"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто загрузил",
        related_name="import_batches",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Когда", auto_now_add=True)
    file_name = models.CharField("Файл", max_length=250, blank=True)
    kind = models.CharField("Что загружали", max_length=16, choices=Kind.choices, default=Kind.STUDENTS)
    domain_code = models.CharField("Домен", max_length=32, blank=True)
    rows_total = models.PositiveIntegerField("Строк в файле", default=0)
    rows_created = models.PositiveIntegerField("Создано записей", default=0)
    rows_updated = models.PositiveIntegerField("Обновлено записей", default=0)
    rows_failed = models.PositiveIntegerField("Строк с ошибкой", default=0)
    status = models.CharField("Состояние", max_length=16, choices=Status.choices, default=Status.APPLIED)
    reverted_at = models.DateTimeField("Отменена", null=True, blank=True)
    reverted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто отменил",
        related_name="reverted_batches",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    note = models.CharField("Примечание", max_length=500, blank=True)

    class Meta:
        verbose_name = "Загрузка файла"
        verbose_name_plural = "История загрузок"
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("-created_at",)), models.Index(fields=("domain_code", "-created_at"))]

    def __str__(self) -> str:
        return f"{self.file_name or self.get_kind_display()} · {self.created_at:%d.%m.%Y}"


class ArchiveEntry(models.Model):
    """Одно удаление: что убрали, кто, когда и сколько связанного ушло с ним.

    Из этих записей строится экран архива. Восстановление поднимает ровно
    то, что ушло в составе этого удаления — по `batch`.
    """

    batch = models.UUIDField("Номер удаления", default=uuid.uuid4, unique=True)
    model_label = models.CharField("Модель", max_length=100)
    object_id = models.CharField("Объект", max_length=64)
    #: имя на момент удаления: сама запись могла бы потом измениться
    title = models.CharField("Что удалено", max_length=250)
    kind_title = models.CharField("Вид записи", max_length=100, blank=True)
    summary = models.CharField("Что ушло вместе", max_length=500, blank=True)
    related_count = models.PositiveIntegerField("Связанных записей", default=0)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто удалил",
        related_name="archive_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Когда удалено", auto_now_add=True)
    restored_at = models.DateTimeField("Когда восстановлено", null=True, blank=True)
    #: запись вычищена из архива насовсем: сама она остаётся строкой
    #: истории — кто, когда и что снёс, — но возвращать уже нечего
    purged_at = models.DateTimeField("Когда удалено навсегда", null=True, blank=True)
    purged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто удалил навсегда",
        related_name="purged_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто восстановил",
        related_name="restored_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Запись архива"
        verbose_name_plural = "Архив"
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("-created_at",)), models.Index(fields=("model_label", "object_id"))]

    def __str__(self) -> str:
        return f"{self.kind_title or self.model_label}: {self.title}"

    @property
    def is_restored(self) -> bool:
        return self.restored_at is not None

    @property
    def is_purged(self) -> bool:
        return self.purged_at is not None


class Notification(models.Model):
    """Короткое сообщение конкретному человеку: «под вашим материалом вопрос».

    Хранится отдельно от `AuditLog`: тот ведёт доменные поля учеников,
    а это адресное уведомление, которое читают и закрывают.

    Текст собирает сервер целиком — фронт его только показывает
    и никаких имён полей в него не подставляет (фаза 17).
    """

    class Kind(models.TextChoices):
        MATERIAL_COMMENT = "material_comment", "Комментарий к материалу"
        MATERIAL_REVIEWED = "material_reviewed", "Материал проверен"
        MATERIAL_PENDING = "material_pending", "Материал ждёт проверки"
        MATERIAL_REPORT = "material_report", "Жалоба на материал"
        MATERIAL_REQUEST = "material_request", "Просят материал"
        #: напоминание о событии календаря: экзамен, дедлайн, срок задачи (фаза 39)
        EVENT_REMINDER = "event_reminder", "Напоминание о событии"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кому",
        related_name="notifications",
        on_delete=models.CASCADE,
    )
    kind = models.CharField("Вид", max_length=32, choices=Kind.choices)
    text = models.CharField("Текст", max_length=500)
    #: куда вести по нажатию — путь внутри интерфейса, а не внешняя ссылка
    link = models.CharField("Куда ведёт", max_length=200, blank=True)
    is_read = models.BooleanField("Прочитано", default=False)
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("recipient", "is_read", "-created_at"))]

    def __str__(self) -> str:
        return self.text
