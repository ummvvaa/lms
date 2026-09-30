"""Роадмап ученика: шаблоны задач, задачи и эссе.

Задачи бывают двух происхождений: из шаблона потока (их заводит директор)
и из дедлайна вуза, куда ученик подаётся. Во втором случае срок задачи
привязан к раунду, а не хранится копией: сдвиг дедлайна в справочнике
сдвигает задачи у всех (инвариант №4).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext, gettext_lazy

from core.archivable import Archivable
from students.models import Student
from universities.models import AdmissionRound


class TaskCategory(models.TextChoices):
    TEST = "test", gettext_lazy("Тест")
    ESSAY = "essay", gettext_lazy("Эссе")
    DOCUMENTS = "documents", gettext_lazy("Документы")
    UNIVERSITY = "university", gettext_lazy("Вузы")
    PORTFOLIO = "portfolio", gettext_lazy("Портфолио")
    FINANCE = "finance", gettext_lazy("Финансы")


class TaskPriority(models.TextChoices):
    HIGH = "high", gettext_lazy("Высокий")
    MEDIUM = "medium", gettext_lazy("Средний")
    LOW = "low", gettext_lazy("Низкий")


class TaskStatus(models.TextChoices):
    TODO = "todo", gettext_lazy("Сделать")
    IN_PROGRESS = "in_progress", gettext_lazy("В работе")
    REVIEW = "review", gettext_lazy("На проверке")
    DONE = "done", gettext_lazy("Готово")
    #: отменена тем, кто её поставил (фаза 61): задача перестала быть нужной.
    #: Не «готово» — XP за неё не начисляется (инвариант №12) — и не удаление:
    #: ученик уже мог её увидеть, и исчезнуть бесследно она не должна
    CANCELLED = "cancelled", gettext_lazy("Отменена")

    @classmethod
    def closed(cls) -> tuple[str, ...]:
        """Статусы, при которых задача больше не висит на ученике."""
        return (cls.DONE, cls.CANCELLED)


class TaskOrigin(models.TextChoices):
    """Откуда взялась задача — это видит и ученик, и куратор.

    Ученик задачи себе не заводит: их ставит человек или система. Показать,
    кто именно, обязательно — иначе задача от куратора читается как своя же
    заметка, и спросить по ней не с кого. Имени в этом признаке нет: имя
    куратора ученику не показывается (фаза 60), роль — показывается.
    """

    DEADLINE = "deadline", gettext_lazy("Из дедлайна вуза")
    PLAN = "plan", gettext_lazy("Из плана по вузу")
    SCHOLARSHIP = "scholarship", gettext_lazy("Из дедлайна стипендии")
    EXAM_GOAL = "exam_goal", gettext_lazy("Из цели по экзамену")
    TEMPLATE = "template", gettext_lazy("Из шаблона потока")
    CURATOR = "curator", gettext_lazy("От куратора")
    SCHOOL = "school", gettext_lazy("От школы")


class TaskTemplate(models.Model):
    """Шаблон задачи по потоку. Заводится директором."""

    title = models.CharField(gettext_lazy("Название"), max_length=250)
    category = models.CharField(gettext_lazy("Категория"), max_length=16, choices=TaskCategory.choices)
    priority = models.CharField(
        gettext_lazy("Приоритет"), max_length=8, choices=TaskPriority.choices, default=TaskPriority.MEDIUM
    )
    description = models.TextField(gettext_lazy("Описание"), blank=True)
    #: месяц учебного года (9 — сентябрь) и день — из них собирается срок
    due_month = models.PositiveSmallIntegerField(gettext_lazy("Месяц срока"), null=True, blank=True)
    due_day = models.PositiveSmallIntegerField(gettext_lazy("День срока"), null=True, blank=True)
    #: кому шаблон: пусто — всем группам. Школа ведёт только выпускников,
    #: поэтому «для класса» и «для выпуска» (голые числа, принимали −1)
    #: убраны: делить поток можно только по группам
    groups = models.ManyToManyField(
        "students.StudyGroup", verbose_name=gettext_lazy("Группы"), related_name="task_templates", blank=True
    )
    is_active = models.BooleanField(gettext_lazy("Активен"), default=True)
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Шаблон задачи")
        verbose_name_plural = gettext_lazy("Шаблоны задач")
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
        NONE = "none", gettext_lazy("Не запускалась")
        RUNNING = "running", gettext_lazy("Идёт")
        DONE = "done", gettext_lazy("Готова")
        FAILED = "failed", gettext_lazy("Не получилась")

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="application_plans", on_delete=models.CASCADE
    )
    #: PROTECT: программу с живым планом ученика справочник не удалит молча —
    #: отказ назовёт число ссылок, как и у списка подачи
    program = models.ForeignKey(
        "universities.Program", verbose_name=gettext_lazy("Программа"), related_name="plans", on_delete=models.PROTECT
    )
    admission_round = models.ForeignKey(
        "universities.AdmissionRound",
        verbose_name=gettext_lazy("Раунд подачи"),
        related_name="plans",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: генерация задач: статус для плашки прогресса, как у подбора (фаза 40)
    generation_status = models.CharField(
        gettext_lazy("Генерация"), max_length=12, choices=Generation.choices, default=Generation.NONE
    )
    generation_offline = models.BooleanField(gettext_lazy("Собрана правилами"), default=True)
    #: предложение с задачами, которое ждёт решения ученика (инвариант №3)
    pending_suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        verbose_name=gettext_lazy("Предложение задач"),
        related_name="plans",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("План поступления")
        verbose_name_plural = gettext_lazy("Планы поступления")
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
        return gettext("План: {student} → {program}").format(student=self.student, program=self.program)

    @property
    def deadline(self):
        """Дедлайн плана — из раунда, не копия (инвариант №4)."""
        return self.admission_round.deadline if self.admission_round_id else None


class Task(Archivable):
    """Задача ученика."""

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="tasks", on_delete=models.CASCADE
    )
    title = models.CharField(gettext_lazy("Название"), max_length=250)
    category = models.CharField(gettext_lazy("Категория"), max_length=16, choices=TaskCategory.choices)
    priority = models.CharField(
        gettext_lazy("Приоритет"), max_length=8, choices=TaskPriority.choices, default=TaskPriority.MEDIUM
    )
    description = models.TextField(gettext_lazy("Описание"), blank=True)
    status = models.CharField(
        gettext_lazy("Статус"), max_length=16, choices=TaskStatus.choices, default=TaskStatus.TODO
    )

    #: срок задачи; у задач из дедлайна вуза берётся из раунда
    due_date = models.DateField(gettext_lazy("Срок"), null=True, blank=True)
    admission_round = models.ForeignKey(
        AdmissionRound,
        verbose_name=gettext_lazy("Раунд вуза"),
        related_name="tasks",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Если заполнено — срок берётся из дедлайна раунда",
    )
    template = models.ForeignKey(
        TaskTemplate,
        verbose_name=gettext_lazy("Шаблон"),
        related_name="tasks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: задача плана по вузу (фаза 41): в архив уходит вместе с планом
    plan = models.ForeignKey(
        ApplicationPlan,
        verbose_name=gettext_lazy("План"),
        related_name="tasks",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    #: задача из дедлайна стипендии (фаза 44): срок живёт в самой стипендии,
    #: и её сдвиг двигает задачу у всех, кто её сохранил (инвариант №4)
    scholarship = models.ForeignKey(
        "universities.Scholarship",
        verbose_name=gettext_lazy("Стипендия"),
        related_name="tasks",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Если заполнено — срок берётся из дедлайна стипендии",
    )
    #: задача из цели по экзамену (фаза 39): срок берётся из самой цели,
    #: а не копируется — сдвинулась дата экзамена, сдвинулся срок (инвариант №4)
    exam_goal = models.ForeignKey(
        "students.ExamGoal",
        verbose_name=gettext_lazy("Цель по экзамену"),
        related_name="tasks",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Если заполнено — срок берётся из даты регистрации или экзамена",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Автор"),
        related_name="authored_tasks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: роль автора на момент постановки (фаза 61). Снимком, как в журнале:
    #: роль у человека сменится, а ученик должен и через год видеть, что
    #: задачу поставил куратор. Имя автора ученику не отдаётся
    author_role = models.CharField(gettext_lazy("Роль автора"), max_length=32, blank=True)
    #: след автора, если его учётную запись удалили навсегда (фаза 67)
    author_title = models.CharField(gettext_lazy("Автор на момент удаления"), max_length=250, blank=True)
    #: кто закрыл или отменил — ученик сам или куратор (фаза 61)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто закрыл"),
        related_name="closed_tasks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Создана"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлена"), auto_now=True)
    completed_at = models.DateTimeField(gettext_lazy("Завершена"), null=True, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Задача")
        verbose_name_plural = gettext_lazy("Задачи")
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
            # одна задача на сохранённую стипендию — напоминание идёт
            # каждый день, а вторая задача об одном и том же не нужна
            models.UniqueConstraint(
                fields=("student", "scholarship"),
                condition=models.Q(scholarship__isnull=False, archived_at__isnull=True),
                name="uniq_task_per_scholarship",
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
        а если её нет — дата экзамена. У задачи о стипендии — в самой
        стипендии (фаза 44).
        """
        if self.admission_round_id:
            return self.admission_round.deadline
        if self.exam_goal_id:
            return self.exam_goal.registration_date or self.exam_goal.exam_date
        if self.scholarship_id:
            return self.scholarship.deadline
        if self.due_date is None and self.plan_id and self.plan.admission_round_id:
            return self.plan.admission_round.deadline
        return self.due_date

    @property
    def origin(self) -> str:
        """Откуда задача взялась. Считается из связей, а не хранится отдельно.

        Порядок проверок важен: задача из дедлайна вуза остаётся задачей
        из дедлайна, даже если её завёл куратор руками, — срок у неё
        всё равно из раунда (инвариант №4).
        """
        if self.admission_round_id:
            return TaskOrigin.DEADLINE
        if self.plan_id:
            return TaskOrigin.PLAN
        if self.scholarship_id:
            return TaskOrigin.SCHOLARSHIP
        if self.exam_goal_id:
            return TaskOrigin.EXAM_GOAL
        if self.template_id:
            return TaskOrigin.TEMPLATE
        if self.author_role == "curator":
            return TaskOrigin.CURATOR
        return TaskOrigin.SCHOOL

    @property
    def origin_title(self) -> str:
        return TaskOrigin(self.origin).label

    @property
    def is_overdue(self) -> bool:
        """Срок прошёл, а задача открыта."""
        from django.utils import timezone

        due = self.effective_due_date
        return bool(due and self.status not in TaskStatus.closed() and due < timezone.localdate())


