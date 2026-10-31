"""Фикстуры кружков: люди и ученики — те же, что у секций; два кружка — из миграции.

Тест с настоящими транзакциями очищает таблицы, а при `--reuse-db` очищенное
так и остаётся — поэтому кружки сеются перед тестом той же функцией, что
в миграции, если их нет.
"""

from __future__ import annotations

import pytest

from clubs.models import Club
from sport.tests.conftest import groups, login, people, pupils, schedule  # фикстуры секций


@pytest.fixture(autouse=True)
def starting_clubs(db):
    from importlib import import_module

    from django.apps import apps

    if not Club.all_objects.exists():
        import_module("clubs.migrations.0001_clubs_and_starting_two").seed(apps, None)


@pytest.fixture
def lab():
    """AI Startup Lab: понедельник и четверг 15:00–18:00, ментор Нурбек."""
    return Club.objects.get(title="AI Startup Lab")


@pytest.fixture
def robots():
    """Робототехника: вторник и пятница 15:00–18:00, ментор Ерзат."""
    return Club.objects.get(title="Робототехника")


@pytest.fixture
def mentor(make_user, lab):
    """Учётка ментора, привязанная к AI Startup Lab."""
    user = make_user("mentor", "mentor@club.kz", full_name="Нурбек Ментор")
    lab.mentor = user
    lab.save(update_fields=["mentor"])
    return user


@pytest.fixture
def other_mentor(make_user, robots):
    user = make_user("mentor", "mentor2@club.kz", full_name="Ерзат Ментор")
    robots.mentor = user
    robots.save(update_fields=["mentor"])
    return user


__all__ = ["groups", "login", "people", "pupils", "schedule"]
