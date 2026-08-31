"""Онбординг ученика и геймификация.

Два сюжета в одном приложении, потому что оба про самого ученика и про то,
как он возвращается в систему: сначала он рассказывает о себе, потом
видит, что его действия к чему-то ведут.

Инвариант №12: XP даётся за действия, а не за результаты. За балл IELTS
или GPA начисления нет и быть не может — иначе система начнёт поощрять
приписки.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from students.models import Student


class OnboardingStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "Заполняется"
    COMPLETED = "completed", "Пройден"
    SKIPPED = "skipped", "Отложен"


class OnboardingSession(models.Model):
    """Прохождение квиза. Прогресс хранится по шагам, а не только в конце.

    Ученик может выйти на третьем вопросе и вернуться через неделю —
    отвечать заново он не должен.
    """

    student = models.OneToOneField(Student, verbose_name="Ученик", related_name="onboarding", on_delete=models.CASCADE)
    status = models.CharField(
        "Состояние", max_length=16, choices=OnboardingStatus.choices, default=OnboardingStatus.IN_PROGRESS
    )
    started_at = models.DateTimeField("Начат", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)
    completed_at = models.DateTimeField("Завершён", null=True, blank=True)

    class Meta:
        verbose_name = "Онбординг"
        verbose_name_plural = "Онбординг"

    def __str__(self) -> str:
        return f"{self.student} · {self.get_status_display()}"

    @property
    def answered_codes(self) -> set[str]:
        return set(self.answers.values_list("question", flat=True))


class OnboardingAnswer(models.Model):
    """Один ответ ученика.

    Хранится отдельно от профиля, даже когда значение уже проставлено:
    директор должен видеть, что это слова ученика, а не проверенный факт.
    """

    session = models.ForeignKey(
        OnboardingSession, verbose_name="Онбординг", related_name="answers", on_delete=models.CASCADE
    )
    question = models.CharField("Вопрос", max_length=32)
    #: строкой — вопросы разного типа, а типизированная колонка живёт в профиле
    value = models.CharField("Ответ", max_length=250, blank=True)
    #: куда легло значение: `students.ExamProfile.ielts_current`
    target = models.CharField("Целевое поле", max_length=120, blank=True)
    domain_code = models.CharField("Домен", max_length=16, blank=True)
    is_confirmed = models.BooleanField("Подтверждено директором", default=False)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто подтвердил",
        related_name="confirmed_onboarding_answers",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    confirmed_at = models.DateTimeField("Когда подтверждено", null=True, blank=True)
    created_at = models.DateTimeField("Отвечено", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Ответ онбординга"
        verbose_name_plural = "Ответы онбординга"
        ordering = ("session", "id")
        constraints = [
            models.UniqueConstraint(fields=("session", "question"), name="uniq_answer_per_question"),
        ]
        indexes = [models.Index(fields=("domain_code", "is_confirmed"))]

    def __str__(self) -> str:
        return f"{self.session.student} · {self.question} = {self.value}"


class XPKind(models.TextChoices):
    """За что начисляется XP. Только действия — инвариант №12.

    Ни одного пункта про баллы экзаменов, GPA или статусы здесь нет
    и появиться не может: это проверяется тестом.
    """

    TASK_DONE = "task_done", "Задача роадмапа выполнена"
    EXERCISE_SOLVED = "exercise_solved", "Упражнение решено"
    MOCK_TAKEN = "mock_taken", "Пробный экзамен пройден"
    PROFILE_SECTION = "profile_section", "Раздел профиля заполнен"
    ESSAY_SUBMITTED = "essay_submitted", "Эссе отправлено на проверку"
    ONBOARDING_DONE = "onboarding_done", "Онбординг пройден"
    #: за то, что поделился разбором и он прошёл проверку, — это действие.
    #: Не за то, скольким он понравился: это уже оценка другими (фаза 19)
    MATERIAL_APPROVED = "material_approved", "Материал прошёл проверку"


class XPEvent(models.Model):
    """Одно начисление. История начислений — тоже строки, а не поле."""

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="xp_events", on_delete=models.CASCADE)
    kind = models.CharField("За что", max_length=32, choices=XPKind.choices)
    amount = models.PositiveSmallIntegerField("Сколько")
    #: на что ссылается начисление — задача, эссе, попытка
    object_label = models.CharField("Объект", max_length=64, blank=True)
    object_id = models.CharField("Идентификатор объекта", max_length=32, blank=True)
    note = models.CharField("Пояснение", max_length=250, blank=True)
    created_at = models.DateTimeField("Когда", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Начисление XP"
        verbose_name_plural = "Начисления XP"
        ordering = ("-created_at",)
        constraints = [
            # одно начисление за один объект: пере-открыл задачу и закрыл снова —
            # это не второй повод дать XP
            models.UniqueConstraint(
                fields=("student", "kind", "object_label", "object_id"),
                condition=~models.Q(object_id=""),
                name="uniq_xp_per_object",
            ),
        ]
        indexes = [models.Index(fields=("student", "-created_at"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.get_kind_display()} +{self.amount}"


class StudentGameState(models.Model):
    """Накопленное состояние: сумма, уровень, стрик.

    Считается по событиям, но хранится отдельно — дашборд не должен
    пересчитывать всю историю на каждый заход.
    """

    student = models.OneToOneField(Student, verbose_name="Ученик", related_name="game_state", on_delete=models.CASCADE)
    xp = models.PositiveIntegerField("Всего XP", default=0)
    level = models.PositiveSmallIntegerField("Уровень", default=1)
    streak_days = models.PositiveSmallIntegerField("Стрик, дней", default=0)
    best_streak = models.PositiveSmallIntegerField("Лучший стрик", default=0)
    last_active_on = models.DateField("Последняя активность", null=True, blank=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Состояние ученика"
        verbose_name_plural = "Состояния учеников"

    def __str__(self) -> str:
        return f"{self.student} · {self.xp} XP, уровень {self.level}"

    @property
    def is_active_today(self) -> bool:
        return self.last_active_on == timezone.localdate()


# --- Профтест: анкета и разбор (фаза 45) -----------------------------------


class CareerQuestionKind(models.TextChoices):
    TEXT = "text", "Свободный ответ"
    CHOICE = "choice", "Выбор из вариантов"


class CareerQuestion(models.Model):
    """Вопрос анкеты профтеста. Справочник, ведёт директор школы.

    В код вопросы не зашиваются: школа меняет формулировки и добавляет свои,
    и новая анкета не должна означать выкат.
    """

    code = models.SlugField("Код", max_length=40, unique=True)
    text = models.CharField("Вопрос", max_length=300)
    hint = models.CharField("Подсказка", max_length=250, blank=True)
    kind = models.CharField(
        "Вид ответа", max_length=12, choices=CareerQuestionKind.choices, default=CareerQuestionKind.TEXT
    )
    #: варианты для выбора — по одному в строке, как списки гайда эссе
    options = models.TextField("Варианты ответа", blank=True, help_text="По одному в строке")
    order = models.PositiveSmallIntegerField("Порядок", default=100)
    is_active = models.BooleanField("Показывать", default=True)

    class Meta:
        verbose_name = "Вопрос профтеста"
        verbose_name_plural = "Вопросы профтеста"
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.text

    @property
    def options_list(self) -> list[str]:
        return [line.strip() for line in self.options.splitlines() if line.strip()]


class CareerRunStatus(models.TextChoices):
    DONE = "done", "Разбор готов"
    FAILED = "failed", "Не получился"


class CareerRun(models.Model):
    """Один проход профтеста: ответы плюс разбор.

    История проходов остаётся: через полгода ученик отвечает иначе,
    и сравнить два разбора полезнее, чем перезаписать один.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="career_runs", on_delete=models.CASCADE)
    status = models.CharField("Состояние", max_length=12, choices=CareerRunStatus.choices, default=CareerRunStatus.DONE)
    summary = models.TextField("Общий вывод", blank=True)
    error = models.CharField("Что пошло не так", max_length=250, blank=True)
    created_at = models.DateTimeField("Пройден", auto_now_add=True)

    class Meta:
        verbose_name = "Проход профтеста"
        verbose_name_plural = "Проходы профтеста"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("student", "-created_at"))]

    def __str__(self) -> str:
        return f"Профтест #{self.pk} · {self.student}"


