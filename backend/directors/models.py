"""Записи кабинетов директоров (решение владельца, 24.10.2026).

Звонки родителям, отметка «просмотрено» у отчётов, задачи сотрудникам,
олимпиады с участниками, освобождения от уроков и спортивные мероприятия
с заявками учеников. Всё, у чего есть история, — строками с датами
(инвариант №5), состояния — `TextChoices`, JSON нет (инвариант №6).
Кто что пишет — `core.domains.CABINET_WRITERS`, а не вьюхи (инвариант №2).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy

from core.archivable import Archivable
from students.models import Student

# --- Звонки родителям (Салтанат и кураторы) ----------------------------------


class CallOutcome(models.TextChoices):
    REACHED = "reached", gettext_lazy("Дозвонились")
    NO_ANSWER = "no_answer", gettext_lazy("Не ответили")
    CALL_BACK = "call_back", gettext_lazy("Перезвонить")


class ParentCall(Archivable):
    """Итог одного звонка родителю: пишется в карточку ученика и в историю звонков."""

    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="parent_calls", on_delete=models.CASCADE
    )
    contact = models.ForeignKey(
        "students.ParentContact",
        verbose_name=gettext_lazy("Кому звонили"),
        related_name="calls",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    outcome = models.CharField(gettext_lazy("Итог"), max_length=12, choices=CallOutcome.choices)
    note = models.TextField(gettext_lazy("Что сказали родители"), blank=True)
    #: правило обзвона, по которому звонили (`CallRule.code`); пусто — звонок не из списка
    rule = models.CharField(gettext_lazy("Правило обзвона"), max_length=40, blank=True)
    called_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто звонил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    called_by_title = models.CharField(gettext_lazy("Кто звонил на момент звонка"), max_length=250, blank=True)
    called_at = models.DateTimeField(gettext_lazy("Когда"), default=timezone.now)

    class Meta:
        verbose_name = gettext_lazy("Звонок родителю")
        verbose_name_plural = gettext_lazy("Звонки родителям")
        ordering = ("-called_at", "-id")
        indexes = [models.Index(fields=("student", "-called_at")), models.Index(fields=("-called_at",))]

    def __str__(self) -> str:
        return f"{self.student} · {self.get_outcome_display()}"


# --- Отчёты: «просмотрено» ---------------------------------------------------


class ReportSeen(models.Model):
    """Директор открыл отчёт за период и отметил «Просмотрено».

    Сами отчёты не хранятся: они считаются из отметок, уроков, пробников
    и отчётов родителям при каждом открытии. Здесь только след, что человек
    их видел, — по виду отчёта и ключу периода («2026-10-24», «2026-W43», «2026-10»).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=gettext_lazy("Кто"), related_name="+", on_delete=models.CASCADE
    )
    kind = models.CharField(gettext_lazy("Отчёт"), max_length=32)
    period = models.CharField(gettext_lazy("Период"), max_length=16)
    seen_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Просмотр отчёта")
        verbose_name_plural = gettext_lazy("Просмотры отчётов")
        constraints = [models.UniqueConstraint(fields=("user", "kind", "period"), name="unique_report_seen")]

    def __str__(self) -> str:
        return f"{self.user} · {self.kind} · {self.period}"


# --- Задачи сотрудникам (Кымбат) ----------------------------------------------


class StaffTaskStatus(models.TextChoices):
    OPEN = "open", gettext_lazy("Открыта")
    DONE = "done", gettext_lazy("Выполнена")
    ACCEPTED = "accepted", gettext_lazy("Принята")
    RETURNED = "returned", gettext_lazy("Возвращена")


