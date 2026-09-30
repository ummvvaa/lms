"""Язык интерфейса по умолчанию и уведомление о языке, выбранном школой.

Ученику — язык его группы (kk или ru), сотруднику — русский; дальше человек
меняет язык сам. Существующим ученикам язык группы проставила миграция,
и тем, у кого интерфейс сменился, один раз показывается уведомление.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.services import create_user
from students.enrollment import enroll
from students.models import Student, StudyGroup

migration = importlib.import_module("accounts.migrations.0012_language_of_group_and_notice")


@pytest.fixture
def kk_group(db) -> StudyGroup:
    return StudyGroup.objects.create(code="K01", parallel=10, language="kk")


@pytest.mark.django_db
def test_enrolled_student_gets_the_group_language(kk_group, group):
    result = enroll(
        rows=[
            {"full_name": "Ахметова Алия Ерлановна", "group": "K01"},
            {"full_name": "Иванов Иван Иванович", "group": group.code, "email": "ivanov@example.kz"},
        ],
        send_mail=False,
    )
    by_name = {row["full_name"]: User.objects.get(pk=row["user"]) for row in result["rows"]}
    assert by_name["Ахметова Алия Ерлановна"].language == "kk"
    assert by_name["Иванов Иван Иванович"].language == "ru"
    # новый ученик ничего не «потерял» — уведомлять не о чем
    assert not any(user.language_notice for user in by_name.values())


@pytest.mark.django_db
def test_account_linked_by_email_gets_the_group_language(kk_group):
    Student.objects.create(
        last_name="Серикова", first_name="Дана", email="dana@example.kz", group=kk_group, graduation_year=2027
    )
    user = create_user(email="dana@example.kz", full_name="Серикова Дана", role=Role.STUDENT)
    assert User.objects.get(pk=user.pk).language == "kk"


@pytest.mark.django_db
def test_staff_default_to_russian():
    user = create_user(email="teacher@example.kz", full_name="Сапарова Жанна", role=Role.TEACHER)
    assert user.language == "ru"


@pytest.mark.django_db
def test_linking_keeps_the_language_of_someone_who_already_came_in(kk_group, make_user):
    from django.utils import timezone

    from students.linking import link_user

    user = make_user(Role.STUDENT, email="came@example.kz", language="en", last_login=timezone.now())
    Student.objects.create(
        last_name="Нурова", first_name="Айя", email="came@example.kz", group=kk_group, graduation_year=2027
    )
    link_user(user)
    user.refresh_from_db()
    assert user.language == "en"


@pytest.mark.django_db
def test_migration_sets_group_language_and_notice_only_where_interface_changes(kk_group, group, make_user):
    kk_student = make_user(Role.STUDENT, email="kk@example.kz")
    ru_student = make_user(Role.STUDENT, email="ru@example.kz", language="kk")
    staff = make_user(Role.CURATOR, email="curator@example.kz", language="en")
    Student.objects.create(last_name="А", first_name="Б", group=kk_group, graduation_year=2027, user=kk_student)
    Student.objects.create(last_name="В", first_name="Г", group=group, graduation_year=2026, user=ru_student)

    migration.adopt_group_language(apps, None)

    kk_student.refresh_from_db()
    ru_student.refresh_from_db()
    staff.refresh_from_db()
    assert (kk_student.language, kk_student.language_notice) == ("kk", True)
    # у русской группы интерфейс и был русским — уведомлять не о чем
    assert (ru_student.language, ru_student.language_notice) == ("ru", False)
    assert (staff.language, staff.language_notice) == ("en", False)


@pytest.mark.django_db
def test_notice_is_closed_by_button_or_by_changing_language(make_user):
    api = APIClient()
    user = make_user(Role.STUDENT, email="notice@example.kz", language="kk", language_notice=True)
    api.force_login(user)
    assert api.get("/api/auth/me/").json()["language_notice"] is True

    # включить уведомление запросом нельзя — только закрыть
    assert api.patch("/api/auth/me/preferences/", {"language_notice": True}, format="json").status_code == 400
    closed = api.patch("/api/auth/me/preferences/", {"language_notice": False}, format="json").json()
    assert closed["language_notice"] is False and closed["language"] == "kk"

    User.objects.filter(pk=user.pk).update(language_notice=True)
    switched = api.patch("/api/auth/me/preferences/", {"language": "ru"}, format="json").json()
    assert switched["language"] == "ru" and switched["language_notice"] is False
