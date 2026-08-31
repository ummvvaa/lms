"""Роадмап ученика: шаблоны задач, задачи и эссе.

Задачи бывают двух происхождений: из шаблона потока (их заводит директор)
и из дедлайна вуза, куда ученик подаётся. Во втором случае срок задачи
привязан к раунду, а не хранится копией: сдвиг дедлайна в справочнике
сдвигает задачи у всех (инвариант №4).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.archivable import Archivable
from students.models import Student
from universities.models import AdmissionRound


class TaskCategory(models.TextChoices):
    TEST = "test", "Тест"
    ESSAY = "essay", "Эссе"
    DOCUMENTS = "documents", "Документы"
    UNIVERSITY = "university", "Вузы"
    PORTFOLIO = "portfolio", "Портфолио"
    FINANCE = "finance", "Финансы"


class TaskPriority(models.TextChoices):
    HIGH = "high", "Высокий"
    MEDIUM = "medium", "Средний"
    LOW = "low", "Низкий"


class TaskStatus(models.TextChoices):
    TODO = "todo", "Сделать"
    IN_PROGRESS = "in_progress", "В работе"
    REVIEW = "review", "На проверке"
    DONE = "done", "Готово"


class TaskTemplate(models.Model):
    """Шаблон задачи по потоку. Заводится директором."""

    title = models.CharField("Название", max_length=250)
    category = models.CharField("Категория", max_length=16, choices=TaskCategory.choices)
    priority = models.CharField("Приоритет", max_length=8, choices=TaskPriority.choices, default=TaskPriority.MEDIUM)
    description = models.TextField("Описание", blank=True)
    #: месяц учебного года (9 — сентябрь) и день — из них собирается срок
    due_month = models.PositiveSmallIntegerField("Месяц срока", null=True, blank=True)
    due_day = models.PositiveSmallIntegerField("День срока", null=True, blank=True)
    graduation_year = models.PositiveSmallIntegerField("Для выпуска", null=True, blank=True)
    grade = models.PositiveSmallIntegerField("Для класса", null=True, blank=True)
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Шаблон задачи"
        verbose_name_plural = "Шаблоны задач"
        ordering = ("due_month", "due_day", "title")

    def __str__(self) -> str:
        return self.title


class ApplicationPlan(Archivable):
    """План поступления по конкретной программе (фаза 41).

    Дедлайн не копируется: он живёт в раунде подачи, и сдвиг в справочнике
    двигает и план, и все его задачи (инвариант №4). Общий роадмап остаётся:
    у школы есть шаги, не привязанные к вузу.
    """

    class Generation(models.TextChoices):
        NONE = "none", "Не запускалась"
        RUNNING = "running", "Идёт"
        DONE = "done", "Готова"
        FAILED = "failed", "Не получилась"

    student = models.ForeignKey(
        Student, verbose_name="Ученик", related_name="application_plans", on_delete=models.CASCADE
    )
    #: PROTECT: программу с живым планом ученика справочник не удалит молча —
    #: отказ назовёт число ссылок, как и у списка подачи
    program = models.ForeignKey(
        "universities.Program", verbose_name="Программа", related_name="plans", on_delete=models.PROTECT
    )
    admission_round = models.ForeignKey(
        "universities.AdmissionRound",
        verbose_name="Раунд подачи",
        related_name="plans",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: генерация задач: статус для плашки прогресса, как у подбора (фаза 40)
    generation_status = models.CharField(
        "Генерация", max_length=12, choices=Generation.choices, default=Generation.NONE
    )
    generation_offline = models.BooleanField("Собрана правилами", default=True)
    #: предложение с задачами, которое ждёт решения ученика (инвариант №3)
    pending_suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        verbose_name="Предложение задач",
        related_name="plans",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "План поступления"
        verbose_name_plural = "Планы поступления"
        ordering = ("-created_at",)
        constraints = [
            # один живой план на программу; архивный не мешает завести новый
            models.UniqueConstraint(
                fields=("student", "program"),
                condition=models.Q(archived_at__isnull=True),
                name="unique_active_plan_per_program",
            )
        ]

    def __str__(self) -> str:
        return f"План: {self.student} → {self.program}"

    @property
    def deadline(self):
        """Дедлайн плана — из раунда, не копия (инвариант №4)."""
        return self.admission_round.deadline if self.admission_round_id else None


class Task(Archivable):
    """Задача ученика."""

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="tasks", on_delete=models.CASCADE)
    title = models.CharField("Название", max_length=250)
    category = models.CharField("Категория", max_length=16, choices=TaskCategory.choices)
    priority = models.CharField("Приоритет", max_length=8, choices=TaskPriority.choices, default=TaskPriority.MEDIUM)
    description = models.TextField("Описание", blank=True)
    status = models.CharField("Статус", max_length=16, choices=TaskStatus.choices, default=TaskStatus.TODO)

    #: срок задачи; у задач из дедлайна вуза берётся из раунда
    due_date = models.DateField("Срок", null=True, blank=True)
    admission_round = models.ForeignKey(
        AdmissionRound,
        verbose_name="Раунд вуза",
        related_name="tasks",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Если заполнено — срок берётся из дедлайна раунда",
    )
    template = models.ForeignKey(
        TaskTemplate, verbose_name="Шаблон", related_name="tasks", on_delete=models.SET_NULL, null=True, blank=True
    )
    #: задача плана по вузу (фаза 41): в архив уходит вместе с планом
    plan = models.ForeignKey(
        ApplicationPlan,
        verbose_name="План",
        related_name="tasks",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    #: задача из цели по экзамену (фаза 39): срок берётся из самой цели,
    #: а не копируется — сдвинулась дата экзамена, сдвинулся срок (инвариант №4)
    exam_goal = models.ForeignKey(
        "students.ExamGoal",
        verbose_name="Цель по экзамену",
        related_name="tasks",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Если заполнено — срок берётся из даты регистрации или экзамена",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор",
        related_name="authored_tasks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)
    completed_at = models.DateTimeField("Завершена", null=True, blank=True)

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ("due_date", "-priority", "id")
        constraints = [
            # одна задача на ученика по одному раунду — генерация идемпотентна
            models.UniqueConstraint(
                fields=("student", "exam_goal"),
                condition=models.Q(exam_goal__isnull=False, archived_at__isnull=True),
                name="unique_task_per_exam_goal",
            ),
            models.UniqueConstraint(
                fields=("student", "admission_round"),
                condition=models.Q(admission_round__isnull=False),
                name="uniq_task_per_student_round",
            ),
            models.UniqueConstraint(
                fields=("student", "template"),
                condition=models.Q(template__isnull=False),
                name="uniq_task_per_student_template",
            ),
        ]
        indexes = [
            models.Index(fields=("student", "status")),
            models.Index(fields=("due_date",)),
        ]

    def __str__(self) -> str:
        return f"{self.student} · {self.title}"

    @property
    def effective_due_date(self):
        """Срок задачи. У задач из вуза дедлайн живёт в раунде (инвариант №4).

        У задачи о регистрации на экзамен — в самой цели: дата регистрации,
        а если её нет — дата экзамена.
        """
        if self.admission_round_id:
            return self.admission_round.deadline
        if self.exam_goal_id:
            return self.exam_goal.registration_date or self.exam_goal.exam_date
        if self.due_date is None and self.plan_id and self.plan.admission_round_id:
            return self.plan.admission_round.deadline
        return self.due_date


class TaskComment(models.Model):
    """Комментарий к задаче."""

    task = models.ForeignKey(Task, verbose_name="Задача", related_name="comments", on_delete=models.CASCADE)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Автор", on_delete=models.SET_NULL, null=True, blank=True
    )
    text = models.TextField("Текст")
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Комментарий к задаче"
        verbose_name_plural = "Комментарии к задачам"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"Комментарий к {self.task_id}"


class EssayType(models.TextChoices):
    PERSONAL_STATEMENT = "personal_statement", "Personal Statement"
    SUPPLEMENTAL = "supplemental", "Дополнительное эссе"
    MOTIVATION = "motivation", "Мотивационное письмо"
    SCHOLARSHIP = "scholarship", "Для стипендии"


class EssayStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    REVIEW = "review", "На проверке"
    REVISION = "revision", "Правки"
    DONE = "done", "Готово"


class Essay(Archivable):
    """Эссе ученика.

    ИИ на этой фазе к эссе не подключается вообще: редактор без генерации.
    Ограничения на участие ИИ появятся в Фазе 5.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="essays", on_delete=models.CASCADE)
    program = models.ForeignKey(
        "universities.Program",
        verbose_name="Программа",
        related_name="essays",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Пусто — общее эссе",
    )
    essay_type = models.CharField("Тип", max_length=24, choices=EssayType.choices)
    #: тип-документ из справочника (фаза 43); из него берётся лимит слов
    doc_type = models.ForeignKey(
        "roadmap.EssayDocType",
        verbose_name="Тип документа",
        related_name="essays",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: свой лимит слов; пусто — берётся из типа документа
    word_limit = models.PositiveSmallIntegerField("Лимит слов", null=True, blank=True)
    title = models.CharField("Название", max_length=250)
    status = models.CharField("Статус", max_length=16, choices=EssayStatus.choices, default=EssayStatus.DRAFT)
    curator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Куратор",
        related_name="curated_essays",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Эссе"
        verbose_name_plural = "Эссе"
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return f"{self.student} · {self.title}"

    @property
    def current_version(self):
        return self.versions.first()


class EssayVersion(models.Model):
    """Версия текста эссе — история правок строками (инвариант №5)."""

    essay = models.ForeignKey(Essay, verbose_name="Эссе", related_name="versions", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField("Номер версии")
    text = models.TextField("Текст", blank=True)
    word_count = models.PositiveSmallIntegerField("Слов", default=0)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Автор", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Версия эссе"
        verbose_name_plural = "Версии эссе"
        ordering = ("-number",)
        constraints = [models.UniqueConstraint(fields=("essay", "number"), name="uniq_essay_version_number")]

    def __str__(self) -> str:
        return f"{self.essay_id} v{self.number}"

    def save(self, *args, **kwargs):
        self.word_count = len(self.text.split())
        super().save(*args, **kwargs)


class EssayComment(models.Model):
    """Комментарий куратора к эссе."""

    essay = models.ForeignKey(Essay, verbose_name="Эссе", related_name="comments", on_delete=models.CASCADE)
    version = models.ForeignKey(
        EssayVersion, verbose_name="Версия", related_name="comments", on_delete=models.CASCADE, null=True, blank=True
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Автор", on_delete=models.SET_NULL, null=True, blank=True
    )
    text = models.TextField("Текст")
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Комментарий к эссе"
        verbose_name_plural = "Комментарии к эссе"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"Комментарий к эссе {self.essay_id}"


# --- Конструктор эссе: типы, гайды, проверка, примеры (фаза 43) ------------


class EssayDocType(models.Model):
    """Тип документа для эссе. Справочник, ведёт директор по поступлению.

    Personal Statement, Motivation Letter и прочее — с описанием и лимитом
    слов по умолчанию. Ученик выбирает тип плиткой при создании эссе.
    """

    code = models.SlugField("Код", max_length=40, unique=True)
    name = models.CharField("Название", max_length=120)
    description = models.CharField("Короткое описание", max_length=250, blank=True)
    default_word_limit = models.PositiveSmallIntegerField("Лимит слов по умолчанию", default=650)
    order = models.PositiveSmallIntegerField("Порядок", default=100)
    is_active = models.BooleanField("Показывать", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Тип документа эссе"
        verbose_name_plural = "Типы документов эссе"
        ordering = ("order", "name")

    def __str__(self) -> str:
        return self.name


class EssayGuide(models.Model):
    """Обучающий гайд из четырёх шагов для типа документа (фаза 43).

    Списки (промпты, ошибки, советы) хранятся строками через перенос —
    фронт разбивает их сам. Ведёт директор по поступлению; в код не зашито.
    """

    doc_type = models.OneToOneField(
        EssayDocType, verbose_name="Тип документа", related_name="guide", on_delete=models.CASCADE
    )
    what_is = models.TextField("Что это за документ", blank=True)
    prompts = models.TextField("Какие бывают вопросы", blank=True, help_text="По одному в строке")
    mistakes = models.TextField("Частые ошибки", blank=True, help_text="По одной в строке")
    tips = models.TextField("Советы", blank=True, help_text="По одному в строке")
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Гайд по эссе"
        verbose_name_plural = "Гайды по эссе"

    def __str__(self) -> str:
        return f"Гайд: {self.doc_type.name}"


class EssayCheckQuestion(models.Model):
    """Вопрос быстрой проверки перед написанием (фаза 43).

    Три вопроса с вариантами: выбранный сразу подсвечивается верным или нет,
    с объяснением. Это закрепление, а не оценка — результат никуда не идёт.
    Варианты типизированными колонками (инвариант №6).
    """

    doc_type = models.ForeignKey(
        EssayDocType, verbose_name="Тип документа", related_name="check_questions", on_delete=models.CASCADE
    )
    text = models.CharField("Вопрос", max_length=300)
    option_a = models.CharField("Вариант A", max_length=250)
    option_b = models.CharField("Вариант B", max_length=250)
    option_c = models.CharField("Вариант C", max_length=250, blank=True)
    option_d = models.CharField("Вариант D", max_length=250, blank=True)
    correct = models.CharField("Верный вариант", max_length=1, default="A")
    explanation = models.CharField("Объяснение", max_length=400, blank=True)
    order = models.PositiveSmallIntegerField("Порядок", default=1)

    class Meta:
        verbose_name = "Вопрос проверки эссе"
        verbose_name_plural = "Вопросы проверки эссе"
        ordering = ("doc_type", "order", "id")

    def __str__(self) -> str:
        return f"{self.doc_type_id} · {self.text[:40]}"


class EssayExample(models.Model):
    """Пример документа для «чтения дня» (фаза 43).

    Архив примеров ведёт директор по поступлению; строка сверху раздела
    меняется ежедневно и ведёт к примеру.
    """

    doc_type = models.ForeignKey(
        EssayDocType,
        verbose_name="Тип документа",
        related_name="examples",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    title = models.CharField("Название", max_length=200)
    source_url = models.URLField("Ссылка", blank=True)
    body = models.TextField("Текст примера", blank=True)
    note = models.CharField("Примечание", max_length=250, blank=True)
    is_active = models.BooleanField("Показывать", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Пример эссе"
        verbose_name_plural = "Примеры эссе"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title
