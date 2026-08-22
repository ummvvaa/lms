"""Центр подготовки: банк заданий, тренировки и пробные экзамены.

Инвариант №5: всё, что имеет историю, живёт строками. Ответы на вопросы —
дочерние записи сессии, варианты ответа — дочерние записи вопроса.
Инвариант №6: никакого JSONB — варианты и ответы это типизированные колонки.

Инвариант №12: XP даётся за прохождение, а не за результат. Начисление
живёт в `engagement.scoring` и зависит только от факта завершения.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from students.models import ExamType, Student


class Section(models.TextChoices):
    """Секции экзаменов. Общий список: у IELTS и SAT они разные, но
    смешивать их в одной модели проще, чем плодить таблицы."""

    LISTENING = "listening", "Listening"
    READING = "reading", "Reading"
    WRITING = "writing", "Writing"
    SPEAKING = "speaking", "Speaking"
    MATH = "math", "Math"
    VERBAL = "verbal", "Verbal"
    ENGLISH = "english", "English"
    SCIENCE = "science", "Science"


class Difficulty(models.TextChoices):
    EASY = "easy", "Простое"
    MEDIUM = "medium", "Среднее"
    HARD = "hard", "Сложное"


class Question(models.Model):
    """Задание банка. Заводит директор экзаменов — руками или импортом."""

    exam_type = models.CharField("Экзамен", max_length=8, choices=ExamType.choices)
    section = models.CharField("Секция", max_length=16, choices=Section.choices)
    topic = models.CharField("Тема", max_length=120, db_index=True)
    difficulty = models.CharField("Сложность", max_length=8, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    text = models.TextField("Текст задания")
    explanation = models.TextField("Объяснение", blank=True, help_text="Показывается в разборе после ответа")
    source = models.CharField("Источник", max_length=250, blank=True)
    is_active = models.BooleanField("Активно", default=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Задание"
        verbose_name_plural = "Банк заданий"
        ordering = ("exam_type", "section", "topic", "id")
        indexes = [
            models.Index(fields=("exam_type", "section", "difficulty")),
            models.Index(fields=("topic",)),
        ]

    def __str__(self) -> str:
        return f"{self.exam_type} · {self.get_section_display()} · {self.topic}"

    @property
    def correct_option(self):
        return self.options.filter(is_correct=True).first()


class QuestionOption(models.Model):
    """Вариант ответа. Строкой, а не полем JSON (инвариант №6)."""

    question = models.ForeignKey(Question, verbose_name="Задание", related_name="options", on_delete=models.CASCADE)
    letter = models.CharField("Метка", max_length=2)
    text = models.CharField("Текст варианта", max_length=500)
    is_correct = models.BooleanField("Верный", default=False)

    class Meta:
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответа"
        ordering = ("question", "letter")
        constraints = [
            models.UniqueConstraint(fields=("question", "letter"), name="uniq_option_letter"),
        ]

    def __str__(self) -> str:
        return f"{self.letter}. {self.text[:40]}"


class SessionStatus(models.TextChoices):
    RUNNING = "running", "Идёт"
    FINISHED = "finished", "Завершена"
    ABANDONED = "abandoned", "Брошена"


class PracticeSession(models.Model):
    """Тренировка: набор вопросов по секции и сложности."""

    student = models.ForeignKey(
        Student, verbose_name="Ученик", related_name="practice_sessions", on_delete=models.CASCADE
    )
    exam_type = models.CharField("Экзамен", max_length=8, choices=ExamType.choices)
    section = models.CharField("Секция", max_length=16, choices=Section.choices, blank=True)
    difficulty = models.CharField("Сложность", max_length=8, choices=Difficulty.choices, blank=True)
    status = models.CharField("Состояние", max_length=16, choices=SessionStatus.choices, default=SessionStatus.RUNNING)
    started_at = models.DateTimeField("Начата", auto_now_add=True)
    finished_at = models.DateTimeField("Завершена", null=True, blank=True)
    seconds_spent = models.PositiveIntegerField("Секунд потрачено", default=0)

    class Meta:
        verbose_name = "Тренировка"
        verbose_name_plural = "Тренировки"
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("student", "-started_at"))]

    def __str__(self) -> str:
        return f"{self.student} · тренировка {self.exam_type} {self.section}"

    @property
    def total(self) -> int:
        return self.answers.count()

    @property
    def correct(self) -> int:
        return self.answers.filter(is_correct=True).count()

    @property
    def percent(self) -> int:
        total = self.total
        return round(self.correct / total * 100) if total else 0


class PracticeAnswer(models.Model):
    """Один ответ ученика внутри тренировки или мока."""

    session = models.ForeignKey(
        PracticeSession, verbose_name="Тренировка", related_name="answers", on_delete=models.CASCADE
    )
    question = models.ForeignKey(Question, verbose_name="Задание", related_name="answers", on_delete=models.PROTECT)
    chosen = models.ForeignKey(
        QuestionOption,
        verbose_name="Выбранный вариант",
        related_name="answers",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    is_correct = models.BooleanField("Верно", default=False)
    seconds = models.PositiveIntegerField("Секунд на ответ", default=0)
    answered_at = models.DateTimeField("Отвечено", auto_now_add=True)

    class Meta:
        verbose_name = "Ответ"
        verbose_name_plural = "Ответы"
        ordering = ("session", "id")
        constraints = [
            models.UniqueConstraint(fields=("session", "question"), name="uniq_answer_per_question_in_session"),
        ]

    def __str__(self) -> str:
        return f"{self.session_id} · {self.question_id} · {'верно' if self.is_correct else 'неверно'}"


class MockExam(models.Model):
    """Пробный экзамен: набор секций с ограничением по времени."""

    title = models.CharField("Название", max_length=200)
    exam_type = models.CharField("Экзамен", max_length=8, choices=ExamType.choices)
    time_limit_minutes = models.PositiveSmallIntegerField("Ограничение, минут", default=60)
    description = models.TextField("Описание", blank=True)
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Пробный экзамен"
        verbose_name_plural = "Пробные экзамены"
        ordering = ("exam_type", "title")

    def __str__(self) -> str:
        return f"{self.title} ({self.exam_type})"


class MockSection(models.Model):
    """Секция внутри мока: сколько заданий и в каком порядке."""

    mock = models.ForeignKey(MockExam, verbose_name="Мок", related_name="sections", on_delete=models.CASCADE)
    section = models.CharField("Секция", max_length=16, choices=Section.choices)
    question_count = models.PositiveSmallIntegerField("Сколько заданий", default=10)
    order = models.PositiveSmallIntegerField("Порядок", default=1)

    class Meta:
        verbose_name = "Секция мока"
        verbose_name_plural = "Секции мока"
        ordering = ("mock", "order")
        constraints = [
            models.UniqueConstraint(fields=("mock", "section"), name="uniq_section_per_mock"),
        ]

    def __str__(self) -> str:
        return f"{self.mock.title} · {self.get_section_display()}"


class MockRun(models.Model):
    """Прохождение мока учеником.

    Результат создаёт `ExamAttempt` с форматом `mock` и источником
    `platform` — чтобы его можно было отличить и от официальной сдачи,
    и от внесённого руками.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="mock_runs", on_delete=models.CASCADE)
    mock = models.ForeignKey(MockExam, verbose_name="Мок", related_name="runs", on_delete=models.PROTECT)
    session = models.OneToOneField(
        PracticeSession, verbose_name="Сессия ответов", related_name="mock_run", on_delete=models.CASCADE
    )
    exam_attempt = models.OneToOneField(
        "students.ExamAttempt",
        verbose_name="Попытка экзамена",
        related_name="mock_run",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: директор экзаменов решает, учитывать ли результат в текущем балле
    counted_in_profile = models.BooleanField("Учтён в текущем балле", default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто решил",
        related_name="reviewed_mock_runs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField("Когда решено", null=True, blank=True)
    created_at = models.DateTimeField("Начат", auto_now_add=True)

    class Meta:
        verbose_name = "Прохождение мока"
        verbose_name_plural = "Прохождения моков"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("student", "-created_at"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.mock.title}"
