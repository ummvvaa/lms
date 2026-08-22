"""Фаза 8, дефект B4: «Проверить баланс списка» — настоящее действие, а не карточка."""

from __future__ import annotations

import pytest

from accounts.models import Role, User
from students.models import Student
from universities.matching import list_balance
from universities.models import Program, StudentUniversity, University


@pytest.fixture
def student(db):
    return Student.objects.create(
        last_name="Ким", first_name="Дана", email="balance@example.kz", grade=11, graduation_year=2027
    )


@pytest.fixture
def programs(db):
    university = University.objects.create(name="Тестовый вуз", country="Канада")
    return [Program.objects.create(university=university, name=f"Программа {i}") for i in range(3)]


@pytest.mark.django_db
def test_empty_list_says_so_plainly(student):
    balance = list_balance(student)

    assert balance["total"] == 0
    assert "пуст" in balance["advice"]


@pytest.mark.django_db
def test_balance_counts_tiers_and_names_the_gap(student, programs):
    StudentUniversity.objects.create(student=student, program=programs[0], tier="reach")
    StudentUniversity.objects.create(student=student, program=programs[1], tier="safety")

    balance = list_balance(student)

    assert balance["counts"] == {"reach": 1, "target": 0, "safety": 1}
    assert balance["gaps"]["target"] == 3
    assert balance["gaps"]["safety"] == 0
    assert "target" in balance["advice"]


@pytest.mark.django_db
def test_endpoint_answers_for_named_student(client, student, programs):
    director = User.objects.create_user(
        email="asem@example.kz",
        password="Пароль!2026x",
        role=Role.DIRECTOR_ADMISSION,
        must_change_password=False,
    )
    client.force_login(director)
    StudentUniversity.objects.create(student=student, program=programs[0], tier="target")

    response = client.get(f"/api/match/list-balance/?student={student.pk}")

    assert response.status_code == 200
    assert response.json()["student_name"] == student.full_name
