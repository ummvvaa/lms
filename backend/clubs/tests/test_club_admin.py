"""Раздел «Кружки» у администратора: два кружка на старте, правка с журналом, архив, записанные."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from clubs import services
from clubs.models import Club, ClubEnrollment
from clubs.tests.conftest import login
from core.models import AuditLog

pytestmark = pytest.mark.django_db


def test_two_clubs_start_open_to_every_parallel(lab, robots):
    assert services.schedule_words(lab.meetings.all()) == "Пн, Чт 15:00–18:00"
    assert services.schedule_words(robots.meetings.all()) == "Вт, Пт 15:00–18:00"
    assert lab.mentor_name == "Нурбек" and robots.mentor_name == "Ерзат"
    for club in (lab, robots):
        assert services.parallels_of(club) == [8, 9, 10, 11]
        assert club.enroll_until is None and services.is_open(club), "запись открыта всегда"
        assert club.marks_enabled is False, "отметка на старте выключена"


def test_only_the_admin_keeps_clubs(people):
    for role, user in people.items():
        code = login(user).get("/api/clubs/").status_code
        if role == "admin":
            assert code == 200
        else:
            assert code in (403, 404), role


def test_admin_creates_edits_and_journals(people):
    api = login(people["admin"])
    body = {
        "title": "Шахматы",
        "description": "Партии и разборы",
        "mentor_name": "Данияр",
        "meetings": [{"weekday": 2, "starts": "15:00", "ends": "16:30"}],
        "parallels": [8, 9],
    }
    made = api.post("/api/clubs/", body, format="json")
    assert made.status_code == 201, made.content
    pk = made.json()["id"]
    assert made.json()["schedule"] == "Ср 15:00–16:30" and made.json()["parallels"] == [8, 9]
    assert AuditLog.objects.filter(model_label="clubs.Club", object_id=str(pk), field_name="created").exists()

    edited = api.patch(f"/api/clubs/{pk}/", {"parallels": [8, 9, 10], "marks_enabled": True}, format="json")
    assert edited.status_code == 200 and edited.json()["parallels"] == [8, 9, 10]
    changed = set(
        AuditLog.objects.filter(model_label="clubs.Club", object_id=str(pk)).values_list("field_name", flat=True)
    )
    assert {"created", "parallels", "marks_enabled"} <= changed
    log = AuditLog.objects.get(model_label="clubs.Club", object_id=str(pk), field_name="parallels")
    assert (log.old_value, log.new_value) == ("8, 9", "8, 9, 10")


@pytest.mark.parametrize(
    "broken",
    [
        {"title": ""},
        {"mentor_name": ""},
        {"meetings": []},
        {"meetings": [{"weekday": 0, "starts": "18:00", "ends": "15:00"}]},
        {
            "meetings": [
                {"weekday": 0, "starts": "15:00", "ends": "16:00"},
                {"weekday": 0, "starts": "17:00", "ends": "18:00"},
            ]
        },
        {"parallels": []},
        {"parallels": [7]},
    ],
)
def test_form_refuses_broken_fields(people, lab, broken):
    api = login(people["admin"])
    assert api.patch(f"/api/clubs/{lab.pk}/", broken, format="json").status_code == 400


def test_window_until_date_closes_enrollment(people, lab):
    api = login(people["admin"])
    past = (timezone.now() - dt.timedelta(days=1)).isoformat()
    assert api.patch(f"/api/clubs/{lab.pk}/", {"enroll_until": past}, format="json").json()["open"] is False
    assert api.patch(f"/api/clubs/{lab.pk}/", {"enroll_until": None}, format="json").json()["open"] is True


def test_mentor_link_takes_only_mentor_accounts(people, lab, make_user):
    api = login(people["admin"])
    assert api.patch(f"/api/clubs/{lab.pk}/", {"mentor": people["curator"].pk}, format="json").status_code == 400
    mentor = make_user("mentor", "m@club.kz", full_name="Нурбек")
    assert api.get("/api/clubs/mentors/").json()["rows"] == [{"id": mentor.pk, "title": "Нурбек"}]
    assert api.patch(f"/api/clubs/{lab.pk}/", {"mentor": mentor.pk}, format="json").json()["mentor"] == mentor.pk


def test_archive_is_soft_and_returns(people, lab, pupils):
    senior, _junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    api = login(people["admin"])
    assert api.delete(f"/api/clubs/{lab.pk}/").status_code == 204
    assert not Club.objects.filter(pk=lab.pk).exists() and Club.all_objects.filter(pk=lab.pk).exists()
    assert ClubEnrollment.objects.filter(club=lab).count() == 1, "записи не удаляются"
    titles = [row["title"] for row in api.get("/api/clubs/").json()["rows"]]
    assert "AI Startup Lab" not in titles
    archived = api.get("/api/clubs/?archived=1").json()["rows"]
    assert [row["title"] for row in archived] == ["AI Startup Lab"]
    assert api.patch(f"/api/clubs/{lab.pk}/", {"archived": False}, format="json").json()["archived"] is False
    assert Club.objects.filter(pk=lab.pk).exists()


def test_members_list_filters_by_group_and_exports(people, lab, pupils):
    senior, junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    services.enroll(student=junior, club=lab, actor=None)
    services.leave(student=junior, club=lab, actor=None)
    api = login(people["admin"])
    body = api.get(f"/api/clubs/{lab.pk}/members/").json()
    assert [(r["student"]["id"], r["left"]) for r in body["rows"]] == [(senior.pk, False), (junior.pk, True)]
    assert body["active"] == 1 and {g["code"] for g in body["groups"]} == {"TOKYO", "PARIS"}
    only = api.get(f"/api/clubs/{lab.pk}/members/?group={senior.group_id}").json()["rows"]
    assert [r["student"]["id"] for r in only] == [senior.pk]
    sheet = api.get(f"/api/clubs/{lab.pk}/members/export/")
    assert sheet.status_code == 200 and "spreadsheet" in sheet["Content-Type"]
