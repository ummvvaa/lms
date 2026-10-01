"""Журнал изменений доменных полей (инвариант №9), архив и история загрузок."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.domains import Source


class AuditLog(models.Model):
    """Одна запись: кто, когда, какое поле какого объекта и откуда изменил.

    Значения хранятся строками — универсально для любых типов колонок
    и читаемо во вкладке истории на карточке ученика.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто изменил"),
        related_name="audit_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: подпись автора на случай, если самой записи больше нет: учётные
    #: записи людей не удаляются никогда, а одноразовые записи прогона —
    #: всегда, и строка журнала после этого не должна читаться как «система»
    actor_title = models.CharField(gettext_lazy("Автор на момент удаления"), max_length=250, blank=True)
    #: роль автора на момент действия (фаза 60). Роль у записи может смениться —
    #: куратор станет директором, — а журнал должен читаться как было:
    #: «подтвердил куратор», а не «подтвердил директор»
    actor_role = models.CharField(gettext_lazy("Роль автора на момент действия"), max_length=32, blank=True)
    #: группа ученика на момент действия (фаза 60): смена куратора и перевод
    #: ученика в другую группу историю не переписывают
    student_group = models.CharField(gettext_lazy("Группа ученика на момент действия"), max_length=16, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True)
    model_label = models.CharField(gettext_lazy("Модель"), max_length=100)
    object_id = models.CharField(gettext_lazy("Объект"), max_length=64)
    student_id = models.BigIntegerField(gettext_lazy("Ученик"), null=True, blank=True, db_index=True)
    field_name = models.CharField(gettext_lazy("Поле"), max_length=100)
    domain_code = models.CharField(gettext_lazy("Домен"), max_length=32, blank=True)
    #: домен, за который действовал автор, когда это не его домен.
    #: Администратор грузит файлы и вставляет текст по всем пяти доменам
    #: (фаза 35) — и владелец домена должен видеть в истории не просто
    #: «изменил администратор», а «изменил администратор за домен
    #: «Экзамены»»: иначе откуда взялось значение, которое он не вносил,
    #: не понять. У правки владельца домена поле пустое
    acting_for = models.CharField(gettext_lazy("За домен"), max_length=32, blank=True)
    old_value = models.TextField(gettext_lazy("Было"), blank=True)
    new_value = models.TextField(gettext_lazy("Стало"), blank=True)
    # 32 символа: «student_onboarding» в 16 не помещается
    source = models.CharField(gettext_lazy("Источник"), max_length=32, choices=Source.CHOICES, default=Source.MANUAL)
    #: объект, к которому относится запись, удалён из базы. Запись остаётся:
    #: журнал не должен ссылаться в пустоту, но и вести на несуществующую
    #: карточку интерфейс не должен
    object_deleted = models.BooleanField(gettext_lazy("Объект удалён"), default=False)
    #: имя объекта на момент удаления. Без него запись про удалённого
    #: насовсем ученика читалась бы как «students.Student#57» — то есть
    #: никак: спросить, чьё это изменение, было бы уже не у кого
    object_title = models.CharField(gettext_lazy("Имя на момент удаления"), max_length=250, blank=True)
    #: удалён безвозвратно, а не просто убран из интерфейса: возвращать
    #: нечего, и предлагать восстановление нельзя
    object_purged = models.BooleanField(gettext_lazy("Удалён безвозвратно"), default=False)
    #: номер удаления, которым объект вычистили из архива. По нему журнал
    #: читается после того, как самой карточки уже нет
    archive_batch = models.UUIDField(gettext_lazy("Номер удаления"), null=True, blank=True, db_index=True)
    suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        verbose_name=gettext_lazy("Предложение"),
        related_name="audit_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: загрузка, в составе которой прошло изменение. По ней откатывается
    #: импорт целиком — тем же способом, что и предложение
    import_batch = models.ForeignKey(
        "core.ImportBatch",
        verbose_name=gettext_lazy("Загрузка"),
        related_name="audit_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Запись аудита")
        verbose_name_plural = gettext_lazy("Журнал изменений")
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
        "students.Student",
        verbose_name=gettext_lazy("Ученик"),
        related_name="readiness_snapshots",
        on_delete=models.CASCADE,
    )
    date = models.DateField(gettext_lazy("Дата среза"))
    score = models.PositiveSmallIntegerField(gettext_lazy("Готовность, %"))
    exam = models.DecimalField(gettext_lazy("Экзамены"), max_digits=5, decimal_places=1, null=True, blank=True)
    admission = models.DecimalField(gettext_lazy("Поступление"), max_digits=5, decimal_places=1, null=True, blank=True)
    talent = models.DecimalField(gettext_lazy("Портфолио"), max_digits=5, decimal_places=1, null=True, blank=True)
    behavior = models.DecimalField(gettext_lazy("Дисциплина"), max_digits=5, decimal_places=1, null=True, blank=True)
    sport = models.DecimalField(gettext_lazy("Спорт"), max_digits=5, decimal_places=1, null=True, blank=True)
    weakest = models.CharField(gettext_lazy("Слабое звено"), max_length=32, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Срез готовности")
        verbose_name_plural = gettext_lazy("Срезы готовности")
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
        STUDENTS = "students", gettext_lazy("Данные учеников")
        REQUIREMENTS = "requirements", gettext_lazy("Требования вузов")
        QUESTIONS = "questions", gettext_lazy("Банк заданий")
        SCHOLARSHIPS = "scholarships", gettext_lazy("Стипендии")

    class Status(models.TextChoices):
        APPLIED = "applied", gettext_lazy("Применена")
        REVERTED = "reverted", gettext_lazy("Отменена")
        PARTIAL = "partial", gettext_lazy("Отменена частично")

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто загрузил"),
        related_name="import_batches",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: след загрузившего, если его запись удалили навсегда (`core.purge`)
    actor_title = models.CharField(gettext_lazy("Кто загрузил, на момент удаления"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True)
    file_name = models.CharField(gettext_lazy("Файл"), max_length=250, blank=True)
    kind = models.CharField(gettext_lazy("Что загружали"), max_length=16, choices=Kind.choices, default=Kind.STUDENTS)
    domain_code = models.CharField(gettext_lazy("Домен"), max_length=32, blank=True)
    rows_total = models.PositiveIntegerField(gettext_lazy("Строк в файле"), default=0)
    rows_created = models.PositiveIntegerField(gettext_lazy("Создано записей"), default=0)
    rows_updated = models.PositiveIntegerField(gettext_lazy("Обновлено записей"), default=0)
    rows_failed = models.PositiveIntegerField(gettext_lazy("Строк с ошибкой"), default=0)
    status = models.CharField(gettext_lazy("Состояние"), max_length=16, choices=Status.choices, default=Status.APPLIED)
    reverted_at = models.DateTimeField(gettext_lazy("Отменена"), null=True, blank=True)
    reverted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто отменил"),
        related_name="reverted_batches",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    note = models.CharField(gettext_lazy("Примечание"), max_length=500, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Загрузка файла")
        verbose_name_plural = gettext_lazy("История загрузок")
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("-created_at",)), models.Index(fields=("domain_code", "-created_at"))]

    def __str__(self) -> str:
        return f"{self.file_name or self.get_kind_display()} · {self.created_at:%d.%m.%Y}"


class ArchiveEntry(models.Model):
    """Одно удаление: что убрали, кто, когда и сколько связанного ушло с ним.

    Из этих записей строится экран архива. Восстановление поднимает ровно
    то, что ушло в составе этого удаления — по `batch`.
    """

    batch = models.UUIDField(gettext_lazy("Номер удаления"), default=uuid.uuid4, unique=True)
    model_label = models.CharField(gettext_lazy("Модель"), max_length=100)
    object_id = models.CharField(gettext_lazy("Объект"), max_length=64)
    #: имя на момент удаления: сама запись могла бы потом измениться
    title = models.CharField(gettext_lazy("Что удалено"), max_length=250)
    kind_title = models.CharField(gettext_lazy("Вид записи"), max_length=100, blank=True)
    summary = models.CharField(gettext_lazy("Что ушло вместе"), max_length=500, blank=True)
    related_count = models.PositiveIntegerField(gettext_lazy("Связанных записей"), default=0)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто удалил"),
        related_name="archive_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: след удалившего, если его запись удалили навсегда (`core.purge`)
    actor_title = models.CharField(gettext_lazy("Кто удалил, на момент удаления"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Когда удалено"), auto_now_add=True)
    restored_at = models.DateTimeField(gettext_lazy("Когда восстановлено"), null=True, blank=True)
    #: запись вычищена из архива насовсем: сама она остаётся строкой
    #: истории — кто, когда и что снёс, — но возвращать уже нечего
    purged_at = models.DateTimeField(gettext_lazy("Когда удалено навсегда"), null=True, blank=True)
    purged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто удалил навсегда"),
        related_name="purged_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто восстановил"),
        related_name="restored_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Запись архива")
        verbose_name_plural = gettext_lazy("Архив")
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
        MATERIAL_COMMENT = "material_comment", gettext_lazy("Комментарий к материалу")
        MATERIAL_REVIEWED = "material_reviewed", gettext_lazy("Материал проверен")
        MATERIAL_PENDING = "material_pending", gettext_lazy("Материал ждёт проверки")
        MATERIAL_REPORT = "material_report", gettext_lazy("Жалоба на материал")
        MATERIAL_REQUEST = "material_request", gettext_lazy("Просят материал")
        #: напоминание о событии календаря: экзамен, дедлайн, срок задачи (фаза 39)
        EVENT_REMINDER = "event_reminder", gettext_lazy("Напоминание о событии")
        #: фоновая операция закончилась — приходит и тогда, когда человек
        #: ушёл с экрана, на котором её запустил (фаза 47)
        JOB_DONE = "job_done", gettext_lazy("Фоновая операция закончилась")
        JOB_FAILED = "job_failed", gettext_lazy("Фоновая операция не получилась")
        # кабинет куратора (фаза 62)
        QUEUE_DECIDED = "queue_decided", gettext_lazy("Строку из вашей очереди решил владелец домена")
        DOCUMENT_REUPLOADED = "document_reuploaded", gettext_lazy("Ученик перезагрузил документ")
        DOCUMENT_EXPIRING = "document_expiring", gettext_lazy("Срок документа истекает")
        ESCALATION_ANSWERED = "escalation_answered", gettext_lazy("Владелец домена ответил на переданное")
        ESCALATION_REQUEST = "escalation_request", gettext_lazy("Куратор передал вопрос")
        # дисциплина у куратора (фаза 66): директор школы оставила заметку
        NOTE_FOR_CURATOR = "note_for_curator", gettext_lazy("Директор школы оставила заметку")
        # учебная часть: урок изменён, не отмечен, просьба о переносе, отчёты собраны
        LESSON_CHANGED = "lesson_changed", gettext_lazy("Изменение в расписании")
        LESSON_UNMARKED = "lesson_unmarked", gettext_lazy("Урок не отмечен")
        LESSON_REQUEST = "lesson_request", gettext_lazy("Просьба учителя о переносе")
        LESSON_REQUEST_DECIDED = "lesson_request_decided", gettext_lazy("Ответ на просьбу о переносе")
        REPORTS_BUILT = "reports_built", gettext_lazy("Отчёты родителям собраны")

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кому"),
        related_name="notifications",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(gettext_lazy("Вид"), max_length=32, choices=Kind.choices)
    text = models.CharField(gettext_lazy("Текст"), max_length=500)
    #: куда вести по нажатию — путь внутри интерфейса, а не внешняя ссылка
    link = models.CharField(gettext_lazy("Куда ведёт"), max_length=200, blank=True)
    is_read = models.BooleanField(gettext_lazy("Прочитано"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Уведомление")
        verbose_name_plural = gettext_lazy("Уведомления")
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("recipient", "is_read", "-created_at"))]

    def __str__(self) -> str:
        return self.text


class BackgroundJob(models.Model):
    """Долгая операция, которая идёт в фоне (фаза 47).

    До этой фазы у каждой долгой операции была своя плашка — у подбора
    своя, у генерации плана своя, у разбора файла не было никакой:
    человек нажимал и не знал, идёт ли что-нибудь. Здесь они сведены
    в один список: название, процент, ссылка на результат.

    Повтор после сбоя хранится не JSON-колонкой, а именем задачи Celery
    и её аргументами текстом (инвариант №6 про JSONB — про доменные
    данные, но заводить первую JSON-колонку в проекте ради механики
    незачем).
    """

    class Status(models.TextChoices):
        RUNNING = "running", gettext_lazy("Идёт")
        DONE = "done", gettext_lazy("Готово")
        FAILED = "failed", gettext_lazy("Не получилось")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто запустил"),
        related_name="jobs",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(gettext_lazy("Вид операции"), max_length=40)
    title = models.CharField(gettext_lazy("Название"), max_length=200)
    status = models.CharField(gettext_lazy("Состояние"), max_length=8, choices=Status.choices, default=Status.RUNNING)
    stage = models.CharField(gettext_lazy("Этап"), max_length=120, blank=True)
    percent = models.PositiveSmallIntegerField(gettext_lazy("Процент"), default=0)
    steps_done = models.PositiveSmallIntegerField(gettext_lazy("Пройдено этапов"), default=0)
    #: id задачи Celery — по нему её находят сигналы завершения
    task_id = models.CharField(gettext_lazy("Задача"), max_length=64, blank=True, db_index=True)
    #: куда вести по нажатию, путь внутри интерфейса
    link = models.CharField(gettext_lazy("Куда ведёт"), max_length=200, blank=True)
    error = models.CharField(gettext_lazy("Что пошло не так"), max_length=300, blank=True)
    #: чем повторить: имя задачи Celery и её аргументы строкой JSON
    retry_task = models.CharField(gettext_lazy("Задача для повтора"), max_length=80, blank=True)
    retry_payload = models.TextField(gettext_lazy("Аргументы повтора"), blank=True)
    #: плашку закрыли крестиком — операция при этом продолжается
    dismissed = models.BooleanField(gettext_lazy("Плашка скрыта"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Запущена"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлена"), auto_now=True)
    finished_at = models.DateTimeField(gettext_lazy("Закончена"), null=True, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Фоновая операция")
        verbose_name_plural = gettext_lazy("Фоновые операции")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("owner", "-created_at")), models.Index(fields=("status",))]

    def __str__(self) -> str:
        return f"{self.title} · {self.get_status_display()}"


