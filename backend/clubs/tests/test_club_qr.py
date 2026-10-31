"""Отметка по QR на встрече кружка: пока отметка выключена, её нет нигде; включена — как у секций.

Время замораживается на понедельник 02.11.2026, 15:10 по Алматы — идёт AI Startup Lab.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from clubs import services
from clubs.models import ClubMark
from clubs.tests.conftest import login
from sport import services as sport
from sport.models import MarkMethod
from sport.tests.conftest import slot_of

pytestmark = pytest.mark.django_db

MONDAY = dt.date(2026, 11, 2)


@pytest.fixture
def at(monkeypatch):
    def move(hour: int, minute: int = 0, day: dt.date = MONDAY):
        moment = timezone.make_aware(dt.datetime.combine(day, dt.time(hour, minute)))
        monkeypatch.setattr(services, "local_now", lambda: timezone.localtime(moment))
        monkeypatch.setattr(sport, "local_now", lambda: timezone.localtime(moment))
        monkeypatch.setattr(sport, "seconds_now", lambda: moment.timestamp())
        return moment

    return move


@pytest.fixture
def member(pupils, lab):
    senior, _junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    return senior


def _enable(lab):
    lab.marks_enabled = True
    lab.save(update_fields=["marks_enabled"])


def test_marks_off_means_no_marking_anywhere(mentor, member, lab, at):
    at(15, 10)
    api = login(mentor)
    assert api.get(f"/api/clubs/{lab.pk}/session/").status_code == 404
    assert api.get(f"/api/clubs/{lab.pk}/session/token/").status_code == 404
    assert api.post(f"/api/clubs/{lab.pk}/session/marks/", {"student": member.pk}).status_code == 404
    # даже настоящий свежий код не отмечает, пока отметка выключена
    token = services.make_token(lab, MONDAY)[0]
    assert login(member.user).post("/api/clubs/scan/", {"token": token}).json()["state"] == "stale"
    assert not ClubMark.objects.exists()


def test_fresh_code_marks_once_when_enabled(mentor, member, lab, at):
    _enable(lab)
    at(15, 10)
    body = login(mentor).get(f"/api/clubs/{lab.pk}/session/token/").json()
    assert body["state"] == "live" and body["token"]
    api = login(member.user)
    first = api.post("/api/clubs/scan/", {"token": body["token"]}).json()
    assert first["state"] == "marked" and first["session"]["section"] == "AI Startup Lab"
    assert api.post("/api/clubs/scan/", {"token": body["token"]}).json()["state"] == "already"
    assert ClubMark.objects.filter(student=member, club=lab, date=MONDAY, method=MarkMethod.QR).count() == 1
    came = login(mentor).get(f"/api/clubs/{lab.pk}/session/").json()
    assert came["came"] == 1 and came["students"][0]["came"]


def test_section_code_does_not_mark_on_club_and_back(member, lab, at):
    _enable(lab)
    at(15, 10)
    section_token = sport.make_token(slot_of("Теннис", 5, 12, 10), MONDAY)[0]
    assert services.read_token(section_token) is None
    assert sport.read_token(services.make_token(lab, MONDAY)[0]) is None


def test_old_code_and_outside_meeting_time(member, lab, at):
    _enable(lab)
    moment = at(15, 10)
    stale = services.make_token(lab, MONDAY, at=moment.timestamp() - 600)[0]
    api = login(member.user)
    assert api.post("/api/clubs/scan/", {"token": stale}).json()["state"] == "stale"
    at(14, 0)
    early = services.make_token(lab, MONDAY)[0]
    assert api.post("/api/clubs/scan/", {"token": early}).json()["state"] == "not_started"
    at(18, 30)
    late = services.make_token(lab, MONDAY)[0]
    assert api.post("/api/clubs/scan/", {"token": late}).json()["state"] == "ended"


def test_not_a_member_is_told_so(pupils, lab, at):
    _senior, junior = pupils
    _enable(lab)
    at(15, 10)
    token = services.make_token(lab, MONDAY)[0]
    assert login(junior.user).post("/api/clubs/scan/", {"token": token}).json()["state"] == "not_enrolled"


def test_scan_before_login_waits_for_the_login(member, lab, at):
    from rest_framework.test import APIClient

    _enable(lab)
    at(15, 10)
    browser = APIClient()
    token = services.make_token(lab, MONDAY)[0]
    assert browser.post("/api/clubs/scan/", {"token": token}).json()["state"] == "login"
    browser.force_login(member.user)
    assert browser.post("/api/clubs/scan/", {}).json()["state"] == "marked"


def test_mentor_marks_by_hand_and_unmarks(mentor, member, lab, at):
    _enable(lab)
    at(15, 10)
    api = login(mentor)
    assert api.post(f"/api/clubs/{lab.pk}/session/marks/", {"student": member.pk}).status_code == 201
    mark = ClubMark.objects.get(student=member, club=lab)
    assert mark.method == MarkMethod.MANUAL and mark.marked_by == mentor
    assert api.delete(f"/api/clubs/{lab.pk}/session/marks/?student={member.pk}").status_code == 204
    assert not ClubMark.objects.exists()
