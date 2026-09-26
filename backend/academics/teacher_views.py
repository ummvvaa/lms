"""Кабинет учителя: «Сегодня», журналы, журнал с матрицей, итог, профиль, ученик глазами учителя.

Учитель видит только свои уроки и учеников своих составов. Кымбат
и администратор открывают любой журнал теми же ручками; куратор — журналы
своих групп на чтение.
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics import calendar as school_calendar
from academics import marks as marking
from academics import rights, teachers
from academics.cache import cached
from academics.calendar import WEEKDAYS_SHORT, date_with_weekday, period_choices, scale_of, today, week_start
from academics.cohorts import member_ids
from academics.models import Course, Excuse, Lesson, LessonKind, LessonStatus, Quarter, RequestStatus, Scheme
from academics.payloads import cohort_dict, course_dict, lesson_dict, person, student_brief, teacher_dict
from academics.results import ResultRefused, calendar_period, course_context, set_finals
from academics.views import _excuse_dict, _forbid, _int, _not_found
from core.domains import ROLE_TEACHER
from students.models import Student


def _course_for(user, pk: int) -> Course | None:
    course = Course.objects.select_related("subject", "cohort", "cohort__group", "teacher").filter(pk=pk).first()
    if course is None or not rights.sees_course(user, course):
        return None
    return course


# --- «Сегодня» --------------------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def today_screen(request):
    """Уроки дня по звонкам, не отмечено за неделю, оценки за неделю, ближайшие СОР и СОЧ."""
    user = request.user
    if user.role != ROLE_TEACHER:
        return _forbid("Это кабинет учителя")
    calendar = school_calendar.load()
    day = today()
    courses = teachers.courses_of(user)
    rows = list(teachers.lessons_of(user, day, day))
    unmarked = teachers.unmarked_lessons(user, calendar)
    counts = {}
    absent_by_lesson = {}
    for lesson in rows:
        ids = member_ids(lesson.course.cohort, lesson.date)
        counts[lesson.pk] = len(ids)
        if lesson.is_marked:
            marks = marking.marks_map([lesson], ids)
            absent = [sid for (lid, sid), mark in marks.items() if mark in ("absent", "excused")]
            students = {s.pk: s for s in Student.objects.filter(pk__in=absent)}
            absent_by_lesson[lesson.pk] = [student_brief(students[sid])["short"] for sid in absent if sid in students]
    now_lesson = next(
        (lesson for lesson in rows if lesson.is_live and calendar.slot_state(lesson.date, lesson.slot) == "now"), None
    )
    week_start_day = week_start(day)
    from academics.models import Grade

    week_grades = Grade.objects.filter(
        lesson__in=teachers.lessons_of(user, week_start_day, day), created_by=user
    ).count()
    upcoming = [
        lesson
        for lesson in teachers.lessons_of(user, day, day + dt.timedelta(days=30))
        if lesson.is_live and lesson.kind != LessonKind.FO and not calendar.lesson_finished(lesson.date, lesson.slot)
    ]
    changes = [
        lesson
        for lesson in teachers.lessons_of(user, week_start_day, week_start_day + dt.timedelta(days=11))
        if lesson.status != LessonStatus.PLANNED
        or (lesson.substitute_id and lesson.substitute_id != user.pk)
        or lesson.substitute_id == user.pk
    ]
    journal_rows = []
    quarter = calendar.current_quarter()
    for course in courses:
        lessons = list(
            Lesson.objects.filter(course=course, status=LessonStatus.PLANNED)
            .filter(Q(date__gte=quarter.starts) if quarter else Q())
            .filter(Q(date__lte=quarter.ends) if quarter else Q())
        )
        past = [lesson for lesson in lessons if calendar.lesson_finished(lesson.date, lesson.slot)]
        journal_rows.append(
            {
                **course_dict(course),
                "students": len(member_ids(course.cohort)),
                "held": len(past),
                "planned": len(lessons),
                "unmarked": sum(1 for lesson in past if not lesson.is_marked),
            }
        )
    profile = teachers.profile_of(user)
    return Response(
        {
            "today": day,
            "today_words": date_with_weekday(day),
            "now_slot": calendar.current_slot(),
            "now_ends": calendar.bell(calendar.current_slot())[1] if calendar.current_slot() else None,
            "teacher": teacher_dict(user, profile),
            "has_courses": bool(courses) or Lesson.objects.filter(Q(teacher=user) | Q(substitute=user)).exists(),
            "lessons": [
                {
                    **lesson_dict(lesson, calendar, students=counts.get(lesson.pk)),
                    "absent": absent_by_lesson.get(lesson.pk, []),
                    "is_substitution": lesson.substitute_id == user.pk,
                }
                for lesson in rows
            ],
            "now_lesson": lesson_dict(now_lesson, calendar) if now_lesson else None,
            "unmarked": [lesson_dict(lesson, calendar) for lesson in unmarked],
            "week_grades": week_grades,
            "journals": journal_rows,
            "assessments": [lesson_dict(lesson, calendar) for lesson in upcoming[:6]],
            "changes": [lesson_dict(lesson, calendar) for lesson in changes],
        }
    )


# --- Журналы -------------------------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def journals(request):
    """Список журналов учителя с числами: ученики, уроки, средний ФО, СОР."""
    user = request.user
    if user.role != ROLE_TEACHER:
        return _forbid("Это кабинет учителя")
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    quarter = calendar.current_quarter()
    rows = []
    for course in teachers.courses_of(user):
        start = quarter.starts if quarter else today() - dt.timedelta(days=60)
        end = quarter.ends if quarter else today()
        context = course_context(course, start, end, scale, quarter=quarter)
        past = [lesson for lesson in context.lessons if calendar.lesson_finished(lesson.date, lesson.slot)]
        stats = [context.stats(sid) for sid in context.student_ids]
        fo = [s.fo_avg for s in stats if s.fo_avg is not None]
        sor_all = [lesson for lesson in context.lessons if lesson.kind == LessonKind.SOR]
        rows.append(
            {
                **course_dict(course),
                "students": len(context.student_ids),
                "held": len(past),
                "planned": len(context.lessons),
                "unmarked": sum(1 for lesson in past if not lesson.is_marked),
                "fo_avg": round(sum(fo) / len(fo), 1) if fo else None,
                "sor_done": sum(1 for lesson in sor_all if calendar.lesson_finished(lesson.date, lesson.slot)),
                "sor_all": len(sor_all),
                "low": sum(1 for s in stats if s.quarter_grade is not None and s.quarter_grade <= 2),
            }
        )
    return Response(
        {
            "teacher": teacher_dict(user, teachers.profile_of(user)),
            "quarter": (
                {"number": quarter.number, "title": quarter.title, "ends": quarter.ends, "closed": quarter.is_closed}
                if quarter
                else None
            ),
            "scale": {
                "weight_fo": scale.weight_fo,
                "weight_sor": scale.weight_sor,
                "weight_soch": scale.weight_soch,
                "edit_days": scale.edit_days,
            },
            "rows": rows,
        }
    )


def journal_payload(course: Course, user, period: str) -> dict:
    """Журнал: колонки — уроки, строки — ученики, клетка — отметка и оценка."""
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    quarter = calendar.current_quarter()
    code = period or (f"q{quarter.number}" if quarter else "")
    start, end, title, period_quarter = calendar_period(calendar, code)
    quarter_for_finals = period_quarter or calendar.quarter_of(start) or quarter
    context = course_context(course, start, end, scale, quarter=quarter_for_finals)
    students = {s.pk: s for s in Student.objects.filter(pk__in=context.student_ids).select_related("group")}
    columns = []
    for lesson in context.lessons:
        state = calendar.slot_state(lesson.date, lesson.slot)
        columns.append(
            {
                "lesson": lesson.pk,
                "date": lesson.date,
                "weekday": WEEKDAYS_SHORT[lesson.date.weekday()],
                "slot": lesson.slot,
                "kind": lesson.kind,
                "kind_label": marking.kind_label(lesson),
                "max_score": lesson.max_score,
                "state": state,
                "future": state == "future",
                "unmarked": state != "future" and not lesson.is_marked,
                "locked": marking.edit_locked(lesson, user, scale),
                "topic": lesson.topic,
                "is_today": lesson.date == today(),
            }
        )
    rows = []
    for sid in context.student_ids:
        student = students.get(sid)
        if student is None:
            continue
        cells = []
        for lesson in context.lessons:
            grade = context.grades.get((lesson.pk, sid))
            cells.append(
                {
                    "mark": context.marks.get((lesson.pk, sid)) if lesson.is_marked else None,
                    "grade": grade.value if grade else None,
                    "comment": grade.comment if grade else "",
                }
            )
        rows.append({**student_brief(student), "cells": cells, "stats": context.stats(sid).as_dict()})
    past = [lesson for lesson in context.lessons if calendar.lesson_finished(lesson.date, lesson.slot)]
    unmarked = [lesson for lesson in past if not lesson.is_marked]
    fo = [row["stats"]["fo_avg"] for row in rows if row["stats"]["fo_avg"] is not None]
    next_assessment = next(
        (
            lesson
            for lesson in context.lessons
            if lesson.kind != LessonKind.FO and not calendar.lesson_finished(lesson.date, lesson.slot)
        ),
        None,
    )
    today_lesson = next((lesson for lesson in context.lessons if lesson.date == today()), None)
    past_topics = [lesson_dict(lesson, calendar) for lesson in past[-3:][::-1]]
    return {
        "course": course_dict(course),
        "period": {"code": code, "title": title, "from": start, "to": end},
        "periods": period_choices(calendar),
        "quarter": (
            {
                "id": quarter_for_finals.pk,
                "number": quarter_for_finals.number,
                "title": quarter_for_finals.title,
                "ends": quarter_for_finals.ends,
                "closed": quarter_for_finals.is_closed,
            }
            if quarter_for_finals
            else None
        ),
        "scheme": course.subject.scheme,
        "columns": columns,
        "rows": rows,
        "kpis": {
            "held": len(past),
            "planned": len(context.lessons),
            "unmarked": len(unmarked),
            "first_unmarked": unmarked[0].pk if unmarked else None,
            "fo_avg": round(sum(fo) / len(fo), 1) if fo else None,
            "low": sum(
                1 for row in rows if row["stats"]["quarter_grade"] is not None and row["stats"]["quarter_grade"] <= 2
            ),
            "next_assessment": lesson_dict(next_assessment, calendar) if next_assessment else None,
        },
        "today_lesson": lesson_dict(today_lesson, calendar) if today_lesson else None,
        "topics": past_topics,
        "all_lessons": [lesson_dict(lesson, calendar) for lesson in context.lessons],
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
        "may_edit": rights.owns_course(user, course),
        "is_owner": course.teacher_id == user.pk,
        "final_window": bool(quarter_for_finals and quarter_for_finals.ends - dt.timedelta(days=6) <= today()),
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def journal(request, pk: int):
    """Журнал за период. Учитель — свой, Кымбат и администратор — любой, куратор — своих групп."""
    course = _course_for(request.user, pk)
    if course is None:
        return _not_found()
    return Response(journal_payload(course, request.user, str(request.query_params.get("period") or "")))


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def journal_export(request, pk: int):
    """Журнал книгой: посещаемость, оценки, темы."""
    from academics.exports import journal_workbook

    course = _course_for(request.user, pk)
    if course is None:
        return _not_found()
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    quarter = calendar.current_quarter()
    code = str(request.query_params.get("period") or (f"q{quarter.number}" if quarter else ""))
    start, end, title, period_quarter = calendar_period(calendar, code)
    context = course_context(course, start, end, scale, quarter=period_quarter or quarter)
    return journal_workbook(
        context, filename=f"журнал {course.subject.short_title} {course.cohort.name} {title}.xlsx", request=request
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def journal_final(request, pk: int):
    """Выставить итог четверти по журналу."""
    course = _course_for(request.user, pk)
    if course is None:
        return _not_found()
    if not rights.owns_course(request.user, course):
        return _forbid("Итог выставляет учитель журнала")
    quarter = Quarter.objects.filter(pk=_int(request.data.get("quarter"))).first()
    if quarter is None:
        return Response({"detail": "Не указана четверть"}, status=http.HTTP_400_BAD_REQUEST)
    rows = request.data.get("rows") or []
    if not isinstance(rows, list):
        return Response({"detail": "Не переданы итоги"}, status=http.HTTP_400_BAD_REQUEST)
    calendar = school_calendar.load()
    try:
        written = set_finals(course, quarter, rows, actor=request.user, scale=scale_of(calendar.year))
    except ResultRefused as error:
        return Response({"detail": str(error)}, status=http.HTTP_400_BAD_REQUEST)
    return Response({"written": written, **journal_payload(course, request.user, f"q{quarter.number}")})


# --- Профиль и ученик глазами учителя --------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def profile(request):
    """Профиль учителя: учётная запись, предметы, кабинет, что видит и кто видит его оценки."""
    user = request.user
    if user.role != ROLE_TEACHER:
        return _forbid("Это кабинет учителя")
    profile = teachers.profile_of(user)
    return Response(
        {
            "teacher": teacher_dict(user, profile),
            "hours": teachers.weekly_hours(user),
            "journals": len(teachers.courses_of(user)),
            "requests": [
                {
                    "id": r.pk,
                    "lesson": lesson_dict(r.lesson, school_calendar.load()),
                    "wanted": r.wanted,
                    "reason": r.reason,
                    "status": r.status,
                    "status_title": r.get_status_display(),
                    "answer": r.answer,
                }
                for r in user.lesson_requests.select_related(
                    "lesson", "lesson__course", "lesson__course__subject", "lesson__course__cohort", "lesson__teacher"
                )[:20]
            ],
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def student_view(request, pk: int):
    """Ученик глазами учителя: имя, группа, куратор, оценки и пропуски по его предметам."""
    user = request.user
    if user.role != ROLE_TEACHER:
        return _forbid("Это кабинет учителя")
    student = Student.objects.select_related("group").filter(pk=pk).first()
    if student is None or student.pk not in set(teachers.taught_student_ids(user)):
        return _not_found()
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    quarter = calendar.current_quarter()
    start = quarter.starts if quarter else today() - dt.timedelta(days=60)
    end = min(quarter.ends if quarter else today(), today())
    courses = [course for course in teachers.courses_of(user) if student.pk in set(member_ids(course.cohort))]
    blocks = []
    for course in courses:
        context = course_context(course, start, end, scale, quarter=quarter)
        stats = context.stats(student.pk)
        recent = []
        for lesson in [lesson for lesson in context.lessons if calendar.lesson_started(lesson.date, lesson.slot)][-6:][
            ::-1
        ]:
            grade = context.grades.get((lesson.pk, student.pk))
            recent.append(
                {
                    "lesson": lesson_dict(lesson, calendar),
                    "mark": context.marks.get((lesson.pk, student.pk)) if lesson.is_marked else None,
                    "grade": grade.value if grade else None,
                }
            )
        blocks.append({"course": course_dict(course), "stats": stats.as_dict(), "recent": recent})
    from accounts.curators import curator_of

    assignment = curator_of(student.group) if student.group_id else None
    return Response(
        {
            "student": student_brief(student),
            "curator": person(assignment.curator) if assignment else None,
            "curator_email": assignment.curator.email if assignment else "",
            "courses": blocks,
            "excuses": [
                _excuse_dict(r)
                for r in Excuse.objects.filter(student=student, ends__gte=start).select_related("created_by")
            ],
        }
    )


def _unused():  # pragma: no cover — держит импорты, которые пригодятся экранам шага 3
    return cohort_dict, RequestStatus, Scheme
