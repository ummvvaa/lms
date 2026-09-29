"""Расписание: серии, уроки строками, правка, накладки, замена, перенос, отмена, архив.

Урок заводится один раз и повторяется каждую неделю до конца года —
и сразу материализуется строками (решение владельца): у отметок и оценок
стабильный внешний ключ, а исключение — обычная правка строки. Прошедшие
уроки не меняются никогда: правка «этот и все следующие» закрывает старую
серию накануне и открывает новую.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from academics import cache
from academics.calendar import SchoolCalendar, date_with_weekday, lesson_groups, today
from academics.cohorts import group_ids_of, member_ids, students_share
from academics.models import Cohort, Course, Lesson, LessonSeries, LessonStatus
from academics.payloads import user_name
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
            "who": (row.actor.full_name or row.actor.email) if row.actor_id else (row.actor_title or "система"),
            "text": row.new_value,
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
        raise ScheduleRefused("Повторяющийся урок начинается с учебного дня")
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
        f"Добавлен урок: {subject.short_title.lower()} {cohort.name}, каждый {_weekday_word(starts)}, {slot} урок",
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
        note=(note or "Разовый урок")[:120],
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    log_change(f"Добавлен разовый урок: {_title(lesson)}, {date:%d.%m.%Y}, {slot} урок", actor=actor, lesson=lesson)
    return lesson


def _weekday_word(day: dt.date) -> str:
    return ("понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье")[day.weekday()]


# --- Накладки ----------------------------------------------------------------


def lessons_at(date: dt.date, slot: int):
    return (
        Lesson.objects.filter(date=date, slot=slot)
        .exclude(status=LessonStatus.CANCELLED)
        .select_related("course", "course__subject", "course__cohort", "teacher", "substitute")
    )


def conflicts_for(
    *,
    date: dt.date,
    slot: int,
    teacher_id: int | None,
    cohort: Cohort,
    room: str = "",
    exclude: int | None = None,
) -> list[Conflict]:
    """Накладки нового или изменённого урока с теми, что уже стоят в это время.

    Поток из групп с разными звонками — тоже накладка (решение владельца,
    27.09.2026): у такого урока нет одного времени начала.
    """
    out: list[Conflict] = []
    out.extend(bells_conflicts(cohort))
    for other in lessons_at(date, slot):
        if exclude is not None and other.pk == exclude:
            continue
        # урок без учителя с другим таким же не накладка: учителя ещё нет
        if teacher_id is not None and other.actual_teacher_id == teacher_id:
            who = other.substitute or other.teacher
            out.append(Conflict("teacher", f"{user_name(who)} ведёт два урока сразу", None, other.pk))
        elif room and other.room and other.room.strip().lower() == room.strip().lower():
            out.append(Conflict("room", f"Кабинет {room} занят дважды", None, other.pk))
        elif students_share(cohort, other.course.cohort, date):
            out.append(
                Conflict(
                    "students",
                    f"У {cohort.name} и {other.course.cohort.name} общие ученики",
                    None,
                    other.pk,
                )
            )
    return out


def bells_conflicts(cohort: Cohort) -> list[Conflict]:
    """Группы состава живут по разным звонкам — предупреждение, как накладка."""
    from academics import calendar as school_calendar
    from academics.cohorts import group_ids_of

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
        title = calendar.schedule_titles.get(schedule_id, "общее") if schedule_id else "общее"
        parts.append(f"{codes.get(group_id, group_id)} — «{title}»")
    return [Conflict("bells", "У групп состава разные звонки: " + ", ".join(parts), None, None)]


def conflicts_between(start: dt.date, end: dt.date) -> list[dict]:
    """Все накладки периода — парами уроков в одно время."""
    rows = list(
        Lesson.objects.filter(date__gte=start, date__lte=end)
        .exclude(status=LessonStatus.CANCELLED)
        .select_related("course", "course__subject", "course__cohort", "teacher", "substitute")
        .order_by("date", "slot", "id")
    )
    by_slot: dict[tuple[dt.date, int], list[Lesson]] = {}
    for lesson in rows:
        by_slot.setdefault((lesson.date, lesson.slot), []).append(lesson)
    out: list[dict] = []
    for (date, slot), group in by_slot.items():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                found = _pair_conflict(a, b, date)
                if found is not None:
                    out.append({"date": date, "slot": slot, **found.as_dict()})
    return out


def _pair_conflict(a: Lesson, b: Lesson, date: dt.date) -> Conflict | None:
    if a.actual_teacher_id is not None and a.actual_teacher_id == b.actual_teacher_id:
        who = a.substitute or a.teacher
        return Conflict("teacher", f"{user_name(who)} ведёт два урока сразу", a.pk, b.pk)
    if a.room and b.room and a.room.strip().lower() == b.room.strip().lower():
        return Conflict("room", f"Кабинет {a.room} занят дважды", a.pk, b.pk)
    if students_share(a.course.cohort, b.course.cohort, date):
        return Conflict("students", f"У {a.course.cohort.name} и {b.course.cohort.name} общие ученики", a.pk, b.pk)
    return None


# --- Правка -------------------------------------------------------------------


def has_marks(lesson: Lesson) -> bool:
    return lesson.marked_at is not None or lesson.attendance.exists() or lesson.grades.exists()


def _refuse_past(lesson: Lesson) -> None:
    if lesson.date < today():
        raise ScheduleRefused("Прошедший урок не меняется: это уже история журнала")


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
    log_change(f"Изменён урок {lesson.date:%d.%m.%Y}: {_title(lesson)}", actor=actor, lesson=lesson)
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
        raise ScheduleRefused("У разового урока нет серии: меняйте только этот урок")
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
        f"Изменена серия с {cut:%d.%m.%Y}: {subject.short_title.lower()} {cohort.name}", actor=actor, lesson=first
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
    busy = lessons_at(lesson.date, lesson.slot).exclude(pk=lesson.pk)
    if any(other.actual_teacher_id == teacher.pk for other in busy):
        raise ScheduleRefused("Этот учитель в это время ведёт урок")
    _apply(lesson, {"substitute": teacher, "reason": reason[:200]}, actor)
    log_change(
        f"Замена: {_title(lesson)} {lesson.date:%d.%m.%Y} — {teacher.full_name or teacher.email}",
        actor=actor,
        lesson=lesson,
    )
    _notify_teachers(lesson, f"Замена на {date_with_weekday(lesson.date)}, {lesson.slot} урок: {_title(lesson)}")
    return lesson


@transaction.atomic
def move(
    lesson: Lesson, *, date: dt.date, slot: int, reason: str, calendar: SchoolCalendar, actor=None, force=False
) -> Lesson:
    """Перенос на другой день или номер. Накладка требует подтверждения."""
    _refuse_past(lesson)
    if not calendar.is_school_day(date):
        raise ScheduleRefused("Это не учебный день")
    found = conflicts_for(
        date=date,
        slot=slot,
        teacher_id=lesson.actual_teacher_id,
        cohort=lesson.course.cohort,
        room=lesson.room,
        exclude=lesson.pk,
    )
    if found and not force:
        raise ScheduleRefused("Есть накладка: " + "; ".join(c.text for c in found))
    changes = {"date": date, "slot": slot, "reason": (reason or "Перенос")[:200]}
    if lesson.status != LessonStatus.MOVED:
        changes["moved_from_date"] = lesson.date
        changes["moved_from_slot"] = lesson.slot
        changes["status"] = LessonStatus.MOVED
    _apply(lesson, changes, actor)
    log_change(f"Перенос: {_title(lesson)} на {date:%d.%m.%Y}, {slot} урок", actor=actor, lesson=lesson)
    _notify_all(lesson, f"Урок перенесён на {date_with_weekday(date)}, {slot} урок: {_title(lesson)}")
    return lesson


@transaction.atomic
def cancel(lesson: Lesson, *, reason: str, actor=None) -> Lesson:
    """Отмена: урок остаётся в расписании зачёркнутым с причиной."""
    _refuse_past(lesson)
    if not reason.strip():
        raise ScheduleRefused("Напишите причину: её увидят ученики")
    _apply(lesson, {"status": LessonStatus.CANCELLED, "reason": reason[:200]}, actor)
    log_change(f"Отменён урок: {_title(lesson)} {lesson.date:%d.%m.%Y}", actor=actor, lesson=lesson)
    _notify_all(lesson, f"Урок отменён: {_title(lesson)}, {date_with_weekday(lesson.date)}. {reason}")
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
    log_change(f"Урок возвращён как было: {_title(lesson)} {lesson.date:%d.%m.%Y}", actor=actor, lesson=lesson)
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
    log_change(f"Удалено: {title}, уроков {gone} с {preview['from']:%d.%m.%Y}", actor=actor)
    return {**preview, "deleted": gone}


@transaction.atomic
def reassign(course: Course, *, teacher, since: dt.date, actor=None) -> Course:
    """Сменить учителя журнала с даты: уроки с неё переходят к новому."""
    old = course.teacher
    course.teacher = teacher
    course.save(update_fields=["teacher"])
    Lesson.objects.filter(course=course, date__gte=since, substitute__isnull=True).update(teacher=teacher)
    log_change(
        f"Журнал {course.subject.short_title.lower()} {course.cohort.name}: с {since:%d.%m.%Y} ведёт "
        f"{user_name(teacher)} вместо {user_name(old) or 'неназначенного учителя'}",
        actor=actor,
    )
    return course


# --- Уведомления -------------------------------------------------------------


def _notify_teachers(lesson: Lesson, text: str) -> None:
    from core.models import Notification
    from materials.services import notify

    for user in {lesson.teacher, lesson.substitute}:
        if user is not None:
            notify(user, kind=Notification.Kind.LESSON_CHANGED, template="{text}", link="/schedule", text=text)


def _notify_all(lesson: Lesson, text: str) -> None:
    """Учителю и ученикам состава — тем, у кого есть учётная запись."""
    from core.models import Notification
    from materials.services import notify
    from students.models import Student

    _notify_teachers(lesson, text)
    ids = member_ids(lesson.course.cohort, lesson.date)
    for student in Student.objects.filter(pk__in=ids, user__isnull=False).select_related("user"):
        notify(student.user, kind=Notification.Kind.LESSON_CHANGED, template="{text}", link="/schedule", text=text)


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
