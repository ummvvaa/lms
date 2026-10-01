"""Правка расписания, составы, учителя, успеваемость по школе, учебный год — Кымбат и администратор."""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics import calendar as school_calendar
from academics import cohorts as composing
from academics import rights, schedule, teachers
from academics.cache import cached
from academics.calendar import DEFAULT_BELLS, lesson_groups, period_choices, scale_of, today, week_start
from academics.cohorts import group_ids_of, member_ids
from academics.models import (
    AcademicYear,
    Bell,
    BellSchedule,
    Break,
    Cohort,
    CohortKind,
    CohortMembership,
    Course,
    GradingScale,
    Holiday,
    Lesson,
    LessonRequest,
    LessonStatus,
    Quarter,
    ReportCadence,
    ReportSettings,
    RequestStatus,
    Scheme,
    Subject,
)
from academics.payloads import (
    cohort_dict,
    course_dict,
    lesson_dict,
    person,
    student_brief,
    subject_dict,
    teacher_dict,
    user_name,
)
from academics.results import calendar_period, course_context, student_attendance, student_summary
from academics.views import _bad, _cohort, _date, _forbid, _group_param, _int, _lesson_for, _not_found, _teacher
from accounts.models import Role, User
from core import school_rules, stored_text
from core.domains import ROLE_ADMIN
from core.i18n import language_of, render
from students.models import Student, StudyGroup


def _editor(request) -> Response | None:
    if not rights.edits_schedule(request.user.role):
        return _forbid(_("Расписание ведут академический директор и администратор"))
    return None


# --- Неделя расписания -----------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cohort_bells(request):
    """Звонки состава — список «Урок» в формах расписания (решение владельца, 01.10.2026).

    Время — по звонкам групп состава, тем же, что у сетки недели и проверки
    накладок: у 10–11 первый урок в 10:15, а не в 8:30 общих звонков, по
    которым в школе не учится ни одна группа. Состав не задан — общие звонки.
    """
    refusal = _editor(request)
    if refusal:
        return refusal
    calendar = school_calendar.load()
    cohort = _cohort(_int(request.query_params.get("cohort")))
    bells = calendar.bells_of(group_ids_of(cohort)) if cohort is not None else calendar.bells
    return Response({"bells": [{"number": n, "starts": s, "ends": e} for n, (s, e) in sorted(bells.items())]})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def schedule_week(request):
    """Неделя с накладками, изменениями, просьбами и последними правками."""
    refusal = _editor(request)
    if refusal:
        return refusal
    calendar = school_calendar.load()
    start = _date(request.query_params.get("from"), week_start(today()))
    end = start + dt.timedelta(days=6)
    rows = list(schedule.lessons_between(start, end))
    view = str(request.query_params.get("view") or "group")
    key = str(request.query_params.get("key") or "")
    groups = list(StudyGroup.objects.filter(is_active=True).order_by("code"))
    staff = teachers.teachers()
    shown = rows
    view_groups: list[int] = []
    if view == "group":
        picked = _group_param(key) or (groups[0] if groups else None)
        view_groups = [picked.pk] if picked else []
        shown = schedule.for_groups(rows, [picked.pk]) if picked else []
        key = picked.code if picked else ""
    elif view == "teacher":
        teacher_id = _int(key) or (staff[0].pk if staff else None)
        shown = schedule.for_teacher(rows, teacher_id) if teacher_id else []
        key = str(teacher_id or "")
    elif view == "room":
        rooms = sorted({lesson.room for lesson in rows if lesson.room})
        room = key or (rooms[0] if rooms else "")
        shown = schedule.for_room(rows, room) if room else []
        key = room
    conflicts = schedule.conflicts_between(start, end)
    next_conflicts = schedule.conflicts_between(start + dt.timedelta(days=7), start + dt.timedelta(days=13))
    counts = {}
    for lesson in shown:
        if lesson.course.cohort_id not in counts:
            counts[lesson.course.cohort_id] = len(member_ids(lesson.course.cohort, lesson.date))
    pending = LessonRequest.objects.filter(status=RequestStatus.PENDING).select_related(
        "teacher", "lesson", "lesson__course", "lesson__course__subject", "lesson__course__cohort", "lesson__teacher"
    )
    from academics.models import LessonSeries

    return Response(
        {
            "from": start,
            "to": end,
            "today": today(),
            "slots": calendar.slots,
            **schedule.week_rows(calendar, shown, view_groups),
            "view": view,
            "key": key,
            "days": [
                {
                    "date": day,
                    "weekday": school_calendar.WEEKDAYS_SHORT[day.weekday()],
                    "school_day": calendar.is_school_day(day),
                    "is_today": day == today(),
                }
                for day in school_calendar.days_between(start, end)
            ],
            "lessons": [
                lesson_dict(lesson, calendar, students=counts.get(lesson.course.cohort_id)) for lesson in shown
            ],
            "ghosts": schedule.moved_ghosts(shown, start, end, calendar),
            "conflicts": conflicts,
            "conflict_ids": sorted({c["lesson"] for c in conflicts} | {c["other"] for c in conflicts}),
            "next_week_conflicts": len(next_conflicts),
            "changes": [lesson_dict(lesson, calendar) for lesson in schedule.changed_between(start, end)],
            "requests": [
                {
                    "id": r.pk,
                    "teacher": person(r.teacher),
                    "lesson": lesson_dict(r.lesson, calendar),
                    "wanted": r.wanted,
                    "reason": r.reason,
                    "created_at": r.created_at,
                }
                for r in pending
            ],
            "log": schedule.recent_changes(),
            "groups": [{"id": g.pk, "code": g.code} for g in groups],
            "teachers": [person(u) for u in staff],
            "rooms": sorted({lesson.room for lesson in rows if lesson.room} | {p.room for p in _profiles() if p.room}),
            "week_total": sum(1 for lesson in rows if lesson.is_live),
            "series_total": LessonSeries.objects.filter(ends__gte=today()).count(),
            "teachers_total": len(staff),
            "groups_total": len(groups),
            "empty": not Lesson.objects.exists(),
        }
    )


