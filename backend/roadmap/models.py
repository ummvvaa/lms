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
        """Срок задачи. У задач из вуза дедлайн живёт в раунде (инвариант №4)."""
        if self.admission_round_id:
            return self.admission_round.deadline
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
    SUPPLEMENTAL = "supplemental", "Supplemental"
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
