"""Словари ответов учебной части — один вид урока, состава и учителя на все экраны."""

from __future__ import annotations

import datetime as dt

from django.utils.translation import gettext_lazy

from academics.calendar import WEEKDAYS_FULL, WEEKDAYS_SHORT, SchoolCalendar, bell_text, date_words, lesson_groups
from academics.cohorts import group_ids_of, kind_title, member_ids
from academics.marks import kind_label
from academics.models import Cohort, CohortKind, Course, Lesson, LessonStatus, Subject, TeacherProfile


def user_name(user) -> str:
    if user is None:
        return ""
    # у сотрудника без почты вместо неё логин
    return user.full_name or user.handle


def short_name(full_name: str) -> str:
    """«Касымова Айжан» → «Касымова А.»."""
    parts = (full_name or "").split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1][0]}."
    return full_name or ""


def person(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.pk, "full_name": user_name(user), "short": short_name(user_name(user))}


def subject_dict(subject: Subject) -> dict:
    return {
        "id": subject.pk,
        "code": subject.code,
        "title": subject.title,
        "title_kk": subject.title_kk,
        "short_title": subject.short_title,
        "scheme": subject.scheme,
        "scheme_title": subject.get_scheme_display(),
        "sor_max": subject.sor_max,
        "soch_max": subject.soch_max,
    }


def cohort_dict(cohort: Cohort, *, on: dt.date | None = None, with_members: bool = False) -> dict:
    out = {
        "id": cohort.pk,
        "kind": cohort.kind,
        "kind_title": kind_title(cohort),
        "name": cohort.name,
        "short_name": cohort.short_name or cohort.name,
        "group": cohort.group.code if cohort.group_id else "",
        "group_id": cohort.group_id,
        "subject": subject_dict(cohort.subject) if cohort.subject_id else None,
        "number": cohort.number,
        "rule": cohort.rule,
        "room": cohort.room,
        #: поток, внутри которого подгруппа (`Cohort.stream`)
        "stream": cohort.stream_id,
        "groups": group_ids_of(cohort),
    }
    ids = member_ids(cohort, on)
    out["students"] = len(ids)
    if with_members:
        out["member_ids"] = ids
    if cohort.kind == CohortKind.STREAM:
        out["parts"] = [
            {"id": part.part_id, "name": part.part.name, "kind": part.part.kind}
            for part in cohort.parts.select_related("part").order_by("part__name")
        ]
    return out


def teacher_dict(user, profile: TeacherProfile | None = None) -> dict:
    profile = profile or getattr(user, "teacher_profile", None)
    subjects = list(profile.subjects.all()) if profile is not None else []
    return {
        "id": user.pk,
        "full_name": user_name(user),
        "short": short_name(user_name(user)),
        "email": user.email,
        "is_active": user.is_active,
        "subjects": [subject_dict(s) for s in subjects],
        "subject_titles": ", ".join(s.title for s in subjects),
        "room": profile.room if profile is not None else "",
    }


def course_dict(course: Course) -> dict:
    return {
        "id": course.pk,
        "subject": subject_dict(course.subject),
        "cohort": cohort_dict(course.cohort),
        "teacher": person(course.teacher),
        "title": f"{course.subject.title} · {course.cohort.name}",
        "report_role": course.report_role,
        "report_role_title": course.get_report_role_display(),
    }


STATUS_WORDS = {
    LessonStatus.PLANNED: gettext_lazy("по плану"),
    LessonStatus.CANCELLED: gettext_lazy("отменён"),
    LessonStatus.MOVED: gettext_lazy("перенесён"),
}


def lesson_dict(lesson: Lesson, calendar: SchoolCalendar, *, students: int | None = None) -> dict:
    groups = lesson_groups(lesson)
    state = calendar.slot_state(lesson.date, lesson.slot, groups=groups)
    return {
        "id": lesson.pk,
        "course": lesson.course_id,
        "date": lesson.date,
        "weekday": WEEKDAYS_SHORT[lesson.date.weekday()],
        "weekday_full": WEEKDAYS_FULL[lesson.date.weekday()],
        "date_words": date_words(lesson.date),
        "slot": lesson.slot,
        "bell": bell_text(calendar, lesson.slot, groups),
        "room": lesson.room,
        "subject": subject_dict(lesson.course.subject),
        "cohort": (
            cohort_dict(lesson.course.cohort, on=lesson.date)
            if students is None
            else {
                "id": lesson.course.cohort_id,
                "kind": lesson.course.cohort.kind,
                "kind_title": kind_title(lesson.course.cohort),
                "name": lesson.course.cohort.name,
                "short_name": lesson.course.cohort.short_name or lesson.course.cohort.name,
                "group": lesson.course.cohort.group.code if lesson.course.cohort.group_id else "",
                "students": students,
            }
        ),
        "teacher": person(lesson.teacher),
        "substitute": person(lesson.substitute),
        "actual_teacher": person(lesson.substitute or lesson.teacher),
        "status": lesson.status,
        "status_title": str(STATUS_WORDS.get(lesson.status, lesson.status)),
        "is_live": lesson.is_live,
        "reason": lesson.reason,
        "moved_from_date": lesson.moved_from_date,
        "moved_from_slot": lesson.moved_from_slot,
        "kind": lesson.kind,
        "kind_label": kind_label(lesson),
        "number": lesson.number,
        "max_score": lesson.max_score,
        "topic": lesson.topic,
        "homework": lesson.homework,
        "note": lesson.note,
        "is_one_off": lesson.series_id is None,
        "marked": lesson.is_marked,
        "marked_at": lesson.marked_at,
        "marked_by": person(lesson.marked_by),
        "state": state,
        "title": f"{lesson.course.subject.title} · {lesson.course.cohort.name}",
    }


def student_brief(student) -> dict:
    return {
        "id": student.pk,
        "full_name": student.full_name,
        "short": short_name(f"{student.last_name} {student.first_name}"),
        "group": student.group.code if student.group_id else "",
    }
