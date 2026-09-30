"""Главная ученика 8–10: учёба вместо готовности к подаче.

Четыре числа — средний балл за четверть, посещаемость, ближайший СОР,
число достижений; уроки сегодня с оценками; «Скоро» — СОР, СОЧ,
олимпиады и соревнования; последние оценки. Всё считает сервер,
подписи и склонения — тоже: экран только рисует.

Средний балл — среднее «сейчас выходит» (или выставленного итога) по
предметам с ФО, СОР и СОЧ; только свой — средних по группе ученику
не показывают никогда (инвариант №7).
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone
from django.utils.translation import gettext as _

from academics import calendar as school_calendar
from academics import marks as marking
from academics import schedule
from academics.calendar import date_with_weekday, scale_of, today
from academics.models import Grade, LessonKind, LessonStatus
from academics.payloads import kind_label, lesson_dict
from academics.results import student_attendance, student_summary
from core.phrasing import plural, tn
from students.models import Activity, Competition, Student

#: сколько дней вперёд смотрит «Скоро»
SOON_DAYS = 30
#: строк в «Скоро» и «Последних оценках»
SOON_ROWS = 5
RECENT_ROWS = 3


def _quarter_words(quarter) -> str:
    return _("за {number} четверть").format(number=quarter.number) if quarter is not None else _("за учебный год")


def _average(student: Student, start: dt.date, end: dt.date, scale, quarter) -> float | None:
    grades = []
    for item in student_summary(student.pk, start, end, scale, quarter=quarter):
        stats = item["stats"]
        value = stats.final if stats.final is not None else stats.quarter_grade
        if value is not None:
            grades.append(value)
    return round(sum(grades) / len(grades), 1) if grades else None


def _assessments(student: Student, start: dt.date, end: dt.date, calendar) -> list:
    lessons = schedule.lessons_between(start, end).exclude(kind=LessonKind.FO).exclude(status=LessonStatus.CANCELLED)
    return [lesson for lesson in schedule.for_student(list(lessons), student.pk) if lesson.is_live]


def _when(day: dt.date, current: dt.date, slot: int | None = None) -> str:
    if day == current:
        return _("сегодня, {slot} урок").format(slot=slot) if slot else _("сегодня")
    if day == current + dt.timedelta(days=1):
        return _("завтра")
    return date_with_weekday(day)


def home_payload(student: Student) -> dict:
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    current = today()
    quarter = calendar.current_quarter()
    if quarter is not None:
        start, end = quarter.starts, min(quarter.ends, current)
    else:
        start, end = current.replace(day=1), current
    seen_end = max(start, end)

    # --- четыре числа ---
    average = _average(student, start, seen_end, scale, quarter)
    attendance = student_attendance(student.pk, start, seen_end)
    missed = attendance.absent
    upcoming = sorted(
        _assessments(student, current, current + dt.timedelta(days=SOON_DAYS), calendar),
        key=lambda lesson: (lesson.date, lesson.slot),
    )
    nearest_sor = next((lesson for lesson in upcoming if lesson.kind == LessonKind.SOR), None)
    year_start = calendar.year.starts if calendar.year is not None else start
    olympiads = Activity.objects.filter(
        student=student, category="olympiad", is_confirmed=True, date__gte=year_start
    ).count()
    competitions = Competition.objects.filter(student=student, date__gte=year_start).count()
    achievements = olympiads + competitions

    kpis = [
        {
            "code": "average",
            "title": _("Средний балл"),
            "value": f"{average:.1f}".replace(".", ",") if average is not None else "",
            "note": _quarter_words(quarter) if average is not None else _("оценок за четверть пока нет"),
            "tone": "",
        },
        {
            "code": "attendance",
            "title": _("Посещаемость"),
            "value": f"{attendance.pct}%" if attendance.pct is not None else "",
            "note": (
                tn(
                    missed,
                    "{n} пропуск {period}|{n} пропуска {period}|{n} пропусков {period}",
                    period=_quarter_words(quarter),
                )
                if attendance.total
                else _("уроков в четверти пока не было")
            ),
            "tone": "",
        },
        {
            "code": "sor",
            "title": _("Ближайший СОР"),
            "value": (
                f"{nearest_sor.date.day} {school_calendar.MONTHS_GENITIVE[nearest_sor.date.month - 1][:3]}"
                if nearest_sor
                else ""
            ),
            "note": (
                f"{nearest_sor.course.subject.name} — {kind_label(nearest_sor)}"
                if nearest_sor
                else tn(
                    SOON_DAYS,
                    "в ближайший {n} день СОР нет|в ближайшие {n} дня СОР нет|в ближайшие {n} дней СОР нет",
                )
            ),
            "tone": "warn" if nearest_sor else "",
        },
        {
            "code": "achievements",
            "title": _("Достижения"),
            "value": str(achievements),
            "note": _("олимпиады и спорт за учебный год"),
            "tone": "",
        },
    ]

    # --- уроки сегодня с оценками ---
    rows = schedule.for_student(list(schedule.lessons_between(current, current)), student.pk)
    grades = marking.grades_map(rows, [student.pk])
    lessons = []
    for lesson in sorted(rows, key=lambda row: row.slot):
        grade = grades.get((lesson.pk, student.pk))
        payload = lesson_dict(lesson, calendar)
        maximum = scale.fo_max if lesson.kind == LessonKind.FO else lesson.max_score
        lessons.append(
            {
                "id": lesson.pk,
                "bell": payload["bell"],
                "subject": lesson.course.subject.name,
                "room": lesson.room,
                "cohort": payload["cohort"].get("short_name", "") if payload["cohort"]["kind"] != "group" else "",
                "status": lesson.status,
                "status_title": payload["status_title"] if lesson.status != LessonStatus.PLANNED else "",
                "kind": lesson.kind,
                "kind_label": kind_label(lesson) if lesson.kind != LessonKind.FO else "",
                "grade": grade.value if grade else None,
                "mark": _mark_of(grade.value, lesson.kind, maximum, scale) if grade else None,
            }
        )

    # --- скоро: СОР и СОЧ, олимпиады, соревнования ---
    soon = [
        {
            "date": lesson.date,
            "title": f"{lesson.course.subject.name} — {kind_label(lesson)}",
            "when": _when(lesson.date, current, lesson.slot),
            "kind": lesson.kind,
            "kind_label": _("СОЧ") if lesson.kind == LessonKind.SOCH else _("СОР"),
            "link": "/calendar",
        }
        for lesson in upcoming
    ]
    horizon = current + dt.timedelta(days=SOON_DAYS)
    for row in Activity.objects.filter(student=student, category="olympiad", date__gte=current, date__lte=horizon):
        soon.append(
            {
                "date": row.date,
                "title": row.title,
                "when": _when(row.date, current),
                "kind": "olympiad",
                "kind_label": _("олимпиада"),
                "link": "/olympiads",
            }
        )
    for row in Competition.objects.filter(student=student, date__gte=current, date__lte=horizon):
        soon.append(
            {
                "date": row.date,
                "title": row.name,
                "when": _when(row.date, current),
                "kind": "competition",
                "kind_label": _("соревнование"),
                "link": "/sport",
            }
        )
    # ДЗ к сдаче — срок в ближайшие дни, ещё не сдано
    from homework import services as homework
    from homework.views import student_assignments

    now = timezone.now()
    todo = [row for row in student_assignments(student) if row.due_at and now <= row.due_at]
    handed = set(
        homework.Submission.objects.filter(
            student=student, assignment__in=todo, submitted_at__isnull=False
        ).values_list("assignment_id", flat=True)
    )
    for row in todo:
        due = timezone.localtime(row.due_at)
        if row.pk in handed or due.date() > horizon:
            continue
        soon.append(
            {
                "date": due.date(),
                "title": _("{subject} — сдать ДЗ до {time}").format(
                    subject=row.lesson.course.subject.name, time=f"{due:%H:%M}"
                ),
                "when": _when(due.date(), current),
                "kind": "homework",
                "kind_label": _("ДЗ"),
                "link": f"/homework/{row.pk}",
            }
        )
    soon.sort(key=lambda row: row["date"])

    # --- последние оценки ---
    recent = []
    for row in (
        Grade.objects.filter(student=student, lesson__date__lte=current)
        .select_related("lesson", "lesson__course__subject")
        .order_by("-lesson__date", "-lesson__slot")[: RECENT_ROWS * 3]
    ):
        if not row.lesson.is_live:
            continue
        lesson = row.lesson
        maximum = scale.fo_max if lesson.kind == LessonKind.FO else lesson.max_score
        detail = kind_label(lesson)
        if lesson.kind != LessonKind.FO and maximum:
            detail = _("{kind} · {value} из {maximum}").format(kind=detail, value=row.value, maximum=maximum)
        recent.append(
            {
                "id": row.pk,
                "subject": lesson.course.subject.name,
                "detail": detail,
                "value": row.value,
                "mark": _mark_of(row.value, lesson.kind, maximum, scale),
                "_date": lesson.date,
            }
        )
        if len(recent) == RECENT_ROWS:
            break
    # оценки за ДЗ — рядом, с пометкой «ДЗ»; в средний балл идут, только если так решила школа
    from academics.views import homework_grades

    for row in homework_grades(student, current - dt.timedelta(days=60), current).order_by("-checked_at")[:RECENT_ROWS]:
        recent.append(
            {
                "id": f"hw{row.pk}",
                "subject": row.assignment.lesson.course.subject.name,
                "detail": _("ДЗ"),
                "value": row.grade,
                "mark": _mark_of(row.grade, LessonKind.FO, scale.fo_max, scale),
                "_date": row.assignment.lesson.date,
            }
        )
    recent.sort(key=lambda item: item["_date"], reverse=True)
    recent = [{k: v for k, v in item.items() if k != "_date"} for item in recent[:RECENT_ROWS]]

    return {
        "date_words": date_with_weekday(current),
        "quarter": (
            _("{quarter} четверть, неделя {week}").format(
                quarter=quarter.number, week=max(1, (current - quarter.starts).days // 7 + 1)
            )
            if quarter is not None and quarter.starts <= current <= quarter.ends
            else ""
        ),
        "kpis": kpis,
        "lessons": lessons,
        "soon": soon[:SOON_ROWS],
        "recent": recent,
        "lessons_empty": _("сегодня уроков нет") if not lessons else "",
        "achievements_words": plural(achievements, "достижение|достижения|достижений"),
    }


def _mark_of(value: int, kind: str, maximum: int | None, scale) -> int | None:
    """Оценка по пятибалльной для цвета клетки: ФО — из 10, СОР и СОЧ — по порогам шкалы."""
    from academics.results import grade_of

    if not maximum:
        return None
    return grade_of(value * 100 / maximum, scale)
