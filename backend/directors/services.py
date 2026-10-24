"""Действия кабинетов директоров: звонок, задача, олимпиада, освобождение, заявка, эссе.

Вьюхи только разбирают запрос и проверяют право по реестру
(`core.domains.CABINET_WRITERS`); что происходит с записью — здесь, одним
местом, чтобы и экран, и посев, и тесты шли тем же путём. Всё, что касается
ученика, пишется в его журнал событием (`core.audit.record_event`).
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from core.audit import record_event
from directors.models import (
    ApplicationKind,
    ApplicationStatus,
    CallOutcome,
    LessonRelease,
    Olympiad,
    OlympiadEntry,
    OlympiadResult,
    ParentCall,
    SportApplication,
    SportEvent,
    StaffTask,
    StaffTaskStatus,
)


class Refused(ValueError):
    """Так сделать нельзя — текст объясняет почему."""


def _title(user) -> str:
    return (getattr(user, "full_name", "") or getattr(user, "email", "") or "")[:250]


# --- Звонки ------------------------------------------------------------------------


@transaction.atomic
def record_call(*, student, outcome: str, note: str = "", contact=None, rule: str = "", actor) -> ParentCall:
    """Записать итог звонка: строка истории и событие «Звонок родителям» в карточке."""
    if outcome not in CallOutcome.values:
        raise Refused(_("Выберите итог звонка"))
    if contact is not None and contact.student_id != student.pk:
        raise Refused(_("Это контакт другого ученика"))
    row = ParentCall.objects.create(
        student=student,
        contact=contact,
        outcome=outcome,
        note=note.strip()[:2000],
        rule=rule[:40],
        called_by=actor,
        called_by_title=_title(actor),
    )
    text = f"{row.get_outcome_display()}: {row.note}" if row.note else str(row.get_outcome_display())
    record_event(student=student, code="parent_call", text=text, actor=actor)
    return row


# --- Задачи сотрудникам -------------------------------------------------------------


def set_task(*, title: str, due: dt.date, assignee, actor) -> StaffTask:
    from core.domains import STAFF_TASK_ASSIGNEES

    title = title.strip()
    if not title:
        raise Refused(_("Напишите задачу"))
    if assignee is None or assignee.role not in STAFF_TASK_ASSIGNEES or not assignee.is_active:
        raise Refused(_("Задачу ставят учителю, куратору или директору"))
    if assignee.pk == getattr(actor, "pk", None):
        raise Refused(_("Себе задачу не ставят"))
    return StaffTask.objects.create(
        title=title[:300], due=due, assignee=assignee, author=actor, author_title=_title(actor)
    )


def mark_done(task: StaffTask) -> StaffTask:
    if task.status not in (StaffTaskStatus.OPEN, StaffTaskStatus.RETURNED):
        raise Refused(_("Задача уже отмечена выполненной"))
    task.status = StaffTaskStatus.DONE
    task.done_at = timezone.now()
    task.save(update_fields=["status", "done_at", "updated_at"])
    return task


def accept(task: StaffTask) -> StaffTask:
    if task.status != StaffTaskStatus.DONE:
        raise Refused(_("Принять можно только выполненную задачу"))
    task.status = StaffTaskStatus.ACCEPTED
    task.accepted_at = timezone.now()
    task.save(update_fields=["status", "accepted_at", "updated_at"])
    return task


def send_back(task: StaffTask, note: str) -> StaffTask:
    if task.status != StaffTaskStatus.DONE:
        raise Refused(_("Вернуть можно только выполненную задачу"))
    if not note.strip():
        raise Refused(_("Напишите, что доделать"))
    task.status = StaffTaskStatus.RETURNED
    task.return_note = note.strip()[:300]
    task.done_at = None
    task.save(update_fields=["status", "return_note", "done_at", "updated_at"])
    return task


def remind(task: StaffTask, *, actor) -> StaffTask:
    """Напоминание исполнителю уведомлением — писем сотрудникам система не шлёт."""
    from core.models import Notification

    if task.status in (StaffTaskStatus.ACCEPTED, StaffTaskStatus.DONE):
        raise Refused(_("Задача уже выполнена"))
    Notification.objects.create(
        recipient=task.assignee,
        kind=Notification.Kind.STAFF_TASK,
        text=_("Напоминание о задаче до {due}: {title}").format(due=f"{task.due:%d.%m}", title=task.title)[:500],
        link="/dashboard",
    )
    task.reminded_at = timezone.now()
    task.save(update_fields=["reminded_at", "updated_at"])
    return task


def is_late(task: StaffTask, on: dt.date | None = None) -> bool:
    day = on or timezone.localdate()
    return task.status in (StaffTaskStatus.OPEN, StaffTaskStatus.RETURNED) and task.due < day


# --- Олимпиады ---------------------------------------------------------------------


def add_entries(olympiad: Olympiad, students) -> int:
    added = 0
    for student in students:
        _row, created = OlympiadEntry.objects.get_or_create(olympiad=olympiad, student=student)
        added += int(created)
    return added


@transaction.atomic
def set_result(entry: OlympiadEntry, result: str, *, actor) -> OlympiadEntry:
    """Результат участника; внесённый — подтверждённая «Олимпиада» в портфолио, одна строка на участие."""
    from students.models import Activity, ActivityCategory

    if result not in OlympiadResult.values:
        raise Refused(_("Выберите результат"))
    entry.result = result
    olympiad = entry.olympiad
    title = f"{olympiad.title} — {entry.get_result_display().lower()}"[:250]
    if result == OlympiadResult.PENDING:
        entry.save(update_fields=["result"])
        return entry
    if entry.activity_id is None:
        entry.activity = Activity.objects.create(
            student=entry.student,
            category=ActivityCategory.OLYMPIAD,
            subject=olympiad.subject,
            title=title,
            date=olympiad.starts,
            is_confirmed=True,
        )
    else:
        Activity.all_objects.filter(pk=entry.activity_id).update(title=title, date=olympiad.starts)
    entry.save(update_fields=["result", "activity"])
    record_event(student=entry.student, code="olympiad_result", text=title, actor=actor)
    return entry


# --- Освобождения ------------------------------------------------------------------


@transaction.atomic
def release(
    *,
    students,
    starts: dt.date,
    ends: dt.date,
    slot_from: int | None,
    slot_to: int | None,
    olympiad: Olympiad | None = None,
    event: SportEvent | None = None,
    actor,
) -> LessonRelease:
    """Освободить учеников от уроков: весь день или уроки «с–по»; учитель и куратор видят пометку."""
    from academics import cache

    students = list(students)
    if not students:
        raise Refused(_("Отметьте учеников"))
    if (olympiad is None) == (event is None):
        raise Refused(_("Выберите олимпиаду или мероприятие"))
    if ends < starts:
        raise Refused(_("Дата «по» раньше даты «с»"))
    if (slot_from is None) != (slot_to is None) or (slot_from is not None and slot_to < slot_from):
        raise Refused(_("Укажите уроки «с» и «по» или весь день"))
    row = LessonRelease.objects.create(
        olympiad=olympiad,
        event=event,
        starts=starts,
        ends=ends,
        slot_from=slot_from,
        slot_to=slot_to,
        created_by=actor,
        created_by_title=_title(actor),
    )
    row.students.set(students)
    cache.invalidate()
    text = f"{row.reason}: {span_text(row)}"
    for student in students:
        record_event(student=student, code="lesson_release", text=text, actor=actor)
    return row


@transaction.atomic
def cancel_release(row: LessonRelease, *, actor) -> None:
    from academics import cache
    from core.archive import archive

    students = list(row.students.all())
    archive(row, actor=actor)
    cache.invalidate()
    for student in students:
        record_event(student=student, code="lesson_release_cancelled", text=row.reason, actor=actor)


def span_text(row: LessonRelease) -> str:
    """«24.10, весь день» или «29.10–30.10, уроки 3–4» — подпись для журнала и выгрузки."""
    days = f"{row.starts:%d.%m}" if row.starts == row.ends else f"{row.starts:%d.%m}–{row.ends:%d.%m}"
    if row.all_day:
        return _("{days}, весь день").format(days=days)
    lessons = str(row.slot_from) if row.slot_from == row.slot_to else f"{row.slot_from}–{row.slot_to}"
    return _("{days}, уроки {lessons}").format(days=days, lessons=lessons)


def releases_between(start: dt.date, end: dt.date, student_ids=None):
    rows = LessonRelease.objects.filter(starts__lte=end, ends__gte=start).select_related("olympiad", "event")
    if student_ids is not None:
        rows = rows.filter(students__in=list(student_ids)).distinct()
    return rows.prefetch_related("students")


def released_map(student_ids, start: dt.date, end: dt.date) -> dict[int, list[LessonRelease]]:
    """`ученик → освобождения`, пересекающие отрезок: для отметок, состава урока и листа куратора."""
    out: dict[int, list[LessonRelease]] = {}
    wanted = set(student_ids)
    for row in releases_between(start, end, wanted):
        for student in row.students.all():
            if student.pk in wanted:
                out.setdefault(student.pk, []).append(row)
    return out


def released_on(found: dict[int, list[LessonRelease]], student_id: int, day: dt.date, slot: int | None = None):
    """Освобождение ученика на день (и урок), если есть."""
    for row in found.get(student_id, ()):
        if slot is None and row.starts <= day <= row.ends:
            return row
        if slot is not None and row.covers(day, slot):
            return row
    return None


def release_label(row: LessonRelease) -> str:
    """«на олимпиаде · Городская по математике · весь день» — чип у куратора и учителя."""
    where = _("на олимпиаде") if row.olympiad_id else _("на соревновании")
    if row.all_day:
        lessons = _("весь день")
    elif row.slot_from == row.slot_to:
        lessons = _("урок {n}").format(n=row.slot_from)
    else:
        lessons = _("уроки {a}–{b}").format(a=row.slot_from, b=row.slot_to)
    return f"{where} · {row.reason} · {lessons}"


# --- Мероприятия и заявки ----------------------------------------------------------


def accepted_players(event: SportEvent) -> int:
    return event.applications.filter(kind=ApplicationKind.PLAY, status=ApplicationStatus.ACCEPTED).count()


def apply(*, event: SportEvent, student, kind: str, comment: str = "") -> SportApplication:
    """Заявка ученика; «приду смотреть» принимается сразу — мест у зрителей не считают."""
    if kind not in ApplicationKind.values:
        raise Refused(_("Выберите: участвовать или смотреть"))
    if event.starts_at < timezone.now():
        raise Refused(_("Мероприятие уже прошло"))
    if kind == ApplicationKind.WATCH and not event.spectators:
        raise Refused(_("Зрителей на это мероприятие не пускают"))
    if SportApplication.objects.filter(event=event, student=student).exists():
        raise Refused(_("Заявка на это мероприятие уже подана"))
    status = ApplicationStatus.ACCEPTED if kind == ApplicationKind.WATCH else ApplicationStatus.PENDING
    return SportApplication.objects.create(
        event=event, student=student, kind=kind, comment=comment.strip()[:300], status=status
    )


def withdraw(application: SportApplication) -> None:
    if application.status == ApplicationStatus.ACCEPTED and application.kind == ApplicationKind.PLAY:
        raise Refused(_("Принятую заявку отменяет директор спорта"))
    application.delete()


@transaction.atomic
def decide(application: SportApplication, status: str, *, actor) -> SportApplication:
    if status not in ApplicationStatus.values:
        raise Refused(_("Выберите решение"))
    event = application.event
    if (
        status == ApplicationStatus.ACCEPTED
        and application.kind == ApplicationKind.PLAY
        and application.status != ApplicationStatus.ACCEPTED
        and event.seats is not None
        and accepted_players(event) >= event.seats
    ):
        raise Refused(_("Все места для участников заняты"))
    application.status = status
    application.decided_by = actor if status != ApplicationStatus.PENDING else None
    application.decided_at = timezone.now() if status != ApplicationStatus.PENDING else None
    application.save(update_fields=["status", "decided_by", "decided_at"])
    if status != ApplicationStatus.PENDING:
        text = f"{event.title}: {application.get_status_display().lower()}"
        record_event(student=application.student, code="sport_application", text=text, actor=actor)
    return application


def release_player(application: SportApplication, *, slot_from, slot_to, actor) -> LessonRelease:
    """«Освободить от уроков» принятого участника — тем же освобождением, что у олимпиад."""
    if application.kind != ApplicationKind.PLAY or application.status != ApplicationStatus.ACCEPTED:
        raise Refused(_("Освободить можно только принятого участника"))
    day = timezone.localtime(application.event.starts_at).date()
    return release(
        students=[application.student],
        starts=day,
        ends=day,
        slot_from=slot_from,
        slot_to=slot_to,
        event=application.event,
        actor=actor,
    )


def release_of(application: SportApplication) -> LessonRelease | None:
    return (
        LessonRelease.objects.filter(event=application.event, students=application.student)
        .order_by("-created_at")
        .first()
    )


# --- Эссе: решение Асем -------------------------------------------------------------


@transaction.atomic
def essay_verdict(essay, *, ok: bool, comment: str, actor):
    """«Норм» — эссе готово, «Не норм» — на правки; комментарий видит ученик. Текст не трогается."""
    from roadmap.models import EssayComment, EssayStatus

    comment = comment.strip()
    if not ok and not comment:
        raise Refused(_("Напишите ученику, что поправить"))
    if essay.status not in (EssayStatus.REVIEW, EssayStatus.DONE, EssayStatus.REVISION):
        raise Refused(_("Эссе ещё не отправлено на проверку"))
    essay.status = EssayStatus.DONE if ok else EssayStatus.REVISION
    essay.save(update_fields=["status", "updated_at"])
    if comment:
        EssayComment.objects.create(essay=essay, version=essay.current_version, author=actor, text=comment[:4000])
    record_event(
        student=essay.student,
        code="essay_verdict",
        text=f"{essay.title}: {essay.get_status_display().lower()}",
        actor=actor,
    )
    return essay
