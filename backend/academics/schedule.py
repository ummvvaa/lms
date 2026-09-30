"""Расписание: серии, уроки строками, правка, накладки, замена, перенос, отмена, архив.

Урок заводится один раз и повторяется каждую неделю до конца года —
и сразу материализуется строками (решение владельца): у отметок и оценок
стабильный внешний ключ, а исключение — обычная правка строки. Прошедшие
уроки не меняются никогда: правка «этот и все следующие» закрывает старую
серию накануне и открывает новую.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from academics import cache
from academics.calendar import SchoolCalendar, date_with_weekday, lesson_groups, today
from academics.cohorts import group_ids_of, member_ids, students_share
from academics.models import Cohort, Course, Lesson, LessonSeries, LessonStatus
from academics.payloads import user_name
from core import stored_text
from core.audit import record_change
from core.domains import Source
from core.models import AuditLog

#: Имя поля журнала для записей о расписании: строка читается словами,
#: а не именем колонки (`core.labels.EXTRA_TITLES`)
SCHEDULE_EVENT = "schedule_change"


class ScheduleRefused(ValueError):
    """Так сделать нельзя — текст объясняет почему."""


@dataclass(frozen=True)
class Conflict:
    """Накладка: вид, слова и два урока."""

    kind: str
    text: str
    lesson_id: int | None
    other_id: int | None

    def as_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "lesson": self.lesson_id, "other": self.other_id}


# --- Журнал изменений расписания -------------------------------------------


def log_change(text: str, *, actor=None, lesson: Lesson | None = None) -> AuditLog:
    """Строка «кто и что поменял в расписании» — тем же журналом, что правки."""
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_role=getattr(actor, "role", "") or "",
        model_label="academics.Lesson",
        object_id=str(lesson.pk) if lesson is not None else "",
        field_name=SCHEDULE_EVENT,
        domain_code="academics",
        old_value="",
        new_value=text[:2000],
        source=Source.MANUAL,
    )


def recent_changes(limit: int = 8) -> list[dict]:
    rows = (
        AuditLog.objects.filter(model_label="academics.Lesson", field_name=SCHEDULE_EVENT)
        .select_related("actor")
        .order_by("-created_at")[:limit]
    )
    return [
        {
            "id": row.pk,
            "when": row.created_at,
            "who": (row.actor.full_name or row.actor.email) if row.actor_id else (row.actor_title or _("система")),
            # фраза хранится по-русски, читающему — на его языке
            "text": stored_text.localize(row.new_value),
            "lesson": int(row.object_id) if row.object_id.isdigit() else None,
        }
        for row in rows
    ]


# --- Материализация ----------------------------------------------------------


def _title(lesson: Lesson) -> str:
    return f"{lesson.course.subject.short_title.lower()} {lesson.course.cohort.name}"


def series_dates(series: LessonSeries, calendar: SchoolCalendar, *, since: dt.date | None = None) -> list[dt.date]:
    """Учебные дни серии: нужный день недели, внутри четвертей, без каникул."""
    start = max(series.starts, since) if since else series.starts
    out = []
    day = start
    while day <= series.ends:
        if day.isoweekday() == series.weekday and calendar.is_school_day(day):
            out.append(day)
        day += dt.timedelta(days=1)
    return out


@transaction.atomic
def materialize(series: LessonSeries, calendar: SchoolCalendar, *, since: dt.date | None = None, actor=None) -> int:
    """Завести строки уроков серии на все её дни. Уже заведённые не трогаются."""
    existing = set(Lesson.all_objects.filter(series=series).values_list("date", flat=True))
    rows = [
        Lesson(
            course=series.course,
            series=series,
            date=day,
            slot=series.slot,
            room=series.room,
            teacher=series.course.teacher,
            created_by=actor if getattr(actor, "pk", None) else None,
        )
        for day in series_dates(series, calendar, since=since)
        if day not in existing
    ]
    Lesson.objects.bulk_create(rows)
    return len(rows)


def _course(subject, teacher, cohort: Cohort) -> Course:
    course = Course.objects.filter(subject=subject, teacher=teacher, cohort=cohort).first()
    if course is None:
        course = Course.objects.create(subject=subject, teacher=teacher, cohort=cohort)
    return course


@transaction.atomic
def create_weekly(
    *,
    subject,
    teacher,
    cohort: Cohort,
    starts: dt.date,
    slot: int,
    room: str,
    calendar: SchoolCalendar,
    actor=None,
    ends: dt.date | None = None,
) -> LessonSeries:
    """Урок каждую неделю с даты до конца года; каникулы и праздники пропускаются."""
    if not calendar.is_school_day(starts):
        raise ScheduleRefused(_("Повторяющийся урок начинается с учебного дня"))
    year_end = ends or (calendar.year.ends if calendar.year else starts + dt.timedelta(days=270))
    course = _course(subject, teacher, cohort)
    series = LessonSeries.objects.create(
        course=course,
        weekday=starts.isoweekday(),
        slot=slot,
        room=room[:40],
        starts=starts,
        ends=year_end,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    materialize(series, calendar, actor=actor)
    first = Lesson.objects.filter(series=series).order_by("date").first()
    log_change(
        stored_text.store(
            stored_text.LESSON_SERIES_ADDED,
            subject=subject.short_title.lower(),
            cohort=cohort.name,
            date=f"{starts:%d.%m.%Y}",
            slot=slot,
        ),
        actor=actor,
        lesson=first,
    )
    return series


@transaction.atomic
def create_once(
    *, subject, teacher, cohort: Cohort, date: dt.date, slot: int, room: str, note: str = "", actor=None
) -> Lesson:
    """Разовый урок: консультация, дополнительный урок."""
    course = _course(subject, teacher, cohort)
    lesson = Lesson.objects.create(
        course=course,
        date=date,
        slot=slot,
        room=room[:40],
        teacher=teacher,
        note=(note or "Разовый урок")[:120],  # i18n-skip: заметка урока хранится в базе как данные
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    log_change(
        stored_text.store(stored_text.LESSON_ADDED, lesson=_title(lesson), date=f"{date:%d.%m.%Y}", slot=slot),
        actor=actor,
        lesson=lesson,
    )
    return lesson


# --- Накладки ----------------------------------------------------------------


# --- Время урока и накладки ----------------------------------------------------
#
# Накладка — пересечение по времени, а не одинаковый номер урока (дефект прода,
# 30.09.2026): у параллелей разные звонки — 1 урок 8–9 классов в 8:00, 10 и 11 —
# в 10:15, и «первый урок» KIOTO и CORNELL у одного учителя — это два разных
# часа дня. Время урока — из звонков его группы; у подгруппы потока — из групп
# потока (`lesson_groups`). Звонка для номера нет — времени не знаем и
# сравниваем, как раньше, по номеру: лучше лишнее предупреждение, чем пропуск.

Span = tuple[dt.time, dt.time]


def span_of(calendar: SchoolCalendar, slot: int, groups) -> Span | None:
    """Начало и конец урока с этим номером по звонкам этих групп."""
    return calendar.bell(slot, groups)


def lesson_span(lesson: Lesson, calendar: SchoolCalendar) -> Span | None:
    return span_of(calendar, lesson.slot, lesson_groups(lesson))


def overlaps(a: Span | None, a_slot: int, b: Span | None, b_slot: int) -> bool:
    """Пересекаются ли два урока по времени; конец одного в начало другого — нет."""
    if a is None or b is None:
        return a_slot == b_slot
    return a[0] < b[1] and b[0] < a[1]


def time_words(span: Span | None, slot: int) -> str:
    """«13:15» или, если звонка нет, «5 урок»."""
    return f"{span[0]:%H:%M}" if span is not None else _("{slot} урок").format(slot=slot)


def lessons_on(date: dt.date):
    """Живые уроки дня со связями — всё, с чем урок может пересечься."""
    return (
        Lesson.objects.filter(date=date)
        .exclude(status=LessonStatus.CANCELLED)
        .select_related("course", "course__subject", "course__cohort", "teacher", "substitute")
        .order_by("slot", "id")
    )


def lessons_overlapping(
    date: dt.date, slot: int, groups, *, calendar: SchoolCalendar | None = None, exclude: int | None = None
) -> list[Lesson]:
    """Уроки дня, которые идут одновременно с уроком `slot` этих групп — по времени."""
    from academics import calendar as school_calendar

    calendar = calendar or school_calendar.load()
    mine = span_of(calendar, slot, groups)
    return [
        other
        for other in lessons_on(date)
        if (exclude is None or other.pk != exclude) and overlaps(mine, slot, lesson_span(other, calendar), other.slot)
    ]


def conflicts_for(
    *,
    date: dt.date,
    slot: int,
    teacher_id: int | None,
    cohort: Cohort,
    room: str = "",
    exclude: int | None = None,
) -> list[Conflict]:
    """Накладки нового или изменённого урока с теми, что идут в то же время.

    Поток из групп с разными звонками — тоже накладка (решение владельца,
    27.09.2026): у такого урока нет одного времени начала.
    """
    out: list[Conflict] = []
    out.extend(bells_conflicts(cohort))
    for other in lessons_overlapping(date, slot, group_ids_of(cohort), exclude=exclude):
        # урок без учителя с другим таким же не накладка: учителя ещё нет
        if teacher_id is not None and other.actual_teacher_id == teacher_id:
            who = other.substitute or other.teacher
            out.append(
                Conflict("teacher", _("{teacher} ведёт два урока сразу").format(teacher=user_name(who)), None, other.pk)
            )
        elif room and other.room and other.room.strip().lower() == room.strip().lower():
            out.append(Conflict("room", _("Кабинет {room} занят дважды").format(room=room), None, other.pk))
        elif students_share(cohort, other.course.cohort, date):
            out.append(
                Conflict(
                    "students",
                    _("У {first} и {second} общие ученики").format(first=cohort.name, second=other.course.cohort.name),
                    None,
                    other.pk,
                )
            )
    return out


def bells_conflicts(cohort: Cohort) -> list[Conflict]:
    """Группы состава живут по разным звонкам — предупреждение, как накладка."""
    from academics import calendar as school_calendar

    groups = group_ids_of(cohort)
    if len(groups) < 2:
        return []
    calendar = school_calendar.load()
    ids = calendar.schedule_ids_of(groups)
    if len(ids) < 2:
        return []
    from students.models import StudyGroup

    codes = {row.pk: row.code for row in StudyGroup.objects.filter(pk__in=groups)}
    parts = []
    for group_id in groups:
        schedule_id = calendar.group_schedule.get(group_id)
        title = calendar.schedule_titles.get(schedule_id, _("общее")) if schedule_id else _("общее")
        parts.append(f"{codes.get(group_id, group_id)} — «{title}»")
    return [Conflict("bells", _("У групп состава разные звонки: {groups}").format(groups=", ".join(parts)), None, None)]


def conflicts_between(start: dt.date, end: dt.date) -> list[dict]:
    """Все накладки периода — парами уроков, которые идут одновременно.

    Уроки дня сравниваются попарно по времени звонков их групп — как в импорте.
    Совместный урок нескольких групп — одна строка урока на поток, накладки
    с самим собой у него нет.
    """
    from academics import calendar as school_calendar

    with cache.scope():
        calendar = school_calendar.load()
        rows = list(
            Lesson.objects.filter(date__gte=start, date__lte=end)
            .exclude(status=LessonStatus.CANCELLED)
            .select_related("course", "course__subject", "course__cohort", "teacher", "substitute")
            .order_by("date", "slot", "id")
        )
        by_day: dict[dt.date, list[tuple[Lesson, Span | None]]] = {}
        for lesson in rows:
            by_day.setdefault(lesson.date, []).append((lesson, lesson_span(lesson, calendar)))
        out: list[dict] = []
        for date, day in by_day.items():
            day.sort(key=lambda pair: (pair[1][0] if pair[1] else dt.time.max, pair[0].slot, pair[0].pk))
            for i, (a, a_span) in enumerate(day):
                for b, b_span in day[i + 1 :]:
                    if not overlaps(a_span, a.slot, b_span, b.slot):
                        continue
                    found = _pair_conflict(a, b, date)
                    if found is not None:
                        when = time_words(_later(a_span, b_span), a.slot)
                        out.append({"date": date, "slot": a.slot, "time": when, **found.as_dict()})
        return out


def _later(a: Span | None, b: Span | None) -> Span | None:
    """Где пересечение начинается: у того, кто начал позже."""
    if a is None or b is None:
        return a or b
    return a if a[0] >= b[0] else b


def _pair_conflict(a: Lesson, b: Lesson, date: dt.date) -> Conflict | None:
    if a.actual_teacher_id is not None and a.actual_teacher_id == b.actual_teacher_id:
        who = a.substitute or a.teacher
        return Conflict("teacher", _("{teacher} ведёт два урока сразу").format(teacher=user_name(who)), a.pk, b.pk)
    if a.room and b.room and a.room.strip().lower() == b.room.strip().lower():
        return Conflict("room", _("Кабинет {room} занят дважды").format(room=a.room), a.pk, b.pk)
    if students_share(a.course.cohort, b.course.cohort, date):
        text = _("У {first} и {second} общие ученики").format(first=a.course.cohort.name, second=b.course.cohort.name)
        return Conflict("students", text, a.pk, b.pk)
    return None


def busy_teacher_ids(lesson: Lesson, *, calendar: SchoolCalendar | None = None) -> dict[int, Lesson]:
    """Кто из учителей ведёт урок одновременно с этим — по времени, а не по номеру."""
    out: dict[int, Lesson] = {}
    for other in lessons_overlapping(
        lesson.date, lesson.slot, lesson_groups(lesson), calendar=calendar, exclude=lesson.pk
    ):
        if other.actual_teacher_id is not None:
            out.setdefault(other.actual_teacher_id, other)
    return out


def substitute_candidates(lesson: Lesson, teachers) -> list[dict]:
    """Кого можно поставить на замену: свободные по времени — первыми, свой предмет — выше.

    Занятый в это время учитель в списке остаётся, но помечен: школа видит,
    почему его нет в выборе, а сервер его всё равно не примет (`substitute`).
    """
    from academics import calendar as school_calendar

    calendar = school_calendar.load()
    busy = busy_teacher_ids(lesson, calendar=calendar)
    out = []
    for teacher in teachers:
        if teacher.pk == lesson.teacher_id:
            continue
        other = busy.get(teacher.pk)
        out.append(
            {
                "id": teacher.pk,
                "free": other is None,
                "busy_with": (
                    f"{other.course.subject.short_title.lower()} {other.course.cohort.name}, "
                    f"{time_words(lesson_span(other, calendar), other.slot)}"
                    if other is not None
                    else ""
                ),
            }
        )
    return out


# --- Правка -------------------------------------------------------------------


def has_marks(lesson: Lesson) -> bool:
    return lesson.marked_at is not None or lesson.attendance.exists() or lesson.grades.exists()


def _refuse_past(lesson: Lesson) -> None:
    if lesson.date < today():
        raise ScheduleRefused(_("Прошедший урок не меняется: это уже история журнала"))


@transaction.atomic
def edit_this(
    lesson: Lesson, *, date: dt.date, slot: int, room: str, teacher=None, reason: str = "", actor=None
) -> Lesson:
    """Только этот урок: дата, номер, кабинет, учитель (как замена).

    У урока без учителя выбранный учитель не замена, а назначенный.
    """
    _refuse_past(lesson)
    changes = {"date": date, "slot": slot, "room": room[:40]}
    if teacher is not None and lesson.teacher_id is None:
        changes["teacher"] = teacher
    elif teacher is not None and teacher.pk != lesson.teacher_id:
        changes["substitute"] = teacher
    elif teacher is not None and teacher.pk == lesson.teacher_id:
        changes["substitute"] = None
    moved = date != lesson.date or slot != lesson.slot
    if moved and lesson.status != LessonStatus.MOVED:
        changes["moved_from_date"] = lesson.date
        changes["moved_from_slot"] = lesson.slot
        changes["status"] = LessonStatus.MOVED
    if reason:
        changes["reason"] = reason[:200]
    _apply(lesson, changes, actor)
    log_change(
        stored_text.store(stored_text.LESSON_CHANGED, date=f"{lesson.date:%d.%m.%Y}", lesson=_title(lesson)),
        actor=actor,
        lesson=lesson,
    )
    return lesson


def _apply(lesson: Lesson, changes: dict, actor) -> None:
    """Записать поля урока в журнал по одному и сохранить."""
    for name, value in changes.items():
        old = getattr(lesson, name)
        record_change(instance=lesson, field_name=name, old_value=old, new_value=value, actor=actor)
        setattr(lesson, name, value)
    lesson.save()


@transaction.atomic
def edit_from(
    lesson: Lesson,
    *,
    subject,
    teacher,
    cohort: Cohort,
    date: dt.date,
    slot: int,
    room: str,
    calendar: SchoolCalendar,
    actor=None,
) -> LessonSeries:
    """Этот и все следующие: старая серия заканчивается накануне, новая идёт с этой даты.

    Уроки старой серии с этой даты уходят: без отметок — насовсем,
    с отметками — в архив (их можно вернуть). Прошедшие не трогаются.
    """
    _refuse_past(lesson)
    series = lesson.series
    if series is None:
        raise ScheduleRefused(_("У разового урока нет серии: меняйте только этот урок"))
    cut = lesson.date
    year_end = series.ends
    _retire_from(series, cut, actor=actor)
    course = _course(subject, teacher, cohort)
    new_series = LessonSeries.objects.create(
        course=course,
        weekday=date.isoweekday(),
        slot=slot,
        room=room[:40],
        starts=date,
        ends=year_end,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    materialize(new_series, calendar, actor=actor)
    first = Lesson.objects.filter(series=new_series).order_by("date").first()
    log_change(
        stored_text.store(
            stored_text.SERIES_CHANGED, date=f"{cut:%d.%m.%Y}", subject=subject.short_title.lower(), cohort=cohort.name
        ),
        actor=actor,
        lesson=first,
    )
    return new_series


def _retire_from(series: LessonSeries, cut: dt.date, *, actor=None) -> int:
    """Закрыть серию накануне `cut`; её уроки с этой даты убрать."""
    from core.archive import archive

    gone = 0
    for row in Lesson.objects.filter(series=series, date__gte=cut):
        if has_marks(row):
            archive(row, actor=actor)
        else:
            row.delete()
        gone += 1
    series.ends = cut - dt.timedelta(days=1)
    if series.ends < series.starts:
        series.delete()
    else:
        series.save(update_fields=["ends"])
    return gone


@transaction.atomic
def substitute(lesson: Lesson, *, teacher, reason: str, actor=None) -> Lesson:
    """Замена на одну дату: заменяющий видит урок у себя и отмечает его."""
    _refuse_past(lesson)
    # занят — по времени звонков: 1 урок 8 класса и 1 урок 10 класса — разные часы
    if teacher.pk in busy_teacher_ids(lesson):
        raise ScheduleRefused(_("Этот учитель в это время ведёт урок"))
    _apply(lesson, {"substitute": teacher, "reason": reason[:200]}, actor)
    log_change(
        stored_text.store(
            stored_text.LESSON_COVER,
            lesson=_title(lesson),
            date=f"{lesson.date:%d.%m.%Y}",
            teacher=teacher.full_name or teacher.email,
        ),
        actor=actor,
        lesson=lesson,
    )
    _notify_teachers(
        lesson,
        lambda: _("Замена на {date}, {slot} урок: {lesson}").format(
            date=date_with_weekday(lesson.date), slot=lesson.slot, lesson=_title(lesson)
        ),
    )
    return lesson


@transaction.atomic
def move(
    lesson: Lesson, *, date: dt.date, slot: int, reason: str, calendar: SchoolCalendar, actor=None, force=False
) -> Lesson:
    """Перенос на другой день или номер. Накладка требует подтверждения."""
    _refuse_past(lesson)
    if not calendar.is_school_day(date):
        raise ScheduleRefused(_("Это не учебный день"))
    found = conflicts_for(
        date=date,
        slot=slot,
        teacher_id=lesson.actual_teacher_id,
        cohort=lesson.course.cohort,
        room=lesson.room,
        exclude=lesson.pk,
    )
    if found and not force:
        raise ScheduleRefused(_("Есть накладка: {conflicts}").format(conflicts="; ".join(c.text for c in found)))
    changes = {"date": date, "slot": slot, "reason": (reason or "Перенос")[:200]}  # i18n-skip: причина хранится в базе
    if lesson.status != LessonStatus.MOVED:
        changes["moved_from_date"] = lesson.date
        changes["moved_from_slot"] = lesson.slot
        changes["status"] = LessonStatus.MOVED
    _apply(lesson, changes, actor)
    log_change(
        stored_text.store(stored_text.LESSON_MOVED, lesson=_title(lesson), date=f"{date:%d.%m.%Y}", slot=slot),
        actor=actor,
        lesson=lesson,
    )
    _notify_all(
        lesson,
        lambda: _("Урок перенесён на {date}, {slot} урок: {lesson}").format(
            date=date_with_weekday(date), slot=slot, lesson=_title(lesson)
        ),
    )
    return lesson


@transaction.atomic
def cancel(lesson: Lesson, *, reason: str, actor=None) -> Lesson:
    """Отмена: урок остаётся в расписании зачёркнутым с причиной."""
    _refuse_past(lesson)
    if not reason.strip():
        raise ScheduleRefused(_("Напишите причину: её увидят ученики"))
    _apply(lesson, {"status": LessonStatus.CANCELLED, "reason": reason[:200]}, actor)
    log_change(
        stored_text.store(stored_text.LESSON_CANCELLED, lesson=_title(lesson), date=f"{lesson.date:%d.%m.%Y}"),
        actor=actor,
        lesson=lesson,
    )
    _notify_all(
        lesson,
        lambda: _("Урок отменён: {lesson}, {date}. {reason}").format(
            lesson=_title(lesson), date=date_with_weekday(lesson.date), reason=reason
        ),
    )
    return lesson


@transaction.atomic
def restore(lesson: Lesson, *, actor=None) -> Lesson:
    """Вернуть как было: снять отмену, замену и перенос."""
    changes: dict = {"substitute": None, "reason": ""}
    if lesson.status == LessonStatus.MOVED and lesson.moved_from_date:
        changes.update(
            {
                "date": lesson.moved_from_date,
                "slot": lesson.moved_from_slot or lesson.slot,
                "moved_from_date": None,
                "moved_from_slot": None,
            }
        )
    changes["status"] = LessonStatus.PLANNED
    _apply(lesson, changes, actor)
    log_change(
        stored_text.store(stored_text.LESSON_RESTORED, lesson=_title(lesson), date=f"{lesson.date:%d.%m.%Y}"),
        actor=actor,
        lesson=lesson,
    )
    return lesson


def delete_preview(lesson: Lesson, scope: str) -> dict:
    """Что уйдёт: сколько уроков и у скольких есть отметки."""
    rows = [lesson]
    if scope == "next" and lesson.series_id:
        rows = list(Lesson.objects.filter(series_id=lesson.series_id, date__gte=lesson.date))
    marked = sum(1 for row in rows if has_marks(row))
    return {
        "count": len(rows),
        "marked": marked,
        "from": lesson.date,
        "to": rows[-1].date if rows else lesson.date,
    }


@transaction.atomic
def delete(lesson: Lesson, *, scope: str, actor=None) -> dict:
    """Удалить урок или серию с этой даты: с отметками — в архив, без — насовсем."""
    from core.archive import archive

    _refuse_past(lesson)
    preview = delete_preview(lesson, scope)
    title = _title(lesson)
    if scope == "next" and lesson.series_id:
        gone = _retire_from(lesson.series, lesson.date, actor=actor)
    else:
        gone = 1
        if has_marks(lesson):
            archive(lesson, actor=actor)
        else:
            lesson.delete()
    log_change(
        stored_text.store(stored_text.SERIES_DELETED, title=title, count=gone, date=f"{preview['from']:%d.%m.%Y}"),
        actor=actor,
    )
    return {**preview, "deleted": gone}


@transaction.atomic
def reassign(course: Course, *, teacher, since: dt.date, actor=None) -> Course:
    """Сменить учителя журнала с даты: уроки с неё переходят к новому."""
    old = course.teacher
    course.teacher = teacher
    course.save(update_fields=["teacher"])
    Lesson.objects.filter(course=course, date__gte=since, substitute__isnull=True).update(teacher=teacher)
    params = {
        "subject": course.subject.short_title.lower(),
        "cohort": course.cohort.name,
        "date": f"{since:%d.%m.%Y}",
        "teacher": user_name(teacher),
    }
    old_name = user_name(old)
    log_change(
        (
            stored_text.store(stored_text.JOURNAL_TEACHER, old=old_name, **params)
            if old_name
            else stored_text.store(stored_text.JOURNAL_TEACHER_FIRST, **params)
        ),
        actor=actor,
    )
    return course


# --- Уведомления -------------------------------------------------------------


def _tell(user, words: Callable[[], str]) -> None:
    """Уведомление об уроке — текст собирается на языке получателя, а не того, кто правил."""
    from core.i18n import language_of
    from core.models import Notification
    from materials.services import notify

    with translation.override(language_of(user)):
        text = words()
    notify(user, kind=Notification.Kind.LESSON_CHANGED, template="{text}", link="/schedule", text=text)


def _notify_teachers(lesson: Lesson, words: Callable[[], str]) -> None:
    for user in {lesson.teacher, lesson.substitute}:
        if user is not None:
            _tell(user, words)


def _notify_all(lesson: Lesson, words: Callable[[], str]) -> None:
    """Учителю и ученикам состава — тем, у кого есть учётная запись."""
    from students.models import Student

    _notify_teachers(lesson, words)
    ids = member_ids(lesson.course.cohort, lesson.date)
    for student in Student.objects.filter(pk__in=ids, user__isnull=False).select_related("user"):
        _tell(student.user, words)


# --- Выборки для экранов ------------------------------------------------------


def lessons_between(start: dt.date, end: dt.date):
    return (
        Lesson.objects.filter(date__gte=start, date__lte=end)
        .select_related("course", "course__subject", "course__cohort", "course__cohort__group", "teacher", "substitute")
        .order_by("date", "slot", "id")
    )


def live_lessons(start: dt.date, end: dt.date) -> list[Lesson]:
    """Живые уроки периода списком — из кэша запроса, если он открыт."""
    store = cache.current()
    if store is not None:
        return store.live_lessons(start, end)
    return list(lessons_between(start, end).exclude(status=LessonStatus.CANCELLED))


def student_lessons(student_id: int, start: dt.date, end: dt.date) -> list[Lesson]:
    """Уроки одного ученика за период — по его составам, без обхода всей школы."""
    from academics.cohorts import cohorts_of_student

    ids = cohorts_of_student(student_id, min(end, today()))
    rows = list(lessons_between(start, end).exclude(status=LessonStatus.CANCELLED).filter(course__cohort_id__in=ids))
    return for_student(rows, student_id)


def for_groups(rows, group_ids: list[int]):
    """Уроки, чей состав задевает эти группы."""
    wanted = set(group_ids)
    return [lesson for lesson in rows if wanted & set(group_ids_of(lesson.course.cohort))]


def for_teacher(rows, teacher_id: int):
    return [lesson for lesson in rows if lesson.actual_teacher_id == teacher_id or lesson.teacher_id == teacher_id]


def for_room(rows, room: str):
    key = room.strip().lower()
    return [lesson for lesson in rows if lesson.room.strip().lower() == key]


def for_student(rows, student_id: int):
    """Уроки ученика: те, в чей состав он входит на дату урока."""
    cache: dict[tuple[int, dt.date], set[int]] = {}
    out = []
    for lesson in rows:
        key = (lesson.course.cohort_id, lesson.date)
        if key not in cache:
            cache[key] = set(member_ids(lesson.course.cohort, lesson.date))
        if student_id in cache[key]:
            out.append(lesson)
    return out


def changed_between(start: dt.date, end: dt.date):
    """Замены, отмены и переносы периода."""
    return [
        lesson
        for lesson in lessons_between(start, end)
        if lesson.status != LessonStatus.PLANNED or lesson.substitute_id is not None
    ]


def stale_unmarked(calendar: SchoolCalendar, start: dt.date, end: dt.date) -> list[Lesson]:
    """Прошедшие живые уроки без отметки за период — по всей школе.

    Урок без учителя сюда не входит: отмечать его некому, пока учителя не назначат.
    """
    return [
        lesson
        for lesson in lessons_between(start, end)
        .filter(status=LessonStatus.PLANNED, marked_at__isnull=True)
        .exclude(teacher__isnull=True, substitute__isnull=True)
        if calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson))
    ]


def moved_ghosts(rows, start: dt.date, end: dt.date) -> list[dict]:
    """Тени перенесённых уроков на прежнем месте — чтобы неделя показала «перенесён на»."""
    out = []
    for lesson in Lesson.objects.filter(
        status=LessonStatus.MOVED, moved_from_date__gte=start, moved_from_date__lte=end
    ).select_related("course", "course__subject", "course__cohort"):
        out.append(
            {
                "lesson": lesson.pk,
                "date": lesson.moved_from_date,
                "slot": lesson.moved_from_slot,
                "moved_to_date": lesson.date,
                "moved_to_slot": lesson.slot,
            }
        )
    return out


def touches_teacher_or_group(
    lesson: Lesson, *, teacher_id: int | None = None, group_ids: list[int] | None = None
) -> bool:
    if teacher_id is not None and lesson.actual_teacher_id == teacher_id:
        return True
    if group_ids and set(group_ids) & set(group_ids_of(lesson.course.cohort)):
        return True
    return False


def year_lessons_count(calendar: SchoolCalendar) -> int:
    return Lesson.objects.filter(date__gte=today()).count() if calendar.year else 0


def series_hours_this_week(start: dt.date, end: dt.date, teacher_id: int | None = None) -> int:
    rows = lessons_between(start, end).exclude(status=LessonStatus.CANCELLED)
    if teacher_id is not None:
        rows = rows.filter(Q(teacher_id=teacher_id, substitute__isnull=True) | Q(substitute_id=teacher_id))
    return rows.count()


def stamp() -> dt.datetime:
    return timezone.now()
