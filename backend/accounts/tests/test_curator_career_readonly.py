"""Профтест у куратора — только чтение своих групп (решение владельца, 19.10.2026)."""

from __future__ import annotations

import datetime as dt

import pytest
from rest_framework.test import APIClient

from accounts.curators import assign
from accounts.models import Role
from students.models import Student, StudyGroup

pytestmark = pytest.mark.django_db


@pytest.fixture
def groups(db):
    return {
        "boston": StudyGroup.objects.create(code="BOSTON", parallel=10),
        "chicago": StudyGroup.objects.create(code="CHICAGO", parallel=10),
    }


@pytest.fixture
def curator(make_user, groups):
    admin = make_user(Role.ADMIN, email="admin@example.kz")
    user = make_user(Role.CURATOR, email="curator@example.kz", full_name="Нурланова Асель")
    assign(group=groups["boston"], curator=user, since=dt.date.today() - dt.timedelta(days=10), actor=admin)
    Student.objects.create(last_name="Абаева", first_name="Айгерим", group=groups["boston"], graduation_year=2028)
    return user


def client_of(user) -> APIClient:
    api = APIClient()
    api.force_login(user)
    return api


def test_curator_reads_own_groups_and_results(curator, groups):
    api = client_of(curator)
    listed = api.get("/api/career/groups/").json()
    assert listed["manage"] is False and [g["code"] for g in listed["groups"]] == ["BOSTON"]
    assert api.get(f"/api/career/results/?group={groups['boston'].pk}").status_code == 200
    assert api.get(f"/api/career/results/?group={groups['chicago'].pk}").json()["group"] is None
    assert api.get("/api/career/tests/").status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/career/tests/"),
        ("post", "/api/career/tests/preview/"),
        ("patch", "/api/career/tests/1/"),
        ("delete", "/api/career/tests/1/"),
        ("post", "/api/career/tests/1/assignments/"),
        ("post", "/api/career/attempts/1/retake/"),
        ("post", "/api/career/analyses/"),
        ("patch", "/api/career/analyses/1/"),
    ],
)
def test_curator_cannot_write_the_career_section(method, path, curator):
    response = getattr(client_of(curator), method)(path, {}, format="json")
    assert response.status_code == 403, (path, response.status_code)
    assert "куратору не открыт" in response.content.decode()
