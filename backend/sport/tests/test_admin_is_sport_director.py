"""Администратор получает всё, что директор спорта, во всех блоках секций и билетов (решение владельца, 27.10.2026).

Обход по маршрутам приложения: каждая ручка директора спорта отвечает
администратору так же, как самому директору, — без 403 и 404. Новая ручка,
не попавшая в список, роняет страж: список и `sport/urls.py` сверяются.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from sport import services, tickets
from sport.models import Section, TicketDrop
from sport.tests.conftest import login, slot_of

pytestmark = pytest.mark.django_db

#: ручки директора спорта: имя маршрута → (метод, тело)
DIRECTOR_ROUTES = {
    "sport-sections": ("get", None),
    "sport-sections-export": ("get", None),
    "sport-section": ("get", None),
    "sport-settings": ("patch", {"enroll_until": None}),
    "sport-student-search": ("get", None),
    "sport-enrollments": ("post", "enroll"),
    "sport-enrollment": ("patch", "move"),
    "sport-students-sections": ("get", None),
    "sport-student-section": ("get", None),
    "sport-sessions-today": ("get", None),
    "sport-session": ("get", None),
    "sport-session-token": ("get", None),
    "sport-session-end": ("post", None),
    "sport-session-mark": ("post", "mark"),
    "sport-attendance": ("get", None),
    "sport-attendance-export": ("get", None),
    "sport-tickets": ("get", None),
    "sport-ticket": ("get", None),
    "sport-ticket-export": ("get", None),
    "sport-ticket-missed": ("post", None),
}

#: ручки ученика: администратору закрыты с причиной «кабинет ученика»
STUDENT_ROUTES = {
    "my-section",
    "my-section-enroll",
    "my-section-leave",
    "sport-scan",
    "my-tickets",
    "my-ticket-claim",
    "my-ticket-decline",
    "my-ticket-accept",
}


def _sport_routes() -> set[str]:
    from sport import urls

    return {pattern.name for pattern in urls.urlpatterns}


def test_route_list_matches_the_app():
    assert set(DIRECTOR_ROUTES) | STUDENT_ROUTES == _sport_routes()


@pytest.fixture
def world(pupils):
    senior, junior = pupils
    slot = slot_of("Теннис", 5, 12, 10)
    services.enroll(student=senior, slot=slot, actor=None, by_director=True)
    now = timezone.now()
    drop = TicketDrop.objects.create(
        title="Матч",
        event_at=now + dt.timedelta(days=2),
        place="Стадион",
        count=1,
        opens_at=now - dt.timedelta(minutes=1),
        pickup="Кабинет",
    )
    claim = tickets.claim(drop=drop, student=senior)
    return {"senior": senior, "junior": junior, "slot": slot, "drop": drop, "claim": claim}


def _url(name: str, world) -> str:
    from django.urls import reverse

    pk = {
        "sport-section": Section.objects.get(title="Теннис").pk,
        "sport-enrollment": world["senior"].section_enrollments.get(ended_at__isnull=True).pk,
        "sport-student-section": world["senior"].pk,
        "sport-session": world["slot"].pk,
        "sport-session-token": world["slot"].pk,
        "sport-session-end": world["slot"].pk,
        "sport-session-mark": world["slot"].pk,
        "sport-ticket": world["drop"].pk,
        "sport-ticket-export": world["drop"].pk,
        "sport-ticket-missed": world["claim"].pk,
    }.get(name)
    return reverse(name, kwargs={"pk": pk}) if pk else reverse(name)


def _body(kind, world):
    if kind == "enroll":
        return {"student": world["junior"].pk, "slot": slot_of("Теннис", 3, 17, 8).pk}
    if kind == "move":
        return {"slot": slot_of("Теннис", 5, 13, 10).pk}
    if kind == "mark":
        return {"student": world["senior"].pk, "date": "2026-10-24"}
    return kind or {}


@pytest.mark.parametrize("role", ["director_sport", "admin"])
@pytest.mark.parametrize("name", sorted(DIRECTOR_ROUTES))
def test_admin_passes_every_sport_director_route(people, world, role, name):
    method, kind = DIRECTOR_ROUTES[name]
    api = login(people[role])
    url = _url(name, world)
    answer = getattr(api, method)(url, _body(kind, world), format="json") if method != "get" else api.get(url)
    assert answer.status_code < 300, (name, answer.status_code, answer.content[:200])


def test_student_routes_are_closed_to_the_admin_with_reason(people):
    from accounts.permissions import ADMIN_CLOSED_ROUTES

    assert STUDENT_ROUTES <= set(ADMIN_CLOSED_ROUTES)
    assert not set(DIRECTOR_ROUTES) & set(ADMIN_CLOSED_ROUTES)
