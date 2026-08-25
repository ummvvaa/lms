"""Фаза 8, дефект B2: список не должен молча обрезаться на 50 записях."""

from __future__ import annotations

import pytest

from accounts.models import Role, User
from students.models import Student


@pytest.fixture
def many_students(db):
    Student.objects.bulk_create(
        Student(
            last_name=f"Ученик{i:03d}",
            first_name="Тест",
            email=f"page{i:03d}@example.kz",
            grade=11,
            graduation_year=2027,
        )
        for i in range(60)
    )


@pytest.fixture
def director(db):
    return User.objects.create_user(
        email="p@example.kz", password="Пароль!2026x", role=Role.DIRECTOR_EXAM, must_change_password=False
    )


@pytest.mark.django_db
def test_page_size_is_honoured(client, many_students, director):
    """Раньше `page_size` игнорировался и таблица видела только первые 50."""
    client.force_login(director)

    payload = client.get("/api/students/?page_size=500").json()

    assert payload["count"] == 60
    assert len(payload["results"]) == 60


@pytest.mark.django_db
def test_page_size_is_capped(client, many_students, director):
    """Потолок нужен, чтобы одним запросом нельзя было вытащить всю базу."""
    client.force_login(director)

    payload = client.get("/api/students/?page_size=100000").json()

    assert len(payload["results"]) <= 500
