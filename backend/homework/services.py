"""Правила сдачи ДЗ: кому задано, срок, сдача до и после срока, проверка, выполнение.

Кому задано — ученикам состава урока на дату урока: ДЗ на подгруппу или поток
получают только её ученики (`academics.cohorts.member_ids`). Проверяет тот, кто
ведёт урок или журнал, Кымбат и администратор; 7-дневного окна у проверки нет,
и проверка не трогает отметку «не был» за урок. Уведомлений нет (решение
владельца, 30.09.2026): ученик видит задание в разделе «Домашние задания»,
в расписании и календаре.

«Выполнение ДЗ, %» — сдано вовремя / всего заданий со сдачей, срок которых
прошёл в периоде. Нет заданий — нет процента, а не ноль.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from academics.models import Lesson, LessonStatus
from core.domains import ROLE_ADMIN, ROLE_STUDENT
from homework.models import Assignment, FileState, LatePolicy, Submission

EXAM_DIRECTOR = "director_exam"
#: срок «сегодня вечером» — 20:00 по Алматы
EVENING = dt.time(20, 0)


class HomeworkRefused(ValueError):
    """Так нельзя — текст объясняет почему."""


# --- Кто что может ------------------------------------------------------------------


def teaches(user, lesson: Lesson) -> bool:
    """Ведёт урок (или заменяет) или ведёт журнал этого урока."""
    uid = getattr(user, "pk", None)
    if not uid:
        return False
    return uid in (lesson.teacher_id, lesson.substitute_id, lesson.course.teacher_id)


def may_set(user, lesson: Lesson) -> bool:
    """Задаёт ДЗ со сдачей тот, кто ведёт урок, и администратор."""
    if getattr(user, "role", "") == ROLE_ADMIN:
        return True
    return getattr(user, "role", "") != ROLE_STUDENT and teaches(user, lesson)


def may_check(user, lesson: Lesson) -> bool:
    """Проверяет учитель урока или журнала, Кымбат и администратор."""
    role = getattr(user, "role", "")
    if role in (ROLE_ADMIN, EXAM_DIRECTOR):
        return True
    return role != ROLE_STUDENT and teaches(user, lesson)


def recipients(lesson: Lesson) -> list[int]:
    """Кому задано: состав урока на дату урока."""
    from academics.cohorts import member_ids

    return member_ids(lesson.course.cohort, lesson.date)


def is_recipient(student_id: int, lesson: Lesson) -> bool:
    return student_id in set(recipients(lesson))


# --- Срок ---------------------------------------------------------------------------


def _at(day: dt.date, time: dt.time) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, time), timezone.get_current_timezone())


def lesson_start(lesson: Lesson) -> dt.datetime | None:
    """Начало урока по звонкам его групп; урока нет в сетке — None."""
    from academics import calendar as school_calendar
    from academics.calendar import lesson_groups

    span = school_calendar.load().bell(lesson.slot, lesson_groups(lesson))
    return _at(lesson.date, span[0]) if span else None


def next_lesson(lesson: Lesson) -> Lesson | None:
    """Следующий живой урок того же журнала."""
    return (
        Lesson.objects.filter(course_id=lesson.course_id)
        .exclude(status=LessonStatus.CANCELLED)
        .exclude(pk=lesson.pk)
        .filter(date__gte=lesson.date)
        .exclude(date=lesson.date, slot__lte=lesson.slot)
        .order_by("date", "slot")
        .first()
    )


def due_options(lesson: Lesson) -> dict:
    """Сроки на выбор: начало следующего урока журнала и «сегодня 20:00»."""
    following = next_lesson(lesson)
    start = lesson_start(following) if following else None
    evening = _at(max(timezone.localdate(), lesson.date), EVENING)
    return {"next_lesson": start, "evening": evening}


def default_due(lesson: Lesson) -> dt.datetime:
    """По умолчанию — начало следующего урока этого журнала; его нет — вечер дня урока."""
    options = due_options(lesson)
    return options["next_lesson"] or options["evening"]


# --- Задание ------------------------------------------------------------------------


def assignment_of(lesson: Lesson) -> Assignment | None:
    return Assignment.objects.filter(lesson=lesson).first()


@transaction.atomic
def save_assignment(
    lesson: Lesson, *, requires_submission: bool, due_at: dt.datetime | None, late_policy: str, actor
) -> Assignment:
    """Сдача в LMS, срок и правило после срока. Текст ДЗ — `Lesson.homework`."""
    if late_policy not in LatePolicy.values:
        raise HomeworkRefused(_("После срока — принимать с пометкой или закрыть сдачу"))
    if requires_submission and due_at is None:
        due_at = default_due(lesson)
    row = assignment_of(lesson)
    if row is None:
        row = Assignment(lesson=lesson, created_by=actor if getattr(actor, "pk", None) else None)
    row.requires_submission = requires_submission
    row.due_at = due_at
    row.late_policy = late_policy
    row.save()
    return row


def ensure_assignment(lesson: Lesson, actor) -> Assignment:
    """Файл учителя без сдачи — задание заводится без сдачи, ДЗ видно в уроке."""
    row = assignment_of(lesson)
    if row is None:
        row = Assignment.objects.create(lesson=lesson, created_by=actor if getattr(actor, "pk", None) else None)
    return row


# --- Сдача ----------------------------------------------------------------------------


def is_past_due(assignment: Assignment, now: dt.datetime | None = None) -> bool:
    return assignment.due_at is not None and (now or timezone.now()) > assignment.due_at


def late_minutes(assignment: Assignment, when: dt.datetime) -> int | None:
    """На сколько минут позже срока; вовремя — None."""
    if assignment.due_at is None or when <= assignment.due_at:
        return None
    return max(1, math.ceil((when - assignment.due_at).total_seconds() / 60))


def draft_of(assignment: Assignment, student) -> Submission:
    """Сдача ученика: черновик заводится при первом файле или тексте."""
    row = Submission.objects.filter(assignment=assignment, student=student).first()
    if row is None:
        row = Submission.objects.create(assignment=assignment, student=student)
    return row


def may_change(submission: Submission, now: dt.datetime | None = None) -> None:
    """Менять работу можно до срока; после срока — только несданную и только если учитель принимает."""
    assignment = submission.assignment
    if submission.is_checked:
        raise HomeworkRefused(_("Учитель уже проверил работу — менять её нельзя"))
    if not is_past_due(assignment, now):
        return
    if submission.is_submitted:
        raise HomeworkRefused(_("Срок прошёл — сданную работу можно только посмотреть"))
    if assignment.late_policy == LatePolicy.CLOSE:
        raise HomeworkRefused(_("Срок прошёл, учитель не принимает работы после срока"))


@transaction.atomic
def submit(assignment: Assignment, student, *, text: str, link: str, comment: str) -> Submission:
    """«Сдать»: до срока — вовремя, после — по правилу задания."""
    if not assignment.requires_submission:
        raise HomeworkRefused(_("По этому заданию сдача в LMS не нужна"))
    if not is_recipient(student.pk, assignment.lesson):
        raise HomeworkRefused(_("Это задание не вашего состава"))
    submission = draft_of(assignment, student)
    now = timezone.now()
    may_change(submission, now)
    # недогруженный файл в работу не входит и сдачу не держит: оборванную
    # загрузку (закрыли вкладку, пропала сеть) уберёт ночная уборка
    ready = submission.files.filter(state=FileState.READY, archived_at__isnull=True).count()
    text, link = text.strip(), link.strip()
    if link and not link.startswith(("http://", "https://")):
        raise HomeworkRefused(_("Ссылка начинается с http:// или https://"))
    if not ready and not text and not link:
        raise HomeworkRefused(_("Приложите файл, напишите ответ или дайте ссылку"))
    submission.text = text[:20000]
    submission.link = link[:500]
    submission.comment = comment.strip()[:2000]
    submission.submitted_at = now
    submission.late_minutes = late_minutes(assignment, now)
    submission.save()
    if submission.late_minutes is None:
        _award(student, submission)
    return submission


def _award(student, submission: Submission) -> None:
    """XP за сдачу в срок — если XP есть у параллели ученика; за оценку XP нет."""
    from core.parallels import parallel_of, section_open

    if not section_open("achievements", parallel_of(student)):
        return
    from engagement.models import XPKind
    from engagement.scoring import award

    award(
        student,
        kind=XPKind.HOMEWORK_ON_TIME,
        object_label="homework.Submission",
        object_id=str(submission.pk),
        note=submission.assignment.lesson.course.subject.title,
    )


@transaction.atomic
def check(submission: Submission, *, grade: int | None, comment: str, actor) -> Submission:
    """Проверено: оценка 1–10 или «без оценки» и комментарий. Вернуть на доработку нельзя."""
    if not submission.is_submitted:
        raise HomeworkRefused(_("Работа ещё не сдана"))
    if grade is not None and not 1 <= int(grade) <= 10:
        raise HomeworkRefused(_("Оценка — от 1 до 10 или «без оценки»"))
    submission.grade = int(grade) if grade is not None else None
    submission.teacher_comment = comment.strip()[:4000]
    submission.checked_at = timezone.now()
    submission.checked_by = actor if getattr(actor, "pk", None) else None
    submission.save()
    return submission


# --- Состояния ------------------------------------------------------------------------

TODO, REVIEW, CHECKED, MISSED = "todo", "review", "checked", "missed"


def student_state(assignment: Assignment, submission: Submission | None, now: dt.datetime | None = None) -> str:
    """Вкладка ученика: к сдаче, на проверке, проверено, не сдано."""
    if submission is not None and submission.is_checked:
        return CHECKED
    if submission is not None and submission.is_submitted:
        return REVIEW
    if is_past_due(assignment, now) and assignment.late_policy == LatePolicy.CLOSE:
        return MISSED
    return TODO


def journal_state(submission: Submission | None, assignment: Assignment, now: dt.datetime | None = None) -> dict:
    """Клетка «ДЗ» журнала: оценка, ✓ без оценки, «сдано» (ждёт проверки), «—» не сдано."""
    if submission is None or not submission.is_submitted:
        missed = is_past_due(assignment, now)
        return {"state": "missed" if missed else "pending", "grade": None, "late": False, "submission": None}
    if submission.is_checked:
        return {
            "state": "checked",
            "grade": submission.grade,
            "late": submission.late_minutes is not None,
            "submission": submission.pk,
        }
    return {
        "state": "submitted",
        "grade": None,
        "late": submission.late_minutes is not None,
        "submission": submission.pk,
    }


def submissions_map(lesson_ids: list[int], student_ids: list[int]) -> dict[tuple[int, int], Submission]:
    """`(урок, ученик)` → сдача: для журнала и оценок."""
    rows = Submission.objects.filter(
        assignment__lesson_id__in=lesson_ids, assignment__requires_submission=True, student_id__in=student_ids
    ).select_related("assignment")
    return {(row.assignment.lesson_id, row.student_id): row for row in rows}


def assignments_map(lesson_ids: list[int]) -> dict[int, Assignment]:
    """Урок → задание со сдачей."""
    rows = Assignment.objects.filter(lesson_id__in=lesson_ids, requires_submission=True)
    return {row.lesson_id: row for row in rows}


def graded_map(lesson_ids: list[int], student_ids: list[int]) -> dict[tuple[int, int], int]:
    """`(урок, ученик)` → оценка за ДЗ, где работа проверена с оценкой.

    Внутри кэша запроса (успеваемость школы — сотни курсов) оценки за ДЗ
    читаются один раз на всех и дальше берутся из памяти.
    """
    from academics import cache

    store = cache.current()
    if store is not None:
        if "homework_graded" not in store.memo:
            store.memo["homework_graded"] = {
                (lesson_id, student_id): grade
                for lesson_id, student_id, grade in Submission.objects.filter(
                    assignment__requires_submission=True, checked_at__isnull=False, grade__isnull=False
                ).values_list("assignment__lesson_id", "student_id", "grade")
            }
        wanted_lessons, wanted_students = set(lesson_ids), set(student_ids)
        return {
            key: grade
            for key, grade in store.memo["homework_graded"].items()
            if key[0] in wanted_lessons and key[1] in wanted_students
        }
    rows = Submission.objects.filter(
        assignment__lesson_id__in=lesson_ids,
        assignment__requires_submission=True,
        student_id__in=student_ids,
        checked_at__isnull=False,
        grade__isnull=False,
    ).values_list("assignment__lesson_id", "student_id", "grade")
    return {(lesson_id, student_id): grade for lesson_id, student_id, grade in rows}


def quarter_rule() -> tuple[bool, float]:
    """Входят ли оценки за ДЗ в четвертную и с каким весом к одной оценке ФО."""
    from core import school_rules

    values = school_rules.values()
    return bool(values[school_rules.HOMEWORK_IN_QUARTER]), values[school_rules.HOMEWORK_WEIGHT] / 100


# --- Выполнение ------------------------------------------------------------------------


@dataclass
class Completion:
    """Выполнение ДЗ ученика за период: задания со сдачей, у которых срок прошёл."""

    total: int = 0
    on_time: int = 0
    late: int = 0
    missed: int = 0

    @property
    def pct(self) -> int | None:
        return round(self.on_time * 100 / self.total) if self.total else None

    def as_dict(self) -> dict:
        return {"total": self.total, "on_time": self.on_time, "late": self.late, "missed": self.missed, "pct": self.pct}


def completion(student_ids: list[int], start: dt.date, end: dt.date) -> dict[int, Completion]:
    """Сдано вовремя / всего заданий со сдачей, срок которых прошёл в периоде."""
    from academics.cohorts import member_ids

    now = timezone.now()
    out = {sid: Completion() for sid in student_ids}
    if not student_ids:
        return out
    wanted = set(student_ids)
    first = _at(start, dt.time(0, 0))
    last = min(now, _at(end, dt.time(23, 59, 59)))
    rows = list(
        Assignment.objects.filter(requires_submission=True, due_at__gte=first, due_at__lte=last)
        .exclude(lesson__status=LessonStatus.CANCELLED)
        .filter(lesson__archived_at__isnull=True)
        .select_related("lesson", "lesson__course", "lesson__course__cohort")
    )
    if not rows:
        return out
    done = {
        (row.assignment_id, row.student_id): row
        for row in Submission.objects.filter(
            assignment__in=rows, student_id__in=student_ids, submitted_at__isnull=False
        )
    }
    members: dict[tuple[int, dt.date], set[int]] = {}
    for assignment in rows:
        lesson = assignment.lesson
        key = (lesson.course.cohort_id, lesson.date)
        if key not in members:
            members[key] = set(member_ids(lesson.course.cohort, lesson.date))
        for sid in members[key] & wanted:
            item = out[sid]
            item.total += 1
            submission = done.get((assignment.pk, sid))
            if submission is None:
                item.missed += 1
            elif submission.late_minutes is None:
                item.on_time += 1
            else:
                item.late += 1
    return out


def current_period(on: dt.date | None = None) -> tuple[dt.date, dt.date]:
    """Период по умолчанию — текущая четверть; её нет — последние 60 дней."""
    from academics import calendar as school_calendar

    day = on or timezone.localdate()
    quarter = school_calendar.load().current_quarter()
    if quarter is not None:
        return quarter.starts, min(quarter.ends, day)
    return day - dt.timedelta(days=60), day


def completion_pct(student_id: int) -> int | None:
    """«Выполнение ДЗ, %» ученика за текущую четверть."""
    start, end = current_period()
    return completion([student_id], start, end)[student_id].pct
