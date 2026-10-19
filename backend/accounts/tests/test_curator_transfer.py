"""Перевод ученика куратором в другую группу той же параллели (решение владельца, 19.10.2026)."""

from __future__ import annotations

import datetime as dt

import pytest
from rest_framework.test import APIClient

from accounts.curators import assign
from accounts.models import Role
from core.labels import field_title
from core.models import AuditLog
from students.enrollment import _make_profiles
from students.models import Student, StudyGroup

pytestmark = pytest.mark.django_db


@pytest.fixture
def groups(db):
    return {
        "boston": StudyGroup.objects.create(code="BOSTON", parallel=10),
        "chicago": StudyGroup.objects.create(code="CHICAGO", parallel=10),
        "seoul": StudyGroup.objects.create(code="SEOUL", parallel=10),
        "tokyo": StudyGroup.objects.create(code="TOKYO", parallel=11),
        "old": StudyGroup.objects.create(code="OLD", parallel=10, archived_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC)),
    }


@pytest.fixture
def pupil(groups):
    student = Student.objects.create(
        last_name="Абаева", first_name="Айгерим", group=groups["boston"], graduation_year=2028
    )
    _make_profiles(student)
    return student


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, email="admin@example.kz")


@pytest.fixture
def curator(make_user, groups, admin):
    user = make_user(Role.CURATOR, email="curator@example.kz", full_name="Нурланова Асель")
    for code in ("boston", "seoul"):
        assign(group=groups[code], curator=user, since=dt.date.today() - dt.timedelta(days=10), actor=admin)
    return user


@pytest.fixture
def receiver(make_user, groups, admin):
    user = make_user(Role.CURATOR, email="receiver@example.kz", full_name="Касенова Айдана")
    assign(group=groups["chicago"], curator=user, since=dt.date.today() - dt.timedelta(days=10), actor=admin)
    return user


def client_of(user) -> APIClient:
    api = APIClient()
    api.force_login(user)
    return api


def test_curator_moves_own_student_within_the_parallel_and_both_journals_see_it(curator, receiver, pupil, groups):
    api = client_of(curator)
    card = api.get(f"/api/curator/students/{pupil.pk}/").json()
    assert [row["code"] for row in card["transfer_targets"]] == ["CHICAGO", "SEOUL"]

    moved = api.post(f"/api/curator/students/{pupil.pk}/transfer/", {"group": "chicago"}, format="json")
    assert moved.status_code == 200, moved.content
    assert moved.json() == {"group": "CHICAGO", "was": "BOSTON", "still_mine": False}
    pupil.refresh_from_db()
    assert pupil.group == groups["chicago"] and pupil.graduation_year == 2028

    rows = list(AuditLog.objects.filter(student_id=pupil.pk).order_by("pk"))
    assert [(row.field_name, row.student_group) for row in rows] == [("group_transfer", "BOSTON"), ("group", "CHICAGO")]
    assert rows[0].new_value == "переведён из BOSTON в CHICAGO" and rows[0].actor == curator
    assert (rows[1].old_value, rows[1].new_value) == (str(groups["boston"].pk), str(groups["chicago"].pk))

    # прежний куратор видит событие в журнале своих групп, нового ученика — нет
    old_journal = api.get("/api/curator/journal/").json()["results"]
    assert any(row["what"] == field_title("students.Student", "group_transfer") for row in old_journal)
    assert api.get(f"/api/curator/students/{pupil.pk}/").status_code == 404
    new_api = client_of(receiver)
    assert new_api.get(f"/api/curator/students/{pupil.pk}/").status_code == 200
    assert any(
        row["group"] == "CHICAGO" and row["what"] for row in new_api.get("/api/curator/journal/").json()["results"]
    )


def test_transfer_to_own_other_group_keeps_the_card(curator, pupil, groups):
    api = client_of(curator)
    moved = api.post(f"/api/curator/students/{pupil.pk}/transfer/", {"group": "SEOUL"}, format="json")
    assert moved.status_code == 200 and moved.json()["still_mine"] is True
    assert api.get(f"/api/curator/students/{pupil.pk}/").json()["group"] == "SEOUL"


def test_transfer_refusals(curator, receiver, admin, pupil, groups):
    api = client_of(curator)
    path = f"/api/curator/students/{pupil.pk}/transfer/"
    assert "той же параллели" in api.post(path, {"group": "TOKYO"}, format="json").json()["detail"]
    assert "уже в этой группе" in api.post(path, {"group": "BOSTON"}, format="json").json()["detail"]
    assert "нет" in api.post(path, {"group": "OLD"}, format="json").json()["detail"]
    assert api.post(path, {"group": "NOPE"}, format="json").status_code == 400
    # чужой ученик для другого куратора не существует; администратору кабинет куратора закрыт
    assert client_of(receiver).post(path, {"group": "CHICAGO"}, format="json").status_code == 404
    assert client_of(admin).post(path, {"group": "CHICAGO"}, format="json").status_code == 403
    pupil.refresh_from_db()
    assert pupil.group == groups["boston"]
    assert not AuditLog.objects.filter(student_id=pupil.pk).exists()
