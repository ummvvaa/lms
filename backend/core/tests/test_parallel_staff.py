"""Сотрудники и параллели: каждый видит и считает только тех, кого ведёт.

Асем ведёт поступление — у неё 8–10 нет нигде: ни в таблице, ни в карточке
(404), ни в числах «из N». Кымбат ведёт экзамены только у 11, а учёбу у
всех: таблица экзаменов — без 8–10, карточка ученика 8–10 открывается,
но без поступления и экзаменов. Салтанат видит всех и фильтрует по
параллели. Куратору в карточке 8–10 не приходят блоки поступления.
"""

from __future__ import annotations

import datetime as dt

import pytest
from rest_framework.test import APIClient

from accounts.models import CuratorAssignment, Role
from students.enrollment import _make_profiles
from students.models import Student, StudyGroup


@pytest.fixture
def school(db):
    """Одна выпускная группа и одна девятая — по ученику в каждой."""
    eleven_group = StudyGroup.objects.create(code="CHICAGO", parallel=11)
    nine_group = StudyGroup.objects.create(code="LISBON", parallel=9)
    eleven = Student.objects.create(
        last_name="Выпускникова", first_name="Алия", email="eleven@example.kz", group=eleven_group, graduation_year=2027
    )
    nine = Student.objects.create(last_name="Девятиклассов", first_name="Ерлан", group=nine_group, graduation_year=2029)
    for student in (eleven, nine):
        _make_profiles(student)
    return {"eleven": eleven, "nine": nine}


def client_of(user) -> APIClient:
    api = APIClient()
    api.force_login(user)
    return api


def names(response) -> list[str]:
    body = response.json()
    rows = body["results"] if isinstance(body, dict) else body
    return sorted(row["full_name"] for row in rows)


def test_asem_does_not_see_juniors_anywhere(school, make_user):
    asem = client_of(make_user(Role.DIRECTOR_ADMISSION, "asem.parallel@example.kz"))

    assert names(asem.get("/api/students/")) == ["Выпускникова Алия"]
    assert names(asem.get("/api/students/", {"parallel": 9})) == []
    assert asem.get(f"/api/students/{school['nine'].pk}/").status_code == 404
    assert asem.get(f"/api/students/{school['eleven'].pk}/").status_code == 200

    cabinet = asem.get("/api/cabinet/").json()
    no_universities = next(stat for stat in cabinet["stats"] if stat["code"] == "no_universities")
    assert no_universities["value"] == 1
    assert no_universities["note"] == "из 1"

    dashboard = asem.get("/api/dashboards/admission/").json()
    assert dashboard["total"] == 1


def test_kymbat_exams_only_for_graduates_but_opens_the_junior_card(school, make_user):
    kymbat = client_of(make_user(Role.DIRECTOR_EXAM, "kymbat.parallel@example.kz"))

    assert names(kymbat.get("/api/students/")) == ["Выпускникова Алия"]
    card = kymbat.get(f"/api/students/{school['nine'].pk}/")
    assert card.status_code == 200
    body = card.json()
    assert "exam" not in body and "admission" not in body and body["readiness"] is None
    assert kymbat.get(f"/api/students/{school['nine'].pk}/readiness/").status_code == 404

    attention = kymbat.get("/api/exam-goals/attention/").json()
    assert [row["name"] for row in attention["no_goals"]] == ["Выпускникова Алия"]


def test_saltanat_sees_everyone_and_filters_by_parallel(school, make_user):
    saltanat = client_of(make_user(Role.DIRECTOR_BEHAVIOR, "saltanat.parallel@example.kz"))

    assert names(saltanat.get("/api/students/")) == ["Выпускникова Алия", "Девятиклассов Ерлан"]
    assert names(saltanat.get("/api/students/", {"parallel": 9})) == ["Девятиклассов Ерлан"]
    assert names(saltanat.get("/api/students/", {"parallel": 11})) == ["Выпускникова Алия"]
    meta = {d["code"]: d["parallels"] for d in saltanat.get("/api/meta/domains/").json()["domains"]}
    assert meta["behavior"] == [8, 9, 10, 11]
    assert meta["admission"] == meta["exam"] == meta["documents"] == [11]


def test_curator_card_of_a_junior_has_no_admission(school, make_user):
    curator = make_user(Role.CURATOR, "curator.parallel@example.kz")
    for student in school.values():
        CuratorAssignment.objects.create(curator=curator, group=student.group, since=dt.date(2026, 9, 1))
    api = client_of(curator)

    card = api.get(f"/api/curator/students/{school['nine'].pk}/").json()
    assert card["has_admission"] is False
    assert card["admission"] is None
    assert card["universities"] == [] and card["mocks"] == []
    assert not {"nogoal", "nomock", "far", "docs"} & {bucket["code"] for bucket in card["buckets"]}

    graduate = api.get(f"/api/curator/students/{school['eleven'].pk}/").json()
    assert graduate["has_admission"] is True
    assert "nogoal" in {bucket["code"] for bucket in graduate["buckets"]}

    matrix = api.get("/api/curator/documents/").json()
    assert [row["full_name"] for row in matrix["results"]] == ["Выпускникова Алия"]


def test_admin_sees_everyone_with_the_parallel_filter(school, make_user):
    admin = make_user(Role.ADMIN, "admin.parallel@example.kz")
    school["eleven"].user = make_user(Role.STUDENT, "eleven@example.kz")
    school["eleven"].save(update_fields=["user"])
    api = client_of(admin)
    users = api.get("/api/users/", {"parallel": 11}).json()["results"]
    assert [row["email"] for row in users] == ["eleven@example.kz"]
    groups = api.get("/api/groups/", {"parallel": 9}).json()["results"]
    assert [row["code"] for row in groups] == ["LISBON"]