def _profiles():
    from academics.models import TeacherProfile

    return TeacherProfile.objects.all()


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def conflicts_check(request):
    """Проверить накладки до сохранения: учитель, кабинет, общие ученики."""
    refusal = _editor(request)
    if refusal:
        return refusal
    data = request.data
    teacher = _teacher(_int(data.get("teacher")))
    cohort = _cohort(_int(data.get("cohort")))
    date = _date(data.get("date"))
    slot = _int(data.get("slot"))
    if cohort is None or date is None or slot is None:
        return _bad(_("Нужны состав, дата и номер урока"))
    calendar = school_calendar.load()
    found = schedule.conflicts_for(
        date=date,
        slot=slot,
        teacher_id=teacher.pk if teacher else None,
        cohort=cohort,
        room=str(data.get("room") or ""),
        exclude=_int(data.get("exclude")),
    )
    return Response({"conflicts": [c.as_dict() for c in found], "school_day": calendar.is_school_day(date)})


# --- Правка урока --------------------------------------------------------------------


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def lesson_edit(request, pk: int):
    """«Только этот урок» или «этот и все следующие»."""
    refusal = _editor(request)
    if refusal:
        return refusal
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    calendar = school_calendar.load()
    data = request.data
    scope = str(data.get("scope") or "this")
    date = _date(data.get("date"), lesson.date)
    slot = _int(data.get("slot"), lesson.slot)
    room = str(data.get("room") if data.get("room") is not None else lesson.room)
    teacher = _teacher(_int(data.get("teacher"))) if data.get("teacher") else None
    cohort = _cohort(_int(data.get("cohort"))) if data.get("cohort") else lesson.course.cohort
    subject = (
        Subject.objects.filter(pk=_int(data.get("subject"))).first() if data.get("subject") else lesson.course.subject
    )
    # учитель серии: выбранный или прежний; урока без учителя — пусто
    probe_teacher = teacher or lesson.teacher
    found = schedule.conflicts_for(
        date=date,
        slot=slot,
        teacher_id=probe_teacher.pk if probe_teacher else None,
        cohort=cohort,
        room=room,
        exclude=lesson.pk,
    )
    if found and not bool(data.get("force")):
        return Response(
            {
                "detail": _("Есть накладка: {conflicts}").format(conflicts="; ".join(c.text for c in found)),
                "conflicts": [c.as_dict() for c in found],
            },
            status=http.HTTP_409_CONFLICT,
        )
    try:
        if scope == "next":
            series = schedule.edit_from(
                lesson,
                subject=subject,
                teacher=probe_teacher,
                cohort=cohort,
                date=date,
                slot=slot,
                room=room,
                calendar=calendar,
                actor=request.user,
            )
            first = series.lessons.order_by("date").first()
            return Response({"series": series.pk, "lesson": lesson_dict(first, calendar) if first else None})
        schedule.edit_this(
            lesson,
            date=date,
            slot=slot,
            room=room,
            teacher=teacher,
            reason=str(data.get("reason") or ""),
            actor=request.user,
        )
    except schedule.ScheduleRefused as error:
        return _bad(str(error))
    return Response({"lesson": lesson_dict(lesson, calendar)})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def lesson_substitutes(request, pk: int):
    """Кого можно поставить на замену: свободен ли учитель по времени звонков урока."""
    refusal = _editor(request)
    if refusal:
        return refusal
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    return Response({"rows": schedule.substitute_candidates(lesson, teachers.teachers())})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def lesson_substitute(request, pk: int):
    refusal = _editor(request)
    if refusal:
        return refusal
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    teacher = _teacher(_int(request.data.get("teacher")))
    if teacher is None:
        return _bad(_("Выберите заменяющего учителя"))
    try:
        schedule.substitute(lesson, teacher=teacher, reason=str(request.data.get("reason") or ""), actor=request.user)
    except schedule.ScheduleRefused as error:
        return _bad(str(error))
    return Response({"lesson": lesson_dict(lesson, school_calendar.load())})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def lesson_move(request, pk: int):
    refusal = _editor(request)
    if refusal:
        return refusal
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    calendar = school_calendar.load()
    date = _date(request.data.get("date"))
    slot = _int(request.data.get("slot"))
    if date is None or slot is None:
        return _bad(_("Нужны новая дата и номер урока"))
    try:
        schedule.move(
            lesson,
            date=date,
            slot=slot,
            reason=str(request.data.get("reason") or ""),
            calendar=calendar,
            actor=request.user,
            force=bool(request.data.get("force")),
        )
    except schedule.ScheduleRefused as error:
        code = http.HTTP_409_CONFLICT if _is_conflict(error) else http.HTTP_400_BAD_REQUEST
        return Response({"detail": str(error)}, status=code)
    return Response({"lesson": lesson_dict(lesson, calendar)})


def _is_conflict(error: Exception) -> bool:
    """Отказ переноса из-за накладки — ответ 409, остальные отказы — 400.

    Признак — код отказа, если `schedule` его ставит, иначе начало текста:
    «Есть накладка: …» на языке ответа или исходное русское.
    """
    if getattr(error, "code", "") == "conflict":
        return True
    text = str(error)
    prefix = _("Есть накладка: {conflicts}").split("{conflicts}")[0].strip()
    return text.startswith(prefix) or text.startswith("Есть накладка")  # i18n-skip: сравнение с исходным текстом отказа


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def lesson_cancel(request, pk: int):
    refusal = _editor(request)
    if refusal:
        return refusal
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    try:
        schedule.cancel(lesson, reason=str(request.data.get("reason") or ""), actor=request.user)
    except schedule.ScheduleRefused as error:
        return _bad(str(error))
    return Response({"lesson": lesson_dict(lesson, school_calendar.load())})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def lesson_restore(request, pk: int):
    refusal = _editor(request)
    if refusal:
        return refusal
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    schedule.restore(lesson, actor=request.user)
    return Response({"lesson": lesson_dict(lesson, school_calendar.load())})


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@cached
def lesson_delete(request, pk: int):
    """GET — что уйдёт; POST — удалить (с отметками — в архив)."""
    refusal = _editor(request)
    if refusal:
        return refusal
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    scope = str((request.data if request.method == "POST" else request.query_params).get("scope") or "this")
    if request.method == "GET":
        return Response(schedule.delete_preview(lesson, scope))
    try:
        return Response(schedule.delete(lesson, scope=scope, actor=request.user))
    except schedule.ScheduleRefused as error:
        return _bad(str(error))


