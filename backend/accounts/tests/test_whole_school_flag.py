"""Флаг «видит всю школу» вместо второй роли `admin` у Салтанат."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.passwords import set_password

PASSWORD = "Салтанат!Школа2026"


def make(email: str, role: str, *, whole_school: bool = False) -> User:
    user = User.objects.create_user(email=email, password=None, role=role, sees_whole_school=whole_school)
    set_password(user, PASSWORD)
    return user


def login(user: User) -> APIClient:
    api = APIClient()
    api.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    return api


@pytest.mark.django_db
def test_flag_opens_the_whole_school_view():
    saltanat = make("saltanat@school.kz", Role.DIRECTOR_BEHAVIOR, whole_school=True)

    api = login(saltanat)

    assert api.get("/api/auth/me/").data["can_see_whole_school"] is True
    assert api.get("/api/dashboards/overview/").status_code == 200


@pytest.mark.django_db
def test_director_without_flag_does_not_see_it():
    kymbat = make("kymbat@school.kz", Role.DIRECTOR_EXAM)

    api = login(kymbat)

    assert api.get("/api/auth/me/").data["can_see_whole_school"] is False
    assert api.get("/api/dashboards/overview/").status_code == 403


@pytest.mark.django_db
def test_flag_gives_reading_only_not_writing(student):
    """Читает всё, пишет только свой домен — вторая роль ей не нужна."""
    saltanat = make("saltanat@school.kz", Role.DIRECTOR_BEHAVIOR, whole_school=True)
    api = login(saltanat)

    # свой домен — можно
    own = api.post(
        "/api/batch/save/",
        {
            "changes": [
                {"student": student.pk, "model": "students.BehaviorProfile", "field": "remarks_count", "value": 2}
            ]
        },
        format="json",
    )
    assert own.data["applied"] == 1

    # чужой — нельзя, флаг тут ничего не меняет
    foreign = api.post(
        "/api/batch/save/",
        {
            "changes": [
                {"student": student.pk, "model": "students.ExamProfile", "field": "ielts_current", "value": "7.0"}
            ]
        },
        format="json",
    )
    assert foreign.data["applied"] == 0
    assert foreign.data["rejected"][0]["reason"] == "«Текущий балл IELTS» ведёт другой директор"

    assert api.patch(f"/api/profiles/exam/{student.pk}/", {"ielts_current": "8.0"}, format="json").status_code == 403


@pytest.mark.django_db
def test_admin_role_stays_technical(student):
    """`admin` управляет людьми и справочниками, но не доменными полями."""
    admin = make("admin@school.kz", Role.ADMIN)
    api = login(admin)

    assert api.get("/api/users/").status_code == 200
    assert api.get("/api/dashboards/overview/").status_code == 200

    response = api.post(
        "/api/batch/save/",
        {
            "changes": [
                {"student": student.pk, "model": "students.BehaviorProfile", "field": "remarks_count", "value": 5}
            ]
        },
        format="json",
    )
    assert response.data["applied"] == 0
