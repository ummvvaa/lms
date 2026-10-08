"""Профтест: тесты профориентации, их прохождение и разбор.

Тест приходит файлом от учителя профориентации (`career/files.py`): вопросы,
шкалы, ключ и диапазоны интерпретации — строками своих таблиц, а не текстом
или JSON (инварианты 5 и 6). Баллы по шкалам считает код по ключу
(`career/scoring.py`), модель получает только профиль выше порога и пишет
разбор в свои строки — в доменные поля ученика ничего не попадает.

Прежняя анкета профтеста (`engagement.CareerQuestion`, `CareerRun`) осталась
в базе без экранов (решение владельца, 08.10.2026): проходы не удаляются.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext, gettext_lazy

from materials.storage import private_storage
from students.models import Student, StudyGroup


def test_upload_to(instance, filename: str) -> str:
    """Файл теста — в закрытом хранилище, без имени из файла."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "xlsx"
    return f"career/tests/{instance.pk or 'new'}-{instance.created_at:%Y%m%d%H%M%S}.{ext}"


class CareerTest(models.Model):
    """Тест профориентации, загруженный файлом.

    Пока тест не включён, ученики его не видят. Тест с попытками не
    удаляется — уходит в архив; без попыток удаляется вместе с файлом.
    """

    title = models.CharField(gettext_lazy("Название"), max_length=200)
    instruction = models.TextField(gettext_lazy("Инструкция"), blank=True)
    #: шкалы с баллом ниже порога в разбор модели не уходят
    #: (решение владельца: «минусы не считаем»; ноль — «затрудняюсь ответить»)
    analysis_min_score = models.SmallIntegerField(gettext_lazy("Порог для разбора"), default=1)
    is_active = models.BooleanField(gettext_lazy("Включён"), default=False)
    file = models.FileField(gettext_lazy("Файл"), upload_to=test_upload_to, storage=private_storage, max_length=300)
    file_name = models.CharField(gettext_lazy("Имя файла"), max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто загрузил"),
        related_name="career_tests",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Загружен"), auto_now_add=True)
    archived_at = models.DateTimeField(gettext_lazy("В архиве с"), null=True, blank=True)
    is_fictional = models.BooleanField(gettext_lazy("Вымышленный"), default=False)

    class Meta:
        verbose_name = gettext_lazy("Тест профориентации")
        verbose_name_plural = gettext_lazy("Тесты профориентации")
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return self.title


class CareerTestOption(models.Model):
    """Вариант ответа теста: подпись и балл («++» → 2, «−−» → −2)."""

    test = models.ForeignKey(CareerTest, related_name="options", on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=1)
    label = models.CharField(gettext_lazy("Подпись"), max_length=60)
    value = models.SmallIntegerField(gettext_lazy("Баллы"))

    class Meta:
        verbose_name = gettext_lazy("Вариант ответа")
        verbose_name_plural = gettext_lazy("Варианты ответа")
        ordering = ("order", "id")
        constraints = [models.UniqueConstraint(fields=("test", "label"), name="uniq_career_option_label")]

    def __str__(self) -> str:
        return self.label


class CareerScale(models.Model):
    """Шкала теста — сфера интересов, тип личности, склонность."""

    test = models.ForeignKey(CareerTest, related_name="scales", on_delete=models.CASCADE)
    code = models.CharField(gettext_lazy("Код"), max_length=40)
    title = models.CharField(gettext_lazy("Название"), max_length=120)
    description = models.TextField(gettext_lazy("Описание"), blank=True)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=1)

    class Meta:
        verbose_name = gettext_lazy("Шкала теста")
        verbose_name_plural = gettext_lazy("Шкалы теста")
        ordering = ("order", "id")
        constraints = [models.UniqueConstraint(fields=("test", "code"), name="uniq_career_scale_code")]

    def __str__(self) -> str:
        return self.title


