"""Генерация задач: из шаблонов потока и из дедлайнов вузов.

Задача, созданная из дедлайна вуза, появляется у всех, кто туда подаётся.
Срок такой задачи не копируется, а берётся из `AdmissionRound`: сдвиг
дедлайна в справочнике сдвигает задачи у всех сразу (инвариант №4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db import transaction

from roadmap.models import Task, TaskCategory, TaskPriority, TaskStatus, TaskTemplate
from students.models import Student
from universities.models import AdmissionRound


@dataclass
class GenerationResult:
    created: int = 0
    skipped: int = 0

    def as_dict(self) -> dict:
        return {"created": self.created, "skipped": self.skipped}


def _due_from_template(template: TaskTemplate, student: Student) -> date | None:
    """Собрать срок из месяца и дня шаблона относительно года выпуска.

    Учебный год: сентябрь–декабрь относятся к году перед выпуском,
    январь–август — к году выпуска.
    """
    if not template.due_month or not template.due_day:
        return None
    year = student.graduation_year - 1 if template.due_month >= 9 else student.graduation_year
    try:
        return date(year, template.due_month, template.due_day)
    except ValueError:
        return None


@transaction.atomic
def generate_from_templates(students, *, author=None) -> GenerationResult:
    """Создать задачи по активным шаблонам. Повторный запуск не плодит копий."""
    result = GenerationResult()
    templates = list(TaskTemplate.objects.filter(is_active=True))

    for student in students:
        existing = set(student.tasks.filter(template__isnull=False).values_list("template_id", flat=True))
        for template in templates:
            if template.graduation_year and template.graduation_year != student.graduation_year:
                continue
            if template.grade and template.grade != student.grade:
                continue
            if template.pk in existing:
                result.skipped += 1
                continue
            Task.objects.create(
                student=student,
                template=template,
                title=template.title,
                category=template.category,
                priority=template.priority,
                description=template.description,
                due_date=_due_from_template(template, student),
                author=author,
            )
            result.created += 1
    return result


@transaction.atomic
def generate_from_deadlines(students, *, author=None) -> GenerationResult:
    """Создать задачи из дедлайнов вузов, куда ученик подаётся.

    Срок не копируется — задача ссылается на раунд, и её `effective_due_date`
    всегда равен текущему дедлайну справочника.
    """
    result = GenerationResult()

    for student in students:
        rows = student.universities.select_related(
            "admission_round__program__university", "program__university"
        ).filter(admission_round__isnull=False)
        existing = set(student.tasks.filter(admission_round__isnull=False).values_list("admission_round_id", flat=True))

        for row in rows:
            admission_round = row.admission_round
            if admission_round.pk in existing:
                result.skipped += 1
                continue
            university = admission_round.program.university.name
            Task.objects.create(
                student=student,
                admission_round=admission_round,
                title=f"Подать заявку: {university} ({admission_round.round_type})",
                category=TaskCategory.UNIVERSITY,
                priority=TaskPriority.HIGH,
                description=f"Программа: {admission_round.program.name}",
                author=author,
            )
            result.created += 1
    return result


def generate_all(students, *, author=None) -> dict:
    """Полная генерация роадмапа: шаблоны плюс дедлайны."""
    students = list(students)
    templates = generate_from_templates(students, author=author)
    deadlines = generate_from_deadlines(students, author=author)
    return {"templates": templates.as_dict(), "deadlines": deadlines.as_dict()}


def tasks_for_round(admission_round: AdmissionRound):
    """Все задачи, привязанные к раунду — их сроки двигаются вместе с ним."""
    return admission_round.tasks.select_related("student")


def complete(task: Task, *, status: str) -> Task:
    """Сменить статус задачи, отметив время завершения.

    Выполненная задача — действие, за которое начисляется XP (инвариант №12).
    Повторное закрытие той же задачи второго начисления не даёт: за это
    отвечает уникальность события по объекту.
    """
    from django.utils import timezone

    task.status = status
    task.completed_at = timezone.now() if status == TaskStatus.DONE else None
    task.save(update_fields=["status", "completed_at", "updated_at"])

    if status == TaskStatus.DONE:
        from engagement.models import XPKind
        from engagement.scoring import award

        award(
            task.student,
            kind=XPKind.TASK_DONE,
            object_label="roadmap.Task",
            object_id=str(task.pk),
            note=task.title[:250],
        )
    return task
