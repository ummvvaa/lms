"""Отметка по QR: свежий подписанный код, своё занятие, только пока оно идёт.

Время замораживается на субботу 31.10.2026, 12:04 по Алматы — идёт теннис
12:00–13:00 для 10–11 классов.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from sport import services
from sport.models import MarkMethod, SectionMark
from sport.tests.conftest import login, slot_of

pytestmark = pytest.mark.django_db

SATURDAY = dt.date(2026, 10, 31)


@pytest.fixture
def at(monkeypatch):
    """Подменить «сейчас» для сервиса и подписи: часы Алматы и секунды эпохи вместе."""

    def move(hour: int, minute: int = 0, day: dt.date = SATURDAY):
        moment = timezone.make_aware(dt.datetime.combine(day, dt.time(hour, minute)))
        monkeypatch.setattr(services, "local_now", lambda: timezone.localtime(moment))
        monkeypatch.setattr(services, "seconds_now", lambda: moment.timestamp())
        return moment

    return move


@pytest.fixture
def enrolled(pupils):
    senior, junior = pupils
    tennis = slot_of("Теннис", 5, 12, 10)
    services.enroll(student=senior, slot=tennis, actor=None, by_director=True)
    return senior, junior, tennis


def _token(slot, at_seconds=None):
    return services.make_token(slot, SATURDAY, at=at_seconds)[0]


def test_fresh_code_marks_once(enrolled, at):
    senior, _junior, tennis = enrolled
    at(12, 4)
    api = login(senior.user)
    body = api.post("/api/sport/scan/", {"token": _token(tennis)}).json()
    assert body["state"] == "marked" and body["session"]["section"] == "Теннис"
    assert api.post("/api/sport/scan/", {"token": _token(tennis)}).json()["state"] == "already"
    assert SectionMark.objects.filter(student=senior, slot=tennis, date=SATURDAY, method=MarkMethod.QR).count() == 1


def test_old_and_forged_codes_are_refused(enrolled, at):
    senior, _junior, tennis = enrolled
    moment = at(12, 4)
    api = login(senior.user)
    ttl = services.ttl()
    # предыдущее окно принимается — запас на дрожание часов, позапрошлое уже нет
    assert api.post("/api/sport/scan/", {"token": _token(tennis, moment.timestamp() - ttl)}).json()["state"] == "marked"
    SectionMark.objects.all().delete()
    assert api.post("/api/sport/scan/", {"token": _token(tennis, moment.timestamp() - 2 * ttl)}).json()["state"] == (
        "stale"
    )
    token = _token(tennis)
    forged = token.replace(f"{tennis.pk}.", f"{tennis.pk + 1}.", 1)
    assert api.post("/api/sport/scan/", {"token": forged}).json()["state"] == "stale"
    assert not SectionMark.objects.exists()


def test_foreign_session_is_named(enrolled, at):
    senior, _junior, _tennis = enrolled
    at(12, 4)
    volleyball = slot_of("Волейбол", 5, 12, 10)
    body = login(senior.user).post("/api/sport/scan/", {"token": _token(volleyball)}).json()
    assert body["state"] == "foreign"
    assert body["session"]["section"] == "Волейбол" and body["mine"]["section"] == "Теннис"
    assert not SectionMark.objects.exists()


def test_outside_session_time_is_refused(enrolled, at):
    senior, _junior, tennis = enrolled
    at(11, 50)
    # код до начала занятия директору не выдаётся, но и подписанный заранее не сработает
    body = login(senior.user).post("/api/sport/scan/", {"token": _token(tennis)}).json()
    assert body["state"] == "not_started"
    at(13, 1)
    assert login(senior.user).post("/api/sport/scan/", {"token": _token(tennis)}).json()["state"] == "ended"


def test_ended_early_session_closes_marks(enrolled, at, people):
    senior, _junior, tennis = enrolled
    at(12, 30)
    assert login(people["director_sport"]).post(f"/api/sport/sessions/{tennis.pk}/end/").status_code == 200
    assert login(senior.user).post("/api/sport/scan/", {"token": _token(tennis)}).json()["state"] == "ended"


def test_scan_before_login_waits_for_login(enrolled, at):
    senior, _junior, tennis = enrolled
    at(12, 4)
    browser = APIClient()
    assert browser.post("/api/sport/scan/", {"token": _token(tennis)}).json()["state"] == "login"
    # вход в том же браузере, через минуту код уже сменился — отметка ставится по удержанию
    browser.force_login(senior.user)
    at(12, 5)
    assert browser.post("/api/sport/scan/", {}).json()["state"] == "marked"
    # другой браузер удержания не получает
    other = login(senior.user)
    assert other.post("/api/sport/scan/", {}).json()["state"] == "stale"


def test_hold_expires_after_two_minutes(enrolled, at):
    senior, _junior, tennis = enrolled
    at(12, 4)
    browser = APIClient()
    browser.post("/api/sport/scan/", {"token": _token(tennis)})
    browser.force_login(senior.user)
    at(12, 7)
    assert browser.post("/api/sport/scan/", {}).json()["state"] == "stale"


def test_student_without_hour_is_not_marked(pupils, at, tennis):
    senior, _junior = pupils
    services.import_enrollment(student=senior, section=tennis, slot=None, enrolled_at=timezone.now())
    at(12, 4)
    body = login(senior.user).post("/api/sport/scan/", {"token": _token(slot_of("Теннис", 5, 12, 10))}).json()
    assert body["state"] == "no_hour"


def test_token_marks_only_own_student(enrolled, at, people):
    """Токен не даёт ничего, кроме отметки вошедшего ученика: сотруднику он бесполезен."""
    _senior, junior, tennis = enrolled
    at(12, 4)
    assert login(people["director_sport"]).post("/api/sport/scan/", {"token": _token(tennis)}).status_code == 403
    # ученик 9 класса не записан на этот час — его отметка не ставится
    assert login(junior.user).post("/api/sport/scan/", {"token": _token(tennis)}).json()["state"] == "not_enrolled"
    assert not SectionMark.objects.exists()


def test_director_shows_code_only_while_live(enrolled, at, people):
    _senior, _junior, tennis = enrolled
    api = login(people["director_sport"])
    at(11, 30)
    assert api.get(f"/api/sport/sessions/{tennis.pk}/token/").json() == {
        "state": "soon",
        "token": "",
        "ttl": services.ttl(),
        "expires_in": 0,
    }
    at(12, 10)
    body = api.get(f"/api/sport/sessions/{tennis.pk}/token/").json()
    assert body["state"] == "live" and body["token"] and 0 < body["expires_in"] <= services.ttl()
    today = api.get("/api/sport/sessions/today/").json()["rows"]
    assert {row["state"] for row in today if row["id"] == tennis.pk} == {"live"}


def test_manual_mark_and_roster(enrolled, at, people):
    senior, junior, tennis = enrolled
    at(12, 20)
    api = login(people["director_sport"])
    assert api.post(f"/api/sport/sessions/{tennis.pk}/marks/", {"student": senior.pk}).status_code == 201
    assert api.post(f"/api/sport/sessions/{tennis.pk}/marks/", {"student": junior.pk}).status_code == 400
    roster = api.get(f"/api/sport/sessions/{tennis.pk}/").json()
    assert [(s["id"], s["came"], s["method"]) for s in roster["students"]] == [(senior.pk, True, "manual")]
    assert api.delete(f"/api/sport/sessions/{tennis.pk}/marks/?student={senior.pk}").status_code == 204
    assert not SectionMark.objects.exists()


@pytest.mark.parametrize("role", ["director_exam", "director_talent", "curator", "teacher"])
def test_strangers_do_not_run_sessions(enrolled, at, people, role):
    senior, _junior, tennis = enrolled
    at(12, 10)
    api = login(people[role])
    refused = (403, 404)
    assert api.get("/api/sport/sessions/today/").status_code in refused
    assert api.get(f"/api/sport/sessions/{tennis.pk}/token/").status_code in refused
    assert api.post(f"/api/sport/sessions/{tennis.pk}/marks/", {"student": senior.pk}).status_code in refused


def test_scan_is_rate_limited(enrolled, at, settings):
    senior, _junior, _tennis = enrolled
    at(12, 4)
    api = login(senior.user)
    codes = [api.post("/api/sport/scan/", {"token": "мусор"}).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
