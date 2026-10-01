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
from django.utils.translation import gettext, gettext_lazy

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
    EASY = "easy", gettext_lazy("Простое")
    MEDIUM = "medium", gettext_lazy("Среднее")
    HARD = "hard", gettext_lazy("Сложное")


class QuestionType(models.TextChoices):
    """Тип вопроса — от него зависит, как показывать и как проверять (фаза 42)."""

    SINGLE = "single", gettext_lazy("Один верный вариант")
    MULTIPLE = "multiple", gettext_lazy("Несколько верных")
    SHORT = "short", gettext_lazy("Короткий ответ")
    WRITING = "writing", gettext_lazy("Письменное задание")
    SPEAKING = "speaking", gettext_lazy("Устное задание")


def _prep_storage():
    """Аудио и картинки банка лежат вне корня веб-сервера — как документы."""
    from materials.storage import private_storage

    return private_storage()


def _passage_media_to(instance: QuestionPassage, filename: str) -> str:
    return f"prep/passages/{instance.pk or 'new'}/{filename}"


class PassageKind(models.TextChoices):
    READING = "reading", gettext_lazy("Текст для чтения")
    LISTENING = "listening", gettext_lazy("Аудио для аудирования")


class QuestionPassage(models.Model):
    """Источник для группы вопросов: текст чтения или аудио аудирования.

    Один текст (или один аудиофайл) относится к нескольким вопросам —
    это выражено связью, а не копией: вопросы ссылаются сюда (фаза 42).
    Для аудирования хранится файл, расшифровка и отрезок времени; файл
    отдаётся только после проверки прав, как материалы и документы.
    """

    exam_type = models.CharField(gettext_lazy("Экзамен"), max_length=12, choices=ExamType.choices)
    section = models.CharField(gettext_lazy("Секция"), max_length=16, choices=Section.choices)
    kind = models.CharField(gettext_lazy("Вид источника"), max_length=12, choices=PassageKind.choices)
    title = models.CharField(gettext_lazy("Заголовок"), max_length=200, blank=True)
    #: текст для чтения или расшифровка аудио
    body = models.TextField(gettext_lazy("Текст или расшифровка"), blank=True)
    #: аудиофайл для аудирования; у чтения пусто
    audio = models.FileField(
        gettext_lazy("Аудиофайл"), upload_to=_passage_media_to, storage=_prep_storage, max_length=300, blank=True
    )
    audio_content_type = models.CharField(gettext_lazy("Тип аудио"), max_length=64, blank=True)
    #: отрезок аудио, к которому относятся вопросы, в секундах
    audio_start = models.PositiveIntegerField(gettext_lazy("Начало отрезка, с"), null=True, blank=True)
    audio_end = models.PositiveIntegerField(gettext_lazy("Конец отрезка, с"), null=True, blank=True)
    source = models.CharField(gettext_lazy("Источник"), max_length=250, blank=True)
    is_active = models.BooleanField(gettext_lazy("Активно"), default=True)
    created_at = models.DateTimeField(gettext_lazy("Создано"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Источник для вопросов")
        verbose_name_plural = gettext_lazy("Источники для вопросов")
        ordering = ("exam_type", "section", "id")

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.title or self.pk}"


class Question(models.Model):
    """Задание банка. Заводит директор экзаменов — руками или импортом."""

    exam_type = models.CharField(gettext_lazy("Экзамен"), max_length=12, choices=ExamType.choices)
    section = models.CharField(gettext_lazy("Секция"), max_length=16, choices=Section.choices)
    topic = models.CharField(gettext_lazy("Тема"), max_length=120, db_index=True)
    #: подтема — уточнение внутри темы, для прогресса и фильтров (фаза 42)
    subtopic = models.CharField(gettext_lazy("Подтема"), max_length=120, blank=True)
    difficulty = models.CharField(
        gettext_lazy("Сложность"), max_length=8, choices=Difficulty.choices, default=Difficulty.MEDIUM
    )
    question_type = models.CharField(
        gettext_lazy("Тип вопроса"), max_length=12, choices=QuestionType.choices, default=QuestionType.SINGLE
    )
    text = models.TextField(gettext_lazy("Текст задания"))
    #: изображение к вопросу — вне корня веб-сервера, как аудио (фаза 42)
    image = models.FileField(
        gettext_lazy("Изображение"), upload_to="prep/questions/", storage=_prep_storage, max_length=300, blank=True
    )
    image_content_type = models.CharField(gettext_lazy("Тип изображения"), max_length=64, blank=True)
    #: источник-группа: текст чтения или аудио аудирования (фаза 42)
    passage = models.ForeignKey(
        QuestionPassage,
        verbose_name=gettext_lazy("Источник"),
        related_name="questions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    explanation = models.TextField(
        gettext_lazy("Объяснение"), blank=True, help_text="Показывается в разборе после ответа"
    )
    #: для письменных секций: критерии оценивания и образец ответа (фаза 42)
    criteria = models.TextField(gettext_lazy("Критерии оценивания"), blank=True)
    sample_answer = models.TextField(gettext_lazy("Образец ответа"), blank=True)
    #: предел открытого ответа: слова — у письменного задания, минуты — у устного.
    #: Это условие задания, которое видит ученик, а не тайминг пробника
    word_limit = models.PositiveIntegerField(gettext_lazy("Лимит слов"), null=True, blank=True)
    minute_limit = models.PositiveSmallIntegerField(gettext_lazy("Лимит минут"), null=True, blank=True)
    #: ожидаемое время на решение — для прогноза и тайминга пробника
    expected_seconds = models.PositiveIntegerField(gettext_lazy("Время на решение, с"), null=True, blank=True)
    source = models.CharField(gettext_lazy("Источник"), max_length=250, blank=True)
    source_year = models.PositiveSmallIntegerField(gettext_lazy("Год источника"), null=True, blank=True)
    is_active = models.BooleanField(gettext_lazy("Активно"), default=True)
    created_at = models.DateTimeField(gettext_lazy("Создано"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Задание")
        verbose_name_plural = gettext_lazy("Банк заданий")
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

    @property
    def is_open(self) -> bool:
        """Открытый ответ: вариантов нет, проверяет человек."""
        return self.question_type in OPEN_TYPES


#: Типы заданий с открытым ответом: Writing и Speaking. Вариантов у них не
#: бывает, верность машина не считает — ответ ученика читает Кымбат
OPEN_TYPES = (QuestionType.WRITING, QuestionType.SPEAKING)

#: Секции, в которых задание бывает только открытым
OPEN_SECTIONS = (Section.WRITING, Section.SPEAKING)


class QuestionOption(models.Model):
    """Вариант ответа. Строкой, а не полем JSON (инвариант №6)."""

    question = models.ForeignKey(
        Question, verbose_name=gettext_lazy("Задание"), related_name="options", on_delete=models.CASCADE
    )
    letter = models.CharField(gettext_lazy("Метка"), max_length=2)
    text = models.CharField(gettext_lazy("Текст варианта"), max_length=500)
    is_correct = models.BooleanField(gettext_lazy("Верный"), default=False)

    class Meta:
        verbose_name = gettext_lazy("Вариант ответа")
        verbose_name_plural = gettext_lazy("Варианты ответа")
        ordering = ("question", "letter")
        constraints = [
            models.UniqueConstraint(fields=("question", "letter"), name="uniq_option_letter"),
        ]

    def __str__(self) -> str:
        return f"{self.letter}. {self.text[:40]}"


class SessionStatus(models.TextChoices):
    RUNNING = "running", gettext_lazy("Идёт")
    FINISHED = "finished", gettext_lazy("Завершена")
    ABANDONED = "abandoned", gettext_lazy("Брошена")


class PracticeSession(models.Model):
    """Тренировка: набор вопросов по секции и сложности."""

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="practice_sessions", on_delete=models.CASCADE
    )
    exam_type = models.CharField(gettext_lazy("Экзамен"), max_length=8, choices=ExamType.choices)
    section = models.CharField(gettext_lazy("Секция"), max_length=16, choices=Section.choices, blank=True)
    difficulty = models.CharField(gettext_lazy("Сложность"), max_length=8, choices=Difficulty.choices, blank=True)
    status = models.CharField(
        gettext_lazy("Состояние"), max_length=16, choices=SessionStatus.choices, default=SessionStatus.RUNNING
    )
    started_at = models.DateTimeField(gettext_lazy("Начата"), auto_now_add=True)
    finished_at = models.DateTimeField(gettext_lazy("Завершена"), null=True, blank=True)
    seconds_spent = models.PositiveIntegerField(gettext_lazy("Секунд потрачено"), default=0)

    class Meta:
        verbose_name = gettext_lazy("Тренировка")
        verbose_name_plural = gettext_lazy("Тренировки")
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("student", "-started_at"))]

    def __str__(self) -> str:
        return gettext("{student} · тренировка {exam} {section}").format(
            student=self.student, exam=self.exam_type, section=self.section
        )

    @property
    def total(self) -> int:
        return self.answers.count()

    @property
    def checked_by_machine(self) -> int:
        """Сколько заданий сессии проверяет машина — процент считается по ним."""
        return self.answers.exclude(question__question_type__in=OPEN_TYPES).count()

    @property
    def correct(self) -> int:
        return self.answers.filter(is_correct=True).count()

    @property
    def percent(self) -> int:
        # открытые ответы ждут человека: в процент верных они не входят,
        # иначе эссе считалось бы ошибкой до проверки
        total = self.checked_by_machine
        return round(self.correct / total * 100) if total else 0