class CareerItem(models.Model):
    """Утверждение или вопрос теста с ключом: в какую шкалу и с каким знаком."""

    test = models.ForeignKey(CareerTest, related_name="items", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField(gettext_lazy("Номер"))
    text = models.TextField(gettext_lazy("Текст"))
    #: пусто только у вопроса со своими вариантами, где шкала у варианта
    scale = models.ForeignKey(CareerScale, related_name="items", on_delete=models.PROTECT, null=True, blank=True)
    #: обратный пункт: балл ответа идёт в шкалу с минусом
    sign = models.SmallIntegerField(gettext_lazy("Знак"), default=1)

    class Meta:
        verbose_name = gettext_lazy("Вопрос теста")
        verbose_name_plural = gettext_lazy("Вопросы теста")
        ordering = ("number", "id")
        constraints = [models.UniqueConstraint(fields=("test", "number"), name="uniq_career_item_number")]

    def __str__(self) -> str:
        return f"{self.number}. {self.text[:60]}"


class CareerItemChoice(models.Model):
    """Свой вариант у вопроса: «а» и «б» с разными шкалами (Климов, Холланд)."""

    item = models.ForeignKey(CareerItem, related_name="choices", on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=1)
    label = models.CharField(gettext_lazy("Текст варианта"), max_length=400)
    scale = models.ForeignKey(CareerScale, related_name="choices", on_delete=models.PROTECT)
    value = models.SmallIntegerField(gettext_lazy("Баллы"), default=1)

    class Meta:
        verbose_name = gettext_lazy("Вариант вопроса")
        verbose_name_plural = gettext_lazy("Варианты вопроса")
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.label


class CareerRange(models.Model):
    """Диапазон интерпретации: от −12 до −6 — «активно отрицается»."""

    test = models.ForeignKey(CareerTest, related_name="ranges", on_delete=models.CASCADE)
    #: пусто — диапазон общий для всех шкал теста
    scale = models.ForeignKey(CareerScale, related_name="ranges", on_delete=models.CASCADE, null=True, blank=True)
    low = models.SmallIntegerField(gettext_lazy("От"))
    high = models.SmallIntegerField(gettext_lazy("До"))
    label = models.CharField(gettext_lazy("Подпись"), max_length=120)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=1)

    class Meta:
        verbose_name = gettext_lazy("Диапазон интерпретации")
        verbose_name_plural = gettext_lazy("Диапазоны интерпретации")
        ordering = ("order", "id")

    def __str__(self) -> str:
        return f"{self.low}…{self.high}: {self.label}"