class TaskComment(models.Model):
    """Комментарий к задаче."""

    task = models.ForeignKey(
        Task, verbose_name=gettext_lazy("Задача"), related_name="comments", on_delete=models.CASCADE
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=gettext_lazy("Автор"), on_delete=models.SET_NULL, null=True, blank=True
    )
    text = models.TextField(gettext_lazy("Текст"))
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Комментарий к задаче")
        verbose_name_plural = gettext_lazy("Комментарии к задачам")
        ordering = ("created_at",)

    def __str__(self) -> str:
        return gettext("Комментарий к задаче {task}").format(task=self.task_id)


class EssayType(models.TextChoices):
    PERSONAL_STATEMENT = "personal_statement", "Personal Statement"
    SUPPLEMENTAL = "supplemental", gettext_lazy("Дополнительное эссе")
    MOTIVATION = "motivation", gettext_lazy("Мотивационное письмо")
    SCHOLARSHIP = "scholarship", gettext_lazy("Для стипендии")
    OTHER = "other", gettext_lazy("Другое")


#: Вид эссе по типу документа из справочника (фаза 49).
#:
#: Виды документов ведёт директор по поступлению в `EssayDocType`, и их
#: девять; старое поле `essay_type` осталось от фазы 4 и знает пять видов.
#: Пока фронт слал в него код типа документа, семь типов из девяти
#: отбивались четырёхсотой: «research_statement» не значится в списке.
#: Соответствие живёт здесь, в одном месте, а незнакомый тип получает
#: «Другое» — справочник пополняет школа, и выката это требовать не должно.
DOC_TYPE_TO_ESSAY_TYPE = {
    "personal_statement": EssayType.PERSONAL_STATEMENT,
    "motivation_letter": EssayType.MOTIVATION,
    "supplemental": EssayType.SUPPLEMENTAL,
    "scholarship": EssayType.SCHOLARSHIP,
}


