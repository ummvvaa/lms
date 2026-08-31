"""Напоминания о событиях и автозадачи о регистрации (фазы 39 и 44).

Уведомление приходит в колокольчик за N дней до события; сроки
настраиваются отдельно для экзаменов, дедлайнов вузов и задач
(`REMIND_*` в настройках). Задача «Зарегистрироваться на экзамен»
появляется заранее и ссылается на цель, а не копирует дату:
сдвинулась дата экзамена — сдвинулся срок (инвариант №4).

Запускается раз в день по расписанию Celery; повторный запуск в тот же
день ничего не дублирует.
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.db import IntegrityError

from core.models import Notification
from roadmap.models import Task, TaskCategory, TaskPriority, TaskStatus
from students.models import ExamGoal


def _today() -> dt.date:
    from django.utils import timezone

    return timezone.localdate()


def create_registration_tasks(today: dt.date | None = None) -> int:
    """Задача «Зарегистрироваться на экзамен» за N дней до даты экзамена.

    Только для целей без даты регистрации в прошлом: если регистрация
    уже позади — напоминать поздно, если задача уже есть — вторая не нужна.
    """
    from django.db.models import Exists, OuterRef

    today = today or _today()
    horizon = today + dt.timedelta(days=settings.REMIND_EXAM_TASK_DAYS)
    created = 0
    # `exclude(tasks__…isnull=True)` здесь не годится: LEFT JOIN подсовывает
    # пустую строку, и цель без задач выглядела бы как цель с живой задачей
    live_task = Task.objects.filter(exam_goal=OuterRef("pk"))
    goals = (
        ExamGoal.objects.filter(exam_date__gte=today, exam_date__lte=horizon)
        .annotate(has_task=Exists(live_task))
        .filter(has_task=False)
        .select_related("exam", "student")
    )
    for goal in goals:
        try:
            Task.objects.create(
                student=goal.student,
                title=f"Зарегистрироваться на экзамен {goal.exam.name}",
                category=TaskCategory.TEST,
                priority=TaskPriority.HIGH,
                status=TaskStatus.TODO,
                description=f"Экзамен {goal.exam.name} назначен на {goal.exam_date:%d.%m.%Y} — "
                "проверьте регистрацию заранее",
                exam_goal=goal,
            )
            created += 1
        except IntegrityError:
            # параллельный запуск уже завёл задачу — это не ошибка
            continue
    return created


def create_scholarship_tasks(today: dt.date | None = None) -> int:
    """Задача «Подать на стипендию» за N дней до её дедлайна (фаза 44).

    Только по сохранённым стипендиям и только пока срок не прошёл: срок
    задачи берётся из самой стипендии, а не копируется (инвариант №4).
    """
    from django.db.models import Exists, OuterRef

    from universities.models import SavedScholarship

    today = today or _today()
    horizon = today + dt.timedelta(days=settings.REMIND_SCHOLARSHIP_DAYS)
    created = 0
    rows = (
        SavedScholarship.objects.filter(scholarship__deadline__gte=today, scholarship__deadline__lte=horizon)
        .annotate(
            has_task=Exists(Task.objects.filter(student=OuterRef("student_id"), scholarship=OuterRef("scholarship_id")))
        )
        .filter(has_task=False)
        .select_related("scholarship", "student")
    )
    for row in rows:
        try:
            Task.objects.create(
                student=row.student,
                title=f"Подать на стипендию {row.scholarship.name}",
                category=TaskCategory.FINANCE,
                priority=TaskPriority.HIGH,
                status=TaskStatus.TODO,
                description=f"Дедлайн подачи — {row.scholarship.deadline:%d.%m.%Y}. "
                "Срок берётся из справочника: сдвинется там — сдвинется здесь",
                scholarship=row.scholarship,
            )
            created += 1
        except IntegrityError:
            # параллельный запуск уже завёл задачу — это не ошибка
            continue
    return created


def _notify_once(user, *, kind: str, template: str, link: str, **params) -> bool:
    """Уведомление один раз в сутки: повторный запуск задачи не дублирует.

    Дедупликация идёт по реальным часам, а не по дню события: задача
    запускается расписанием, и второй запуск в те же сутки должен молчать.
    """
    from django.utils import timezone

    from core.i18n import render
    from materials.services import notify

    if user is None:
        return False
    text = render(getattr(user, "language", "ru"), template, **params)
    exists = Notification.objects.filter(
        recipient=user, kind=kind, link=link, text=text, created_at__gte=timezone.now() - dt.timedelta(days=1)
    ).exists()
    if exists:
        return False
    return notify(user, kind=kind, template=template, link=link, **params) is not None


def send_event_reminders(today: dt.date | None = None) -> int:
    """Напоминания за N дней: экзамены и регистрации, дедлайны вузов, задачи."""
    from universities.models import SavedScholarship, StudentUniversity

    today = today or _today()
    sent = 0

    exam_day = today + dt.timedelta(days=settings.REMIND_EXAM_DAYS)
    for goal in ExamGoal.objects.filter(exam_date=exam_day).select_related("exam", "student__user"):
        sent += _notify_once(
            goal.student.user,
            kind=Notification.Kind.EVENT_REMINDER,
            template="Экзамен {exam} через {days} дней — {date}",
            link="/calendar",
            exam=goal.exam.name,
            days=settings.REMIND_EXAM_DAYS,
            date=f"{goal.exam_date:%d.%m.%Y}",
        )
    for goal in ExamGoal.objects.filter(registration_date=exam_day).select_related("exam", "student__user"):
        sent += _notify_once(
            goal.student.user,
            kind=Notification.Kind.EVENT_REMINDER,
            template="Регистрация на {exam} закрывается {date}",
            link="/calendar",
            exam=goal.exam.name,
            date=f"{goal.registration_date:%d.%m.%Y}",
        )

    deadline_day = today + dt.timedelta(days=settings.REMIND_DEADLINE_DAYS)
    rows = StudentUniversity.objects.filter(
        admission_round__isnull=False, admission_round__deadline=deadline_day
    ).select_related("admission_round", "program__university", "student__user")
    for row in rows:
        sent += _notify_once(
            row.student.user,
            kind=Notification.Kind.EVENT_REMINDER,
            template="Дедлайн подачи в {university} — {date}",
            link="/universities",
            university=row.program.university.name,
            date=f"{row.admission_round.deadline:%d.%m.%Y}",
        )

    scholarship_day = today + dt.timedelta(days=settings.REMIND_SCHOLARSHIP_DAYS)
    saved = SavedScholarship.objects.filter(scholarship__deadline=scholarship_day).select_related(
        "scholarship", "student__user"
    )
    for row in saved:
        sent += _notify_once(
            row.student.user,
            kind=Notification.Kind.EVENT_REMINDER,
            template="Дедлайн стипендии {name} — {date}",
            link="/scholarships",
            name=row.scholarship.name,
            date=f"{row.scholarship.deadline:%d.%m.%Y}",
        )

    task_day = today + dt.timedelta(days=settings.REMIND_TASK_DAYS)
    tasks = (
        Task.objects.exclude(status=TaskStatus.DONE)
        .filter(due_date=task_day, admission_round__isnull=True, exam_goal__isnull=True, scholarship__isnull=True)
        .select_related("student__user")
    )
    for task in tasks:
        sent += _notify_once(
            task.student.user,
            kind=Notification.Kind.EVENT_REMINDER,
            template="Срок задачи «{title}» — {date}",
            link="/roadmap",
            title=task.title,
            date=f"{task.due_date:%d.%m.%Y}",
        )
    # у задач из целей срок живёт в цели: напоминаем по нему же
    goal_tasks = (
        Task.objects.exclude(status=TaskStatus.DONE)
        .filter(exam_goal__isnull=False)
        .select_related("student__user", "exam_goal")
    )
    for task in goal_tasks:
        if task.effective_due_date == task_day:
            sent += _notify_once(
                task.student.user,
                kind=Notification.Kind.EVENT_REMINDER,
                template="Срок задачи «{title}» — {date}",
                link="/roadmap",
                title=task.title,
                date=f"{task.effective_due_date:%d.%m.%Y}",
            )
    return sent


def run_daily(today: dt.date | None = None) -> dict:
    """Дневной прогон: сначала автозадачи, потом напоминания."""
    today = today or _today()
    return {
        "tasks_created": create_registration_tasks(today),
        "scholarship_tasks_created": create_scholarship_tasks(today),
        "reminders_sent": send_event_reminders(today),
    }
