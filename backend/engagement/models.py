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
from django.utils.translation import gettext, gettext_lazy

from students.models import Student


class OnboardingStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", gettext_lazy("Заполняется")
    COMPLETED = "completed", gettext_lazy("Пройден")
    SKIPPED = "skipped", gettext_lazy("Отложен")


class OnboardingSession(models.Model):
    """Прохождение квиза. Прогресс хранится по шагам, а не только в конце.

    Ученик может выйти на третьем вопросе и вернуться через неделю —
    отвечать заново он не должен.
    """

    student = models.OneToOneField(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="onboarding", on_delete=models.CASCADE
    )
    status = models.CharField(
        gettext_lazy("Состояние"), max_length=16, choices=OnboardingStatus.choices, default=OnboardingStatus.IN_PROGRESS
    )
    started_at = models.DateTimeField(gettext_lazy("Начат"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлён"), auto_now=True)
    completed_at = models.DateTimeField(gettext_lazy("Завершён"), null=True, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Онбординг")
        verbose_name_plural = gettext_lazy("Онбординг")

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
        OnboardingSession, verbose_name=gettext_lazy("Онбординг"), related_name="answers", on_delete=models.CASCADE
    )
    question = models.CharField(gettext_lazy("Вопрос"), max_length=32)
    #: строкой — вопросы разного типа, а типизированная колонка живёт в профиле
    value = models.CharField(gettext_lazy("Ответ"), max_length=250, blank=True)
    #: куда легло значение: `students.ExamProfile.ielts_current`
    target = models.CharField(gettext_lazy("Целевое поле"), max_length=120, blank=True)
    domain_code = models.CharField(gettext_lazy("Домен"), max_length=16, blank=True)
    is_confirmed = models.BooleanField(gettext_lazy("Подтверждено директором"), default=False)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто подтвердил"),
        related_name="confirmed_onboarding_answers",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    confirmed_at = models.DateTimeField(gettext_lazy("Когда подтверждено"), null=True, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Отвечено"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Ответ онбординга")
        verbose_name_plural = gettext_lazy("Ответы онбординга")
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

    TASK_DONE = "task_done", gettext_lazy("Задача роадмапа выполнена")
    EXERCISE_SOLVED = "exercise_solved", gettext_lazy("Упражнение решено")
    MOCK_TAKEN = "mock_taken", gettext_lazy("Mock Test онлайн пройден")
    PROFILE_SECTION = "profile_section", gettext_lazy("Раздел профиля заполнен")
    ESSAY_SUBMITTED = "essay_submitted", gettext_lazy("Эссе отправлено на проверку")
    ONBOARDING_DONE = "onboarding_done", gettext_lazy("Онбординг пройден")
    #: сдача ДЗ в срок — действие; за оценку учителя XP нет (инвариант №12)
    HOMEWORK_ON_TIME = "homework_on_time", gettext_lazy("ДЗ сдано в срок")
    #: за то, что поделился разбором и он прошёл проверку, — это действие.
    #: Не за то, скольким он понравился: это уже оценка другими (фаза 19)
    MATERIAL_APPROVED = "material_approved", gettext_lazy("Материал прошёл проверку")


class XPEvent(models.Model):
    """Одно начисление. История начислений — тоже строки, а не поле."""

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="xp_events", on_delete=models.CASCADE
    )
    kind = models.CharField(gettext_lazy("За что"), max_length=32, choices=XPKind.choices)
    amount = models.PositiveSmallIntegerField(gettext_lazy("Сколько"))
    #: на что ссылается начисление — задача, эссе, попытка
    object_label = models.CharField(gettext_lazy("Объект"), max_length=64, blank=True)
    object_id = models.CharField(gettext_lazy("Идентификатор объекта"), max_length=32, blank=True)
    note = models.CharField(gettext_lazy("Пояснение"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = gettext_lazy("Начисление XP")
        verbose_name_plural = gettext_lazy("Начисления XP")
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

    student = models.OneToOneField(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="game_state", on_delete=models.CASCADE
    )
    xp = models.PositiveIntegerField(gettext_lazy("Всего XP"), default=0)
    level = models.PositiveSmallIntegerField(gettext_lazy("Уровень"), default=1)
    streak_days = models.PositiveSmallIntegerField(gettext_lazy("Стрик, дней"), default=0)
    best_streak = models.PositiveSmallIntegerField(gettext_lazy("Лучший стрик"), default=0)
    last_active_on = models.DateField(gettext_lazy("Последняя активность"), null=True, blank=True)
    updated_at = models.DateTimeField(gettext_lazy("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Состояние ученика")
        verbose_name_plural = gettext_lazy("Состояния учеников")

    def __str__(self) -> str:
        return gettext("{student} · {xp} XP, уровень {level}").format(
            student=self.student, xp=self.xp, level=self.level
        )

    @property
    def is_active_today(self) -> bool:
        return self.last_active_on == timezone.localdate()


# --- Профтест: анкета и разбор (фаза 45) -----------------------------------


class CareerQuestionKind(models.TextChoices):
    TEXT = "text", gettext_lazy("Свободный ответ")
    CHOICE = "choice", gettext_lazy("Выбор из вариантов")
    #: несколько вариантов сразу плюс свой (фаза 48). Анкета из шести
    #: пустых полей не заполняется: сочинение в шесть окон никто писать
    #: не станет, и ученик закрывает экран, не начав
    MULTI = "multi", gettext_lazy("Несколько вариантов")


class CareerQuestion(models.Model):
    """Вопрос анкеты профтеста. Справочник, ведёт директор школы.

    В код вопросы не зашиваются: школа меняет формулировки и добавляет свои,
    и новая анкета не должна означать выкат.
    """

    code = models.SlugField(gettext_lazy("Код"), max_length=40, unique=True)
    text = models.CharField(gettext_lazy("Вопрос"), max_length=300)
    hint = models.CharField(gettext_lazy("Подсказка"), max_length=250, blank=True)
    kind = models.CharField(
        gettext_lazy("Вид ответа"), max_length=12, choices=CareerQuestionKind.choices, default=CareerQuestionKind.TEXT
    )
    #: варианты для выбора — по одному в строке, как списки гайда эссе
    options = models.TextField(gettext_lazy("Варианты ответа"), blank=True, help_text="По одному в строке")
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=100)
    is_active = models.BooleanField(gettext_lazy("Показывать"), default=True)

    class Meta:
        verbose_name = gettext_lazy("Вопрос профтеста")
        verbose_name_plural = gettext_lazy("Вопросы профтеста")
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.text

    @property
    def options_list(self) -> list[str]:
        return [line.strip() for line in self.options.splitlines() if line.strip()]


class CareerRunStatus(models.TextChoices):
    DONE = "done", gettext_lazy("Разбор готов")
    FAILED = "failed", gettext_lazy("Не получился")


class CareerRun(models.Model):
    """Один проход профтеста: ответы плюс разбор.

    История проходов остаётся: через полгода ученик отвечает иначе,
    и сравнить два разбора полезнее, чем перезаписать один.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="career_runs", on_delete=models.CASCADE
    )
    status = models.CharField(
        gettext_lazy("Состояние"), max_length=12, choices=CareerRunStatus.choices, default=CareerRunStatus.DONE
    )
    summary = models.TextField(gettext_lazy("Общий вывод"), blank=True)
    error = models.CharField(gettext_lazy("Что пошло не так"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Пройден"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Проход профтеста")
        verbose_name_plural = gettext_lazy("Проходы профтеста")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("student", "-created_at"))]

    def __str__(self) -> str:
        return gettext("Профтест #{number} · {student}").format(number=self.pk, student=self.student)


class CareerAnswer(models.Model):
    """Ответ на один вопрос анкеты — строкой, а не полем прохода."""

    run = models.ForeignKey(
        CareerRun, verbose_name=gettext_lazy("Проход"), related_name="answers", on_delete=models.CASCADE
    )
    question = models.ForeignKey(
        CareerQuestion, verbose_name=gettext_lazy("Вопрос"), related_name="answers", on_delete=models.PROTECT
    )
    value = models.TextField(gettext_lazy("Ответ"), blank=True)

    class Meta:
        verbose_name = gettext_lazy("Ответ профтеста")
        verbose_name_plural = gettext_lazy("Ответы профтеста")
        ordering = ("question__order", "id")
        constraints = [models.UniqueConstraint(fields=("run", "question"), name="uniq_career_answer")]

    def __str__(self) -> str:
        return f"{self.run_id} · {self.question_id}"


class CareerDirection(models.Model):
    """Одно направление из разбора.

    Программы — связью со справочником, а не названиями текстом: инвариант
    №10 держится кодом, и «выдуманная программа» здесь физически не хранится.
    """

    run = models.ForeignKey(
        CareerRun, verbose_name=gettext_lazy("Проход"), related_name="directions", on_delete=models.CASCADE
    )
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=1)
    title = models.CharField(gettext_lazy("Направление"), max_length=150)
    reasoning = models.TextField(gettext_lazy("Почему подходит"), blank=True)
    subjects = models.CharField(gettext_lazy("Какие предметы нужны"), max_length=300, blank=True)
    exams = models.CharField(gettext_lazy("Какие экзамены нужны"), max_length=300, blank=True)
    programs = models.ManyToManyField(
        "universities.Program",
        verbose_name=gettext_lazy("Программы справочника"),
        related_name="career_directions",
        blank=True,
    )
    #: ученик согласился — направление ушло предложением директору
    agreed_at = models.DateTimeField(gettext_lazy("Когда согласился"), null=True, blank=True)
    suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        verbose_name=gettext_lazy("Предложение"),
        related_name="career_directions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Направление профтеста")
        verbose_name_plural = gettext_lazy("Направления профтеста")
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.title


# --- Достижения-бейджи (фаза 46) -------------------------------------------


class BadgeMetric(models.TextChoices):
    """Что именно считает бейдж.

    Инвариант №12: только действия. Ни одного пункта про балл экзамена,
    GPA, статус или место в рейтинге здесь нет и появиться не может —
    это проверяется тестом по самому перечню, а не по аккуратности.

    Условие бейджа — справочник (`Badge`), а не код: новый бейдж заводится
    строкой без выката. Но мерить его можно только тем, что система умеет
    считать, — поэтому набор мер закрыт, а порог у каждой записи свой.
    """

    TASKS_DONE = "tasks_done", gettext_lazy("Выполненные задачи роадмапа")
    EXERCISES_SOLVED = "exercises_solved", gettext_lazy("Решённые упражнения")
    MOCKS_TAKEN = "mocks_taken", gettext_lazy("Пройденные Mock Test онлайн")
    PROFILE_SECTIONS = "profile_sections", gettext_lazy("Заполненные разделы профиля")
    ESSAYS_STARTED = "essays_started", gettext_lazy("Начатые эссе")
    ONBOARDING_DONE = "onboarding_done", gettext_lazy("Пройденная анкета первого входа")
    MATERIALS_APPROVED = "materials_approved", gettext_lazy("Материалы, прошедшие проверку")
    RESOURCES_READ = "resources_read", gettext_lazy("Прочитанные материалы раздела «Ресурсы»")
    STREAK_DAYS = "streak_days", gettext_lazy("Дней подряд с действиями")
    PLANS_CREATED = "plans_created", gettext_lazy("Созданные планы по вузам")
    DOCUMENTS_UPLOADED = "documents_uploaded", gettext_lazy("Загруженные документы портфолио")


class Badge(models.Model):
    """Бейдж: что нужно сделать и сколько раз.

    Закрытые бейджи показываются с замком и условием, а не прячутся:
    ученик должен видеть, что можно получить.
    """

    code = models.SlugField(gettext_lazy("Код"), max_length=40, unique=True)
    name = models.CharField(gettext_lazy("Название"), max_length=120)
    description = models.CharField(gettext_lazy("Описание"), max_length=250, blank=True)
    metric = models.CharField(gettext_lazy("Что считаем"), max_length=32, choices=BadgeMetric.choices)
    threshold = models.PositiveIntegerField(gettext_lazy("Сколько нужно"), default=1)
    #: имя иконки из нашего набора — эмодзи в интерфейсе нет (фаза 22)
    icon = models.CharField(gettext_lazy("Иконка"), max_length=32, blank=True, default="medal")
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=100)
    is_active = models.BooleanField(gettext_lazy("Показывать"), default=True)

    class Meta:
        verbose_name = gettext_lazy("Бейдж")
        verbose_name_plural = gettext_lazy("Бейджи")
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.name


class BadgeAward(models.Model):
    """Выданный бейдж. Дата нужна: «получен 12 марта» читается иначе, чем «есть»."""

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="badges", on_delete=models.CASCADE
    )
    badge = models.ForeignKey(
        Badge, verbose_name=gettext_lazy("Бейдж"), related_name="awards", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(gettext_lazy("Получен"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Полученный бейдж")
        verbose_name_plural = gettext_lazy("Полученные бейджи")
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("student", "badge"), name="uniq_badge_per_student")]

    def __str__(self) -> str:
        return f"{self.student} · {self.badge}"


# --- Справочники фазы 49: сюжеты главной и правила обзвона -----------------


class CueCondition(models.TextChoices):
    """Из-за чего сюжет попадает на главную ученика.

    Набор закрытый: условие считает код, а слова, кнопку и цвет ведёт
    школа. Новый сюжет заводится строкой без выката, но выдумать новую
    измеримую величину без кода нельзя — тот же приём, что у бейджей.
    """

    PORTFOLIO_GAP = "portfolio_gap", gettext_lazy("Портфолио заполнено не до конца")
    EXAM_GOAL_GAP = "exam_goal_gap", gettext_lazy("До цели по экзамену не хватает")
    SCHOLARSHIP_DEADLINE = "scholarship_deadline", gettext_lazy("Стипендии с ближайшим дедлайном не просмотрены")
    PLAN_IDLE = "plan_idle", gettext_lazy("План не открывали неделю")
    NO_UNIVERSITIES = "no_universities", gettext_lazy("Список вузов пуст")
    DOCUMENTS_MISSING = "documents_missing", gettext_lazy("Документы не загружены")


class CueTone(models.TextChoices):
    """Цвет карточки сюжета — из набора крупных карточек раздела."""

    BRAND = "brand", gettext_lazy("Оранжевый")
    INK = "ink", gettext_lazy("Графит")
    TEAL = "teal", gettext_lazy("Бирюза")
    INDIGO = "indigo", gettext_lazy("Индиго")


class HomeCue(models.Model):
    """Сюжет карусели на главной ученика (фаза 49).

    Карусель — не украшение, а список незакрытых мест: портфолио не
    заполнено, до цели по экзамену не хватает, стипендии с дедлайном
    не просмотрены, план не открывали неделю. Каждый сюжет — приглашение
    закрыть одно место, и пока незакрытых мест нет, карусели нет вовсе.

    Надпись над заголовком собирает код: в ней живое число («Портфолио
    заполнено на 63%»), и в справочнике ему взяться неоткуда.
    """

    code = models.SlugField(gettext_lazy("Код"), max_length=40, unique=True)
    condition = models.CharField(gettext_lazy("Условие"), max_length=32, choices=CueCondition.choices)
    title = models.CharField(gettext_lazy("Заголовок"), max_length=120)
    description = models.CharField(gettext_lazy("Описание"), max_length=250, blank=True)
    action_label = models.CharField(gettext_lazy("Подпись кнопки"), max_length=60)
    action_path = models.CharField(gettext_lazy("Куда ведёт кнопка"), max_length=120)
    tone = models.CharField(
        gettext_lazy("Цвет карточки"), max_length=16, choices=CueTone.choices, default=CueTone.BRAND
    )
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=100)
    is_active = models.BooleanField(gettext_lazy("Показывать"), default=True)

    class Meta:
        verbose_name = gettext_lazy("Сюжет главной")
        verbose_name_plural = gettext_lazy("Сюжеты главной")
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.title


class CallCondition(models.TextChoices):
    """Из-за чего ученик попадает в список «кому позвонить»."""

    ABSENCES = "absences", gettext_lazy("Пропуски занятий")
    MOCK_DROP = "mock_drop", gettext_lazy("Просел по Mock Test")
    INACTIVE = "inactive", gettext_lazy("Не заходил в систему")
    MISSED_DEADLINE = "missed_deadline", gettext_lazy("Пропустил дедлайн")
    NO_CONTACT = "no_contact", gettext_lazy("Нет контактов родителей")


class CallUrgency(models.TextChoices):
    """Насколько срочно звонить — чип в строке списка."""

    NOW = "now", gettext_lazy("Срочно")
    TODAY = "today", gettext_lazy("Сегодня")
    WEEK = "week", gettext_lazy("На неделе")


class CallRule(models.Model):
    """Правило списка «Кому позвонить сегодня» (фаза 49).

    Список собирается из пропусков, моков, активности и дедлайнов, а порог
    и формулировка причины живут здесь: «три пропуска подряд» и «пять»
    школа меняет сама, без выката.
    """

    code = models.SlugField(gettext_lazy("Код"), max_length=40, unique=True)
    condition = models.CharField(gettext_lazy("Условие"), max_length=32, choices=CallCondition.choices)
    reason = models.CharField(gettext_lazy("Причина одной фразой"), max_length=120)
    urgency = models.CharField(
        gettext_lazy("Срочность"), max_length=8, choices=CallUrgency.choices, default=CallUrgency.TODAY
    )
    #: сколько должно набраться, чтобы правило сработало: процент, дни, разы
    threshold = models.DecimalField(gettext_lazy("Порог"), max_digits=6, decimal_places=1, default=1)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=100)
    is_active = models.BooleanField(gettext_lazy("Показывать"), default=True)

    class Meta:
        verbose_name = gettext_lazy("Правило обзвона")
        verbose_name_plural = gettext_lazy("Правила обзвона")
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.reason