class EssayStatus(models.TextChoices):
    DRAFT = "draft", gettext_lazy("Черновик")
    REVIEW = "review", gettext_lazy("На проверке")
    REVISION = "revision", gettext_lazy("Правки")
    DONE = "done", gettext_lazy("Готово")


class Essay(Archivable):
    """Эссе ученика.

    ИИ на этой фазе к эссе не подключается вообще: редактор без генерации.
    Ограничения на участие ИИ появятся в Фазе 5.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="essays", on_delete=models.CASCADE
    )
    program = models.ForeignKey(
        "universities.Program",
        verbose_name=gettext_lazy("Программа"),
        related_name="essays",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Пусто — общее эссе",
    )
    #: вид эссе; с фазы 49 не обязателен — выводится из типа документа
    essay_type = models.CharField(gettext_lazy("Тип"), max_length=24, choices=EssayType.choices, blank=True)
    #: тип-документ из справочника (фаза 43); из него берётся лимит слов
    doc_type = models.ForeignKey(
        "roadmap.EssayDocType",
        verbose_name=gettext_lazy("Тип документа"),
        related_name="essays",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: свой лимит слов; пусто — берётся из типа документа
    word_limit = models.PositiveSmallIntegerField(gettext_lazy("Лимит слов"), null=True, blank=True)
    title = models.CharField(gettext_lazy("Название"), max_length=250)
    status = models.CharField(
        gettext_lazy("Статус"), max_length=16, choices=EssayStatus.choices, default=EssayStatus.DRAFT
    )
    curator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Куратор"),
        related_name="curated_essays",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Создано"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Эссе")
        verbose_name_plural = gettext_lazy("Эссе")
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return f"{self.student} · {self.title}"

    def save(self, *args, **kwargs):
        # вид выводится из типа документа: тип ведёт справочник, а старое
        # поле осталось для отбора и для эссе, заведённых сотрудником
        if not self.essay_type:
            code = self.doc_type.code if self.doc_type_id else ""
            self.essay_type = DOC_TYPE_TO_ESSAY_TYPE.get(code, EssayType.OTHER)
        super().save(*args, **kwargs)

    @property
    def current_version(self):
        return self.versions.first()


class EssayVersion(models.Model):
    """Версия текста эссе — история правок строками (инвариант №5)."""

    essay = models.ForeignKey(
        Essay, verbose_name=gettext_lazy("Эссе"), related_name="versions", on_delete=models.CASCADE
    )
    number = models.PositiveSmallIntegerField(gettext_lazy("Номер версии"))
    text = models.TextField(gettext_lazy("Текст"), blank=True)
    word_count = models.PositiveSmallIntegerField(gettext_lazy("Слов"), default=0)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=gettext_lazy("Автор"), on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(gettext_lazy("Создана"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Версия эссе")
        verbose_name_plural = gettext_lazy("Версии эссе")
        ordering = ("-number",)
        constraints = [models.UniqueConstraint(fields=("essay", "number"), name="uniq_essay_version_number")]

    def __str__(self) -> str:
        return f"{self.essay_id} v{self.number}"

    def save(self, *args, **kwargs):
        self.word_count = len(self.text.split())
        super().save(*args, **kwargs)


class EssayComment(models.Model):
    """Комментарий куратора к эссе."""

    essay = models.ForeignKey(
        Essay, verbose_name=gettext_lazy("Эссе"), related_name="comments", on_delete=models.CASCADE
    )
    version = models.ForeignKey(
        EssayVersion,
        verbose_name=gettext_lazy("Версия"),
        related_name="comments",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=gettext_lazy("Автор"), on_delete=models.SET_NULL, null=True, blank=True
    )
    text = models.TextField(gettext_lazy("Текст"))
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Комментарий к эссе")
        verbose_name_plural = gettext_lazy("Комментарии к эссе")
        ordering = ("created_at",)

    def __str__(self) -> str:
        return gettext("Комментарий к эссе {essay}").format(essay=self.essay_id)


# --- Конструктор эссе: типы, гайды, проверка, примеры (фаза 43) ------------


class EssayDocType(models.Model):
    """Тип документа для эссе. Справочник, ведёт директор по поступлению.

    Personal Statement, Motivation Letter и прочее — с описанием и лимитом
    слов по умолчанию. Ученик выбирает тип плиткой при создании эссе.
    """

    code = models.SlugField(gettext_lazy("Код"), max_length=40, unique=True)
    name = models.CharField(gettext_lazy("Название"), max_length=120)
    description = models.CharField(gettext_lazy("Короткое описание"), max_length=250, blank=True)
    default_word_limit = models.PositiveSmallIntegerField(gettext_lazy("Лимит слов по умолчанию"), default=650)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=100)
    is_active = models.BooleanField(gettext_lazy("Показывать"), default=True)
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Тип документа эссе")
        verbose_name_plural = gettext_lazy("Типы документов эссе")
        ordering = ("order", "name")

    def __str__(self) -> str:
        return self.name


class EssayGuide(models.Model):
    """Обучающий гайд из четырёх шагов для типа документа (фаза 43).

    Списки (промпты, ошибки, советы) хранятся строками через перенос —
    фронт разбивает их сам. Ведёт директор по поступлению; в код не зашито.
    """

    doc_type = models.OneToOneField(
        EssayDocType, verbose_name=gettext_lazy("Тип документа"), related_name="guide", on_delete=models.CASCADE
    )
    what_is = models.TextField(gettext_lazy("Что это за документ"), blank=True)
    prompts = models.TextField(gettext_lazy("Какие бывают вопросы"), blank=True, help_text="По одному в строке")
    mistakes = models.TextField(gettext_lazy("Частые ошибки"), blank=True, help_text="По одной в строке")
    tips = models.TextField(gettext_lazy("Советы"), blank=True, help_text="По одному в строке")
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Гайд по эссе")
        verbose_name_plural = gettext_lazy("Гайды по эссе")

    def __str__(self) -> str:
        return gettext("Гайд: {document}").format(document=self.doc_type.name)


class EssayCheckQuestion(models.Model):
    """Вопрос быстрой проверки перед написанием (фаза 43).

    Три вопроса с вариантами: выбранный сразу подсвечивается верным или нет,
    с объяснением. Это закрепление, а не оценка — результат никуда не идёт.
    Варианты типизированными колонками (инвариант №6).
    """

    doc_type = models.ForeignKey(
        EssayDocType,
        verbose_name=gettext_lazy("Тип документа"),
        related_name="check_questions",
        on_delete=models.CASCADE,
    )
    text = models.CharField(gettext_lazy("Вопрос"), max_length=300)
    option_a = models.CharField(gettext_lazy("Вариант A"), max_length=250)
    option_b = models.CharField(gettext_lazy("Вариант B"), max_length=250)
    option_c = models.CharField(gettext_lazy("Вариант C"), max_length=250, blank=True)
    option_d = models.CharField(gettext_lazy("Вариант D"), max_length=250, blank=True)
    correct = models.CharField(gettext_lazy("Верный вариант"), max_length=1, default="A")
    explanation = models.CharField(gettext_lazy("Объяснение"), max_length=400, blank=True)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=1)

    class Meta:
        verbose_name = gettext_lazy("Вопрос проверки эссе")
        verbose_name_plural = gettext_lazy("Вопросы проверки эссе")
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
        verbose_name=gettext_lazy("Тип документа"),
        related_name="examples",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    title = models.CharField(gettext_lazy("Название"), max_length=200)
    source_url = models.URLField(gettext_lazy("Ссылка"), blank=True)
    body = models.TextField(gettext_lazy("Текст примера"), blank=True)
    note = models.CharField(gettext_lazy("Примечание"), max_length=250, blank=True)
    is_active = models.BooleanField(gettext_lazy("Показывать"), default=True)
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Пример эссе")
        verbose_name_plural = gettext_lazy("Примеры эссе")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title
