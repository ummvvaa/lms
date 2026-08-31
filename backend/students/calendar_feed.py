"""Календарь ученика: экзамены, дедлайны, соревнования, задачи (фаза 39).

Событие не хранится отдельной таблицей — оно живёт у источника
(цель, раунд, соревнование, задача), и календарь собирает их на лету.
Копия события устаревала бы молча, как хранимый вердикт соответствия.

Цель, отправленная учеником и ещё не подтверждённая, тоже показывается —
с пометкой «ждёт проверки»: это его календарь и его слова.
"""

from __future__ import annotations

import datetime as dt

from core.domains import ROLE_STUDENT
from students.models import Activity, Competition, ExamGoal, Student

#: как далеко смотрим назад и вперёд — календарь, а не архив
PAST_DAYS = 90
FUTURE_DAYS = 400


def _within(date, today: dt.date) -> bool:
    if date is None:
        return False
    return today - dt.timedelta(days=PAST_DAYS) <= date <= today + dt.timedelta(days=FUTURE_DAYS)


def _event(kind: str, title: str, date, link: str, *, pending: bool = False) -> dict:
    return {"kind": kind, "title": title, "date": date.isoformat(), "link": link, "pending": pending}


def _pending_goal_events(student: Student, today: dt.date) -> list[dict]:
    """Цели из нерешённых предложений ученика — по строкам предложения."""
    from suggestions.models import SuggestionChange, SuggestionStatus

    rows = SuggestionChange.objects.filter(
        suggestion__role=ROLE_STUDENT,
        suggestion__status=SuggestionStatus.PENDING,
        student=student,
        model_label="students.ExamGoal",
    ).exclude(new_object_key="")
    groups: dict[str, dict[str, str]] = {}
    for row in rows:
        key = f"{row.suggestion_id}:{row.new_object_key}"
        groups.setdefault(key, {})[row.field_name] = row.new_value

    events: list[dict] = []
    for fields in groups.values():
        exam = fields.get("exam", "")
        for field, title in (("exam_date", "Экзамен"), ("registration_date", "Регистрация")):
            raw = fields.get(field)
            if not raw:
                continue
            try:
                date = dt.date.fromisoformat(raw)
            except ValueError:
                continue
            if _within(date, today):
                events.append(_event("exam", f"{title}: {exam}".strip(), date, "/my-data", pending=True))
    return events


def events_for(student: Student, today: dt.date | None = None) -> list[dict]:
    """Все события ученика с датами, отсортированные по времени."""
    from django.utils import timezone

    from roadmap.models import Task, TaskStatus
    from universities.models import StudentUniversity

    today = today or timezone.localdate()
    events: list[dict] = []

    for goal in ExamGoal.objects.filter(student=student).select_related("exam"):
        if _within(goal.exam_date, today):
            events.append(_event("exam", f"Экзамен: {goal.exam.name}", goal.exam_date, "/my-data"))
        if _within(goal.registration_date, today):
            events.append(_event("exam", f"Регистрация: {goal.exam.name}", goal.registration_date, "/my-data"))
    events += _pending_goal_events(student, today)

    rows = StudentUniversity.objects.filter(student=student, admission_round__isnull=False).select_related(
        "admission_round", "program__university"
    )
    for row in rows:
        deadline = row.admission_round.deadline
        if _within(deadline, today):
            events.append(_event("deadline", f"Дедлайн: {row.program.university.name}", deadline, "/universities"))

    for competition in Competition.objects.filter(student=student, date__isnull=False):
        if _within(competition.date, today):
            events.append(_event("competition", f"Соревнование: {competition.name}", competition.date, "/my-data"))

    for activity in Activity.objects.filter(student=student, category="olympiad", date__isnull=False):
        if _within(activity.date, today):
            events.append(_event("olympiad", f"Олимпиада: {activity.title}", activity.date, "/my-data"))

    for task in (
        Task.objects.filter(student=student)
        .exclude(status=TaskStatus.DONE)
        .select_related("admission_round", "exam_goal")
    ):
        due = task.effective_due_date
        if _within(due, today):
            events.append(_event("task", f"Задача: {task.title}", due, "/roadmap"))

    events.sort(key=lambda e: e["date"])
    return events


def state(student: Student, today: dt.date | None = None) -> dict:
    """Календарь целиком плюс ближайшее событие с обратным отсчётом."""
    from django.utils import timezone

    today = today or timezone.localdate()
    events = events_for(student, today)
    upcoming = [e for e in events if e["date"] >= today.isoformat()]
    nearest = upcoming[0] if upcoming else None
    if nearest is not None:
        days_left = (dt.date.fromisoformat(nearest["date"]) - today).days
        nearest = {**nearest, "days_left": days_left}
    return {"today": today.isoformat(), "events": events, "nearest": nearest}
