"""Фаза 11: «задания на сегодня» — три дела по приоритету и близости срока."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from engagement import today
from engagement.models import XPKind
from engagement.scoring import award_size
from roadmap.models import Task, TaskStatus
from students.models import Student


@pytest.fixture
def student(db):
    return Student.objects.create(
        last_name="Ким", first_name="Дана", email="today@school.kz", grade=11, graduation_year=2027
    )


def task(student, title, *, priority="medium", days=None, status=TaskStatus.TODO) -> Task:
    return Task.objects.create(
        student=student,
        title=title,
        category="test",
        priority=priority,
        status=status,
        due_date=timezone.localdate() + timedelta(days=days) if days is not None else None,
    )


@pytest.mark.django_db
def test_three_tasks_at_most(student):
    for i in range(6):
        task(student, f"Задача {i}", days=i)

    assert len(today.for_student(student)) == 3


@pytest.mark.django_db
def test_priority_comes_first_then_the_deadline(student):
    task(student, "Низкий, завтра", priority="low", days=1)
    task(student, "Высокий, через месяц", priority="high", days=30)
    task(student, "Высокий, послезавтра", priority="high", days=2)

    titles = [row["title"] for row in today.for_student(student)]

    assert titles[0] == "Высокий, послезавтра"
    assert titles[1] == "Высокий, через месяц"


@pytest.mark.django_db
def test_done_tasks_do_not_come_back(student):
    task(student, "Уже сделана", days=1, status=TaskStatus.DONE)
    task(student, "Ещё нет", days=2)

    assert [row["title"] for row in today.for_student(student)] == ["Ещё нет"]


@pytest.mark.django_db
def test_every_task_shows_its_xp(student):
    task(student, "С наградой", days=1)

    row = today.for_student(student)[0]

    assert row["xp"] == award_size(XPKind.TASK_DONE)


@pytest.mark.django_db
def test_tasks_without_a_deadline_do_not_crowd_out_urgent_ones(student):
    task(student, "Без срока")
    task(student, "Через три дня", days=3)

    assert today.for_student(student)[0]["title"] == "Через три дня"


@pytest.mark.django_db
def test_empty_roadmap_is_not_an_error(student):
    assert today.for_student(student) == []
