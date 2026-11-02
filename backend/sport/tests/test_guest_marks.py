"""Гостевая отметка (02.11.2026): ученик отсканировал код секции, в которую не записан.

Границы, которые легко сломать тихо:
* отметка сохраняется гостевой, ученик видит «отмечен как гость», повтор — без дубля;
* в списке занятия гости — отдельным блоком, в «Пришли» записанных не попадают;
* гость не входит ни в процент записанных, ни в «отмечено вручную»;
* «Записать в эту секцию» идёт тем же путём, что запись директора: пересечение —
  отказ с причиной, сверх лимита часа — подтверждение; записанный гость
  становится обычной отметкой.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from sport import services
from sport.models import SectionEnrollment, SectionMark, SectionSlot
from sport.tests.conftest import login, slot_of

pytestmark = pytest.mark.django_db

#: суббота 31 октября 2026, 12:20 — идёт теннис 12:00–13:00 для 10–11
DURING = dt.datetime(2026, 10, 31, 12, 20)


@pytest.fixture
def saturday(monkeypatch):
    now = timezone.make_aware(DURING)
    monkeypatch.setattr(services, "local_now", lambda: timezone.localtime(now))
    return now


def _scan(student, slot, now):
    return services.mark_by_scan(student=student, slot_id=slot.pk, day=now.date(), now=now)


def test_scan_of_foreign_section_saves_a_guest_mark(pupils, saturday):
    senior, _junior = pupils
    tennis = slot_of("Теннис", 5, 12, 10)
    answer = _scan(senior, tennis, saturday)
    assert answer["state"] == "guest"
    mark = SectionMark.objects.get(student=senior, slot=tennis)
    assert mark.is_guest
    assert _scan(senior, tennis, saturday)["state"] == "guest_already"
    assert SectionMark.objects.filter(student=senior).count() == 1


def test_scan_of_own_section_at_other_hour_is_still_not_yours(pupils, saturday):
    senior, _junior = pupils
    services.enroll(student=senior, slot=slot_of("Теннис", 5, 13, 10), actor=None, by_director=True)
    answer = _scan(senior, slot_of("Теннис", 5, 12, 10), saturday)
    assert answer["state"] == "foreign" and not SectionMark.objects.exists()


def test_guest_goes_to_its_own_block_and_not_to_percent(people, pupils, saturday, monkeypatch):
    senior, junior = pupils
    tennis = slot_of("Теннис", 5, 12, 10)
    # записанный на этот час — для процента; гость — второй ученик 10 параллели
    member = SectionEnrollment.objects.create(
        student=senior,
        section=tennis.section,
        slot=tennis,
        enrolled_at=timezone.make_aware(dt.datetime(2026, 10, 1)),
        source="lms",
    )
    from students.models import Student

    guest = Student.objects.create(last_name="Гостев", first_name="Арман", group=senior.group, graduation_year=2028)
    _scan(senior, tennis, saturday)
    _scan(guest, tennis, saturday)
    api = login(people["director_sport"])
    body = api.get(f"/api/sport/sessions/{tennis.pk}/?date=2026-10-31").json()
    assert [s["id"] for s in body["students"]] == [senior.pk]
    assert [g["id"] for g in body["guest_rows"]] == [guest.pk]
    assert body["came"] == 1 and body["guests"] == 1
    attendance = api.get(f"/api/sport/attendance/?slot={tennis.pk}&month=2026-10").json()
    assert [r["student"]["id"] for r in attendance["rows"]] == [senior.pk]
    assert attendance["guests"][0]["visits"] == 1 and "guest" in attendance["guests"][0]["cells"]
    assert attendance["figures"]["manual"] == 0
    # процент записанного — от его отметок; гостевая на его часе не считалась бы
    after = timezone.make_aware(dt.datetime(2026, 11, 1, 9, 0))
    monkeypatch.setattr(services, "local_now", lambda: timezone.localtime(after))
    assert services.month_percents([member], "2026-10")[member.pk] == 20
    SectionMark.objects.filter(student=senior).update(is_guest=True)
    assert services.month_percents([member], "2026-10")[member.pk] == 0
    assert junior.pk not in [g["id"] for g in body["guest_rows"]]


def test_director_enrolls_a_guest_in_one_click_and_the_mark_counts(people, pupils, saturday):
    senior, _junior = pupils
    tennis = slot_of("Теннис", 5, 12, 10)
    _scan(senior, tennis, saturday)
    api = login(people["director_sport"])
    guest = api.get(f"/api/sport/sessions/{tennis.pk}/?date=2026-10-31").json()["guest_rows"][0]
    assert guest["refusal"] == "" and guest["warnings"] == []
    answer = api.post("/api/sport/enrollments/", {"student": senior.pk, "slot": tennis.pk}, format="json")
    assert answer.status_code == 201
    assert not SectionMark.objects.get(student=senior, slot=tennis).is_guest
    body = api.get(f"/api/sport/sessions/{tennis.pk}/?date=2026-10-31").json()
    assert body["guest_rows"] == [] and body["students"][0]["came"] is True


def test_guest_that_cannot_be_enrolled_says_why(people, pupils, saturday):
    senior, _junior = pupils
    tennis = slot_of("Теннис", 5, 12, 10)
    # футбол в то же время — записать на теннис нельзя, кнопка объясняет почему
    services.enroll(student=senior, slot=slot_of("Футбол", 5, 12, 10), actor=None, by_director=True)
    _scan(senior, tennis, saturday)
    api = login(people["director_sport"])
    guest = api.get(f"/api/sport/sessions/{tennis.pk}/?date=2026-10-31").json()["guest_rows"][0]
    assert "Футбол" in guest["refusal"]
    assert api.post("/api/sport/enrollments/", {"student": senior.pk, "slot": tennis.pk}).status_code == 400


def test_full_hour_takes_a_guest_only_after_confirm(people, pupils, saturday):
    senior, _junior = pupils
    tennis = slot_of("Теннис", 5, 12, 10)
    SectionSlot.objects.filter(pk=tennis.pk).update(capacity=0)
    _scan(senior, tennis, saturday)
    api = login(people["director_sport"])
    guest = api.get(f"/api/sport/sessions/{tennis.pk}/?date=2026-10-31").json()["guest_rows"][0]
    assert guest["warnings"] and guest["refusal"] == ""
    payload = {"student": senior.pk, "slot": tennis.pk}
    assert api.post("/api/sport/enrollments/", payload, format="json").status_code == 409
    assert api.post("/api/sport/enrollments/", {**payload, "force": True}, format="json").status_code == 201


def test_student_page_says_guest(pupils, saturday):
    """Ответ ручки отметки гостю — состояние «guest», без чужих имён."""
    senior, _junior = pupils
    tennis = slot_of("Теннис", 5, 12, 10)
    token, _left = services.make_token(tennis, saturday.date())
    api = login(senior.user)
    answer = api.post("/api/sport/scan/", {"token": token}, format="json").json()
    assert answer["state"] == "guest"
    assert SectionMark.objects.get(student=senior).is_guest
