"""Посещаемость секций: пропуск — нет отметки на прошедшем занятии; куратор видит только свои группы."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from sport import services
from sport.models import MarkMethod, SectionEnrollment, SectionMark
from sport.tests.conftest import login, slot_of

pytestmark = pytest.mark.django_db


@pytest.fixture
def october(monkeypatch, pupils):
    """Сейчас — понедельник 2 ноября 2026; оба ученика записаны с 1 октября."""
    now = timezone.make_aware(dt.datetime(2026, 11, 2, 10, 0))
    monkeypatch.setattr(services, "local_now", lambda: timezone.localtime(now))
    senior, junior = pupils
    since = timezone.make_aware(dt.datetime(2026, 10, 1, 9, 0))
    rows = []
    for student, slot in ((senior, slot_of("Теннис", 5, 12, 10)), (junior, slot_of("Теннис", 3, 17, 8))):
        rows.append(
            SectionEnrollment.objects.create(
                student=student, section=slot.section, slot=slot, enrolled_at=since, source="lms"
            )
        )
    return rows


def test_percent_counts_held_sessions_only(october, people):
    senior_row, _junior_row = october
    saturdays = [dt.date(2026, 10, d) for d in (3, 10, 17, 24, 31)]
    for day in saturdays[:4]:
        SectionMark.objects.create(student=senior_row.student, slot=senior_row.slot, date=day, method=MarkMethod.QR)
    api = login(people["director_sport"])
    body = api.get(f"/api/sport/attendance/?slot={senior_row.slot_id}&month=2026-10").json()
    assert body["dates"] == [d.isoformat() for d in saturdays]
    row = body["rows"][0]
    assert row["cells"] == ["qr", "qr", "qr", "qr", "absent"] and row["percent"] == 80
    assert body["figures"]["sessions"] == 5 and body["figures"]["below"] == 0


def test_below_threshold_and_manual(october, people):
    senior_row, _junior_row = october
    SectionMark.objects.create(
        student=senior_row.student, slot=senior_row.slot, date=dt.date(2026, 10, 3), method=MarkMethod.MANUAL
    )
    body = login(people["admin"]).get(f"/api/sport/attendance/?slot={senior_row.slot_id}&month=2026-10").json()
    assert body["rows"][0]["percent"] == 20 and body["rows"][0]["below"] is True
    assert body["figures"]["manual"] == 1 and body["figures"]["below"] == 1


def test_curator_sees_own_groups_only(october, people):
    senior_row, junior_row = october
    api = login(people["curator"])
    own = api.get(f"/api/sport/attendance/?slot={senior_row.slot_id}&month=2026-10").json()
    assert [r["student"]["id"] for r in own["rows"]] == [senior_row.student_id]
    other = api.get(f"/api/sport/attendance/?slot={junior_row.slot_id}&month=2026-10").json()
    assert other["rows"] == []
    sheets = api.get("/api/sport/attendance/export/?month=2026-10&preview=1").json()["sheets"]
    assert len(sheets) == 1 and sheets[0]["total"] == 1


@pytest.mark.parametrize("role", ["director_exam", "director_behavior", "teacher"])
def test_strangers_do_not_read_attendance(october, people, role):
    api = login(people[role])
    assert api.get("/api/sport/attendance/").status_code in (403, 404)
    assert api.get("/api/sport/attendance/export/").status_code in (403, 404)


def test_student_sees_own_marks_and_percent(october):
    senior_row, _junior_row = october
    SectionMark.objects.create(
        student=senior_row.student, slot=senior_row.slot, date=dt.date(2026, 10, 31), method=MarkMethod.QR
    )
    body = login(senior_row.student.user).get("/api/my/section/").json()
    mine = body["enrollment"]
    assert mine["percent"] == 20 and mine["came"] == 1
    assert mine["marks"][0] == {"date": "2026-10-31", "came": True, "method": "qr", "at": mine["marks"][0]["at"]}
    text = login(senior_row.student.user).get("/api/my/section/").content.decode()
    # ярлыков «ниже порога» и средних по группе у ученика нет
    assert "below" not in text and "average" not in text
