"""Фикстуры секций: люди всех ролей, группы 9 и 10 класса, ученики со своими учётками.

Расписание секций приходит миграцией (пять секций, четырнадцать занятий).
Тест с настоящими транзакциями (гонка за место) очищает таблицы, а при
`--reuse-db` очищенное так и остаётся — поэтому расписание сеется перед
каждым тестом той же функцией, что в миграции, если его нет.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.curators import assign
from sport.models import Section, SectionSlot
from students.models import Student, StudyGroup

DIRECTORS = ("director_behavior", "director_exam", "director_admission", "director_talent", "director_sport")


@pytest.fixture(autouse=True)
def schedule(db):
    from importlib import import_module

    from django.apps import apps

    if not Section.all_objects.exists():
        import_module("sport.migrations.0001_sections_and_tickets").seed(apps, None)


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def people(make_user):
    out = {role: make_user(role, f"{role}@sec.kz", full_name=role) for role in DIRECTORS}
    out["admin"] = make_user("admin", "admin@sec.kz", full_name="Администратор")
    out["teacher"] = make_user("teacher", "teacher@sec.kz", full_name="Учитель")
    out["curator"] = make_user("curator", "curator@sec.kz", full_name="Куратор")
    return out


@pytest.fixture
def groups(people):
    mine = StudyGroup.objects.create(code="TOKYO", parallel=10)
    other = StudyGroup.objects.create(code="PARIS", parallel=9)
    assign(group=mine, curator=people["curator"], since=timezone.localdate() - dt.timedelta(days=30))
    return mine, other


@pytest.fixture
def pupils(groups, make_user):
    """Ученик 10 класса (группа куратора) и ученик 9 класса (чужая группа)."""
    mine, other = groups
    senior = Student.objects.create(
        last_name="Абдрахман",
        first_name="Мирас",
        group=mine,
        graduation_year=2028,
        user=make_user("student", "s@sec.kz"),
    )
    junior = Student.objects.create(
        last_name="Бекова",
        first_name="Жанель",
        group=other,
        graduation_year=2029,
        user=make_user("student", "j@sec.kz"),
    )
    return senior, junior


def slot_of(title: str, weekday: int, hour: int, grade_from: int) -> SectionSlot:
    return SectionSlot.objects.get(
        section__title=title, weekday=weekday, starts=dt.time(hour, 0), grade_from=grade_from
    )


@pytest.fixture
def tennis():
    """Теннис: четверг 17:00 для 8–9 и три субботних часа для 10–11."""
    return Section.objects.get(title="Теннис")


@pytest.fixture
def open_enroll():
    from sport import services

    services.set_enroll_until(timezone.now() + dt.timedelta(days=7), actor=None)
