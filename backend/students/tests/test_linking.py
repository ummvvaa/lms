"""Фаза 16: карточка ученика и учётная запись связываются по почте.

Отдельного поля «привязать аккаунт» в интерфейсе нет и быть не должно:
почта в карточке и почта, которой человек входит, — одно и то же.
Без этой связи ученик входит в пустой кабинет и не понимает, почему.
"""

from __future__ import annotations

import pytest

from accounts.models import Role, User
from accounts.services import create_user
from students.linking import link_student, link_user
from students.models import Student


def make_student(email: str) -> Student:
    return Student.objects.create(last_name="Ахметова", first_name="Алия", email=email, grade=11, graduation_year=2027)


@pytest.mark.django_db
def test_student_created_after_the_account_gets_linked():
    user = create_user(email="link.one@school.kz", role=Role.STUDENT)
    student = make_student("link.one@school.kz")

    assert link_student(student) == user
    student.refresh_from_db()
    assert student.user == user


@pytest.mark.django_db
def test_account_created_after_the_card_gets_linked():
    student = make_student("link.two@school.kz")

    user = create_user(email="link.two@school.kz", role=Role.STUDENT)

    student.refresh_from_db()
    assert student.user == user


@pytest.mark.django_db
def test_directors_account_is_not_linked_to_a_card():
    student = make_student("link.three@school.kz")
    director = create_user(email="link.three@school.kz", role=Role.DIRECTOR_EXAM)

    assert link_user(director) is None
    student.refresh_from_db()
    assert student.user is None


@pytest.mark.django_db
def test_one_account_does_not_get_two_cards():
    create_user(email="link.four@school.kz", role=Role.STUDENT)
    first = make_student("link.four@school.kz")
    link_student(first)

    second = Student.objects.create(
        last_name="Однофамилец", first_name="Тест", email="other.four@school.kz", grade=11, graduation_year=2027
    )
    second.email = "link.four@school.kz"  # почту так не меняют, но проверим защиту
    assert link_student(second) is None


@pytest.mark.django_db
def test_admin_creating_a_student_links_the_account(client):
    from accounts.passwords import set_password

    admin = User.objects.create_user(email="link.admin@school.kz", password=None, role=Role.ADMIN)
    set_password(admin, "Связка!Проверка2026")
    learner = create_user(email="link.five@school.kz", role=Role.STUDENT)

    client.post(
        "/api/auth/login/",
        data={"email": admin.email, "password": "Связка!Проверка2026"},
        content_type="application/json",
    )
    response = client.post(
        "/api/students/",
        data={
            "last_name": "Ахметова",
            "first_name": "Алия",
            "email": "link.five@school.kz",
            "grade": 11,
            "graduation_year": 2027,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    student = Student.objects.get(pk=response.json()["id"])
    assert student.user == learner
    # пять профилей создаются сразу, иначе кабинет открывается наполовину
    assert all(getattr(student, name, None) for name in ("behavior", "admission", "exam", "talent", "sport"))
