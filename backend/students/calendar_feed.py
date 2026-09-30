"""Календарь ученика: экзамены, дедлайны, стипендии, соревнования, задачи.

Событие не хранится отдельной таблицей — оно живёт у источника
(цель, раунд, стипендия, соревнование, задача), и календарь собирает их
на лету.
Копия события устаревала бы молча, как хранимый вердикт соответствия.

Цель, отправленная учеником и ещё не подтверждённая, тоже показывается —
с пометкой «ждёт проверки»: это его календарь и его слова.
"""

from __future__ import annotations

import datetime as dt

from django.utils.translation import gettext as _

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
        titles = (("exam_date", _("Экзамен: {exam}")), ("registration_date", _("Регистрация: {exam}")))
        for field, title in titles:
            raw = fields.get(field)
            if not raw:
                continue
            try:
                date = dt.date.fromisoformat(raw)
            except ValueError:
                continue
            if _within(date, today):
                events.append(_event("exam", title.format(exam=exam).strip(), date, "/my-data", pending=True))
    return events


def events_for(student: Student, today: dt.date | None = None) -> list[dict]:
    """Все события ученика с датами, отсортированные по времени."""
    from django.utils import timezone

    from core.parallels import has_admission
    from roadmap.models import Task, TaskStatus
    from universities.models import StudentUniversity

    today = today or timezone.localdate()
    if not has_admission(student):
        return _junior_events(student, today)
    events: list[dict] = []

    for goal in ExamGoal.objects.filter(student=student).select_related("exam"):
        if _within(goal.exam_date, today):
            events.append(_event("exam", _("Экзамен: {exam}").format(exam=goal.exam.name), goal.exam_date, "/my-data"))
        if _within(goal.registration_date, today):
            events.append(
                _event("exam", _("Регистрация: {exam}").format(exam=goal.exam.name), goal.registration_date, "/my-data")
            )
    events += _pending_goal_events(student, today)

    rows = StudentUniversity.objects.filter(student=student, admission_round__isnull=False).select_related(
        "admission_round", "program__university"
    )
    for row in rows:
        deadline = row.admission_round.deadline
        if _within(deadline, today):
            events.append(
                _event(
                    "deadline",
                    _("Дедлайн: {university}").format(university=row.program.university.name),
                    deadline,
                    "/universities",
                )
            )

    # дедлайны сохранённых стипендий (фаза 44): дата живёт у самой
    # стипендии, календарь только показывает её (инвариант №4)
    from universities.models import SavedScholarship

    saved = SavedScholarship.objects.filter(student=student, scholarship__deadline__isnull=False).select_related(
        "scholarship"
    )
    for row in saved:
        deadline = row.scholarship.deadline
        if _within(deadline, today):
            events.append(
                _event(
                    "scholarship",
                    _("Стипендия: {scholarship}").format(scholarship=row.scholarship.name),
                    deadline,
                    "/scholarships",
                )
            )

    for competition in Competition.objects.filter(student=student, date__isnull=False):
        if _within(competition.date, today):
            events.append(
                _event(
                    "competition",
                    _("Соревнование: {competition}").format(competition=competition.name),
                    competition.date,
                    "/my-data",
                )
            )

    for activity in Activity.objects.filter(student=student, category="olympiad", date__isnull=False):
        if _within(activity.date, today):
            events.append(
                _event(
                    "olympiad", _("Олимпиада: {olympiad}").format(olympiad=activity.title), activity.date, "/my-data"
                )
            )

    for task in (
        Task.objects.filter(student=student)
        .exclude(status__in=TaskStatus.closed())
        .select_related("admission_round", "exam_goal")
    ):
        due = task.effective_due_date
        if _within(due, today):
            events.append(_event("task", _("Задача: {task}").format(task=task.title), due, "/roadmap"))

    events.sort(key=lambda e: e["date"])
    return events


def _junior_events(student: Student, today: dt.date) -> list[dict]:
    """Календарь 8–10: олимпиады и соревнования. Поступления — экзаменов,
    дедлайнов, стипендий и задач плана — у 8–10 нет (`core/parallels.py`);
    СОР и СОЧ приходят днями из `assessment_days`, как у 11."""
    events: list[dict] = []
    for competition in Competition.objects.filter(student=student, date__isnull=False):
        if _within(competition.date, today):
            events.append(
                _event(
                    "competition",
                    _("Соревнование: {competition}").format(competition=competition.name),
                    competition.date,
                    "/sport",
                )
            )
    for activity in Activity.objects.filter(student=student, category="olympiad", date__isnull=False):
        if _within(activity.date, today):
            events.append(
                _event(
                    "olympiad", _("Олимпиада: {olympiad}").format(olympiad=activity.title), activity.date, "/olympiads"
                )
            )
    events.sort(key=lambda e: e["date"])
    return events


