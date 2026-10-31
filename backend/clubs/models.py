"""Кружки (решение владельца, 31.10.2026): AI Startup Lab, Робототехника и следующие.

Кружок — название, описание, ментор, встречи по дням недели, разрешённые
параллели и окно записи. Мест без лимита, заявок и одобрений нет: ученик
записывается сам и сразу, может состоять в нескольких кружках. Запись
с историей — строками: выход закрывает строку, а не удаляет её
(инвариант №5); записаться снова — новая строка.

Ментор — текстовое имя для карточки и необязательная привязка к учётке
с ролью «Ментор»: учётки заводит администратор позже, кружок без неё
живёт. Отметка посещения выключена, пока администратор её не включит.

Кто что пишет — `core.domains.CABINET_WRITERS` и `clubs.rights` (инвариант №2).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy

from core.archivable import Archivable
from materials.storage import private_storage
from sport.models import MarkMethod, Weekday
from students.models import Student


class Club(Archivable):
    """Кружок. Встречи — `ClubMeeting`, параллели — `ClubParallel`."""

    title = models.CharField(gettext_lazy("Название"), max_length=120)
    description = models.TextField(gettext_lazy("Описание"), blank=True)
    mentor_name = models.CharField(gettext_lazy("Ментор"), max_length=120)
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Учётка ментора"),
        related_name="mentored_clubs",
        # учётку убирают — кружок остаётся с именем ментора на карточке
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: пусто — запись открыта всегда; дата — открыта до неё
    enroll_until = models.DateTimeField(gettext_lazy("Запись открыта до"), null=True, blank=True)
    marks_enabled = models.BooleanField(gettext_lazy("Отметка посещения"), default=False)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок в списке"), default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто завёл"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    is_fictional = models.BooleanField(gettext_lazy("Вымышленный"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Заведён"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Кружок")
        verbose_name_plural = gettext_lazy("Кружки")
        ordering = ("order", "title", "id")

    def __str__(self) -> str:
        return self.title


class ClubMeeting(models.Model):
    """Встреча кружка по расписанию: день недели и время. Правка кружка пересобирает их целиком."""

    club = models.ForeignKey(
        Club, verbose_name=gettext_lazy("Кружок"), related_name="meetings", on_delete=models.CASCADE
    )
    weekday = models.PositiveSmallIntegerField(gettext_lazy("День недели"), choices=Weekday.choices)
    starts = models.TimeField(gettext_lazy("Начало"))
    ends = models.TimeField(gettext_lazy("Конец"))

    class Meta:
        verbose_name = gettext_lazy("Встреча кружка")
        verbose_name_plural = gettext_lazy("Встречи кружков")
        ordering = ("club", "weekday", "starts", "id")
        constraints = [
            models.CheckConstraint(condition=models.Q(ends__gt=models.F("starts")), name="meeting_ends_after_starts"),
            models.UniqueConstraint(fields=("club", "weekday"), name="one_meeting_a_day"),
        ]

    def __str__(self) -> str:
        return f"{self.club} · {self.get_weekday_display()} {self.starts:%H:%M}"


class ClubParallel(models.Model):
    """Параллель, которой открыта запись в кружок: галочка 8, 9, 10 или 11."""

    club = models.ForeignKey(
        Club, verbose_name=gettext_lazy("Кружок"), related_name="parallels", on_delete=models.CASCADE
    )
    parallel = models.PositiveSmallIntegerField(gettext_lazy("Параллель"))

    class Meta:
        verbose_name = gettext_lazy("Параллель кружка")
        verbose_name_plural = gettext_lazy("Параллели кружков")
        ordering = ("club", "parallel")
        constraints = [models.UniqueConstraint(fields=("club", "parallel"), name="unique_club_parallel")]

    def __str__(self) -> str:
        return f"{self.club} · {self.parallel}"


class ClubEnrollment(models.Model):
    """Запись ученика в кружок. Действующая — без `ended_at`, в кружке у ученика она одна."""

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="club_enrollments", on_delete=models.CASCADE
    )
    club = models.ForeignKey(
        Club, verbose_name=gettext_lazy("Кружок"), related_name="enrollments", on_delete=models.PROTECT
    )
    enrolled_at = models.DateTimeField(gettext_lazy("Записался"), default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто записал"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    ended_at = models.DateTimeField(gettext_lazy("Вышел из кружка"), null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто закрыл запись"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Запись в кружок")
        verbose_name_plural = gettext_lazy("Записи в кружки")
        ordering = ("-enrolled_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("student", "club"), condition=models.Q(ended_at__isnull=True), name="one_active_club_row"
            ),
        ]
        indexes = [models.Index(fields=("club", "ended_at"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.club}"


class ClubMark(models.Model):
    """Ученик пришёл на встречу кружка в эту дату: по QR или отмечен вручную."""

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="club_marks", on_delete=models.CASCADE
    )
    club = models.ForeignKey(Club, verbose_name=gettext_lazy("Кружок"), related_name="marks", on_delete=models.PROTECT)
    date = models.DateField(gettext_lazy("Дата встречи"))
    marked_at = models.DateTimeField(gettext_lazy("Когда отмечен"), default=timezone.now)
    method = models.CharField(gettext_lazy("Как отмечен"), max_length=8, choices=MarkMethod.choices)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто отметил вручную"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    marked_by_title = models.CharField(gettext_lazy("Кто отметил на момент отметки"), max_length=250, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Отметка на встрече кружка")
        verbose_name_plural = gettext_lazy("Отметки на встречах кружков")
        ordering = ("-date", "-marked_at")
        constraints = [models.UniqueConstraint(fields=("student", "club", "date"), name="unique_club_mark")]
        indexes = [models.Index(fields=("club", "date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.club} · {self.date}"


def homework_upload_to(instance, filename: str) -> str:
    """Файл задания — в закрытом хранилище, без имени из файла."""
    ext = filename.rsplit(".", 1)[-1].lower()[:10] if "." in filename else "bin"
    return f"clubs/homework/{instance.club_id}-{timezone.now():%Y%m%d%H%M%S}.{ext}"


class ClubHomework(Archivable):
    """Задание ментора кружку: текст, срок, необязательный файл. Снятое уходит в архив.

    Сдачи здесь нет: ученики кружка видят задание в «Кружках».
    """

    club = models.ForeignKey(
        Club, verbose_name=gettext_lazy("Кружок"), related_name="homework", on_delete=models.PROTECT
    )
    text = models.TextField(gettext_lazy("Задание"))
    due = models.DateField(gettext_lazy("Срок"))
    file = models.FileField(
        gettext_lazy("Файл"), upload_to=homework_upload_to, storage=private_storage, max_length=300, blank=True
    )
    file_name = models.CharField(gettext_lazy("Имя файла"), max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто опубликовал"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Опубликовано"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Изменено"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Задание кружка")
        verbose_name_plural = gettext_lazy("Задания кружков")
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.club} · {self.due}"


class ClubNote(Archivable):
    """Заметка ментора об ученике: свободный текст с датой.

    Читают только ментор этого кружка и администратор — список в одном
    месте, `clubs.rights.NOTE_READERS`. Куратор, директора и ученик — никогда.
    """

    club = models.ForeignKey(Club, verbose_name=gettext_lazy("Кружок"), related_name="notes", on_delete=models.PROTECT)
    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="club_notes", on_delete=models.CASCADE
    )
    text = models.TextField(gettext_lazy("Текст"))
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Автор"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    author_title = models.CharField(gettext_lazy("Автор на момент удаления"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Когда"), default=timezone.now)

    class Meta:
        verbose_name = gettext_lazy("Заметка ментора")
        verbose_name_plural = gettext_lazy("Заметки ментора")
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("club", "student"))]

    def __str__(self) -> str:
        return f"{self.club} · {self.student}"