class PracticeAnswer(models.Model):
    """Один ответ ученика внутри тренировки или мока."""

    session = models.ForeignKey(
        PracticeSession, verbose_name=gettext_lazy("Тренировка"), related_name="answers", on_delete=models.CASCADE
    )
    question = models.ForeignKey(
        Question, verbose_name=gettext_lazy("Задание"), related_name="answers", on_delete=models.PROTECT
    )
    chosen = models.ForeignKey(
        QuestionOption,
        verbose_name=gettext_lazy("Выбранный вариант"),
        related_name="answers",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    is_correct = models.BooleanField(gettext_lazy("Верно"), default=False)
    #: открытый ответ — текст эссе или тезисы устного ответа. Запись голоса
    #: не берём: это микрофон, хранение и право слушать — отдельная работа
    text = models.TextField(gettext_lazy("Открытый ответ"), blank=True)
    #: проверка открытого ответа: оценка и слова проверяющего. Оценка —
    #: по шкале экзамена, её ставит человек; в балл тренировки она не входит
    review_score = models.DecimalField(
        gettext_lazy("Оценка проверяющего"), max_digits=4, decimal_places=1, null=True, blank=True
    )
    review_comment = models.TextField(gettext_lazy("Комментарий проверяющего"), blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Проверил"),
        related_name="reviewed_open_answers",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(gettext_lazy("Проверено"), null=True, blank=True)
    seconds = models.PositiveIntegerField(gettext_lazy("Секунд на ответ"), default=0)
    answered_at = models.DateTimeField(gettext_lazy("Отвечено"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Ответ")
        verbose_name_plural = gettext_lazy("Ответы")
        ordering = ("session", "id")
        constraints = [
            models.UniqueConstraint(fields=("session", "question"), name="uniq_answer_per_question_in_session"),
        ]

    def __str__(self) -> str:
        verdict = gettext("верно") if self.is_correct else gettext("неверно")
        return f"{self.session_id} · {self.question_id} · {verdict}"


class MockExam(models.Model):
    """Пробный экзамен: набор секций с ограничением по времени."""

    title = models.CharField(gettext_lazy("Название"), max_length=200)
    exam_type = models.CharField(gettext_lazy("Экзамен"), max_length=8, choices=ExamType.choices)
    time_limit_minutes = models.PositiveSmallIntegerField(gettext_lazy("Ограничение, минут"), default=60)
    description = models.TextField(gettext_lazy("Описание"), blank=True)
    is_active = models.BooleanField(gettext_lazy("Активен"), default=True)
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Mock Test онлайн")
        verbose_name_plural = gettext_lazy("Mock Test онлайн")
        ordering = ("exam_type", "title")

    def __str__(self) -> str:
        return f"{self.title} ({self.exam_type})"


class MockSection(models.Model):
    """Секция внутри мока: сколько заданий и в каком порядке."""

    mock = models.ForeignKey(
        MockExam, verbose_name=gettext_lazy("Mock Test"), related_name="sections", on_delete=models.CASCADE
    )
    section = models.CharField(gettext_lazy("Секция"), max_length=16, choices=Section.choices)
    question_count = models.PositiveSmallIntegerField(gettext_lazy("Сколько заданий"), default=10)
    #: ограничение времени на секцию; 0 — берётся общее ограничение теста (фаза 42)
    section_time_minutes = models.PositiveSmallIntegerField(gettext_lazy("Время на секцию, минут"), default=0)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=1)

    class Meta:
        verbose_name = gettext_lazy("Секция Mock Test")
        verbose_name_plural = gettext_lazy("Секции Mock Test")
        ordering = ("mock", "order")
        constraints = [
            models.UniqueConstraint(fields=("mock", "section"), name="uniq_section_per_mock"),
        ]

    def __str__(self) -> str:
        return f"{self.mock.title} · {self.get_section_display()}"


class MockReview(models.TextChoices):
    """Решение академического директора по Mock Test онлайн — подпись приходит с сервера.

    Подписи собирал фронт по двум полям, и «не засчитан» ученик не видел:
    ему отдавали только «засчитан или нет», и после отказа он так и читал
    «ждёт сверки». Слова ученику и директору — свои только у ожидания.
    """

    COUNTED = "counted", gettext_lazy("засчитан")
    REJECTED = "rejected", gettext_lazy("не засчитан")
    WAITING = "waiting", gettext_lazy("ждёт сверки")


#: директору то же ожидание называется по-своему: решение за ним
WAITING_FOR_DIRECTOR = gettext_lazy("ждёт решения")


class MockRun(models.Model):
    """Прохождение мока учеником.

    Результат создаёт `ExamAttempt` с форматом `mock` и источником
    `platform` — чтобы его можно было отличить и от официальной сдачи,
    и от внесённого руками.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="mock_runs", on_delete=models.CASCADE
    )
    mock = models.ForeignKey(
        MockExam, verbose_name=gettext_lazy("Mock Test"), related_name="runs", on_delete=models.PROTECT
    )
    session = models.OneToOneField(
        PracticeSession, verbose_name=gettext_lazy("Сессия ответов"), related_name="mock_run", on_delete=models.CASCADE
    )
    exam_attempt = models.OneToOneField(
        "students.ExamAttempt",
        verbose_name=gettext_lazy("Попытка экзамена"),
        related_name="mock_run",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: директор экзаменов решает, учитывать ли результат в текущем балле
    counted_in_profile = models.BooleanField(gettext_lazy("Учтён в текущем балле"), default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто решил"),
        related_name="reviewed_mock_runs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(gettext_lazy("Когда решено"), null=True, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Начат"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Прохождение Mock Test")
        verbose_name_plural = gettext_lazy("Прохождения Mock Test")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("student", "-created_at"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.mock.title}"

    @property
    def review_state(self) -> str:
        """`counted`, `rejected` или `waiting`: решение директора, а не два поля."""
        if self.counted_in_profile:
            return MockReview.COUNTED
        return MockReview.REJECTED if self.reviewed_at else MockReview.WAITING

    def review_title(self, *, for_director: bool = False) -> str:
        if for_director and self.review_state == MockReview.WAITING:
            return str(WAITING_FOR_DIRECTOR)
        return str(MockReview(self.review_state).label)


class TheoryLevel(models.TextChoices):
    BASIC = "basic", gettext_lazy("Базовый")
    MEDIUM = "medium", gettext_lazy("Средний")
    ADVANCED = "advanced", gettext_lazy("Продвинутый")


class TheoryLesson(models.Model):
    """Короткий урок теории внутри экзамена (фаза 42).

    Ведёт академический директор: заводит, правит, удаляет. Группируется
    по секциям, у каждого урока уровень и время чтения. Файл (конспект,
    PDF) — вне корня веб-сервера, отдаётся после проверки прав.
    """

    exam_type = models.CharField(gettext_lazy("Экзамен"), max_length=12, choices=ExamType.choices)
    section = models.CharField(gettext_lazy("Секция"), max_length=16, choices=Section.choices, blank=True)
    title = models.CharField(gettext_lazy("Название"), max_length=200)
    level = models.CharField(
        gettext_lazy("Уровень"), max_length=12, choices=TheoryLevel.choices, default=TheoryLevel.BASIC
    )
    reading_minutes = models.PositiveSmallIntegerField(gettext_lazy("Время чтения, минут"), default=5)
    body = models.TextField(gettext_lazy("Текст урока"), blank=True)
    file = models.FileField(
        gettext_lazy("Файл"), upload_to="prep/theory/", storage=_prep_storage, max_length=300, blank=True
    )
    file_content_type = models.CharField(gettext_lazy("Тип файла"), max_length=64, blank=True)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=100)
    is_active = models.BooleanField(gettext_lazy("Показывать"), default=True)
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Урок теории")
        verbose_name_plural = gettext_lazy("Теория")
        ordering = ("exam_type", "section", "order", "id")
        indexes = [models.Index(fields=("exam_type", "section"))]

    def __str__(self) -> str:
        return f"{self.exam_type} · {self.title}"