class CareerAnswer(models.Model):
    """Ответ на один вопрос анкеты — строкой, а не полем прохода."""

    run = models.ForeignKey(CareerRun, verbose_name="Проход", related_name="answers", on_delete=models.CASCADE)
    question = models.ForeignKey(
        CareerQuestion, verbose_name="Вопрос", related_name="answers", on_delete=models.PROTECT
    )
    value = models.TextField("Ответ", blank=True)

    class Meta:
        verbose_name = "Ответ профтеста"
        verbose_name_plural = "Ответы профтеста"
        ordering = ("question__order", "id")
        constraints = [models.UniqueConstraint(fields=("run", "question"), name="uniq_career_answer")]

    def __str__(self) -> str:
        return f"{self.run_id} · {self.question_id}"


class CareerDirection(models.Model):
    """Одно направление из разбора.

    Программы — связью со справочником, а не названиями текстом: инвариант
    №10 держится кодом, и «выдуманная программа» здесь физически не хранится.
    """

    run = models.ForeignKey(CareerRun, verbose_name="Проход", related_name="directions", on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField("Порядок", default=1)
    title = models.CharField("Направление", max_length=150)
    reasoning = models.TextField("Почему подходит", blank=True)
    subjects = models.CharField("Какие предметы нужны", max_length=300, blank=True)
    exams = models.CharField("Какие экзамены нужны", max_length=300, blank=True)
    programs = models.ManyToManyField(
        "universities.Program", verbose_name="Программы справочника", related_name="career_directions", blank=True
    )
    #: ученик согласился — направление ушло предложением директору
    agreed_at = models.DateTimeField("Когда согласился", null=True, blank=True)
    suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        verbose_name="Предложение",
        related_name="career_directions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Направление профтеста"
        verbose_name_plural = "Направления профтеста"
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.title
