"""«Задания на сегодня»: три задачи, выбранные из роадмапа.

Выбор — по приоритету и близости дедлайна. Никакого сравнения с другими
учениками, рейтингов и таблиц лидеров: в контексте поступления это вредно.
"""

from __future__ import annotations

from django.utils import timezone

from engagement.models import XPKind
from engagement.scoring import award_size
from roadmap.models import Task, TaskStatus
from students.models import Student

#: Сколько задач показываем. Три — столько, сколько реально делается за день.
HOW_MANY = 3

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}

#: Дальше этого срока задача уже не «на сегодня».
FAR_AWAY = 10_000


def _urgency(task: Task) -> tuple[int, int]:
    """Чем меньше — тем выше в списке: приоритет, потом близость срока."""
    due = task.effective_due_date
    days = (due - timezone.localdate()).days if due else FAR_AWAY
    return (PRIORITY_RANK.get(task.priority, 1), days)


def for_student(student: Student, *, limit: int = HOW_MANY) -> list[dict]:
    """Три ближайших дела с указанием XP."""
    tasks = (
        Task.objects.filter(student=student)
        .exclude(status=TaskStatus.DONE)
        .select_related("admission_round__program__university")
    )
    chosen = sorted(tasks, key=_urgency)[:limit]
    reward = award_size(XPKind.TASK_DONE)

    rows = []
    for task in chosen:
        due = task.effective_due_date
        rows.append(
            {
                "id": task.pk,
                "title": task.title,
                "category": task.category,
                "priority": task.priority,
                "status": task.status,
                "due_date": due.isoformat() if due else None,
                "days_left": (due - timezone.localdate()).days if due else None,
                "from_deadline": bool(task.admission_round_id),
                "university_name": (task.admission_round.program.university.name if task.admission_round_id else None),
                "xp": reward,
            }
        )
    return rows