# --- Составы --------------------------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def cohorts(request):
    """Группы с подгруппами и потоки."""
    refusal = _editor(request)
    if refusal:
        return refusal
    groups = list(StudyGroup.objects.filter(is_active=True).order_by("code"))
    # подгруппа, чьё членство закрыто новым делением, — история журналов,
    # а не состав: в показатели и строки она не входит
    live = set(CohortMembership.objects.filter(until__isnull=True).values_list("cohort_id", flat=True))
    subgroups = [
        c
        for c in Cohort.objects.filter(kind=CohortKind.SUBGROUP, stream__isnull=True).select_related("subject", "group")
        if c.pk in live
    ]
    streams = list(Cohort.objects.filter(kind=CohortKind.STREAM))
    # подгруппы внутри потоков показываются у потока, даже пока в них никого
    inner: dict[int, list[Cohort]] = {}
    for c in (
        Cohort.objects.filter(kind=CohortKind.SUBGROUP, stream__isnull=False).select_related("subject").order_by("name")
    ):
        inner.setdefault(c.stream_id, []).append(c)
    used = {}
    for course in Course.objects.select_related("subject", "teacher", "cohort"):
        used.setdefault(course.cohort_id, []).append(
            f"{course.subject.short.lower()}, "
            + ((person(course.teacher) or {}).get("short") or _("учитель не назначен"))
        )
    from accounts.curators import curator_of

    rows = []
    for group in groups:
        mine = [c for c in subgroups if c.group_id == group.pk]
        assignment = curator_of(group)
        rows.append(
            {
                "id": group.pk,
                "code": group.code,
                "students": group.students.filter(is_active=True).count(),
                "curator": user_name(assignment.curator) if assignment else "",
                "subgroups": [{**cohort_dict(c), "used": used.get(c.pk, [])} for c in mine],
                "streams": [s.short_name or s.name for s in streams if group.pk in group_ids_of(s)],
            }
        )
    not_split = 0
    for group in groups:
        by_subject: dict[int, set[int]] = {}
        for c in subgroups:
            if c.group_id == group.pk:
                by_subject.setdefault(c.subject_id, set()).update(member_ids(c))
        ids = set(group.students.filter(is_active=True).values_list("pk", flat=True))
        for covered in by_subject.values():
            not_split += len(ids - covered)
    return Response(
        {
            "groups": rows,
            "streams": [
                {
                    **cohort_dict(s),
                    "used": used.get(s.pk, []),
                    "subgroups": [{**cohort_dict(c), "used": used.get(c.pk, [])} for c in inner.get(s.pk, [])],
                }
                for s in streams
            ],
            "subjects": [subject_dict(s) for s in Subject.objects.filter(is_active=True)],
            "kpis": {
                "groups": len(groups),
                "students": Student.objects.filter(is_active=True).count(),
                "subgroups": len(subgroups) + sum(len(rows) for rows in inner.values()),
                "subgroup_groups": len({c.group_id for c in subgroups}),
                "streams": len(streams),
                "not_split": not_split,
            },
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@cached
def cohort(request, pk: int):
    """Состав подгруппы или потока: прочитать, поменять членов, удалить неиспользуемый."""
    refusal = _editor(request)
    if refusal:
        return refusal
    row = Cohort.objects.select_related("subject", "group").filter(pk=pk).first()
    if row is None:
        return _not_found()
    if request.method == "GET":
        payload = cohort_dict(row, with_members=True)
        if row.group_id or row.stream_id:
            # подгруппа потока набирается из всех групп потока
            payload["candidates"] = [
                student_brief(s)
                for s in Student.objects.filter(group_id__in=group_ids_of(row), is_active=True).order_by(
                    "last_name", "first_name"
                )
            ]
        payload["used"] = [
            course_dict(c) for c in Course.objects.filter(cohort=row).select_related("subject", "teacher", "cohort")
        ]
        return Response(payload)
    if request.method == "DELETE":
        if Course.objects.filter(cohort=row).exists():
            return Response(
                {"detail": _("Состав стоит в расписании: сначала уберите или перенесите его уроки")},
                status=http.HTTP_409_CONFLICT,
            )
        if row.kind == CohortKind.GROUP:
            return _bad(_("Состав «вся группа» не удаляется"))
        row.delete()
        return Response({"deleted": pk})
    if row.kind == CohortKind.SUBGROUP:
        ids = [int(i) for i in (request.data.get("members") or []) if str(i).isdigit()]
        if not ids:
            return _bad(_("В подгруппе должен быть хотя бы один ученик"))
        since = _date(request.data.get("since"), today())
        composing.set_members(row, ids, since)
        schedule.log_change(
            stored_text.store(stored_text.COHORT_CHANGED, name=row.name, count=len(ids), date=f"{since:%d.%m.%Y}"),
            actor=request.user,
        )
    elif row.kind == CohortKind.STREAM:
        parts = list(
            Cohort.objects.filter(pk__in=[int(i) for i in (request.data.get("parts") or []) if str(i).isdigit()])
        )
        if len(parts) < 2:
            return _bad(_("В потоке хотя бы две части"))
        composing.make_stream(name=str(request.data.get("name") or row.name), parts=parts, stream=row)
        schedule.log_change(stored_text.store(stored_text.STREAM_CHANGED, name=row.name), actor=request.user)
    return Response(cohort_dict(row, with_members=True))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def cohort_split(request):
    """Разделить группу на подгруппы по предмету с даты."""
    refusal = _editor(request)
    if refusal:
        return refusal
    group = _group_param(request.data.get("group"))
    subject = Subject.objects.filter(pk=_int(request.data.get("subject"))).first()
    parts = request.data.get("parts")
    if group is None or subject is None or not isinstance(parts, list) or len(parts) < 2:
        return _bad(_("Нужны группа, предмет и хотя бы две части"))
    lists = [[int(i) for i in part if str(i).isdigit()] for part in parts]
    if any(not part for part in lists):
        return _bad(_("В каждой подгруппе должен быть хотя бы один ученик"))
    since = _date(request.data.get("since"), today())
    made = composing.split_group(
        group=group,
        subject=subject,
        parts=lists,
        since=since,
        rule=str(request.data.get("rule") or ""),
        actor=request.user,
    )
    schedule.log_change(
        stored_text.store(
            stored_text.GROUP_SPLIT, group=group.code, subject=subject.short_title.lower(), count=len(made)
        ),
        actor=request.user,
    )
    return Response({"cohorts": [cohort_dict(c) for c in made]}, status=http.HTTP_201_CREATED)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def cohort_stream(request):
    """Собрать поток из групп и подгрупп."""
    refusal = _editor(request)
    if refusal:
        return refusal
    name = str(request.data.get("name") or "").strip()
    ids = [int(i) for i in (request.data.get("parts") or []) if str(i).isdigit()]
    parts = list(Cohort.objects.filter(pk__in=ids).exclude(kind=CohortKind.STREAM))
    if not name:
        return _bad(_("Нужно название"))
    if len(parts) < 2:
        return _bad(_("В потоке хотя бы две части"))
    stream = composing.make_stream(name=name, parts=parts)
    schedule.log_change(stored_text.store(stored_text.STREAM_BUILT, name=stream.name), actor=request.user)
    return Response(cohort_dict(stream, with_members=True), status=http.HTTP_201_CREATED)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def group_cohorts(request):
    """Составы, к которым можно поставить урок: группы, подгруппы группы, потоки."""
    refusal = _editor(request)
    if refusal:
        return refusal
    rows = []
    for group in StudyGroup.objects.filter(is_active=True).order_by("code"):
        rows.append(cohort_dict(composing.group_cohort(group)))
    for row in (
        Cohort.objects.exclude(kind=CohortKind.GROUP).select_related("subject", "group").order_by("kind", "name")
    ):
        rows.append(cohort_dict(row))
    return Response({"rows": rows})


# --- Учителя ---------------------------------------------------------------------------


def _teacher_row(user: User, calendar) -> dict:
    fill = teachers.week_fill(user, calendar)
    courses = teachers.courses_of(user)
    return {
        **teacher_dict(user),
        "hours": teachers.weekly_hours(user),
        "journals": len(courses),
        "week": fill["week"],
        "unmarked": [lesson_dict(lesson, calendar) for lesson in fill["unmarked"]],
        "fill": fill["fill"],
        "last_marked": lesson_dict(fill["last_marked"], calendar) if fill["last_marked"] else None,
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def teachers_list(request):
    """Учителя: нагрузка, журналы, заполнение за неделю, кто не отметил."""
    refusal = _editor(request)
    if refusal:
        return refusal
    calendar = school_calendar.load()
    rows = [_teacher_row(user, calendar) for user in teachers.teachers()]
    start = week_start(today())
    return Response(
        {
            "rows": rows,
            "kpis": {
                "teachers": len(rows),
                "with_lessons": sum(1 for r in rows if r["hours"]),
                "journals": Course.objects.count(),
                "unmarked_teachers": sum(1 for r in rows if r["unmarked"]),
                "substitutions": Lesson.objects.filter(
                    date__gte=start, date__lte=start + dt.timedelta(days=6), substitute__isnull=False
                ).count(),
            },
            "subjects": [subject_dict(s) for s in Subject.objects.filter(is_active=True)],
            "may_create": request.user.role == ROLE_ADMIN,
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@cached
def teacher_detail(request, pk: int):
    """Учитель: журналы и неотмеченные уроки; PATCH — предметы и кабинет."""
    refusal = _editor(request)
    if refusal:
        return refusal
    user = User.objects.filter(pk=pk, role=Role.TEACHER).first()
    if user is None:
        return _not_found()
    calendar = school_calendar.load()
    if request.method == "PATCH":
        profile = teachers.profile_of(user)
        if "room" in request.data:
            profile.room = str(request.data.get("room") or "")[:40]
            profile.save(update_fields=["room"])
        if "subjects" in request.data:
            ids = [int(i) for i in (request.data.get("subjects") or []) if str(i).isdigit()]
            profile.subjects.set(Subject.objects.filter(pk__in=ids))
    row = _teacher_row(user, calendar)
    row["courses"] = [
        {
            **course_dict(course),
            "hours": course.series.filter(ends__gte=today()).count(),
            "students": len(member_ids(course.cohort)),
        }
        for course in teachers.courses_of(user)
    ]
    return Response(row)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def teacher_remind(request, pk: int):
    """Напомнить учителю обо всех его неотмеченных уроках недели — одним уведомлением."""
    refusal = _editor(request)
    if refusal:
        return refusal
    user = User.objects.filter(pk=pk, role=Role.TEACHER).first()
    if user is None:
        return _not_found()
    return Response({"reminded": _remind(user, school_calendar.load())})


def _remind(user: User, calendar) -> int:
    from academics.teachers import lesson_words
    from core.models import Notification
    from materials.services import notify

    rows = teachers.unmarked_lessons(user, calendar)
    for lesson in rows:
        # уведомление — на языке учителя: шаблон переводит `notify`, номер урока — здесь
        notify(
            user,
            kind=Notification.Kind.LESSON_UNMARKED,
            template=gettext_noop("Куратор напоминает: не отмечен урок {lesson}, {when}"),
            link=f"/lessons/{lesson.pk}",
            lesson=lesson_words(lesson),
            when=render(language_of(user), "{slot} урок", slot=lesson.slot),
        )
    return len(rows)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def teachers_remind_all(request):
    refusal = _editor(request)
    if refusal:
        return refusal
    calendar = school_calendar.load()
    reminded = 0
    for user in teachers.teachers():
        if _remind(user, calendar):
            reminded += 1
    return Response({"teachers": reminded})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def course_reassign(request, pk: int):
    """Сменить учителя журнала с даты."""
    refusal = _editor(request)
    if refusal:
        return refusal
    course = Course.objects.select_related("subject", "cohort", "teacher").filter(pk=pk).first()
    if course is None:
        return _not_found()
    teacher = _teacher(_int(request.data.get("teacher")))
    if teacher is None or teacher.pk == course.teacher_id:
        return _bad(_("Выберите другого учителя"))
    since = _date(request.data.get("since"), today())
    schedule.reassign(course, teacher=teacher, since=since, actor=request.user)
    return Response(course_dict(course))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def course_report_role(request, pk: int):
    """Раздел отчёта родителям у журнала: GE/EEP, SAT Verbal, SAT Math или нет — Кымбат и администратор."""
    from academics.models import ReportRole

    refusal = _editor(request)
    if refusal:
        return refusal
    course = Course.objects.select_related("subject", "cohort", "teacher").filter(pk=pk).first()
    if course is None:
        return _not_found()
    role = str(request.data.get("report_role") or "")
    if role not in ReportRole.values:
        return _bad(_("Раздел — GE/EEP, SAT Verbal, SAT Math или нет"))
    if role != course.report_role:
        # журнал расписания пишется по-русски, как и в `schedule`: подписи разделов — тоже
        with translation.override("ru"):
            before = course.get_report_role_display()
        course.report_role = role
        course.save(update_fields=["report_role"])
        with translation.override("ru"):
            after = course.get_report_role_display()
        schedule.log_change(
            stored_text.store(
                stored_text.JOURNAL_SECTION,
                subject=course.subject.short_title.lower(),
                cohort=course.cohort.name,
                before=before,
                after=after,
            ),
            actor=request.user,
        )
    return Response(course_dict(course))


# --- Успеваемость по школе -----------------------------------------------------------


HEAT_TONE = ((85, "good"), (65, "info"), (40, "warn"), (0, "bad"))


def _tone(pct: float | None) -> str:
    if pct is None:
        return ""
    for edge, tone in HEAT_TONE:
        if pct >= edge:
            return tone
    return "bad"


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def school_grades(request):
    """Тепловая карта группы × предметы, посещаемость, прогноз двоек, журналы без оценок."""
    refusal = _editor(request)
    if refusal:
        return refusal
    return Response(school_grades_payload(str(request.query_params.get("period") or _default_period())))


def school_grades_payload(code: str) -> dict:
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    start, end, title, quarter = calendar_period(calendar, code)
    end = min(end, today())
    groups = list(StudyGroup.objects.filter(is_active=True).order_by("code"))
    subjects = list(Subject.objects.filter(is_active=True, scheme=Scheme.KZ, courses__isnull=False).distinct())
    heat = []
    risk = []
    worst = []
    attendance_all = []
    stats_cache: dict[tuple[int, int], object] = {}
    courses = list(Course.objects.select_related("subject", "cohort", "cohort__group").all())
    contexts = {course.pk: course_context(course, start, end, scale, quarter=quarter) for course in courses}
    for group in groups:
        cells = []
        students = list(Student.objects.filter(group=group, is_active=True))
        for subject in subjects:
            values = []
            for course in courses:
                if course.subject_id != subject.pk or group.pk not in group_ids_of(course.cohort):
                    continue
                context = contexts[course.pk]
                for sid in context.student_ids:
                    if sid in {s.pk for s in students}:
                        stats = context.stats(sid)
                        stats_cache[(course.pk, sid)] = stats
                        if stats.quarter_pct is not None:
                            values.append(stats.quarter_pct)
            avg = round(sum(values) / len(values)) if values else None
            cells.append({"subject": subject.pk, "pct": avg, "tone": _tone(avg)})
        pcts = []
        for student in students:
            totals = student_attendance(student.pk, start, end)
            if totals.pct is not None:
                pcts.append(totals.pct)
                worst.append({**student_brief(student), "attendance": totals.as_dict()})
            lows = [
                (course, stats)
                for (cid, sid), stats in stats_cache.items()
                if sid == student.pk and stats.quarter_grade == 2
                for course in courses
                if course.pk == cid
            ]
            if lows:
                risk.append(
                    {
                        **student_brief(student),
                        "subjects": [f"{c.subject.short} {round(s.quarter_pct)} %" for c, s in lows],
                    }
                )
        att = round(sum(pcts) / len(pcts)) if pcts else None
        if att is not None:
            attendance_all.append(att)
        heat.append({"group": group.code, "group_id": group.pk, "cells": cells, "attendance": att})
    worst.sort(key=lambda r: (r["attendance"]["pct"], r["full_name"]))
    empty_journals = []
    two_weeks = today() - dt.timedelta(days=13)
    for course in courses:
        past = [
            lesson
            for lesson in course.lessons.filter(date__gte=two_weeks, date__lte=today(), status=LessonStatus.PLANNED)
            if calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson))
        ]
        if past and not any(lesson.grades.exists() for lesson in past):
            empty_journals.append(course_dict(course))
    from academics.models import QuarterResult

    finals = QuarterResult.objects.filter(quarter=quarter).values("course").distinct().count() if quarter else 0
    return {
        "period": {"code": code, "title": title, "from": start, "to": end},
        "periods": period_choices(calendar),
        "subjects": [subject_dict(s) for s in subjects],
        "heat": heat,
        "kpis": {
            "attendance": round(sum(attendance_all) / len(attendance_all)) if attendance_all else None,
            "risk": len(risk),
            "empty_journals": len(empty_journals),
            "finals": finals,
            "quarter_ends": (
                quarter.ends if quarter else (calendar.current_quarter().ends if calendar.current_quarter() else None)
            ),
        },
        "risk": risk,
        "worst_attendance": worst[:5],
        "empty_journals": empty_journals,
        "has_courses": bool(courses),
    }


def _default_period() -> str:
    day = today()
    return f"{day.year}-{day.month:02d}"


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def school_grades_cell(request):
    """Ученики группы по предмету: ФО, СОР, «выходит»."""
    refusal = _editor(request)
    if refusal:
        return refusal
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    start, end, title, quarter = calendar_period(calendar, str(request.query_params.get("period") or _default_period()))
    end = min(end, today())
    group = _group_param(request.query_params.get("group"))
    subject = Subject.objects.filter(pk=_int(request.query_params.get("subject"))).first()
    if group is None or subject is None:
        return _not_found()
    rows = []
    courses = [
        c
        for c in Course.objects.filter(subject=subject).select_related("subject", "cohort", "teacher")
        if group.pk in group_ids_of(c.cohort)
    ]
    ids = set(Student.objects.filter(group=group, is_active=True).values_list("pk", flat=True))
    for course in courses:
        context = course_context(course, start, end, scale, quarter=quarter)
        students = {s.pk: s for s in Student.objects.filter(pk__in=context.student_ids).select_related("group")}
        for sid in context.student_ids:
            if sid in ids and sid in students:
                rows.append(
                    {
                        **student_brief(students[sid]),
                        "course": course_dict(course),
                        "stats": context.stats(sid).as_dict(),
                    }
                )
    rows.sort(
        key=lambda r: (r["stats"]["quarter_pct"] if r["stats"]["quarter_pct"] is not None else 999, r["full_name"])
    )
    return Response({"group": group.code, "subject": subject_dict(subject), "period": title, "rows": rows})


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def school_grades_export(request):
    """Тепловая карта книгой."""
    from core.exports import Column, workbook_of_sheets

    refusal = _editor(request)
    if refusal:
        return refusal
    payload = school_grades_payload(str(request.query_params.get("period") or _default_period()))
    subjects = payload["subjects"]
    columns = [Column(_("Группа"), lambda row: row["group"], 14)]
    for index, subject in enumerate(subjects):
        columns.append(Column(subject["short_title"], (lambda i: lambda row: row["cells"][i]["pct"])(index), 12))
    columns.append(Column(_("Посещаемость, %"), lambda row: row["attendance"], 14))
    return workbook_of_sheets(
        filename=_("успеваемость {period}.xlsx").format(period=payload["period"]["title"]),
        sheets=[(_("Группы и предметы"), columns, payload["heat"])],
        request=request,
    )


# --- Успеваемость группы (куратор, Кымбат, администратор) -----------------------------


def group_grades_payload(group: StudyGroup, code: str) -> dict:
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    start, end, title, quarter = calendar_period(calendar, code)
    end = min(end, today())
    students = list(
        Student.objects.filter(group=group, is_active=True).select_related("group").order_by("last_name", "first_name")
    )
    courses = [
        c for c in Course.objects.select_related("subject", "cohort", "teacher") if group.pk in group_ids_of(c.cohort)
    ]
    subjects = []
    seen = set()
    for course in sorted(courses, key=lambda c: (c.subject.order, c.subject.title)):
        if course.subject_id not in seen:
            seen.add(course.subject_id)
            subjects.append(subject_dict(course.subject))
    contexts = {course.pk: course_context(course, start, end, scale, quarter=quarter) for course in courses}
    rows = []
    need = []
    attendance_below = school_rules.value(school_rules.ATTENDANCE_BELOW)
    for student in students:
        cells = []
        for subject in subjects:
            found = None
            for course in courses:
                if course.subject_id == subject["id"] and student.pk in contexts[course.pk].student_ids:
                    found = contexts[course.pk].stats(student.pk)
                    break
            if found is None:
                cells.append({"text": "", "grade": None, "pct": None, "tone": "", "none": _("нет")})
            elif subject["scheme"] == Scheme.FO:
                cells.append(
                    {
                        "text": f"{found.fo_avg}" if found.fo_avg is not None else "",
                        "grade": None,
                        "pct": None,
                        "tone": "",
                        "none": _("нет"),
                    }
                )
            elif found.quarter_grade is not None:
                cells.append(
                    {
                        "text": str(found.final or found.quarter_grade),
                        "grade": found.final or found.quarter_grade,
                        "pct": round(found.quarter_pct, 1),
                        "tone": _grade_tone(found.final or found.quarter_grade),
                        "none": "",
                    }
                )
            else:
                cells.append({"text": "", "grade": None, "pct": None, "tone": "", "none": _("мало")})
        totals = student_attendance(student.pk, start, end)
        row = {
            **student_brief(student),
            "cells": cells,
            "attendance_pct": totals.pct,
            "absent": totals.absent,
            "excused": totals.excused,
        }
        rows.append(row)
        low = [
            f"{subjects[i]['short_title']} {c['grade']}"
            for i, c in enumerate(cells)
            if c["grade"] is not None and c["grade"] <= 2
        ]
        if low or (totals.pct is not None and totals.pct < attendance_below):
            need.append({**student_brief(student), "low": low, "attendance_pct": totals.pct})
    journals = []
    week_ago = today() - dt.timedelta(days=6)
    for course in courses:
        past = [
            lesson
            for lesson in course.lessons.filter(date__gte=week_ago, date__lte=today(), status=LessonStatus.PLANNED)
            if calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson))
        ]
        journals.append({**course_dict(course), "unmarked": sum(1 for lesson in past if not lesson.is_marked)})
    pcts = [r["attendance_pct"] for r in rows if r["attendance_pct"] is not None]
    return {
        "group": group.code,
        "group_id": group.pk,
        "period": {"code": code, "title": title, "from": start, "to": end},
        "periods": period_choices(calendar),
        "subjects": subjects,
        "rows": rows,
        "need_help": need,
        "journals": journals,
        "attendance_below": attendance_below,
        "kpis": {
            "attendance": round(sum(pcts) / len(pcts)) if pcts else None,
            "risk": sum(1 for r in rows if any(c["grade"] == 2 for c in r["cells"])),
            "absent": sum(r["absent"] for r in rows),
            "unmarked": sum(j["unmarked"] for j in journals),
        },
        "has_courses": bool(courses),
    }


def _grade_tone(grade: int | None) -> str:
    return {5: "good", 4: "good", 3: "warn", 2: "bad"}.get(grade or 0, "")


def _group_readable(user, raw) -> StudyGroup | None:
    """Группа, чью успеваемость человек вправе видеть: куратор — свои."""
    from accounts.curators import curated_group_ids
    from core.domains import ROLE_CURATOR

    picked = _group_param(raw)
    if user.role == ROLE_CURATOR:
        mine = curated_group_ids(user)
        if picked is not None and picked.pk in mine:
            return picked
        if picked is None and mine:
            return StudyGroup.objects.filter(pk__in=mine).order_by("code").first()
        return None
    if rights.reads_all(user.role):
        return picked or StudyGroup.objects.filter(is_active=True).order_by("code").first()
    return None


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def group_grades(request):
    """Успеваемость группы по предметам: куратор — своей, Кымбат и администратор — любой."""
    from core.domains import ROLE_CURATOR

    if not (rights.reads_all(request.user.role) or request.user.role == ROLE_CURATOR):
        return _forbid(_("Успеваемость группы видят куратор, академический директор и администратор"))
    group = _group_readable(request.user, request.query_params.get("group"))
    if group is None:
        if request.query_params.get("group"):
            return _not_found()
        return Response(
            {"group": "", "rows": [], "subjects": [], "kpis": {}, "need_help": [], "journals": [], "has_courses": False}
        )
    return Response(group_grades_payload(group, str(request.query_params.get("period") or _default_period())))


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def group_grades_export(request):
    from academics.exports import group_grades_workbook
    from core.domains import ROLE_CURATOR

    if not (rights.reads_all(request.user.role) or request.user.role == ROLE_CURATOR):
        return _forbid(_("Успеваемость группы видят куратор, академический директор и администратор"))
    group = _group_readable(request.user, request.query_params.get("group"))
    if group is None:
        return _not_found()
    payload = group_grades_payload(group, str(request.query_params.get("period") or _default_period()))
    return group_grades_workbook(
        filename=_("успеваемость {group} {period}.xlsx").format(group=group.code, period=payload["period"]["title"]),
        subjects=payload["subjects"],
        rows=payload["rows"],
        group_code=group.code,
        request=request,
    )


# --- Учебный год -------------------------------------------------------------------------


def year_payload() -> dict:
    calendar = school_calendar.load()
    year = calendar.year
    scale = scale_of(year)
    config = school_calendar.report_settings_of(year)
    from academics.reports import cadence_words

    return {
        "year": {"id": year.pk, "title": year.title, "starts": year.starts, "ends": year.ends} if year else None,
        "quarters": [
            {
                "id": q.pk,
                "number": q.number,
                "title": q.title,
                # название на языке читающего: по умолчанию («1 четверть») переводится, своё — как введено
                "name": stored_text.localize(q.title),
                "starts": q.starts,
                "ends": q.ends,
                "closed": q.is_closed,
                "closed_at": q.closed_at,
                "current": q.starts <= today() <= q.ends,
                "past": q.ends < today(),
            }
            for q in calendar.quarters
        ],
        "breaks": [
            {"id": b.pk, "title": b.title, "name": stored_text.localize(b.title), "starts": b.starts, "ends": b.ends}
            for b in calendar.breaks
        ],
        "holidays": [
            {"id": h.pk, "date": h.date, "title": h.title, "name": stored_text.localize(h.title)}
            for h in (year.holidays.all() if year else [])
        ],
        "bells": [{"number": n, "starts": s, "ends": e} for n, (s, e) in sorted(calendar.bells.items())],
        "bell_schedules": bell_schedules_payload(year),
        "scale": {
            "weight_fo": scale.weight_fo,
            "weight_sor": scale.weight_sor,
            "weight_soch": scale.weight_soch,
            "threshold_5": scale.threshold_5,
            "threshold_4": scale.threshold_4,
            "threshold_3": scale.threshold_3,
            "fo_max": scale.fo_max,
            "edit_days": scale.edit_days,
        },
        "reports": {
            "cadence": config.cadence,
            "cadence_title": cadence_words(config),
            "cadences": [{"code": c, "title": t} for c, t in ReportCadence.choices],
            "sections": {
                "attendance": config.section_attendance,
                "grades": config.section_grades,
                "exams": config.section_exams,
                "documents": config.section_documents,
                "curator": config.section_curator,
                "discipline": config.section_discipline,
            },
        },
        "subjects": [subject_dict(s) for s in Subject.objects.all()],
    }


@extend_schema(responses={200: dict})
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@cached
def year(request):
    """Учебный год: четверти, каникулы, праздники, звонки, шкала, отчёты. PATCH — частями."""
    refusal = _editor(request)
    if refusal:
        return refusal
    if request.method == "GET":
        return Response(year_payload())
    data = request.data
    try:
        with transaction.atomic():
            _save_year(data, actor=request.user)
    except ValueError as error:
        return _bad(str(error))
    return Response(year_payload())


def bell_schedules_payload(year) -> list[dict]:
    """Расписания звонков года карточками: название, звонки, группы."""
    if year is None:
        return []
    school_calendar.default_schedule(year)
    out = []
    for row in year.bell_schedules.prefetch_related("groups", "bells").order_by("-is_default", "title"):
        out.append(
            {
                "id": row.pk,
                "title": row.title,
                "name": stored_text.localize(row.title),
                "is_default": row.is_default,
                "groups": sorted(group.code for group in row.groups.all()),
                "bells": [
                    {"number": b.number, "starts": b.starts, "ends": b.ends}
                    for b in sorted(row.bells.all(), key=lambda b: b.number)
                ],
            }
        )
    return out


def _parse_bells(rows) -> list[tuple[int, dt.time, dt.time]]:
    out = []
    for raw in rows or []:
        number = _int(raw.get("number"))
        try:
            starts = dt.time.fromisoformat(str(raw.get("starts")))
            ends = dt.time.fromisoformat(str(raw.get("ends")))
        except ValueError as error:
            raise ValueError(_("Урок {number}: время в виде 08:30").format(number=number)) from error
        if number is None or ends <= starts:
            raise ValueError(_("Урок {number}: конец раньше начала").format(number=number))
        out.append((number, starts, ends))
    return out


def _save_bell_schedule(year, raw: dict) -> BellSchedule:
    """Завести или поправить расписание звонков: название, звонки, группы."""
    row = BellSchedule.objects.filter(year=year, pk=_int(raw.get("id"))).first() if raw.get("id") else None
    if row is None:
        # название по умолчанию — данные школы в базе, не перевод
        row = BellSchedule.objects.create(year=year, title=str(raw.get("title") or "Звонки")[:60])  # i18n-skip: данные
    elif raw.get("title"):
        row.title = str(raw["title"])[:60]
        row.save(update_fields=["title"])
    if "bells" in raw:
        parsed = _parse_bells(raw["bells"])
        Bell.objects.filter(schedule=row).exclude(number__in=[n for n, _s, _e in parsed]).delete()
        for number, starts, ends in parsed:
            Bell.objects.update_or_create(
                schedule=row, number=number, defaults={"year": year, "starts": starts, "ends": ends}
            )
    if "groups" in raw and not row.is_default:
        codes = [str(code) for code in (raw.get("groups") or [])]
        groups = list(StudyGroup.objects.filter(code__in=codes, is_active=True))
        # группа живёт по одному расписанию: из прежнего она уходит
        for other in BellSchedule.objects.filter(year=year).exclude(pk=row.pk):
            other.groups.remove(*groups)
        row.groups.set(groups)
    return row


def _save_year(data: dict, *, actor) -> None:
    year = school_calendar.current_year()
    if "year" in data:
        raw = data["year"] or {}
        starts, ends = _date(raw.get("starts")), _date(raw.get("ends"))
        if starts is None or ends is None or ends <= starts:
            raise ValueError(_("У учебного года нужны даты начала и конца"))
        if year is None:
            AcademicYear.objects.filter(is_current=True).update(is_current=False)
            year = AcademicYear.objects.create(
                title=str(raw.get("title") or f"{starts.year}–{ends.year}")[:20],
                starts=starts,
                ends=ends,
                is_current=True,
            )
        else:
            year.title = str(raw.get("title") or year.title)[:20]
            year.starts, year.ends = starts, ends
            year.save()
    if year is None:
        raise ValueError(_("Сначала заведите учебный год"))
    if "quarters" in data:
        for raw in data["quarters"] or []:
            starts, ends = _date(raw.get("starts")), _date(raw.get("ends"))
            number = _int(raw.get("number"))
            if starts is None or ends is None or number is None:
                continue
            if ends < starts:
                raise ValueError(_("{number} четверть: начало позже конца").format(number=number))
            Quarter.objects.update_or_create(  # i18n-skip: название четверти по умолчанию — данные школы в базе
                year=year,
                number=number,
                defaults={"starts": starts, "ends": ends, "title": str(raw.get("title") or f"{number} четверть")[:40]},
            )
    if "breaks" in data:
        Break.objects.filter(year=year).delete()
        for raw in data["breaks"] or []:
            starts, ends = _date(raw.get("starts")), _date(raw.get("ends"))
            if starts and ends and ends >= starts:
                Break.objects.create(  # i18n-skip: название по умолчанию — данные школы в базе
                    year=year, title=str(raw.get("title") or "Каникулы")[:60], starts=starts, ends=ends
                )
    if "holidays" in data:
        Holiday.objects.filter(year=year).delete()
        for raw in data["holidays"] or []:
            day = _date(raw.get("date"))
            if day:
                Holiday.objects.get_or_create(  # i18n-skip: название по умолчанию — данные школы в базе
                    year=year, date=day, defaults={"title": str(raw.get("title") or "Праздник")[:80]}
                )
    if "bells" in data:
        # прежний вид записи: звонки года — это общее расписание
        _save_bell_schedule(year, {"id": school_calendar.default_schedule(year).pk, "bells": data["bells"]})
    if "bell_schedules" in data:
        for raw in data["bell_schedules"] or []:
            _save_bell_schedule(year, raw)
    if data.get("drop_bell_schedule"):
        row = BellSchedule.objects.filter(year=year, pk=_int(data["drop_bell_schedule"]), is_default=False).first()
        if row is None:
            raise ValueError(_("Общее расписание звонков не удаляется"))
        row.delete()
    if "scale" in data:
        raw = data["scale"] or {}
        scale, _created = GradingScale.objects.get_or_create(year=year)
        for name in (
            "weight_fo",
            "weight_sor",
            "weight_soch",
            "threshold_5",
            "threshold_4",
            "threshold_3",
            "fo_max",
            "edit_days",
        ):
            if name in raw:
                setattr(scale, name, int(raw[name]))
        if scale.weight_fo + scale.weight_sor + scale.weight_soch != 100:
            raise ValueError(
                _("Сумма весов {total}, нужно 100").format(total=scale.weight_fo + scale.weight_sor + scale.weight_soch)
            )
        if not (scale.threshold_5 > scale.threshold_4 > scale.threshold_3):
            raise ValueError(_("Пороги должны идти по убыванию"))
        scale.save()
    if "reports" in data:
        raw = data["reports"] or {}
        config, _created = ReportSettings.objects.get_or_create(year=year)
        if raw.get("cadence") in (ReportCadence.MONTH, ReportCadence.QUARTER):
            config.cadence = raw["cadence"]
        sections = raw.get("sections") or {}
        for key, name in (
            ("attendance", "section_attendance"),
            ("grades", "section_grades"),
            ("exams", "section_exams"),
            ("documents", "section_documents"),
            ("curator", "section_curator"),
            ("discipline", "section_discipline"),
        ):
            if key in sections:
                setattr(config, name, bool(sections[key]))
        config.save()
    if "subjects" in data:
        for raw in data["subjects"] or []:
            code = str(raw.get("code") or "").strip()
            if not code:
                continue
            names = {
                field: str(raw.get(field) or "").strip()[:100] for field in ("title_kk", "title_en") if field in raw
            }
            if set(raw) <= {"code", "title_kk", "title_en"}:
                # только названия на казахском и английском — остальное у предмета не трогается
                Subject.objects.filter(code=code).update(**names)
                continue
            # казахское — для интерфейса и отчётов родителям на казахском, английское — для интерфейса
            defaults = dict(names)
            Subject.objects.update_or_create(
                code=code[:32],
                defaults={
                    **defaults,
                    "title": str(raw.get("title") or code)[:100],
                    "short_title": str(raw.get("short_title") or raw.get("title") or code)[:32],
                    "scheme": raw.get("scheme") if raw.get("scheme") in (Scheme.KZ, Scheme.FO) else Scheme.KZ,
                    "sor_max": _int(raw.get("sor_max"), 15),
                    "soch_max": _int(raw.get("soch_max"), 25),
                    "is_active": bool(raw.get("is_active", True)),
                },
            )
    default = school_calendar.default_schedule(year)
    if default.bells.count() == 0:
        for number, starts, ends in DEFAULT_BELLS:
            Bell.objects.create(
                year=year,
                schedule=default,
                number=number,
                starts=dt.time.fromisoformat(starts),
                ends=dt.time.fromisoformat(ends),
            )
    schedule.log_change(stored_text.store(stored_text.YEAR_SETTINGS), actor=actor)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def quarter_close(request, pk: int):
    """Закрыть или открыть приём итогов четверти. Закрытие собирает отчёты за четверть."""
    from academics.results import close_quarter, open_quarter
    from academics.tasks import build_quarter_reports

    refusal = _editor(request)
    if refusal:
        return refusal
    quarter = Quarter.objects.select_related("year").filter(pk=pk).first()
    if quarter is None:
        return _not_found()
    closed = bool(request.data.get("closed", True))
    if closed:
        close_quarter(quarter, actor=request.user)
        schedule.log_change(stored_text.store(stored_text.RESULTS_CLOSED, quarter=quarter.title), actor=request.user)
        build_quarter_reports.delay(quarter.pk)
    else:
        open_quarter(quarter, actor=request.user)
        schedule.log_change(stored_text.store(stored_text.RESULTS_OPENED, quarter=quarter.title), actor=request.user)
    return Response(
        {"quarter": {"id": quarter.pk, "number": quarter.number, "title": quarter.title, "closed": quarter.is_closed}}
    )


def _unused():  # pragma: no cover
    return student_summary


# --- Импорт расписания из книги школы -------------------------------------------------


def _import_file(request) -> tuple[bytes | None, Response | None]:
    """Файл из запроса или ответ-отказ. Импорт — только у администратора."""
    if request.user.role != ROLE_ADMIN:
        return None, _forbid(_("Импорт расписания — у администратора"))
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return None, _bad(_("Файл не приложен"))
    if not uploaded.name.lower().endswith((".xlsx", ".xlsm")):
        return None, _bad(_("Нужна книга Excel (.xlsx)"))
    return uploaded.read(), None


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def schedule_import_preview(request):
    """Предпросмотр импорта: что создастся, что обновится, предупреждения. Базу не меняет."""
    from academics import schedule_import

    data, refusal = _import_file(request)
    if refusal:
        return refusal
    try:
        report = schedule_import.preview(data)
    except schedule_import.ImportRefused as error:
        return _bad(str(error))
    return Response(report)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def schedule_import_apply(request):
    """Применить файл одной транзакцией. Пароли новых учёток — в ответе, один раз."""
    from academics import schedule_import

    data, refusal = _import_file(request)
    if refusal:
        return refusal
    try:
        report = schedule_import.apply(data, actor=request.user, expected=str(request.data.get("fingerprint") or ""))
    except schedule_import.ImportRefused as error:
        return _bad(str(error))
    if report["errors"]:
        return Response(report, status=http.HTTP_400_BAD_REQUEST)
    response = Response(report)
    # пароли открытым текстом: ни в кэш браузера, ни в прокси
    response["Cache-Control"] = "private, no-store"
    return response