class CareerAssignment(models.Model):
    """Кому открыт тест: группе целиком (`student` пусто) или отдельному ученику."""

    test = models.ForeignKey(CareerTest, related_name="assignments", on_delete=models.CASCADE)
    group = models.ForeignKey(StudyGroup, related_name="career_assignments", on_delete=models.CASCADE)
    student = models.ForeignKey(
        Student, related_name="career_assignments", on_delete=models.CASCADE, null=True, blank=True
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="career_assignments", on_delete=models.SET_NULL, null=True, blank=True
    )
    assigned_at = models.DateTimeField(gettext_lazy("Назначен"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Назначение теста")
        verbose_name_plural = gettext_lazy("Назначения теста")
        constraints = [
            models.UniqueConstraint(
                fields=("test", "group"), condition=models.Q(student__isnull=True), name="uniq_career_assign_group"
            ),
            models.UniqueConstraint(
                fields=("test", "student"), condition=models.Q(student__isnull=False), name="uniq_career_assign_student"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.test_id} → {self.group_id}/{self.student_id or '*'}"


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", gettext_lazy("Идёт")
    DONE = "done", gettext_lazy("Сдан")


class CareerAttempt(models.Model):
    """Прохождение теста учеником: черновик на сервере, по завершении — баллы.

    Одна действующая попытка на тест (Д1): «пройти заново» разрешает
    учитель — прежняя попытка уходит в историю с `archived_at`.
    """

    test = models.ForeignKey(CareerTest, related_name="attempts", on_delete=models.CASCADE)
    student = models.ForeignKey(Student, related_name="career_attempts", on_delete=models.CASCADE)
    status = models.CharField(
        gettext_lazy("Состояние"), max_length=12, choices=AttemptStatus.choices, default=AttemptStatus.IN_PROGRESS
    )
    started_at = models.DateTimeField(gettext_lazy("Начат"), auto_now_add=True)
    finished_at = models.DateTimeField(gettext_lazy("Сдан"), null=True, blank=True)
    archived_at = models.DateTimeField(gettext_lazy("В истории с"), null=True, blank=True)
    retake_allowed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто разрешил пройти заново"),
        related_name="career_retakes",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Попытка теста")
        verbose_name_plural = gettext_lazy("Попытки теста")
        ordering = ("-started_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("test", "student"),
                condition=models.Q(archived_at__isnull=True),
                name="uniq_career_attempt_live",
            )
        ]
        indexes = [models.Index(fields=("student", "status"))]

    def __str__(self) -> str:
        return gettext("Попытка #{number} · {student}").format(number=self.pk, student=self.student)

    @property
    def is_done(self) -> bool:
        return self.status == AttemptStatus.DONE


class CareerAttemptAnswer(models.Model):
    """Ответ на один вопрос: вариант теста или свой вариант вопроса."""

    attempt = models.ForeignKey(CareerAttempt, related_name="answers", on_delete=models.CASCADE)
    item = models.ForeignKey(CareerItem, related_name="answers", on_delete=models.PROTECT)
    option = models.ForeignKey(
        CareerTestOption, related_name="answers", on_delete=models.PROTECT, null=True, blank=True
    )
    choice = models.ForeignKey(
        CareerItemChoice, related_name="answers", on_delete=models.PROTECT, null=True, blank=True
    )
    answered_at = models.DateTimeField(gettext_lazy("Отвечен"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Ответ на вопрос")
        verbose_name_plural = gettext_lazy("Ответы на вопросы")
        constraints = [models.UniqueConstraint(fields=("attempt", "item"), name="uniq_career_answer_item")]

    def __str__(self) -> str:
        return f"{self.attempt_id} · {self.item_id}"


class CareerAttemptScore(models.Model):
    """Балл по шкале за попытку — строкой, по нему строятся полоски и разбор."""

    attempt = models.ForeignKey(CareerAttempt, related_name="scores", on_delete=models.CASCADE)
    scale = models.ForeignKey(CareerScale, related_name="scores", on_delete=models.PROTECT)
    score = models.SmallIntegerField(gettext_lazy("Балл"))
    label = models.CharField(gettext_lazy("Интерпретация"), max_length=120, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Балл по шкале")
        verbose_name_plural = gettext_lazy("Баллы по шкалам")
        ordering = ("-score", "scale__order")
        constraints = [models.UniqueConstraint(fields=("attempt", "scale"), name="uniq_career_score_scale")]

    def __str__(self) -> str:
        return f"{self.scale_id}: {self.score}"


class AnalysisStatus(models.TextChoices):
    RUNNING = "running", gettext_lazy("Идёт")
    DONE = "done", gettext_lazy("Готов")
    FAILED = "failed", gettext_lazy("Не получился")


class CareerAnalysis(models.Model):
    """Разбор модели по выбранным сданным тестам ученика.

    `fingerprint` — номера попыток, по которым считался разбор: тот же
    набор не разбирается второй раз, пока учитель не нажмёт «Пересчитать»
    (решение владельца, 08.10.2026). Текст правит учитель; ученик видит
    разбор только после «Показать ученику».
    """

    student = models.ForeignKey(Student, related_name="career_analyses", on_delete=models.CASCADE)
    attempts = models.ManyToManyField(CareerAttempt, related_name="analyses", blank=True)
    fingerprint = models.CharField(gettext_lazy("Набор попыток"), max_length=200, db_index=True)
    status = models.CharField(
        gettext_lazy("Состояние"), max_length=8, choices=AnalysisStatus.choices, default=AnalysisStatus.RUNNING
    )
    language = models.CharField(gettext_lazy("Язык разбора"), max_length=2, default="ru")
    summary = models.TextField(gettext_lazy("Общий вывод"), blank=True)
    error = models.CharField(gettext_lazy("Что пошло не так"), max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто запустил"),
        related_name="career_analyses",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Запущен"), auto_now_add=True)
    finished_at = models.DateTimeField(gettext_lazy("Готов"), null=True, blank=True)
    visible_to_student = models.BooleanField(gettext_lazy("Показан ученику"), default=False)
    edited_at = models.DateTimeField(gettext_lazy("Правил учитель"), null=True, blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто правил"),
        related_name="edited_career_analyses",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Разбор профтеста")
        verbose_name_plural = gettext_lazy("Разборы профтеста")
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("student", "-created_at"))]

    def __str__(self) -> str:
        return gettext("Разбор #{number} · {student}").format(number=self.pk, student=self.student)


class CareerAnalysisDirection(models.Model):
    """Одно направление разбора. Программы — только из справочника (инвариант 10)."""

    analysis = models.ForeignKey(CareerAnalysis, related_name="directions", on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=1)
    title = models.CharField(gettext_lazy("Направление"), max_length=150)
    reasoning = models.TextField(gettext_lazy("Почему подходит"), blank=True)
    professions = models.CharField(gettext_lazy("Профессии"), max_length=300, blank=True)
    subjects = models.CharField(gettext_lazy("Какие предметы нужны"), max_length=300, blank=True)
    exams = models.CharField(gettext_lazy("Какие экзамены нужны"), max_length=300, blank=True)
    programs = models.ManyToManyField(
        "universities.Program",
        verbose_name=gettext_lazy("Программы справочника"),
        related_name="career_analysis_directions",
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Направление разбора")
        verbose_name_plural = gettext_lazy("Направления разбора")
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.title
