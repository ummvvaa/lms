"""Учителя: чьи журналы, какие ученики, нагрузка и заполнение журналов."""

from __future__ import annotations

import datetime as dt

from django.db.models import Q

from academics.calendar import lesson_groups, today, week_start
from academics.cohorts import member_ids
from academics.models import Course, Lesson, LessonStatus, TeacherProfile
from accounts.models import Role, User


def teachers() -> list[User]:
    """Действующие учётные записи с ролью «Учитель»."""
    return list(User.objects.filter(role=Role.TEACHER, is_active=True).order_by("full_name", "email"))


def profile_of(user: User) -> TeacherProfile:
    profile, _ = TeacherProfile.objects.get_or_create(user=user)
    return profile


def courses_of(user: User) -> list[Course]:
    """Журналы учителя — по предмету, потом по составу."""
    return list(
        Course.objects.filter(teacher=user)
        .select_related("subject", "cohort", "cohort__group")
        .order_by("subject__order", "cohort__name")
    )


def taught_student_ids(user: User, on: dt.date | None = None) -> list[int]:
    """Ученики всех составов учителя на дату — граница его видимости."""
    seen: list[int] = []
    for course in Course.objects.filter(teacher=user).select_related("cohort"):
        for sid in member_ids(course.cohort, on):
            if sid not in seen:
                seen.append(sid)
    # ученики уроков, где учитель заменяет сегодня, тоже видны — иначе
    # заменяющему нечего отмечать
    day = on or today()
    for lesson in Lesson.objects.filter(substitute=user, date=day).select_related("course__cohort"):
        for sid in member_ids(lesson.course.cohort, day):
            if sid not in seen:
                seen.append(sid)
    return seen


def lessons_of(user: User, start: dt.date, end: dt.date):
    """Уроки учителя за период: свои и замены."""
    return (
        Lesson.objects.filter(date__gte=start, date__lte=end)
        .filter(Q(teacher=user, substitute__isnull=True) | Q(substitute=user))
        .select_related("course", "course__subject", "course__cohort", "course__cohort__group", "teacher", "substitute")
        .order_by("date", "slot")
    )


def weekly_hours(user: User) -> int:
    """Уроков в неделю по действующим сериям."""
    from academics.models import LessonSeries

    day = today()
    return LessonSeries.objects.filter(course__teacher=user, ends__gte=day, course__archived_at__isnull=True).count()


def unmarked_lessons(user: User | None, calendar, *, days: int = 6) -> list[Lesson]:
    """Прошедшие живые уроки без сохранённой посещаемости за последние дни."""
    day = today()
    rows = Lesson.objects.filter(
        date__gte=day - dt.timedelta(days=days),
        date__lte=day,
        status=LessonStatus.PLANNED,
        marked_at__isnull=True,
    ).select_related("course", "course__subject", "course__cohort", "teacher", "substitute")
    if user is not None:
        rows = rows.filter(Q(teacher=user, substitute__isnull=True) | Q(substitute=user))
    return [
        lesson
        for lesson in rows.order_by("date", "slot")
        if calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson))
    ]


def week_fill(user: User, calendar) -> dict:
    """Заполнение журналов за неделю: сколько прошедших уроков отмечено."""
    day = today()
    start = week_start(day)
    week = [lesson for lesson in lessons_of(user, start, day) if lesson.is_live]
    past = [lesson for lesson in week if calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson))]
    unmarked = [lesson for lesson in past if not lesson.is_marked]
    last = (
        Lesson.objects.filter(marked_by=user, marked_at__isnull=False).order_by("-marked_at").first()
        if past or True
        else None
    )
    return {
        "week": len(past),
        "unmarked": unmarked,
        "fill": round((len(past) - len(unmarked)) * 100 / len(past)) if past else None,
        "last_marked": last,
    }


def lesson_words(lesson: Lesson) -> str:
    """«английский BOSTON, 25.09» — как урок называется в уведомлении."""
    return f"{lesson.course.subject.short_title.lower()} {lesson.course.cohort.name}, {lesson.date:%d.%m}"
