"""Занятие секции у директора и отказ от меняющегося кода (решение владельца, 05.11.2026).

У секции один постоянный код — на экране «Занятие и QR» и на печатном листе
(`test_printed_sheet.py`, `test_printed_scan.py`). Меняющийся код секциям
отключён: его токен отклоняется, ручка выдачи закрыта. Механизм в сервисе
оставлен — тем же устройством работают кружки, — поэтому он проверяется здесь
на уровне сервиса. Ручная отметка директора остаётся и пишется в журнал.

Время замораживается на субботу 31.10.2026, 12:04 по Алматы — идёт теннис
12:00–13:00 для 10–11 классов.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AuditLog
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


def test_changing_code_is_retired_for_sections(enrolled, at, people):
    """Токен меняющегося кода секции больше не отмечает никого: ни вошедшего, ни после входа."""
    senior, _junior, tennis = enrolled
    at(12, 4)
    token = _token(tennis)
    assert login(senior.user).post("/api/sport/scan/", {"token": token}).json() == {"state": "retired"}
    # сотруднику и не вошедшему — тот же ответ; до входа код в браузере больше не держится
    assert login(people["director_sport"]).post("/api/sport/scan/", {"token": token}).json() == {"state": "retired"}
    browser = APIClient()
    assert browser.post("/api/sport/scan/", {"token": token}).json() == {"state": "retired"}
    assert services.HOLD_KEY not in browser.session
    browser.force_login(senior.user)
    assert browser.post("/api/sport/scan/", {}).json() == {"state": "retired"}
    assert browser.post("/api/sport/scan/", {"token": "мусор"}).json() == {"state": "retired"}
    assert not SectionMark.objects.exists()


def test_director_gets_no_changing_code(enrolled, at, people):
    """Ручки выдачи меняющегося кода у секций больше нет — директору и администратору 404 с причиной."""
    _senior, _junior, tennis = enrolled
    at(12, 10)
    for role in ("director_sport", "admin"):
        api = login(people[role])
        answer = api.get(f"/api/sport/sessions/{tennis.pk}/token/")
        assert answer.status_code == 404 and "постоянный" in answer.json()["detail"], role
        today = api.get("/api/sport/sessions/today/").json()["rows"]
        assert {row["state"] for row in today if row["id"] == tennis.pk} == {"live"}


def test_changing_code_mechanism_is_kept_for_clubs(enrolled, at):
    """Механизм токена на окно времени остался в сервисе: свежий читается, старый и подделанный — нет."""
    senior, _junior, tennis = enrolled
    moment = at(12, 4)
    ttl = services.ttl()
    assert services.ROTATING_QR is False
    assert services.read_token(_token(tennis)) == (tennis.pk, SATURDAY)
    # предыдущее окно принимается — запас на дрожание часов, позапрошлое уже нет
    assert services.read_token(_token(tennis, moment.timestamp() - ttl)) == (tennis.pk, SATURDAY)
    assert services.read_token(_token(tennis, moment.timestamp() - 2 * ttl)) is None
    forged = _token(tennis).replace(f"{tennis.pk}.", f"{tennis.pk + 1}.", 1)
    assert services.read_token(forged) is None
    # сервис отметки по такому токену живёт (его путём идут тесты гостей), но маршрут секций к нему не ведёт
    answer = services.mark_by_scan(student=senior, slot_id=tennis.pk, day=SATURDAY)
    assert answer["state"] == "marked"
    assert SectionMark.objects.filter(student=senior, method=MarkMethod.QR).count() == 1


def test_session_runs_by_schedule_and_cannot_be_ended_early(enrolled, at, people):
    """«Закончить занятие» убрано: занятие идёт по расписанию, ручки конца занятия нет."""
    _senior, _junior, tennis = enrolled
    at(12, 30)
    api = login(people["director_sport"])
    assert api.post(f"/api/sport/sessions/{tennis.pk}/end/").status_code == 404
    assert api.get(f"/api/sport/sessions/{tennis.pk}/").json()["state"] == "live"
    at(13, 0)
    assert api.get(f"/api/sport/sessions/{tennis.pk}/").json()["state"] == "past"


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
    # отметка вручную и её снятие — в журнале ученика, с автором
    journal = list(
        AuditLog.objects.filter(student_id=senior.pk, field_name=services.EVENT)
        .order_by("id")
        .values_list("new_value", "actor__email")
    )[-2:]
    assert journal == [
        ("Секция: отмечен вручную — Теннис, Сб 12:00–13:00, 31.10.2026", "director_sport@sec.kz"),
        ("Секция: отметка снята — Теннис, Сб 12:00–13:00, 31.10.2026", "director_sport@sec.kz"),
    ]
    # повторное снятие ничего не снимает и в журнал не пишет
    assert api.delete(f"/api/sport/sessions/{tennis.pk}/marks/?student={senior.pk}").status_code == 204
    assert AuditLog.objects.filter(student_id=senior.pk, new_value__startswith="Секция: отметка снята").count() == 1


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
