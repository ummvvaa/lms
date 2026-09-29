"""Общее API учебной части: справка, уроки, урок, просьбы, причины, оценки ученика, посещаемость, риски.

Все вьюхи — функции: у учебной части нет доменных сериализаторов, права
считаются по `academics.rights`, границы — по `core.scope`. Чужой урок
и чужой ученик — 404, не 403 (по 403 видно, что запись существует).
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics import calendar as school_calendar
from academics import marks as marking
from academics import rights, schedule
from academics.cache import cached
from academics.calendar import (
    WEEKDAYS_SHORT,
    date_with_weekday,
    lesson_groups,
    month_title,
    period_choices,
    scale_of,
    today,
    week_start,
)
from academics.cohorts import group_ids_of, member_ids
from academics.models import (
    Excuse,
    Lesson,
    LessonKind,
    LessonRequest,
    LessonStatus,
    RequestStatus,
    Subject,
)
from academics.payloads import course_dict, kind_label, lesson_dict, person, student_brief, subject_dict, user_name
from academics.results import calendar_period, student_attendance, student_summary, unexcused_days
from accounts.curators import curated_group_ids
from core.domains import ROLE_CURATOR, ROLE_STUDENT, ROLE_TEACHER
from core.scope import sees_student, visible_students
from students.models import Student, StudyGroup


def _forbid(detail: str) -> Response:
    return Response({"detail": detail}, status=http.HTTP_403_FORBIDDEN)


def _not_found() -> Response:
    return Response({"detail": "Не найдено"}, status=http.HTTP_404_NOT_FOUND)


def _bad(detail: str) -> Response:
    return Response({"detail": detail}, status=http.HTTP_400_BAD_REQUEST)


def _date(raw, default: dt.date | None = None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return default


def _int(raw, default=None):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# --- Справка -------------------------------------------------------------------


def meta_payload(user) -> dict:
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    config = school_calendar.report_settings_of(calendar.year)
    day = today()
    rooms = sorted(
        {
            *Lesson.objects.filter(date__gte=day - dt.timedelta(days=30))
            .exclude(room="")
            .values_list("room", flat=True),
            *(row.room for row in _profiles() if row.room),
        }
    )
    return {
        "today": day,
        "today_words": date_with_weekday(day),
        "now_slot": calendar.current_slot(),
        "year": (
            {
                "id": calendar.year.pk,
                "title": calendar.year.title,
                "starts": calendar.year.starts,
                "ends": calendar.year.ends,
            }
            if calendar.year
            else None
        ),
        "quarters": [
            {
                "id": q.pk,
                "number": q.number,
                "title": q.title,
                "starts": q.starts,
                "ends": q.ends,
                "closed": q.is_closed,
                "current": q.starts <= day <= q.ends,
            }
            for q in calendar.quarters
        ],
        "current_quarter": (calendar.current_quarter().number if calendar.current_quarter() else None),
        "bells": [{"number": n, "starts": s, "ends": e} for n, (s, e) in sorted(calendar.bells.items())],
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
        "reports": {"cadence": config.cadence, "cadence_title": config.get_cadence_display()},
        "subjects": [subject_dict(s) for s in Subject.objects.filter(is_active=True)],
        "rooms": rooms,
        "periods": period_choices(calendar),
        "mark_words": marking.MARK_WORDS,
        "mark_short": marking.MARK_SHORT,
        "kinds": [{"code": code, "title": title} for code, title in LessonKind.choices],
        "may_edit_schedule": rights.edits_schedule(user.role),
        "role": user.role,
    }


def _profiles():
    from academics.models import TeacherProfile

    return TeacherProfile.objects.all()


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def meta(request):
    """Справка учебной части: год, четверти, звонки, шкала, предметы, периоды."""
    return Response(meta_payload(request.user))


# --- Уроки --------------------------------------------------------------------


def _lessons_for(user, start: dt.date, end: dt.date, params) -> list[Lesson] | None:
    """Уроки периода в границах роли и фильтров. `None` — роли расписание не открыто."""
    role = user.role
    rows = list(schedule.lessons_between(start, end))
    if role == ROLE_TEACHER:
        rows = schedule.for_teacher(rows, user.pk)
    elif role == ROLE_CURATOR:
        mine = curated_group_ids(user)
        picked = _group_param(params.get("group"))
        wanted = [picked.pk] if picked is not None and picked.pk in mine else mine
        rows = schedule.for_groups(rows, wanted)
    elif role == ROLE_STUDENT:
        student = getattr(user, "student", None)
        if student is None:
            return []
        rows = schedule.for_student(rows, student.pk)
    elif rights.reads_all(role):
        picked = _group_param(params.get("group"))
        if picked is not None:
            rows = schedule.for_groups(rows, [picked.pk])
        teacher = _int(params.get("teacher"))
        if teacher is not None:
            rows = schedule.for_teacher(rows, teacher)
        room = str(params.get("room") or "").strip()
        if room:
            rows = schedule.for_room(rows, room)
        student = _int(params.get("student"))
        if student is not None:
            rows = schedule.for_student(rows, student)
    else:
        return None
    return rows


def _group_param(raw) -> StudyGroup | None:
    if raw in (None, "", "all"):
        return None
    if str(raw).isdigit():
        return StudyGroup.objects.filter(pk=int(raw)).first()
    return StudyGroup.objects.filter(code__iexact=str(raw).strip()).first()


def _week_bounds(params) -> tuple[dt.date, dt.date]:
    start = _date(params.get("from"))
    end = _date(params.get("to"))
    if start is None:
        start = week_start(today())
    if end is None:
        end = start + dt.timedelta(days=6)
    if (end - start).days > 62:
        end = start + dt.timedelta(days=62)
    return start, end


def _counts(lessons: list[Lesson]) -> dict[int, int]:
    """Число учеников по составу — один расчёт на состав."""
    out: dict[int, int] = {}
    for lesson in lessons:
        if lesson.course.cohort_id not in out:
            out[lesson.course.cohort_id] = len(member_ids(lesson.course.cohort, lesson.date))
    return out


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@cached
def lessons(request):
    """GET — уроки периода в границах роли; POST — новый урок (Кымбат, администратор)."""
    if request.method == "POST":
        return _create_lesson(request)
    calendar = school_calendar.load()
    start, end = _week_bounds(request.query_params)
    rows = _lessons_for(request.user, start, end, request.query_params)
    if rows is None:
        return _forbid("Расписание этой роли не открыто")
    counts = _counts(rows)
    ghosts = schedule.moved_ghosts(rows, start, end)
    if request.user.role == ROLE_TEACHER:
        ghosts = [g for g in ghosts if any(lesson.pk == g["lesson"] for lesson in rows)]
    return Response(
        {
            "from": start,
            "to": end,
            "today": today(),
            "now_slot": calendar.current_slot(),
            "slots": calendar.slots,
            "days": [
                {
                    "date": day,
                    "weekday": WEEKDAYS_SHORT[day.weekday()],
                    "school_day": calendar.is_school_day(day),
                    "is_today": day == today(),
                }
                for day in school_calendar.days_between(start, end)
            ],
            "lessons": [lesson_dict(lesson, calendar, students=counts.get(lesson.course.cohort_id)) for lesson in rows],
            "ghosts": ghosts,
        }
    )


def _create_lesson(request):
    if not rights.edits_schedule(request.user.role):
        return _forbid("Уроки заводят академический директор и администратор")
    calendar = school_calendar.load()
    data = request.data
    subject = Subject.objects.filter(pk=_int(data.get("subject"))).first()
    teacher = _teacher(_int(data.get("teacher")))
    cohort = _cohort(_int(data.get("cohort")))
    date = _date(data.get("date"))
    slot = _int(data.get("slot"))
    # учитель необязателен: урок можно поставить, а учителя назначить потом
    if subject is None or cohort is None or date is None or slot is None:
        return _bad("Нужны предмет, состав, дата и номер урока")
    if data.get("teacher") and teacher is None:
        return _bad("Такого учителя нет")
    room = str(data.get("room") or "").strip()
    repeat = str(data.get("repeat") or "weekly")
    found = schedule.conflicts_for(
        date=date, slot=slot, teacher_id=teacher.pk if teacher else None, cohort=cohort, room=room
    )
    if found and not bool(data.get("force")):
        return Response(
            {"detail": "Есть накладка: " + "; ".join(c.text for c in found), "conflicts": [c.as_dict() for c in found]},
            status=http.HTTP_409_CONFLICT,
        )
    try:
        if repeat == "once":
            lesson = schedule.create_once(
                subject=subject,
                teacher=teacher,
                cohort=cohort,
                date=date,
                slot=slot,
                room=room,
                note=str(data.get("note") or ""),
                actor=request.user,
            )
            return Response({"lesson": lesson_dict(lesson, calendar), "created": 1}, status=http.HTTP_201_CREATED)
        series = schedule.create_weekly(
            subject=subject,
            teacher=teacher,
            cohort=cohort,
            starts=date,
            slot=slot,
            room=room,
            calendar=calendar,
            actor=request.user,
        )
    except schedule.ScheduleRefused as error:
        return _bad(str(error))
    first = series.lessons.order_by("date").first()
    return Response(
        {
            "series": series.pk,
            "created": series.lessons.count(),
            "lesson": lesson_dict(first, calendar) if first else None,
        },
        status=http.HTTP_201_CREATED,
    )


def _teacher(pk):
    from academics.teachers import teaching_users

    if pk is None:
        return None
    return teaching_users().filter(pk=pk).first()


def _cohort(pk):
    from academics.models import Cohort

    if pk is None:
        return None
    return Cohort.objects.filter(pk=pk).first()


def _lesson_for(user, pk: int) -> Lesson | None:
    """Урок в границах роли. Чужой — как несуществующий."""
    lesson = (
        Lesson.objects.select_related(
            "course", "course__subject", "course__cohort", "course__cohort__group", "teacher", "substitute", "marked_by"
        )
        .filter(pk=pk)
        .first()
    )
    if lesson is None:
        return None
    role = user.role
    if rights.reads_all(role) or role == "director_behavior":
        return lesson
    if role == ROLE_TEACHER:
        return lesson if lesson.teacher_id == user.pk or lesson.substitute_id == user.pk else None
    if role == ROLE_CURATOR:
        # свой урок куратор видит и вне своих групп: «учитель + куратор»
        if lesson.teacher_id == user.pk or lesson.substitute_id == user.pk:
            return lesson
        return lesson if set(group_ids_of(lesson.course.cohort)) & set(curated_group_ids(user)) else None
    if role == ROLE_STUDENT:
        student = getattr(user, "student", None)
        if student is not None and student.pk in set(member_ids(lesson.course.cohort, lesson.date)):
            return lesson
        return None
    return None


def _roster(lesson: Lesson, calendar, scale) -> list[dict]:
    """Ученики урока с отметкой, оценкой и короткой статистикой по журналу."""
    from academics.results import course_context

    ids = member_ids(lesson.course.cohort, lesson.date)
    students = {s.pk: s for s in Student.objects.filter(pk__in=ids).select_related("group")}
    marks = marking.marks_map([lesson], ids)
    grades = marking.grades_map([lesson], ids)
    quarter = calendar.quarter_of(lesson.date)
    start = quarter.starts if quarter else lesson.date - dt.timedelta(days=60)
    context = course_context(lesson.course, start, min(lesson.date, today()), scale, quarter=quarter)
    excused = marking.excuses_of(ids, lesson.date, lesson.date)
    out = []
    for sid in ids:
        student = students.get(sid)
        if student is None:
            continue
        grade = grades.get((lesson.pk, sid))
        stats = context.stats(sid)
        out.append(
            {
                **student_brief(student),
                "mark": marks.get((lesson.pk, sid)) if lesson.is_marked else None,
                "grade": grade.value if grade else None,
                "comment": grade.comment if grade else "",
                "excused": marking.is_excused(excused, sid, lesson.date),
                "absences": stats.absent + stats.excused,
                "fo_avg": stats.fo_avg,
            }
        )
    return out


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def lesson_detail(request, pk: int):
    """Урок: факты, состав с отметками и оценками, что можно сделать."""
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    role = request.user.role
    payload = {"lesson": lesson_dict(lesson, calendar), "course": course_dict(lesson.course)}
    series = lesson.series
    payload["repeat"] = (
        f"каждый {lesson_dict(lesson, calendar)['weekday_full']}, до {series.ends:%d.%m.%Y}"
        if series
        else "разовый урок"
    )
    if role == ROLE_STUDENT:
        student = request.user.student
        marks = marking.marks_map([lesson], [student.pk])
        grade = marking.grades_map([lesson], [student.pk]).get((lesson.pk, student.pk))
        payload["mine"] = {
            "mark": marks.get((lesson.pk, student.pk)) if lesson.is_marked else None,
            "grade": grade.value if grade else None,
            "comment": grade.comment if grade else "",
            "homework": lesson.homework,
        }
        return Response(payload)
    payload["roster"] = _roster(lesson, calendar, scale)
    payload["absent"] = [row["short"] for row in payload["roster"] if row["mark"] in ("absent", "excused")]
    payload["late"] = [row["short"] for row in payload["roster"] if row["mark"] == "late"]
    payload["may_mark"] = rights.marks_lesson(request.user, lesson) and lesson.is_live
    payload["may_grade"] = rights.grades_lesson(request.user, lesson) and lesson.is_live
    payload["locked"] = marking.edit_locked(lesson, request.user, scale)
    quarter = calendar.quarter_of(lesson.date)
    payload["quarter_closed"] = bool(quarter and quarter.is_closed)
    payload["may_edit"] = rights.edits_schedule(role)
    payload["may_remind"] = (
        rights.reminds(role)
        and lesson.actual_teacher_id is not None
        and lesson.is_live
        and not lesson.is_marked
        and calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson))
    )
    payload["may_request"] = role == ROLE_TEACHER and lesson.date >= today() and lesson.is_live
    payload["conflicts"] = (
        [
            c.as_dict()
            for c in schedule.conflicts_for(
                date=lesson.date,
                slot=lesson.slot,
                teacher_id=lesson.actual_teacher_id,
                cohort=lesson.course.cohort,
                room=lesson.room,
                exclude=lesson.pk,
            )
        ]
        if rights.edits_schedule(role)
        else []
    )
    payload["scale"] = {"fo_max": scale.fo_max, "edit_days": scale.edit_days}
    return Response(payload)


# --- Отметки и оценки --------------------------------------------------------------


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def lesson_attendance(request, pk: int):
    """Сохранить отметки урока: `rows` или `all_present`."""
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    if not rights.marks_lesson(request.user, lesson):
        return _forbid("Посещаемость отмечает учитель урока")
    calendar = school_calendar.load()
    rows = request.data.get("rows") or []
    if not isinstance(rows, list):
        return _bad("Не переданы отметки")
    try:
        result = marking.save_attendance(
            lesson, rows, actor=request.user, calendar=calendar, all_present=bool(request.data.get("all_present"))
        )
    except marking.MarkRefused as error:
        return _bad(str(error))
    lesson.refresh_from_db()
    scale = scale_of(calendar.year)
    return Response({**result, "lesson": lesson_dict(lesson, calendar), "roster": _roster(lesson, calendar, scale)})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def lesson_grade(request, pk: int):
    """Поставить, изменить или снять оценку одному ученику."""
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    if not rights.grades_lesson(request.user, lesson):
        return _forbid("Оценку ставит учитель урока")
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    student = Student.objects.filter(pk=_int(request.data.get("student"))).first()
    if student is None:
        return _not_found()
    comment = request.data.get("comment")
    try:
        grade = marking.set_grade(
            lesson,
            student,
            request.data.get("value"),
            comment=str(comment) if comment is not None else None,
            actor=request.user,
            calendar=calendar,
            scale=scale,
        )
    except marking.MarkRefused as error:
        return _bad(str(error))
    lesson.refresh_from_db()
    return Response(
        {
            "grade": grade.value if grade else None,
            "comment": grade.comment if grade else "",
            "lesson": lesson_dict(lesson, calendar),
            "roster": _roster(lesson, calendar, scale),
        }
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@cached
def lesson_meta(request, pk: int):
    """Тема, домашнее задание, вид, номер и максимум СОР или СОЧ."""
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    if not (rights.grades_lesson(request.user, lesson) or rights.edits_schedule(request.user.role)):
        return _forbid("Тему и задание пишет учитель урока")
    fields = {k: v for k, v in request.data.items() if k in ("topic", "homework", "kind", "number", "max_score")}
    try:
        marking.set_lesson_meta(lesson, actor=request.user, **fields)
    except (marking.MarkRefused, ValueError) as error:
        return _bad(str(error))
    return Response({"lesson": lesson_dict(lesson, school_calendar.load())})


# --- Просьбы о переносе ---------------------------------------------------------


def _request_dict(row: LessonRequest, calendar) -> dict:
    return {
        "id": row.pk,
        "teacher": person(row.teacher),
        "lesson": lesson_dict(row.lesson, calendar),
        "wanted": row.wanted,
        "reason": row.reason,
        "status": row.status,
        "status_title": row.get_status_display(),
        "answer": row.answer,
        "decided_by": person(row.decided_by),
        "decided_at": row.decided_at,
        "created_at": row.created_at,
    }


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@cached
def requests(request):
    """Просьбы о переносе: учитель — свои, Кымбат и администратор — все."""
    calendar = school_calendar.load()
    role = request.user.role
    if request.method == "GET":
        if role == ROLE_TEACHER:
            rows = LessonRequest.objects.filter(teacher=request.user)
        elif rights.edits_schedule(role):
            rows = LessonRequest.objects.all()
        else:
            return _forbid("Просьбы учителей видят академический директор и администратор")
        rows = rows.select_related(
            "teacher",
            "lesson",
            "lesson__course",
            "lesson__course__subject",
            "lesson__course__cohort",
            "lesson__teacher",
            "decided_by",
        )
        return Response({"rows": [_request_dict(row, calendar) for row in rows[:100]]})
    if role != ROLE_TEACHER:
        return _forbid("Просьбу о переносе подаёт учитель")
    lesson = _lesson_for(request.user, _int(request.data.get("lesson")) or 0)
    if lesson is None:
        return _not_found()
    reason = str(request.data.get("reason") or "").strip()
    if not reason:
        return _bad("Напишите причину")
    if lesson.date < today():
        return _bad("Прошедший урок не переносят")
    row = LessonRequest.objects.create(
        teacher=request.user, lesson=lesson, wanted=str(request.data.get("wanted") or "")[:200], reason=reason[:300]
    )
    from academics.teachers import lesson_words
    from accounts.models import Role, User
    from core.models import Notification
    from materials.services import notify

    for user in User.objects.filter(role__in=(Role.DIRECTOR_EXAM, Role.ADMIN), is_active=True):
        notify(
            user,
            kind=Notification.Kind.LESSON_REQUEST,
            template="Просьба о переносе: {teacher} — {lesson}, {when}",
            link="/schedule",
            teacher=user_name(request.user),
            lesson=lesson_words(lesson),
            when=f"{lesson.slot} урок",
        )
    return Response({"request": _request_dict(row, calendar)}, status=http.HTTP_201_CREATED)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def request_decide(request, pk: int):
    """«Одобрить» переносит урок, «Отклонить» просит ответ."""
    if not rights.edits_schedule(request.user.role):
        return _forbid("Просьбы решают академический директор и администратор")
    row = (
        LessonRequest.objects.select_related(
            "lesson", "teacher", "lesson__course", "lesson__course__subject", "lesson__course__cohort"
        )
        .filter(pk=pk)
        .first()
    )
    if row is None:
        return _not_found()
    if row.status != RequestStatus.PENDING:
        return _bad("Просьба уже решена")
    calendar = school_calendar.load()
    approve = bool(request.data.get("approve"))
    answer = str(request.data.get("answer") or "").strip()
    from academics.teachers import lesson_words
    from core.models import Notification
    from materials.services import notify

    if approve:
        date = _date(request.data.get("date"), row.lesson.date)
        slot = _int(request.data.get("slot"), row.lesson.slot)
        try:
            schedule.move(
                row.lesson,
                date=date,
                slot=slot,
                reason=row.reason,
                calendar=calendar,
                actor=request.user,
                force=bool(request.data.get("force")),
            )
        except schedule.ScheduleRefused as error:
            return _bad(str(error))
        row.status = RequestStatus.APPROVED
        row.answer = answer or f"перенесён на {date:%d.%m}, {slot} урок"
        template = "Просьба о переносе {lesson} одобрена: {answer}"
    else:
        if not answer:
            return _bad("Напишите ответ учителю")
        row.status = RequestStatus.REJECTED
        row.answer = answer[:300]
        template = "Просьба о переносе {lesson} отклонена: {answer}"
    row.decided_by = request.user
    row.decided_at = timezone.now()
    row.save()
    notify(
        row.teacher,
        kind=Notification.Kind.LESSON_REQUEST_DECIDED,
        template=template,
        link="/schedule",
        lesson=lesson_words(row.lesson),
        answer=row.answer,
    )
    row.lesson.refresh_from_db()
    return Response({"request": _request_dict(row, calendar)})


# --- Напоминание учителю ----------------------------------------------------------


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def lesson_remind(request, pk: int):
    """Куратор, Кымбат или администратор напоминает учителю о неотмеченном уроке."""
    if not rights.reminds(request.user.role):
        return _forbid("Напоминают куратор, академический директор и администратор")
    lesson = _lesson_for(request.user, pk)
    if lesson is None:
        return _not_found()
    if lesson.is_marked or not lesson.is_live:
        return _bad("Урок уже отмечен")
    from academics.teachers import lesson_words
    from core.audit import record_event
    from core.models import Notification
    from materials.services import notify

    who = lesson.substitute or lesson.teacher
    if who is None:
        return _bad("У урока не назначен учитель — напоминать некому")
    notify(
        who,
        kind=Notification.Kind.LESSON_UNMARKED,
        template="Куратор напоминает: не отмечен урок {lesson}, {when}",
        link=f"/lessons/{lesson.pk}",
        lesson=lesson_words(lesson),
        when=f"{lesson.slot} урок",
    )
    for sid in member_ids(lesson.course.cohort, lesson.date)[:1]:
        student = Student.objects.filter(pk=sid).first()
        if student is not None:
            record_event(
                student=student,
                code="teacher_reminded",
                text=f"{lesson_words(lesson)}, {user_name(who)}",
                actor=request.user,
            )
    return Response({"reminded": user_name(who)})


# --- Уважительные причины ----------------------------------------------------------


def _excuse_dict(row: Excuse) -> dict:
    return {
        "id": row.pk,
        "student": row.student_id,
        "starts": row.starts,
        "ends": row.ends,
        "reason": row.reason,
        "document": row.document,
        "document_title": row.get_document_display(),
        "has_file": bool(row.file),
        "created_by": user_name(row.created_by) if row.created_by_id else row.created_by_title,
        "created_at": row.created_at,
    }


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@cached
def excuses(request):
    """Уважительные причины ученика: список и оформление за период."""
    role = request.user.role
    if role == ROLE_STUDENT:
        return _forbid("Причины оформляет школа")
    if request.method == "GET":
        student = Student.objects.filter(pk=_int(request.query_params.get("student"))).first()
        if student is None or not sees_student(request.user, student.pk):
            return _not_found()
        rows = Excuse.objects.filter(student=student).select_related("created_by")
        return Response({"rows": [_excuse_dict(r) for r in rows], "may_write": rights.writes_excuse(role)})
    if not rights.writes_excuse(role):
        return _forbid("Уважительную причину оформляют куратор группы и администратор")
    student = Student.objects.filter(pk=_int(request.data.get("student"))).first()
    if student is None or not sees_student(request.user, student.pk):
        return _not_found()
    starts = _date(request.data.get("starts"))
    ends = _date(request.data.get("ends"), starts)
    if starts is None:
        return _bad("Укажите даты")
    try:
        row = marking.add_excuse(
            student=student,
            starts=starts,
            ends=ends,
            reason=str(request.data.get("reason") or ""),
            document=str(request.data.get("document") or "other"),
            file=request.FILES.get("file"),
            actor=request.user,
        )
    except marking.MarkRefused as error:
        return _bad(str(error))
    return Response({"excuse": _excuse_dict(row)}, status=http.HTTP_201_CREATED)


@extend_schema(responses={200: dict})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@cached
def excuse_drop(request, pk: int):
    """Снять причину: пропуски снова «н»."""
    if not rights.writes_excuse(request.user.role):
        return _forbid("Уважительную причину снимают куратор группы и администратор")
    row = Excuse.objects.select_related("student").filter(pk=pk).first()
    if row is None or not sees_student(request.user, row.student_id):
        return _not_found()
    marking.drop_excuse(row, actor=request.user)
    return Response({"dropped": row.pk})


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def excuse_file(request, pk: int):
    """Файл справки — после проверки границы, вне корня веб-сервера."""
    from django.http import FileResponse

    row = Excuse.objects.select_related("student").filter(pk=pk).first()
    if row is None or request.user.role == ROLE_STUDENT or not sees_student(request.user, row.student_id):
        return _not_found()
    if not row.file:
        return _not_found()
    response = FileResponse(row.file.open("rb"), content_type="application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="excuse-{row.pk}"'
    response["Cache-Control"] = "private, no-store"
    return response


# --- Оценки ученика (карточка, отчёт, сам ученик) -------------------------------------


def student_grades_payload(student: Student, period: str, *, for_student: bool) -> dict:
    """Успеваемость одного ученика за период: по предметам и посещаемость по дням."""
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    start, end, title, quarter = calendar_period(calendar, period or _default_period(calendar))
    end_seen = min(end, today())
    summary = student_summary(student.pk, start, end_seen, scale, quarter=quarter)
    totals = student_attendance(student.pk, start, end_seen)
    rows = []
    for item in summary:
        course, stats = item["course"], item["stats"]
        rows.append({"course": course_dict(course), "stats": stats.as_dict()})
    days = [
        {
            "date": day,
            "weekday": WEEKDAYS_SHORT[day.weekday()],
            "marks": [
                {"lesson": lesson.pk, "subject": lesson.course.subject.short_title, "slot": lesson.slot, "mark": mark}
                for lesson, mark in items
            ],
            "has_absent": any(mark == "absent" for _l, mark in items),
        }
        for day, items in sorted(totals.days.items())
    ]
    # оценки периода строками — с комментарием учителя: ученик читает
    # его у себя, в отчёт родителям он не идёт
    from academics.models import Grade

    grade_rows = (
        Grade.objects.filter(student=student, lesson__date__gte=start, lesson__date__lte=end_seen)
        .select_related("lesson", "lesson__course", "lesson__course__subject")
        .order_by("-lesson__date", "-lesson__slot")
    )
    grades = [
        {
            "lesson": row.lesson_id,
            "date": row.lesson.date,
            "subject": row.lesson.course.subject.short_title,
            "subject_title": row.lesson.course.subject.title,
            "kind": row.lesson.kind,
            "kind_label": kind_label(row.lesson),
            "value": row.value,
            "max": scale.fo_max if row.lesson.kind == LessonKind.FO else row.lesson.max_score,
            "comment": row.comment,
        }
        for row in grade_rows
        if row.lesson.is_live
    ]
    payload = {
        "student": student_brief(student),
        "period": {"code": period or _default_period(calendar), "title": title, "from": start, "to": end},
        "periods": period_choices(calendar),
        "subjects": rows,
        "attendance": totals.as_dict(),
        "days": days,
        "grades": grades,
        "scale": {
            "weight_fo": scale.weight_fo,
            "weight_sor": scale.weight_sor,
            "weight_soch": scale.weight_soch,
            "fo_max": scale.fo_max,
        },
    }
    if not for_student:
        payload["unexcused_days"] = unexcused_days(student.pk, start, end_seen, totals)
        payload["excuses"] = [
            _excuse_dict(r)
            for r in Excuse.objects.filter(student=student, starts__lte=end, ends__gte=start).select_related(
                "created_by"
            )
        ]
    return payload


def _default_period(calendar) -> str:
    day = today()
    return f"{day.year}-{day.month:02d}"


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def student_grades(request, pk: int):
    """Вкладка «Успеваемость» в карточке: куратор своей группы, учитель своих составов, Кымбат, администратор."""
    role = request.user.role
    if role == ROLE_STUDENT:
        return _forbid("Свои оценки — на экране «Оценки»")
    if not rights.reads_grades(role):
        return _forbid("Оценки видят куратор, учитель, академический директор и администратор")
    student = Student.objects.select_related("group").filter(pk=pk).first()
    if student is None or not sees_student(request.user, student.pk):
        return _not_found()
    payload = student_grades_payload(student, str(request.query_params.get("period") or ""), for_student=False)
    payload["may_excuse"] = rights.writes_excuse(role)
    return Response(payload)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def my_grades(request):
    """Оценки и пропуски ученика — без ярлыков, без средних по группе."""
    student = getattr(request.user, "student", None)
    if request.user.role != ROLE_STUDENT or student is None:
        return _forbid("Экран ученика")
    return Response(student_grades_payload(student, str(request.query_params.get("period") or ""), for_student=True))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def my_lessons(request):
    """Уроки ученика на день: для главной и календаря."""
    student = getattr(request.user, "student", None)
    if request.user.role != ROLE_STUDENT or student is None:
        return _forbid("Экран ученика")
    calendar = school_calendar.load()
    day = _date(request.query_params.get("date"), today())
    rows = schedule.for_student(list(schedule.lessons_between(day, day)), student.pk)
    marks = marking.marks_map(rows, [student.pk])
    grades = marking.grades_map(rows, [student.pk])
    out = []
    for lesson in rows:
        grade = grades.get((lesson.pk, student.pk))
        out.append(
            {
                **lesson_dict(lesson, calendar),
                "mine": {
                    "mark": marks.get((lesson.pk, student.pk)) if lesson.is_marked else None,
                    "grade": grade.value if grade else None,
                    "homework": lesson.homework,
                },
            }
        )
    upcoming = [
        lesson_dict(lesson, calendar)
        for lesson in schedule.for_student(
            list(
                schedule.lessons_between(day, day + dt.timedelta(days=30))
                .exclude(kind=LessonKind.FO)
                .exclude(status=LessonStatus.CANCELLED)
            ),
            student.pk,
        )
    ]
    return Response({"date": day, "now_slot": calendar.current_slot(), "lessons": out, "assessments": upcoming})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def my_home(request):
    """Главная ученика 8–10: учёба, олимпиады и спорт — без поступления."""
    from academics.junior_home import home_payload

    student = getattr(request.user, "student", None)
    if request.user.role != ROLE_STUDENT or student is None:
        return _forbid("Экран ученика")
    return Response(home_payload(student))


# --- Посещаемость по урокам ----------------------------------------------------------


def _attendance_groups(user) -> list[StudyGroup]:
    query = StudyGroup.objects.filter(is_active=True).order_by("code")
    if user.role == ROLE_CURATOR:
        query = query.filter(pk__in=curated_group_ids(user))
    return list(query)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def attendance(request):
    """Посещаемость группы по урокам: день или месяц. Куратор — свои группы, Салтанат читает."""
    if not rights.reads_attendance(request.user.role):
        return _forbid("Посещаемость по урокам видят куратор, директор школы и академический директор")
    groups = _attendance_groups(request.user)
    picked = _group_param(request.query_params.get("group"))
    if picked is not None and picked.pk not in {g.pk for g in groups}:
        return _not_found()
    group = picked or (groups[0] if groups else None)
    payload = attendance_payload(
        group,
        view=str(request.query_params.get("view") or "day"),
        # без даты — последний учебный день: в воскресенье лист открывается
        # на пятницу, а не на «не учебный» (замечание владельца, 27.09.2026)
        day=_date(request.query_params.get("date"), last_school_day()),
        month=str(request.query_params.get("month") or ""),
    )
    payload["groups"] = [{"id": g.pk, "code": g.code} for g in groups]
    payload["may_excuse"] = rights.writes_excuse(request.user.role)
    payload["may_remind"] = rights.reminds(request.user.role)
    return Response(payload)


def last_school_day(limit: int = 30) -> dt.date:
    """Сегодня, если учебный день, иначе ближайший прошедший учебный."""
    calendar = school_calendar.load()
    day = today()
    for _ in range(limit):
        if calendar.is_school_day(day):
            return day
        day -= dt.timedelta(days=1)
    return today()


def attendance_payload(group: StudyGroup | None, *, view: str, day: dt.date, month: str = "") -> dict:
    calendar = school_calendar.load()
    if group is None:
        return {"group": None, "group_code": "", "view": view, "date": day, "rows": [], "slots": [], "days": []}
    students = list(Student.objects.filter(group=group, is_active=True).order_by("last_name", "first_name", "id"))
    ids = [s.pk for s in students]
    if view == "month":
        first, last = _month_bounds(month, day)
        last = min(last, today())
        rows = list(schedule.lessons_between(first, last).exclude(status=LessonStatus.CANCELLED))
        rows = schedule.for_groups(rows, [group.pk])
        marks = marking.marks_map(rows, ids)
        days = [d for d in school_calendar.days_between(first, last) if calendar.is_school_day(d)]
        by_student_day: dict[tuple[int, dt.date], dict] = {}
        for lesson in rows:
            members = set(member_ids(lesson.course.cohort, lesson.date))
            for sid in ids:
                if sid not in members:
                    continue
                cell = by_student_day.setdefault(
                    (sid, lesson.date), {"absent": 0, "excused": 0, "late": 0, "unmarked": 0, "lessons": 0}
                )
                cell["lessons"] += 1
                mark = marks.get((lesson.pk, sid))
                if mark is None:
                    if calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson)):
                        cell["unmarked"] += 1
                elif mark in ("absent", "excused", "late"):
                    cell[mark] += 1
        out_rows = []
        for student in students:
            totals = student_attendance(student.pk, first, last)
            out_rows.append(
                {
                    **student_brief(student),
                    "cells": [
                        by_student_day.get(
                            (student.pk, d), {"absent": 0, "excused": 0, "late": 0, "unmarked": 0, "lessons": 0}
                        )
                        for d in days
                    ],
                    "pct": totals.pct,
                    "absent": totals.absent,
                    "excused": totals.excused,
                    "late": totals.late,
                    "unexcused_days": unexcused_days(student.pk, first, last, totals),
                }
            )
        return {
            "group": group.pk,
            "group_code": group.code,
            "view": "month",
            "month": f"{first.year}-{first.month:02d}",
            "month_title": month_title(first),
            "days": [{"date": d, "day": d.day, "weekday": WEEKDAYS_SHORT[d.weekday()]} for d in days],
            "rows": out_rows,
        }
    # день
    rows = schedule.for_groups(
        list(schedule.lessons_between(day, day).exclude(status=LessonStatus.CANCELLED)), [group.pk]
    )
    marks = marking.marks_map(rows, ids)
    slots = sorted({lesson.slot for lesson in rows})
    members_cache = {lesson.pk: set(member_ids(lesson.course.cohort, day)) for lesson in rows}
    out_rows = []
    now_slot = calendar.current_slot() if day == today() else None
    absent_now: list[str] = []
    all_day: list[dict] = []
    totals = {"absent": 0, "excused": 0, "late": 0}
    for student in students:
        cells = []
        done = 0
        counts = {"absent": 0, "excused": 0, "late": 0}
        for slot in slots:
            mine = [lesson for lesson in rows if lesson.slot == slot and student.pk in members_cache[lesson.pk]]
            if not mine:
                cells.append({"has_lesson": False})
                continue
            lesson = mine[0]
            mark = marks.get((lesson.pk, student.pk))
            started = calendar.lesson_started(lesson.date, lesson.slot, lesson_groups(lesson))
            cells.append(
                {
                    "has_lesson": True,
                    "lesson": lesson.pk,
                    "subject": lesson.course.subject.short_title,
                    "teacher": person(lesson.substitute or lesson.teacher),
                    "started": started,
                    "mark": mark if lesson.is_marked else None,
                    "unmarked": started
                    and not lesson.is_marked
                    and calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson)),
                }
            )
            if lesson.is_marked and mark is not None:
                done += 1
                if mark in counts:
                    counts[mark] += 1
                if now_slot == slot and mark in ("absent", "excused"):
                    absent_now.append(student_brief(student)["short"])
        for key in counts:
            totals[key] += counts[key]
        row = {**student_brief(student), "cells": cells, "marked": done, **counts}
        if done >= 2 and counts["absent"] + counts["excused"] == done and counts["absent"] > 0:
            excused_periods = marking.excuses_of([student.pk], day, day)
            all_day.append({**student_brief(student), "excused": marking.is_excused(excused_periods, student.pk, day)})
        out_rows.append(row)
    unmarked = [
        lesson_dict(lesson, calendar)
        for lesson in rows
        if lesson.is_live
        and not lesson.is_marked
        and calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson))
    ]
    first, last = day.replace(day=1), min(day, today())
    not_excused = []
    for student in students:
        found = list(unexcused_days(student.pk, first, last))
        if found:
            not_excused.append({**student_brief(student), "days": found})
    return {
        "group": group.pk,
        "group_code": group.code,
        "view": "day",
        "date": day,
        "date_words": date_with_weekday(day),
        "school_day": calendar.is_school_day(day),
        "now_slot": now_slot,
        "slots": [
            {
                "slot": slot,
                "bell": school_calendar.bell_text(calendar, slot),
                "subjects": sorted({lesson.course.subject.short_title for lesson in rows if lesson.slot == slot}),
            }
            for slot in slots
        ],
        "rows": out_rows,
        "absent_now": absent_now,
        "all_day": all_day,
        "totals": totals,
        "unmarked": unmarked,
        "not_excused": not_excused,
        "lessons": [lesson_dict(lesson, calendar) for lesson in rows],
    }


def _month_bounds(raw: str, day: dt.date) -> tuple[dt.date, dt.date]:
    from academics.reports import month_bounds

    if len(raw) == 7 and raw[4] == "-" and raw[:4].isdigit() and raw[5:].isdigit():
        return month_bounds(dt.date(int(raw[:4]), int(raw[5:]), 1))
    return month_bounds(day)


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def attendance_export(request):
    """Та же посещаемость книгой XLSX; `?preview=1` — таблицей."""
    from academics.exports import day_attendance_workbook, month_attendance_workbook

    if not rights.reads_attendance(request.user.role):
        return _forbid("Посещаемость по урокам видят куратор, директор школы и академический директор")
    groups = _attendance_groups(request.user)
    picked = _group_param(request.query_params.get("group"))
    if picked is not None and picked.pk not in {g.pk for g in groups}:
        return _not_found()
    group = picked or (groups[0] if groups else None)
    if group is None:
        return _not_found()
    view = str(request.query_params.get("view") or "day")
    payload = attendance_payload(
        group,
        view=view,
        day=_date(request.query_params.get("date"), today()),
        month=str(request.query_params.get("month") or ""),
    )
    if view == "month":
        return month_attendance_workbook(
            filename=f"посещаемость {group.code} {payload['month']}.xlsx",
            days=[d["date"] for d in payload["days"]],
            rows=payload["rows"],
            group_code=group.code,
            request=request,
        )
    return day_attendance_workbook(
        filename=f"посещаемость {group.code} {payload['date']:%d.%m.%Y}.xlsx",
        slots=[s["slot"] for s in payload["slots"]],
        rows=payload["rows"],
        group_code=group.code,
        request=request,
    )


# --- Риски по урокам (Салтанат, администратор) -------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def risks(request):
    """Пропуски по урокам за месяц: посещаемость ниже порога и дни без причины."""
    from django.conf import settings

    if not rights.reads_risks(request.user.role):
        return _forbid("Риски по посещаемости читают директор школы и администратор")
    calendar = school_calendar.load()
    start, end, title, _q = calendar_period(
        calendar, str(request.query_params.get("period") or _default_period(calendar))
    )
    end = min(end, today())
    threshold = int(settings.ACADEMICS_RULES.get("RISK_ATTENDANCE_BELOW", 85))
    picked = _group_param(request.query_params.get("group"))
    students = visible_students(request.user).filter(is_active=True).select_related("group")
    if picked is not None:
        students = students.filter(group=picked)
    rows = []
    for student in students.order_by("group__code", "last_name", "first_name"):
        totals = student_attendance(student.pk, start, end)
        days = unexcused_days(student.pk, start, end, totals)
        if totals.total and ((totals.pct is not None and totals.pct < threshold) or days):
            rows.append({**student_brief(student), "attendance": totals.as_dict(), "unexcused_days": days})
    rows.sort(key=lambda r: (r["attendance"]["pct"] if r["attendance"]["pct"] is not None else 101, r["full_name"]))
    return Response(
        {
            "period": {"title": title, "from": start, "to": end},
            "threshold": threshold,
            "rows": rows,
            "periods": period_choices(calendar),
        }
    )


# --- Кабинет куратора и дашборд Кымбат: блоки учёбы ---------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def curator_home(request):
    """Блоки учёбы на главной куратора: сегодня в группах, кого дёргать, отчёты."""
    from academics.models import ParentReport, ReportStatus
    from academics.results import course_context
    from accounts.curators import picked_groups

    if request.user.role != ROLE_CURATOR:
        return _forbid("Это кабинет куратора")
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    group_ids, picked = picked_groups(request.user, request.query_params.get("group"))
    groups = list(StudyGroup.objects.filter(pk__in=group_ids).order_by("code"))
    day = today()
    now_slot = calendar.current_slot()
    today_rows = schedule.for_groups(list(schedule.lessons_between(day, day)), group_ids)
    blocks = []
    absent_now: list[str] = []
    for group in groups:
        rows = [lesson for lesson in today_rows if group.pk in group_ids_of(lesson.course.cohort)]
        live = [lesson for lesson in rows if lesson.is_live]
        ids = list(Student.objects.filter(group=group, is_active=True).values_list("pk", flat=True))
        marks = marking.marks_map(live, ids)
        absent = sorted({sid for (lid, sid), mark in marks.items() if mark in ("absent", "excused")})
        students = {s.pk: s for s in Student.objects.filter(pk__in=absent)}
        now_lesson = next(
            (
                lesson
                for lesson in live
                if calendar.slot_state(lesson.date, lesson.slot, groups=lesson_groups(lesson)) == "now"
            ),
            None,
        )
        unmarked = [
            lesson
            for lesson in live
            if not lesson.is_marked and calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson))
        ]
        if now_lesson is not None:
            absent_now += [
                student_brief(students[sid])["short"]
                for (lid, sid), mark in marks.items()
                if lid == now_lesson.pk and mark in ("absent", "excused") and sid in students
            ]
        blocks.append(
            {
                "group": group.code,
                "lessons": len(live),
                "now": lesson_dict(now_lesson, calendar) if now_lesson else None,
                "absent": [student_brief(students[sid])["short"] for sid in absent if sid in students],
                "unmarked": len(unmarked),
            }
        )
    first, last = day.replace(day=1), day
    students = list(Student.objects.filter(group_id__in=group_ids, is_active=True).select_related("group"))
    risk2 = []
    unexcused = []
    for student in students:
        summary = student_summary(student.pk, first, last, scale)
        if any(item["stats"].quarter_grade == 2 for item in summary):
            risk2.append(student_brief(student))
        if unexcused_days(student.pk, first, last):
            unexcused.append(student_brief(student))
    reports = ParentReport.objects.filter(student__in=students).order_by("-period_start")
    latest = reports.first()
    report_block = None
    if latest is not None:
        same = reports.filter(period_kind=latest.period_kind, period_start=latest.period_start)
        report_block = {
            "title": latest.title,
            "total": same.count(),
            "draft": same.filter(status=ReportStatus.DRAFT).count(),
            "checked": same.filter(status=ReportStatus.CHECKED).count(),
            "exported": same.filter(status=ReportStatus.EXPORTED).count(),
            "sent": same.filter(status=ReportStatus.SENT).count(),
        }
    del course_context
    return Response(
        {
            "group": picked,
            "now_slot": now_slot,
            "today": blocks,
            "absent_now": absent_now,
            "risk_grade": risk2,
            "unexcused": unexcused,
            "reports": report_block,
            "cadence": school_calendar.report_settings_of(calendar.year).cadence,
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def dashboard_block(request):
    """Блок «Учёба» на дашборде Кымбат и администратора."""
    from academics.models import LessonSeries, ParentReport, ReportStatus

    if not rights.reads_all(request.user.role):
        return _forbid("Блок учёбы — у академического директора и администратора")
    calendar = school_calendar.load()
    day = today()
    start = week_start(day)
    if not LessonSeries.objects.exists() and not Lesson.objects.exists():
        return Response({"empty": True})
    today_rows = [lesson for lesson in schedule.lessons_between(day, day) if lesson.is_live]
    unmarked = schedule.stale_unmarked(calendar, start, day)
    teachers = sorted({user_name(lesson.substitute or lesson.teacher) for lesson in unmarked})
    changes = schedule.changed_between(start, start + dt.timedelta(days=4))
    next_conflicts = schedule.conflicts_between(start + dt.timedelta(days=7), start + dt.timedelta(days=11))
    pending = (
        LessonRequest.objects.filter(status=RequestStatus.PENDING).select_related("teacher").order_by("-created_at")
    )
    latest = ParentReport.objects.order_by("-period_start").first()
    reports = None
    if latest is not None:
        same = ParentReport.objects.filter(period_kind=latest.period_kind, period_start=latest.period_start)
        reports = {"title": latest.title, "total": same.count(), "sent": same.filter(status=ReportStatus.SENT).count()}
    return Response(
        {
            "empty": False,
            "lessons_today": len(today_rows),
            "now_slot": calendar.current_slot(),
            "unmarked": len(unmarked),
            "unmarked_teachers": teachers,
            "changes": len(changes),
            "next_conflicts": len(next_conflicts),
            "next_conflict_text": next_conflicts[0]["text"] if next_conflicts else "",
            "requests": pending.count(),
            "request_text": f"{user_name(pending[0].teacher)}: {pending[0].reason}" if pending else "",
            "reports": reports,
        }
    )