class StaffTask(Archivable):
    """Поручение учителю, куратору или директору: текст, срок, приёмка.

    Исполнитель видит задачу у себя на главной и отмечает «Выполнено»;
    поставивший принимает или возвращает с причиной. Возвращённая снова
    ждёт исполнителя.
    """

    title = models.CharField(gettext_lazy("Задача"), max_length=300)
    due = models.DateField(gettext_lazy("Срок"))
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Исполнитель"),
        related_name="staff_tasks",
        on_delete=models.CASCADE,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто поставил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    author_title = models.CharField(gettext_lazy("Кто поставил на момент постановки"), max_length=250, blank=True)
    status = models.CharField(
        gettext_lazy("Статус"), max_length=10, choices=StaffTaskStatus.choices, default=StaffTaskStatus.OPEN
    )
    #: почему вернули — видит исполнитель
    return_note = models.CharField(gettext_lazy("Почему вернули"), max_length=300, blank=True)
    done_at = models.DateTimeField(gettext_lazy("Выполнена"), null=True, blank=True)
    accepted_at = models.DateTimeField(gettext_lazy("Принята"), null=True, blank=True)
    reminded_at = models.DateTimeField(gettext_lazy("Напомнили"), null=True, blank=True)
    is_fictional = models.BooleanField(gettext_lazy("Вымышленная"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Поставлена"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Изменена"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Задача сотруднику")
        verbose_name_plural = gettext_lazy("Задачи сотрудникам")
        ordering = ("due", "id")
        indexes = [models.Index(fields=("assignee", "status")), models.Index(fields=("status", "due"))]

    def __str__(self) -> str:
        return self.title


# --- Олимпиады (Арман) -------------------------------------------------------------


class OlympiadLevel(models.TextChoices):
    SCHOOL = "school", gettext_lazy("Школьная")
    CITY = "city", gettext_lazy("Городская")
    NATIONAL = "national", gettext_lazy("Республиканская")
    INTERNATIONAL = "international", gettext_lazy("Международная")


class Olympiad(Archivable):
    """Олимпиада школы: предмет, уровень, место и даты. Участники — строками."""

    title = models.CharField(gettext_lazy("Название"), max_length=250)
    subject = models.ForeignKey(
        "directories.OlympiadSubject",
        verbose_name=gettext_lazy("Предмет"),
        related_name="olympiads",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    level = models.CharField(gettext_lazy("Уровень"), max_length=16, choices=OlympiadLevel.choices)
    place = models.CharField(gettext_lazy("Место"), max_length=200, blank=True)
    starts = models.DateField(gettext_lazy("С"))
    ends = models.DateField(gettext_lazy("По"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто добавил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    is_fictional = models.BooleanField(gettext_lazy("Вымышленная"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Добавлена"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Олимпиада")
        verbose_name_plural = gettext_lazy("Олимпиады")
        ordering = ("starts", "id")
        constraints = [
            models.CheckConstraint(condition=models.Q(ends__gte=models.F("starts")), name="olympiad_ends_after_starts")
        ]

    def __str__(self) -> str:
        return self.title


class OlympiadResult(models.TextChoices):
    PENDING = "pending", gettext_lazy("Ждём")
    PARTICIPANT = "participant", gettext_lazy("Участник")
    PRIZE = "prize", gettext_lazy("Призёр")
    WINNER = "winner", gettext_lazy("Победитель")


class OlympiadEntry(Archivable):
    """Участник олимпиады и его результат.

    Внесённый результат один раз заводит подтверждённую «Олимпиаду»
    в портфолио ученика (`activity`), правка результата обновляет ту же
    строку: результат живёт в одном месте, портфолио на него ссылается.
    """

    olympiad = models.ForeignKey(
        Olympiad, verbose_name=gettext_lazy("Олимпиада"), related_name="entries", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="olympiad_entries", on_delete=models.CASCADE
    )
    result = models.CharField(
        gettext_lazy("Результат"), max_length=12, choices=OlympiadResult.choices, default=OlympiadResult.PENDING
    )
    activity = models.OneToOneField(
        "students.Activity",
        verbose_name=gettext_lazy("Строка портфолио"),
        related_name="olympiad_entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Добавлен"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Участник олимпиады")
        verbose_name_plural = gettext_lazy("Участники олимпиад")
        ordering = ("olympiad", "student__last_name", "id")
        constraints = [models.UniqueConstraint(fields=("olympiad", "student"), name="unique_olympiad_entry")]

    def __str__(self) -> str:
        return f"{self.student} · {self.olympiad}"


# --- Спортивные мероприятия (Нурлыбек) ---------------------------------------------


class SportEventKind(models.TextChoices):
    COMPETITION = "competition", gettext_lazy("Соревнование")
    EVENT = "event", gettext_lazy("Мероприятие")


class SportEvent(Archivable):
    """Соревнование или мероприятие школы: ученик видит его в «Спорте» и подаёт заявку."""

    title = models.CharField(gettext_lazy("Название"), max_length=250)
    kind = models.CharField(gettext_lazy("Тип"), max_length=12, choices=SportEventKind.choices)
    sport_type = models.ForeignKey(
        "directories.SportType",
        verbose_name=gettext_lazy("Вид спорта"),
        related_name="events",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    starts_at = models.DateTimeField(gettext_lazy("Дата и время"))
    place = models.CharField(gettext_lazy("Место"), max_length=200)
    #: мест для участников; пусто — без ограничения
    seats = models.PositiveSmallIntegerField(gettext_lazy("Мест для участников"), null=True, blank=True)
    spectators = models.BooleanField(gettext_lazy("Можно прийти зрителем"), default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто добавил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    is_fictional = models.BooleanField(gettext_lazy("Вымышленное"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Добавлено"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Спортивное мероприятие")
        verbose_name_plural = gettext_lazy("Спортивные мероприятия")
        ordering = ("starts_at", "id")

    def __str__(self) -> str:
        return self.title


class ApplicationKind(models.TextChoices):
    PLAY = "play", gettext_lazy("Участвовать")
    WATCH = "watch", gettext_lazy("Приду смотреть")


class ApplicationStatus(models.TextChoices):
    PENDING = "pending", gettext_lazy("Ждёт решения")
    ACCEPTED = "accepted", gettext_lazy("Принята")
    DECLINED = "declined", gettext_lazy("Отклонена")


class SportApplication(models.Model):
    """Заявка ученика на мероприятие: участвовать (с комментарием) или прийти смотреть."""

    event = models.ForeignKey(
        SportEvent, verbose_name=gettext_lazy("Мероприятие"), related_name="applications", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        Student, verbose_name=gettext_lazy("Ученик"), related_name="sport_applications", on_delete=models.CASCADE
    )
    kind = models.CharField(gettext_lazy("Заявка"), max_length=8, choices=ApplicationKind.choices)
    comment = models.CharField(gettext_lazy("Комментарий директору"), max_length=300, blank=True)
    status = models.CharField(
        gettext_lazy("Статус"), max_length=10, choices=ApplicationStatus.choices, default=ApplicationStatus.PENDING
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто решил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(gettext_lazy("Когда решили"), null=True, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Подана"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Заявка на мероприятие")
        verbose_name_plural = gettext_lazy("Заявки на мероприятия")
        ordering = ("-created_at", "-id")
        constraints = [models.UniqueConstraint(fields=("event", "student"), name="unique_sport_application")]

    def __str__(self) -> str:
        return f"{self.student} · {self.event}"


# --- Освобождения от уроков (Арман и Нурлыбек) ----------------------------------


class LessonRelease(Archivable):
    """Освобождение учеников от уроков: олимпиада или мероприятие, даты, весь день или уроки «с–по».

    Пропуск освобождённого урока читается как уважительный («у») — правило
    живёт в `academics.marks.marks_map`, как и у причин за период. Учитель
    видит пометку в составе урока, куратор — чип вместо трёх кнопок.
    """

    olympiad = models.ForeignKey(
        Olympiad,
        verbose_name=gettext_lazy("Олимпиада"),
        related_name="releases",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    event = models.ForeignKey(
        SportEvent,
        verbose_name=gettext_lazy("Мероприятие"),
        related_name="releases",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    starts = models.DateField(gettext_lazy("С"))
    ends = models.DateField(gettext_lazy("По"))
    #: уроки «с–по» по номеру звонка; пусто — весь день
    slot_from = models.PositiveSmallIntegerField(gettext_lazy("С урока"), null=True, blank=True)
    slot_to = models.PositiveSmallIntegerField(gettext_lazy("По урок"), null=True, blank=True)
    students = models.ManyToManyField(Student, verbose_name=gettext_lazy("Ученики"), related_name="lesson_releases")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто освободил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_by_title = models.CharField(gettext_lazy("Кто освободил на момент записи"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Записано"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Освобождение от уроков")
        verbose_name_plural = gettext_lazy("Освобождения от уроков")
        ordering = ("starts", "id")
        constraints = [
            models.CheckConstraint(condition=models.Q(ends__gte=models.F("starts")), name="release_ends_after_starts"),
            models.CheckConstraint(
                condition=models.Q(olympiad__isnull=False) | models.Q(event__isnull=False), name="release_has_reason"
            ),
            models.CheckConstraint(
                condition=(models.Q(slot_from__isnull=True) & models.Q(slot_to__isnull=True))
                | (
                    models.Q(slot_from__isnull=False)
                    & models.Q(slot_to__isnull=False)
                    & models.Q(slot_to__gte=models.F("slot_from"))
                ),
                name="release_slots_pair",
            ),
        ]
        indexes = [models.Index(fields=("starts", "ends"))]

    def __str__(self) -> str:
        return f"{self.reason} · {self.starts:%d.%m}–{self.ends:%d.%m}"

    @property
    def reason(self) -> str:
        source = self.olympiad or self.event
        return source.title if source else ""

    @property
    def all_day(self) -> bool:
        return self.slot_from is None

    def covers(self, day, slot: int) -> bool:
        if not (self.starts <= day <= self.ends):
            return False
        return self.all_day or (self.slot_from <= slot <= self.slot_to)
