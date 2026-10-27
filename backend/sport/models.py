"""Спортивные секции и билеты (решение владельца, 27.10.2026).

Секция — площадка и вид спорта, под ней занятия по часам (слоты) со своим
лимитом и своей группой классов. Ученик записан ровно в одну секцию и на
один час; перенесённый из бота может стоять без часа, пока не выберет.
Запись с историей — строками: выход закрывает строку, а не удаляет её
(инвариант №5). Отметка — строка на ученика и занятие в дату; пропуск —
это отсутствие отметки на прошедшем занятии, отдельно не хранится.

Билеты — раздача бесплатных билетов школы: первые N нажавших после старта
получают билет, остальные стоят в очереди по времени нажатия.

Кто что пишет — `core.domains.CABINET_WRITERS` (инвариант №2).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy

from core.archivable import Archivable
from students.models import Student


class Weekday(models.IntegerChoices):
    """День недели — как `date.weekday()`: понедельник ноль."""

    MON = 0, gettext_lazy("Понедельник")
    TUE = 1, gettext_lazy("Вторник")
    WED = 2, gettext_lazy("Среда")
    THU = 3, gettext_lazy("Четверг")
    FRI = 4, gettext_lazy("Пятница")
    SAT = 5, gettext_lazy("Суббота")
    SUN = 6, gettext_lazy("Воскресенье")


class Section(Archivable):
    """Секция: вид спорта и площадка. Занятия по часам — `SectionSlot`."""

    title = models.CharField(gettext_lazy("Название"), max_length=120)
    sport_type = models.ForeignKey(
        "directories.SportType",
        verbose_name=gettext_lazy("Вид спорта"),
        related_name="sections",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    address = models.CharField(gettext_lazy("Адрес площадки"), max_length=250)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок в списке"), default=0)
    is_fictional = models.BooleanField(gettext_lazy("Вымышленная"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Добавлена"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Секция")
        verbose_name_plural = gettext_lazy("Секции")
        ordering = ("order", "title", "id")

    def __str__(self) -> str:
        return self.title


class SectionSlot(Archivable):
    """Занятие секции по расписанию: день недели, час, классы «с–по» и лимит мест.

    Классы хранятся границами (8–9, 10–11), а не набором: так завтра можно
    завести занятие для 8–11 без новой колонки. Убранное занятие уходит
    в архив — на нём остаются отметки прошлых недель.
    """

    section = models.ForeignKey(
        Section, verbose_name=gettext_lazy("Секция"), related_name="slots", on_delete=models.CASCADE
    )
    weekday = models.PositiveSmallIntegerField(gettext_lazy("День недели"), choices=Weekday.choices)
    starts = models.TimeField(gettext_lazy("Начало"))
    ends = models.TimeField(gettext_lazy("Конец"))
    grade_from = models.PositiveSmallIntegerField(gettext_lazy("С класса"))
    grade_to = models.PositiveSmallIntegerField(gettext_lazy("По класс"))
    room = models.CharField(gettext_lazy("Кабинет или уточнение"), max_length=80, blank=True)
    capacity = models.PositiveSmallIntegerField(gettext_lazy("Мест"))

    class Meta:
        verbose_name = gettext_lazy("Занятие секции")
        verbose_name_plural = gettext_lazy("Занятия секций")
        ordering = ("section", "weekday", "starts", "grade_from", "id")
        constraints = [
            models.CheckConstraint(condition=models.Q(ends__gt=models.F("starts")), name="slot_ends_after_starts"),
            models.CheckConstraint(
                condition=models.Q(grade_to__gte=models.F("grade_from")), name="slot_grades_ordered"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.section} · {self.get_weekday_display()} {self.starts:%H:%M}"

    def fits(self, grade: int) -> bool:
        """Подходит ли занятие ученику этого класса."""
        return self.grade_from <= grade <= self.grade_to


class EnrollmentSource(models.TextChoices):
    LMS = "lms", gettext_lazy("LMS")
    BOT = "bot", gettext_lazy("Перенос из бота")
    DIRECTOR = "director", gettext_lazy("Записал директор спорта")


class SectionEnrollment(models.Model):
    """Запись ученика в секцию. Активная — без `ended_at`, у ученика она одна.

    Час (`slot`) пуст только у перенесённых из бота, у кого в группе классов
    несколько занятий: ученик выбирает его сам или час назначает директор.
    """

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="section_enrollments", on_delete=models.CASCADE
    )
    section = models.ForeignKey(
        Section, verbose_name=gettext_lazy("Секция"), related_name="enrollments", on_delete=models.PROTECT
    )
    slot = models.ForeignKey(
        SectionSlot,
        verbose_name=gettext_lazy("Час занятия"),
        related_name="enrollments",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    enrolled_at = models.DateTimeField(gettext_lazy("Записался"), default=timezone.now)
    source = models.CharField(gettext_lazy("Откуда запись"), max_length=10, choices=EnrollmentSource.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто записал"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: час назначил директор, а не ученик
    slot_set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто назначил час"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    slot_set_at = models.DateTimeField(gettext_lazy("Когда назначен час"), null=True, blank=True)
    ended_at = models.DateTimeField(gettext_lazy("Вышел из секции"), null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто закрыл запись"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Запись в секцию")
        verbose_name_plural = gettext_lazy("Записи в секции")
        ordering = ("-enrolled_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("student",), condition=models.Q(ended_at__isnull=True), name="one_active_section"
            ),
        ]
        indexes = [models.Index(fields=("slot", "ended_at")), models.Index(fields=("section", "ended_at"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.section}"


class MarkMethod(models.TextChoices):
    QR = "qr", gettext_lazy("По QR")
    MANUAL = "manual", gettext_lazy("Вручную")


class SectionMark(models.Model):
    """Ученик пришёл на занятие в эту дату: по QR или отмечен директором вручную."""

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="section_marks", on_delete=models.CASCADE
    )
    slot = models.ForeignKey(
        SectionSlot, verbose_name=gettext_lazy("Занятие"), related_name="marks", on_delete=models.PROTECT
    )
    date = models.DateField(gettext_lazy("Дата занятия"))
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
        verbose_name = gettext_lazy("Отметка на занятии")
        verbose_name_plural = gettext_lazy("Отметки на занятиях")
        ordering = ("-date", "-marked_at")
        constraints = [models.UniqueConstraint(fields=("student", "slot", "date"), name="unique_section_mark")]
        indexes = [models.Index(fields=("slot", "date")), models.Index(fields=("student", "-date"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.slot} · {self.date}"


class SessionEnd(models.Model):
    """Директор закончил занятие раньше расписания: отметки по QR на эту дату закрыты."""

    slot = models.ForeignKey(
        SectionSlot, verbose_name=gettext_lazy("Занятие"), related_name="ends_early", on_delete=models.CASCADE
    )
    date = models.DateField(gettext_lazy("Дата занятия"))
    ended_at = models.DateTimeField(gettext_lazy("Когда закончено"), default=timezone.now)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто закончил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Законченное занятие")
        verbose_name_plural = gettext_lazy("Законченные занятия")
        constraints = [models.UniqueConstraint(fields=("slot", "date"), name="unique_session_end")]

    def __str__(self) -> str:
        return f"{self.slot} · {self.date}"


class SectionSettings(models.Model):
    """Настройка записи на секции — одна строка на школу.

    «Запись открыта до» — дата и время, а правила школы (`core.SchoolRule`)
    хранят только числа; и ведёт её директор спорта, а не только
    администратор. Пусто — запись закрыта.
    """

    enroll_until = models.DateTimeField(gettext_lazy("Запись на секции открыта до"), null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто поменял"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_at = models.DateTimeField(gettext_lazy("Когда поменяли"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Настройка записи на секции")
        verbose_name_plural = gettext_lazy("Настройки записи на секции")

    def __str__(self) -> str:
        return str(self.enroll_until or "")


# --- Билеты ---------------------------------------------------------------------------


class TicketDrop(Archivable):
    """Раздача бесплатных билетов: событие, сколько билетов, когда старт и кому."""

    title = models.CharField(gettext_lazy("Событие"), max_length=250)
    event_at = models.DateTimeField(gettext_lazy("Когда событие"))
    place = models.CharField(gettext_lazy("Где"), max_length=200)
    count = models.PositiveSmallIntegerField(gettext_lazy("Сколько билетов"))
    opens_at = models.DateTimeField(gettext_lazy("Старт раздачи"))
    pickup = models.CharField(gettext_lazy("Где и до когда забрать"), max_length=250)
    grade_from = models.PositiveSmallIntegerField(gettext_lazy("С класса"), default=8)
    grade_to = models.PositiveSmallIntegerField(gettext_lazy("По класс"), default=11)
    offer_minutes = models.PositiveSmallIntegerField(gettext_lazy("Минут на ответ из очереди"), default=30)
    announced_at = models.DateTimeField(gettext_lazy("Анонс разослан"), null=True, blank=True)
    reminded_at = models.DateTimeField(gettext_lazy("Напоминание разослано"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто опубликовал"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    is_fictional = models.BooleanField(gettext_lazy("Вымышленная"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Опубликована"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Раздача билетов")
        verbose_name_plural = gettext_lazy("Раздачи билетов")
        ordering = ("-opens_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(grade_to__gte=models.F("grade_from")), name="ticket_grades_ordered"
            ),
            models.CheckConstraint(condition=models.Q(count__gte=1), name="ticket_count_positive"),
        ]

    def __str__(self) -> str:
        return self.title


class ClaimStatus(models.TextChoices):
    RECEIVED = "received", gettext_lazy("Получил")
    QUEUED = "queued", gettext_lazy("В очереди")
    OFFERED = "offered", gettext_lazy("Предложен")
    DECLINED = "declined", gettext_lazy("Отказался")
    EXPIRED = "expired", gettext_lazy("Истёк")
    LEFT = "left", gettext_lazy("Вышел из очереди")
    MISSED = "missed", gettext_lazy("Не забрал")


#: статусы, в которых билет занят: роздан или предложен из очереди
HELD = (ClaimStatus.RECEIVED, ClaimStatus.OFFERED)


class TicketClaim(models.Model):
    """Нажатие «Забрать» учеником: билет, место в очереди или отказ.

    Время нажатия хранится с микросекундами — по нему идёт очередь.
    Место в очереди не хранится: оно считается по времени нажатия
    среди тех, кто ещё ждёт.
    """

    drop = models.ForeignKey(
        TicketDrop, verbose_name=gettext_lazy("Раздача"), related_name="claims", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="ticket_claims", on_delete=models.CASCADE
    )
    pressed_at = models.DateTimeField(gettext_lazy("Нажал"), default=timezone.now)
    status = models.CharField(gettext_lazy("Статус"), max_length=10, choices=ClaimStatus.choices)
    #: билет пришёл из очереди, а не первым нажатием
    from_queue = models.BooleanField(gettext_lazy("Из очереди"), default=False)
    offered_at = models.DateTimeField(gettext_lazy("Предложен"), null=True, blank=True)
    offer_until = models.DateTimeField(gettext_lazy("Ответить до"), null=True, blank=True)
    decided_at = models.DateTimeField(gettext_lazy("Когда изменился статус"), null=True, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Заявка на билет")
        verbose_name_plural = gettext_lazy("Заявки на билеты")
        ordering = ("pressed_at", "id")
        constraints = [models.UniqueConstraint(fields=("drop", "student"), name="one_ticket_claim")]
        indexes = [
            models.Index(fields=("drop", "status", "pressed_at")),
            models.Index(fields=("status", "offer_until")),
        ]

    def __str__(self) -> str:
        return f"{self.student} · {self.drop}"