def assessment_days(student: Student, today: dt.date) -> list[dict]:
    """Дни СОР и СОЧ: в календаре это выделенные дни с подписью, а не события.

    Уроки живут в «Расписании» (решение владельца, 28.09.2026): в ленте
    календаря их нет, а день с работой подсвечен и подписан «предмет — вид».
    """
    from academics.models import LessonKind
    from academics.payloads import kind_label
    from academics.schedule import student_lessons

    start = today - dt.timedelta(days=PAST_DAYS)
    end = today + dt.timedelta(days=FUTURE_DAYS)
    days: list[dict] = []
    for lesson in student_lessons(student.pk, start, end):
        if lesson.kind == LessonKind.FO or not lesson.is_live:
            continue
        subject = lesson.course.subject
        # «СОР 2» не рвётся между словом и номером: неразрывный пробел
        work = kind_label(lesson).replace(" ", "\u00a0")
        days.append(
            {
                "date": lesson.date.isoformat(),
                "title": f"{subject.name} — {work}",
                "short": f"{subject.short or subject.name} — {work}",
            }
        )
    days.sort(key=lambda row: row["date"])
    return days


def homework_events(student: Student, today: dt.date) -> list[dict]:
    """Сроки ДЗ со сдачей в LMS — у всех параллелей; сданное из календаря уходит."""
    from django.utils import timezone

    from homework.models import Submission
    from homework.views import student_assignments

    rows = [row for row in student_assignments(student) if row.due_at is not None]
    handed = set(
        Submission.objects.filter(student=student, assignment__in=rows, submitted_at__isnull=False).values_list(
            "assignment_id", flat=True
        )
    )
    events = []
    for row in rows:
        due = timezone.localtime(row.due_at)
        if row.pk in handed or not _within(due.date(), today):
            continue
        title = _("ДЗ: {subject} — до {time}").format(subject=row.lesson.course.subject.name, time=f"{due:%H:%M}")
        events.append(_event("homework", title, due.date(), f"/homework/{row.pk}"))
    return events


def state(student: Student, today: dt.date | None = None) -> dict:
    """Календарь целиком плюс ближайшее событие с обратным отсчётом."""
    from django.utils import timezone

    today = today or timezone.localdate()
    events = events_for(student, today) + homework_events(student, today)
    events.sort(key=lambda e: e["date"])
    upcoming = [e for e in events if e["date"] >= today.isoformat()]
    nearest = upcoming[0] if upcoming else None
    if nearest is not None:
        days_left = (dt.date.fromisoformat(nearest["date"]) - today).days
        nearest = {**nearest, "days_left": days_left}
    return {
        "today": today.isoformat(),
        "events": events,
        "nearest": nearest,
        "assessment_days": assessment_days(student, today),
    }


def staff_state(today: dt.date | None = None) -> dict:
    """Календарь сотрудника: события его учеников, а не свои (фаза 49).

    Директор смотрит на тот же месяц, что и ученик, но в строке события
    стоит число сдающих или подающих: «Пробный SAT · 84 ученика». Личных
    задач конкретного ребёнка здесь нет — это школьный календарь.
    """
    from django.db.models import Count, Q
    from django.utils import timezone

    from universities.models import AdmissionRound

    today = today or timezone.localdate()
    start = today - dt.timedelta(days=PAST_DAYS)
    end = today + dt.timedelta(days=FUTURE_DAYS)
    events: list[dict] = []

    goals = (
        ExamGoal.objects.filter(student__is_active=True, exam_date__gte=start, exam_date__lte=end)
        .values("exam_date", "exam__name")
        .annotate(students=Count("id"))
    )
    for row in goals:
        events.append(
            {
                **_event("exam", row["exam__name"], row["exam_date"], "/mocks"),
                "students": row["students"],
            }
        )

    rounds = (
        AdmissionRound.objects.filter(deadline__gte=start, deadline__lte=end)
        .annotate(students=Count("applicants", filter=Q(applicants__student__is_active=True)))
        .select_related("program__university")
    )
    for row in rounds:
        if row.students == 0:
            continue
        events.append(
            {
                **_event(
                    "deadline",
                    _("Дедлайн {university}").format(university=row.program.university.name),
                    row.deadline,
                    "/deadlines",
                ),
                "students": row.students,
            }
        )

    competitions = (
        Competition.objects.filter(student__is_active=True, date__gte=start, date__lte=end)
        .values("name", "date")
        .annotate(students=Count("student_id", distinct=True))
    )
    for row in competitions:
        events.append(
            {
                **_event("competition", row["name"], row["date"], "/competitions"),
                "students": row["students"],
            }
        )

    events.sort(key=lambda e: e["date"])
    upcoming = [e for e in events if e["date"] >= today.isoformat()]
    nearest = upcoming[0] if upcoming else None
    if nearest is not None:
        nearest = {**nearest, "days_left": (dt.date.fromisoformat(nearest["date"]) - today).days}
    return {"today": today.isoformat(), "events": events, "nearest": nearest}
