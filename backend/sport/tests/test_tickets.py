"""Билеты: нажатие до старта не принимается, первые N получают, очередь идёт по времени нажатия.

* последний билет не достаётся двоим одновременно нажавшим;
* отказ отдаёт билет первому в очереди с ответом за `offer_minutes`, не ответил — следующему;
* анонс и напоминание приходят ученикам классов раздачи, на их языке;
* раздачу ведут директор спорта и администратор; чужой директор и куратор — нет.
"""

from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections
from django.utils import timezone

from core.models import Notification
from sport import tickets
from sport.models import ClaimStatus, TicketClaim, TicketDrop
from sport.services import Refused
from sport.tests.conftest import login
from students.models import Student

pytestmark = pytest.mark.django_db


def make_drop(count=2, opens_in=-1, **extra) -> TicketDrop:
    now = timezone.now()
    return TicketDrop.objects.create(
        title="Футбол, матч лиги",
        event_at=now + dt.timedelta(days=3),
        place="Центральный стадион",
        count=count,
        opens_at=now + dt.timedelta(minutes=opens_in),
        pickup="Кабинет директора спорта, до 18:00 накануне",
        **extra,
    )


@pytest.fixture
def crowd(groups, make_user):
    mine, _other = groups
    return [
        Student.objects.create(
            last_name=f"Болельщик{n}",
            first_name="Тест",
            group=mine,
            graduation_year=2028,
            user=make_user("student", f"fan{n}@sec.kz"),
        )
        for n in range(4)
    ]


def test_claim_before_start_is_refused(crowd):
    drop = make_drop(opens_in=10)
    answer = login(crowd[0].user).post(f"/api/my/tickets/{drop.pk}/claim/")
    assert answer.status_code == 400 and not TicketClaim.objects.exists()
    body = login(crowd[0].user).get("/api/my/tickets/").json()
    assert body["now"] and body["rows"][0]["stage"] == "announce"


def test_first_n_get_tickets_rest_queue_in_order(crowd):
    drop = make_drop(count=2)
    states = [login(s.user).post(f"/api/my/tickets/{drop.pk}/claim/").json()["mine"] for s in crowd]
    assert [s["status"] for s in states] == ["received", "received", "queued", "queued"]
    assert [s["place"] for s in states[2:]] == [1, 2]
    # один билет в руки: повторное нажатие ничего не меняет
    again = login(crowd[0].user).post(f"/api/my/tickets/{drop.pk}/claim/").json()["mine"]
    assert again["status"] == "received" and TicketClaim.objects.filter(drop=drop).count() == 4


def test_decline_offers_to_first_in_queue_then_next_on_timeout(crowd):
    drop = make_drop(count=1)
    for student in crowd[:3]:
        tickets.claim(drop=drop, student=student)
    login(crowd[0].user).post(f"/api/my/tickets/{drop.pk}/decline/")
    second = TicketClaim.objects.get(drop=drop, student=crowd[1])
    assert second.status == ClaimStatus.OFFERED and second.offer_until
    assert Notification.objects.filter(recipient=crowd[1].user, kind=Notification.Kind.TICKET_OFFERED).exists()
    # не ответил вовремя — билет третьему
    tickets.expire_offers(now=second.offer_until + dt.timedelta(seconds=1))
    second.refresh_from_db()
    third = TicketClaim.objects.get(drop=drop, student=crowd[2])
    assert second.status == ClaimStatus.EXPIRED and third.status == ClaimStatus.OFFERED
    body = login(crowd[2].user).post(f"/api/my/tickets/{drop.pk}/accept/").json()["mine"]
    assert body["status"] == "received" and body["from_queue"] is True


def test_leaving_queue_and_missed_pickup(crowd, people):
    drop = make_drop(count=1)
    first, second, third = (tickets.claim(drop=drop, student=s) for s in crowd[:3])
    login(crowd[1].user).post(f"/api/my/tickets/{drop.pk}/decline/")
    assert TicketClaim.objects.get(pk=second.pk).status == ClaimStatus.LEFT
    answer = login(people["director_sport"]).post(f"/api/sport/ticket-claims/{first.pk}/missed/")
    assert answer.status_code == 200 and answer.json()["status"] == "missed"
    assert TicketClaim.objects.get(pk=third.pk).status == ClaimStatus.OFFERED


def test_announce_and_reminder_reach_only_audience(crowd, pupils):
    _senior, junior = pupils
    drop = make_drop(opens_in=4, parallel_from=10, parallel_to=11)
    reached = tickets.announce(drop)
    assert reached == len(crowd) + 1  # плюс ученик 10 класса из `pupils`
    assert not Notification.objects.filter(recipient=junior.user).exists()
    assert tickets.announce(TicketDrop.objects.get(pk=drop.pk)) == 0
    assert tickets.remind_soon() == reached and tickets.remind_soon() == 0
    # 9 класс эту раздачу не видит и не забирает
    assert login(junior.user).get("/api/my/tickets/").json()["rows"] == []
    assert login(junior.user).post(f"/api/my/tickets/{drop.pk}/claim/").status_code == 404


def test_director_sees_claims_with_milliseconds_and_exports(crowd, people):
    drop = make_drop(count=1)
    for student in crowd[:2]:
        tickets.claim(drop=drop, student=student)
    body = login(people["director_sport"]).get(f"/api/sport/tickets/{drop.pk}/").json()
    assert [c["status"] for c in body["claims"]] == ["received", "queued"]
    assert "." in body["claims"][0]["pressed_at"]
    sheet = login(people["admin"]).get(f"/api/sport/tickets/{drop.pk}/export/?preview=1").json()["sheets"][0]
    assert sheet["total"] == 1


def test_director_publishes_and_strangers_cannot(people, django_capture_on_commit_callbacks):
    now = timezone.now()
    body = {
        "title": "Хоккей",
        "event_at": (now + dt.timedelta(days=5)).isoformat(),
        "opens_at": (now + dt.timedelta(days=2)).isoformat(),
        "place": "Ледовый дворец",
        "pickup": "Кабинет директора спорта",
        "count": 20,
        "parallel_from": 8,
        "parallel_to": 11,
    }
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        answer = login(people["director_sport"]).post("/api/sport/tickets/", body, format="json")
    assert answer.status_code == 201 and len(callbacks) == 1
    for role in ("director_exam", "curator", "teacher"):
        assert login(people[role]).post("/api/sport/tickets/", body, format="json").status_code in (403, 404)
        assert login(people[role]).get("/api/sport/tickets/").status_code in (403, 404)


def test_student_sees_no_other_names(crowd):
    drop = make_drop(count=1)
    for student in crowd[:3]:
        tickets.claim(drop=drop, student=student)
    text = login(crowd[2].user).get("/api/my/tickets/").content.decode()
    assert "Болельщик0" not in text and "Болельщик1" not in text


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_last_ticket_goes_to_one_of_two(groups):
    mine, _other = groups
    drop = make_drop(count=1)
    racers = [
        Student.objects.create(last_name=f"Гонщик{n}", first_name="Тест", group=mine, graduation_year=2028)
        for n in range(2)
    ]

    def press(pk):
        close_old_connections()
        try:
            return tickets.claim(drop=drop, student=Student.objects.get(pk=pk)).status
        except Refused:
            return "refused"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(press, [r.pk for r in racers]))
    assert sorted(outcomes) == ["queued", "received"]
