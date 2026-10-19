"""Куратор с группами только 8–10 — без того, что есть только у 11 (решение владельца, 19.10.2026).

Документы, задачи плана, очередь экзаменов, цели и официальные баллы, вузы,
эссе, готовность и каталог у него не существуют: 404 по адресу, ничего
в ответах главной и учеников, нет кнопки «Ближайшие дедлайны». Смешанный
куратор видит это только по группам 11. Пробники остаются у всех.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIClient

from accounts.curators import assign, leads_admission
from accounts.models import Role
from accounts.permissions import CURATOR_READ_ROUTES, CURATOR_WRITE_ROUTES, curator_admission_routes
from core.parallels import MOCK_ROUTES, admission_routes
from students.enrollment import _make_profiles
from students.models import Student, StudyGroup
from suggestions import assistant

pytestmark = pytest.mark.django_db


@pytest.fixture
def groups(db):
    return {
        "lisbon": StudyGroup.objects.create(code="LISBON", parallel=9),
        "porto": StudyGroup.objects.create(code="PORTO", parallel=10),
        "madrid": StudyGroup.objects.create(code="MADRID", parallel=9),
        "chicago": StudyGroup.objects.create(code="CHICAGO", parallel=11),
    }


@pytest.fixture
def pupils(groups):
    rows = {
        "nine": Student.objects.create(
            last_name="Девятова", first_name="Алия", group=groups["lisbon"], graduation_year=2029
        ),
        "ten": Student.objects.create(
            last_name="Десятов", first_name="Ерлан", group=groups["porto"], graduation_year=2028
        ),
        "madrid": Student.objects.create(
            last_name="Мадридова", first_name="Сауле", group=groups["madrid"], graduation_year=2029
        ),
        "eleven": Student.objects.create(
            last_name="Выпускникова",
            first_name="Дана",
            email="eleven@example.kz",
            group=groups["chicago"],
            graduation_year=2027,
        ),
    }
    for student in rows.values():
        _make_profiles(student)
    return rows


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, email="admin@example.kz")


@pytest.fixture
def junior_curator(make_user, groups, admin):
    user = make_user(Role.CURATOR, email="junior.curator@example.kz", full_name="Куратор Младших")
    for code in ("lisbon", "porto"):
        assign(group=groups[code], curator=user, since=dt.date.today() - dt.timedelta(days=10), actor=admin)
    return user


@pytest.fixture
def mixed_curator(make_user, groups, admin):
    user = make_user(Role.CURATOR, email="mixed.curator@example.kz", full_name="Куратор Смешанный")
    for code in ("madrid", "chicago"):
        assign(group=groups[code], curator=user, since=dt.date.today() - dt.timedelta(days=10), actor=admin)
    return user


def client_of(user) -> APIClient:
    api = APIClient()
    api.force_login(user)
    return api


def url_of(name: str, pk: int) -> str:
    for kwargs in ({}, {"pk": pk}, {"student_id": pk}):
        try:
            return reverse(name, kwargs=kwargs)
        except NoReverseMatch:
            continue
    raise NoReverseMatch(name)


#: что проверяется адресом: экраны кабинета и несколько разделов 11 из реестра
CLOSED = (
    "curator-documents",
    "curator-documents-export",
    "curator-tasks",
    "suggestion-students-queue",
    "exam-goal-list",
    "student-university-list",
    "essay-list",
    "student-readiness",
    "university-list",
    "program-list",
    "profile-admission-detail",
    "profile-exam-detail",
)


def test_me_says_whether_the_curator_leads_admission(junior_curator, mixed_curator, admin, pupils):
    assert client_of(junior_curator).get("/api/auth/me/").json()["has_admission"] is False
    assert client_of(mixed_curator).get("/api/auth/me/").json()["has_admission"] is True
    assert client_of(admin).get("/api/auth/me/").json()["has_admission"] is None
    assert leads_admission(mixed_curator, []) is False
    assert not leads_admission(admin)


def test_the_closed_list_comes_from_the_parallels_registry():
    """Маршруты разделов 11 — из реестра, пробники остаются; всё закрытое знакомо шлюзу."""
    closed = curator_admission_routes()
    assert {"exam-goal-list", "task-list", "student-readiness", "essay-list", "catalog"} <= admission_routes()
    assert not MOCK_ROUTES & closed
    assert set(CLOSED) <= closed
    from accounts.permissions import CURATOR_ADMISSION_ONLY_ROUTES

    assert CURATOR_ADMISSION_ONLY_ROUTES <= CURATOR_READ_ROUTES | CURATOR_WRITE_ROUTES


@pytest.mark.parametrize("name", CLOSED)
def test_junior_only_curator_gets_404_and_mixed_curator_does_not(name, junior_curator, mixed_curator, pupils):
    assert client_of(junior_curator).get(url_of(name, pupils["nine"].pk)).status_code == 404, name
    assert client_of(mixed_curator).get(url_of(name, pupils["eleven"].pk)).status_code != 404, name


def test_junior_only_curator_cannot_assign_or_move_a_task(junior_curator, pupils):
    api = client_of(junior_curator)
    made = api.post("/api/curator/tasks/", {"title": "Принести справку", "group": "LISBON"}, format="json")
    assert made.status_code == 404
    assert api.post("/api/curator/tasks/1/status/", {"status": "done"}, format="json").status_code == 404
    assert api.post("/api/curator/documents/remind/", {"group": "LISBON"}, format="json").status_code == 404


def test_mocks_stay_open_to_the_junior_only_curator(junior_curator, pupils):
    api = client_of(junior_curator)
    assert api.get(reverse("attempt-list")).status_code == 200
    card = api.get(f"/api/curator/students/{pupils['nine'].pk}/").json()
    assert card["has_admission"] is False
    assert "mocks" in card and card["tasks"] == [] and card["admission"] is None


def test_home_and_students_of_the_junior_only_curator_have_no_admission(junior_curator, pupils):
    api = client_of(junior_curator)
    home = api.get("/api/curator/overview/").json()
    assert home["has_admission"] is False
    assert home["numbers"] == [] and home["queue"] == [] and home["tasks"] == []
    assert (home["queue_total"], home["tasks_due"], home["tasks_overdue"]) == (0, 0, 0)
    assert {row["code"] for row in home["buckets"]} == {"rejected"}

    students = api.get("/api/curator/students/").json()
    assert students["has_admission"] is False
    assert {row["code"] for row in students["buckets"]} == {"rejected"}
    assert {row["full_name"] for row in students["results"]} == {"Девятова Алия", "Десятов Ерлан"}

    export = api.get("/api/curator/students/export/")
    assert export.status_code == 200
    from io import BytesIO

    from openpyxl import load_workbook

    header = [cell.value for cell in load_workbook(BytesIO(export.content)).active[1]]
    assert "IELTS" not in header and "SAT" not in header and "Документы" not in header
    assert "Последний Mock Test" in header

    profile = api.get("/api/curator/profile/").json()
    assert profile["has_admission"] is False and profile["confirms"] == []
    assert "Поступление" not in profile["writes"]


def test_mixed_curator_sees_admission_only_through_the_graduating_group(mixed_curator, pupils):
    api = client_of(mixed_curator)
    everything = api.get("/api/curator/overview/").json()
    assert everything["has_admission"] is True and len(everything["numbers"]) == 4
    assert "nogoal" in {row["code"] for row in everything["buckets"]}

    juniors = api.get("/api/curator/overview/?group=MADRID").json()
    assert juniors["has_admission"] is False and juniors["numbers"] == []
    assert api.get("/api/curator/students/?group=MADRID").json()["has_admission"] is False

    matrix = api.get("/api/curator/documents/").json()
    assert [row["full_name"] for row in matrix["results"]] == ["Выпускникова Дана"]

    # задача плана — только 11: девятой группе и девятикласснику некому ставить
    body = {"title": "Собрать документы", "group": "MADRID"}
    assert api.post("/api/curator/tasks/", body, format="json").status_code == 404
    body = {"title": "Собрать документы", "student": pupils["madrid"].pk}
    assert api.post("/api/curator/tasks/", body, format="json").status_code == 404
    made = api.post("/api/curator/tasks/", {"title": "Собрать документы", "group": "CHICAGO"}, format="json")
    assert made.status_code == 201 and made.json()["students"] == [pupils["eleven"].pk]
    rows = api.get("/api/curator/tasks/").json()["results"]
    assert {row["student"] for row in rows} == {pupils["eleven"].pk}


def test_deadlines_button_is_gone_and_refused_for_the_junior_only_curator(junior_curator, mixed_curator, pupils):
    codes = {q.code for q in assistant.quick_for(Role.CURATOR, junior_curator)}
    assert "deadlines_soon" not in codes and "focus_today" in codes
    assert "deadlines_soon" in {q.code for q in assistant.quick_for(Role.CURATOR, mixed_curator)}
    reply = assistant.run_quick("deadlines_soon", actor=junior_curator, role=Role.CURATOR)
    assert "Такой кнопки" in reply["text"]
    api = client_of(junior_curator)
    quick = api.get("/api/assistant/quick/")
    assert quick.status_code == 200
    assert "deadlines_soon" not in str(quick.content)
