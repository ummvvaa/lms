"""Фаза 9: исчезнувшая сессия — это 401, а не пятисотка.

Человек вышел во второй вкладке — первая должна спокойно уйти на вход.
"""

from __future__ import annotations

import pytest
from django.contrib.sessions.models import Session

from accounts.models import Role, User
from accounts.passwords import set_password

PASSWORD = "Проверка!Сессии2026"


@pytest.fixture
def user(db):
    person = User.objects.create_user(email="two.tabs@school.kz", password=None, role=Role.DIRECTOR_EXAM)
    set_password(person, PASSWORD)
    return person


@pytest.mark.django_db
def test_deleted_session_answers_401_not_500(client, user):
    client.post("/api/auth/login/", data={"email": user.email, "password": PASSWORD}, content_type="application/json")
    assert client.get("/api/auth/me/").status_code == 200

    # вторая вкладка вышла: строка сессии исчезла из базы
    Session.objects.all().delete()

    response = client.get("/api/auth/me/")

    assert response.status_code in (401, 403)
    assert response.status_code != 500
