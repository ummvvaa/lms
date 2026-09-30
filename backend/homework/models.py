"""Сдача домашних заданий в LMS: задание урока, сдача ученика, файлы.

Текст ДЗ — как раньше, `Lesson.homework`. Задание (`Assignment`) заводится,
когда учителю нужна сдача в LMS или он прикладывает файлы: срок, правило
«после срока», файлы учителя. Получают задание ученики состава урока на дату
урока — подгруппа и поток получают только своих (`academics.cohorts.member_ids`).

Сдача (`Submission`) — строка на ученика и задание: пока не нажато «Сдать»,
это черновик с загружаемыми файлами; до срока работу можно заменить. Проверка —
оценка 1–10 или «без оценки» и комментарий учителя; вернуть на доработку нельзя
(решение владельца, 30.09.2026). Оценка за ДЗ живёт здесь, а не в `Grade`:
у урока своя оценка, у ДЗ — своя колонка «ДЗ» в журнале.

Файлы (`HomeworkFile`) лежат в закрытом хранилище (`homework.storage`):
Yandex Object Storage в регионе kz или, без настроек, локальный диск.
Удаление мягкое (`Archivable`); объект в хранилище стирается при очистке архива.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.archivable import Archivable


class LatePolicy(models.TextChoices):
    """Что делать со сдачей после срока — учитель выбирает на каждое задание."""

    ACCEPT = "accept", "Принимать с пометкой «с опозданием»"
    CLOSE = "close", "Закрыть сдачу"


class Assignment(Archivable):
    """Задание урока со сдачей в LMS и/или файлами учителя."""

    lesson = models.ForeignKey(
        "academics.Lesson", verbose_name="Урок", related_name="assignments", on_delete=models.CASCADE
    )
    requires_submission = models.BooleanField("Нужна сдача в LMS", default=False)
    due_at = models.DateTimeField("Срок сдачи", null=True, blank=True)
    late_policy = models.CharField("После срока", max_length=8, choices=LatePolicy.choices, default=LatePolicy.ACCEPT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто задал",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Задано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Задание со сдачей"
        verbose_name_plural = "Задания со сдачей"
        ordering = ("-due_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("lesson",), condition=models.Q(archived_at__isnull=True), name="one_assignment_per_lesson"
            )
        ]
        indexes = [models.Index(fields=("requires_submission", "due_at"))]

    def __str__(self) -> str:
        return f"ДЗ · {self.lesson}"


class Submission(Archivable):
    """Сдача ученика: черновик, сдано, проверено."""

    assignment = models.ForeignKey(
        Assignment, verbose_name="Задание", related_name="submissions", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        "students.Student", verbose_name="Ученик", related_name="submissions", on_delete=models.CASCADE
    )
    text = models.TextField("Текст ответа", blank=True)
    link = models.URLField("Ссылка", max_length=500, blank=True)
    comment = models.TextField("Комментарий учителю", blank=True)
    #: пусто — черновик: файлы грузятся, но «Сдать» ещё не нажато
    submitted_at = models.DateTimeField("Сдано", null=True, blank=True)
    #: на сколько минут позже срока сдано; вовремя — пусто
    late_minutes = models.PositiveIntegerField("Опоздание, мин", null=True, blank=True)
    checked_at = models.DateTimeField("Проверено", null=True, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто проверил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: 1–10; проверено без оценки — пусто при заполненном `checked_at`
    grade = models.PositiveSmallIntegerField("Оценка", null=True, blank=True)
    teacher_comment = models.TextField("Комментарий учителя", blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Сдача ДЗ"
        verbose_name_plural = "Сдачи ДЗ"
        ordering = ("assignment", "student")
        constraints = [
            models.UniqueConstraint(
                fields=("assignment", "student"),
                condition=models.Q(archived_at__isnull=True),
                name="one_submission_per_student",
            ),
            models.CheckConstraint(
                condition=models.Q(grade__isnull=True) | models.Q(grade__gte=1, grade__lte=10),
                name="homework_grade_1_10",
            ),
        ]
        indexes = [models.Index(fields=("student", "submitted_at"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.assignment}"

    @property
    def is_submitted(self) -> bool:
        return self.submitted_at is not None

    @property
    def is_checked(self) -> bool:
        return self.checked_at is not None


class FileKind(models.TextChoices):
    """Как файл показывать в LMS: PDF и фото — постранично, звук и видео — плеером."""

    PDF = "pdf", "PDF"
    IMAGE = "image", "Фото"
    AUDIO = "audio", "Аудио"
    VIDEO = "video", "Видео"
    OTHER = "other", "Файл"


class FileState(models.TextChoices):
    UPLOADING = "uploading", "Загружается"
    READY = "ready", "Загружен"


class HomeworkFile(Archivable):
    """Файл учителя к заданию или файл ученика в сдаче — ровно одно из двух."""

    assignment = models.ForeignKey(
        Assignment, verbose_name="Задание", related_name="files", on_delete=models.CASCADE, null=True, blank=True
    )
    submission = models.ForeignKey(
        Submission, verbose_name="Сдача", related_name="files", on_delete=models.CASCADE, null=True, blank=True
    )
    #: путь объекта в хранилище — без имени файла человека, его знает только база
    key = models.CharField("Ключ в хранилище", max_length=300, unique=True)
    name = models.CharField("Имя файла", max_length=250)
    content_type = models.CharField("Тип", max_length=120, blank=True)
    kind = models.CharField("Вид", max_length=8, choices=FileKind.choices, default=FileKind.OTHER)
    size = models.BigIntegerField("Размер, байт", default=0)
    #: PDF, склеенный из снимков: сколько было фото
    photos = models.PositiveSmallIntegerField("Из фото", null=True, blank=True)
    state = models.CharField("Состояние", max_length=10, choices=FileState.choices, default=FileState.UPLOADING)
    #: номер загрузки по частям в хранилище; у загрузки одним куском пусто
    upload_id = models.CharField("Загрузка по частям", max_length=200, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто загрузил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    created_at = models.DateTimeField("Загружен", auto_now_add=True)

    class Meta:
        verbose_name = "Файл ДЗ"
        verbose_name_plural = "Файлы ДЗ"
        ordering = ("order", "id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(assignment__isnull=False, submission__isnull=True)
                    | models.Q(assignment__isnull=True, submission__isnull=False)
                ),
                name="homework_file_has_one_owner",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def drop_stored(self) -> bool:
        """Стереть объект в хранилище — зовёт очистка архива (`core.purge.drop_stored`)."""
        from homework.storage import backend

        store = backend()
        if self.state == FileState.UPLOADING and self.upload_id:
            store.abort(self.key, self.upload_id)
        else:
            store.delete(self.key)
        return True
