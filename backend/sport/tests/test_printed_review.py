"""«На проверку»: отметки по печатному QR с неточным местом ждут решения директора спорта.

Границы, которые легко сломать тихо:
* пока отметка ждёт, её нет ни в «пришли», ни в проценте, ни в Excel, ни у ученика;
* подтверждённая — обычная отметка со способом «по печатному QR» и расстоянием;
* отклонённую повторный скан не возвращает, а директор может отметить вручную;
* решить по отметке можно один раз; чужим ролям очередь закрыта.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from sport.models import MarkStatus, SectionMark, SectionMarkMethod
from sport.tests.conftest import SATURDAY, away, login, slot_of
from sport.tests.conftest import scan_printed as scan

pytestmark = pytest.mark.django_db


def test_pending_mark_counts_nowhere_until_confirmed(people, member, at):
    senior, slot = member
    row = senior.section_enrollments.get()
    row.enrolled_at = row.slot_set_at = timezone.make_aware(dt.datetime(2026, 10, 1))
    row.save()
    at(12, 4)
    assert scan(senior, slot.section, away(40, 600))["state"] == "review"
    director = login(people["director_sport"])

    session = director.get(f"/api/sport/sessions/{slot.pk}/").json()
    assert session["came"] == 0 and session["pending"] == 1 and not session["students"][0]["came"]
    queue = director.get("/api/sport/marks/pending/").json()["rows"]
    assert [item["student"]["id"] for item in queue] == [senior.pk]
    assert "неточно" in queue[0]["why"] and queue[0]["distance"] == "40 м"

    at(13, 30)
    month = director.get(f"/api/sport/attendance/?slot={slot.pk}&month=2026-10").json()
    cell = month["rows"][0]["cells"][month["dates"].index(SATURDAY.isoformat())]
    assert cell == "absent" and month["rows"][0]["percent"] == 0
    preview = director.get(f"/api/sport/attendance/export/?slot={slot.pk}&month=2026-10&preview=1")
    assert preview.status_code == 200 and "был" not in preview.content.decode()
    assert login(senior.user).get("/api/my/section/").json()["enrollments"][0]["came"] == 0

    mark = SectionMark.objects.get(student=senior)
    answer = director.post(f"/api/sport/marks/{mark.pk}/review/", {"decision": "confirm"}, format="json")
    assert answer.status_code == 200 and answer.json()["status"] == "confirmed"
    mark.refresh_from_db()
    assert mark.reviewed_by == people["director_sport"] and mark.reviewed_at is not None
    session = director.get(f"/api/sport/sessions/{slot.pk}/?date={SATURDAY}").json()
    student = session["students"][0]
    assert session["came"] == 1 and session["pending"] == 0
    assert (student["came"], student["method"], student["distance"]) == (True, "printed", "40 м")
    month = director.get(f"/api/sport/attendance/?slot={slot.pk}&month=2026-10").json()
    assert month["rows"][0]["cells"][month["dates"].index(SATURDAY.isoformat())] == "printed"
    assert month["rows"][0]["percent"] == 20  # одно занятие из пяти суббот октября
    assert not director.get("/api/sport/marks/pending/").json()["rows"]
    # второй раз решить нельзя
    again = director.post(f"/api/sport/marks/{mark.pk}/review/", {"decision": "reject"}, format="json")
    assert again.status_code == 400


def test_rejected_mark_stays_out_and_director_can_still_mark_by_hand(people, member, at):
    senior, slot = member
    at(12, 4)
    assert scan(senior, slot.section, away(380))["state"] == "review"
    mark = SectionMark.objects.get(student=senior)
    director = login(people["director_sport"])
    answer = director.post(f"/api/sport/marks/{mark.pk}/review/", {"decision": "reject"}, format="json")
    assert answer.json()["status"] == "rejected"
    assert director.get(f"/api/sport/sessions/{slot.pk}/").json()["came"] == 0
    # отклонённую повторный скан не возвращает
    assert scan(senior, slot.section, away(5))["state"] == "rejected"
    assert director.post(f"/api/sport/marks/{mark.pk}/review/", {"decision": "maybe"}, format="json").status_code == 400
    made = director.post(f"/api/sport/sessions/{slot.pk}/marks/", {"student": senior.pk}, format="json")
    assert made.status_code == 201
    mark.refresh_from_db()
    assert mark.status == MarkStatus.CONFIRMED and mark.method == SectionMarkMethod.MANUAL


def test_pending_guest_becomes_a_guest_after_confirm(people, pupils, court, at):
    senior, _junior = pupils
    slot = slot_of("Теннис", 5, 12, 10)
    at(12, 4)
    answer = scan(senior, court, away(250))
    assert answer["state"] == "review" and answer["guest"] is True
    director = login(people["director_sport"])
    assert director.get(f"/api/sport/sessions/{slot.pk}/").json()["guest_rows"] == []
    queue = director.get("/api/sport/marks/pending/").json()["rows"]
    assert queue[0]["guest"] is True and "за радиусом" in queue[0]["why"]
    director.post(f"/api/sport/marks/{queue[0]['id']}/review/", {"decision": "confirm"}, format="json")
    guests = director.get(f"/api/sport/sessions/{slot.pk}/").json()["guest_rows"]
    assert [(g["id"], g["method"], g["distance"]) for g in guests] == [(senior.pk, "printed", "250 м")]


def test_review_is_closed_to_other_roles(people, member, at):
    senior, slot = member
    at(12, 4)
    assert scan(senior, slot.section, away(300))["state"] == "review"
    mark = SectionMark.objects.get(student=senior)
    for user in (people["curator"], people["teacher"], people["director_exam"], senior.user):
        api = login(user)
        assert api.get("/api/sport/marks/pending/").status_code in (403, 404), user.role
        answer = api.post(f"/api/sport/marks/{mark.pk}/review/", {"decision": "confirm"}, format="json")
        assert answer.status_code in (403, 404), user.role
    mark.refresh_from_db()
    assert mark.status == MarkStatus.PENDING
    # администратор решает так же, как директор спорта
    answer = login(people["admin"]).post(f"/api/sport/marks/{mark.pk}/review/", {"decision": "confirm"}, format="json")
    assert answer.status_code == 200