class KeyCheck(models.Model):
    """Контрольная запись ключа паролей учеников (фаза 65).

    Одна строка: известная фраза, зашифрованная `CREDENTIALS_KEY`. По ней
    `preflight` отличает «ключ есть» от «ключ тот самый»: другой ключ
    расшифровать её не сможет, и станет ясно, что сохранённые пароли
    учеников этим ключом не открыть. Создаётся `credentials_key --init`.
    """

    ciphertext = models.TextField(gettext_lazy("Шифртекст"))
    created_at = models.DateTimeField(gettext_lazy("Создана"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Контрольная запись ключа")
        verbose_name_plural = gettext_lazy("Контрольные записи ключа")

    def __str__(self) -> str:
        return _("Контрольная запись от {date}").format(date=f"{self.created_at:%d.%m.%Y}")


class SchoolRule(models.Model):
    """Значение настраиваемого правила школы: порог, окно, срок, лимит.

    Сами правила — подпись, единица, значение по умолчанию и границы —
    описаны в реестре `core.school_rules`, здесь только то, что поменял
    администратор. Строки нет — действует значение по умолчанию; «Сбросить»
    удаляет строку. Правила — целые числа: проценты, дни, оценки.
    """

    code = models.CharField(gettext_lazy("Правило"), max_length=64, unique=True)
    value = models.IntegerField(gettext_lazy("Значение"))
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто поменял"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_at = models.DateTimeField(gettext_lazy("Когда поменяли"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Правило школы")
        verbose_name_plural = gettext_lazy("Правила школы")

    def __str__(self) -> str:
        return f"{self.code} = {self.value}"
