"""Кабинет куратора после перехода на учебную часть.

«Напомнить всем» о документах
уважает выбранную группу (D64), посещаемость в карточке считается по урокам,
а отметка дня осталась на чтение.
"""

from __future__ import annotations

import pytest

from academics import marks as marking
from academics.tests.conftest import days, login
from accounts.curators import assign
from students.models import AttendanceDay

pytestmark = pytest.mark.django_db


def test_documents_reminder_respects_the_picked_group(curator, chicago, pupils, admin):
    """«Напомнить всем» по BOSTON не трогает CHICAGO, хотя куратор ведёт обе (D64)."""
    from roadmap.models import Task

    assign(group=chicago, curator=curator, since=days(-10), actor=admin)
    client = login(curator)
    made = client.post("/api/curator/documents/remind/", {"group": "BOSTON"}, format="json")
    assert made.status_code == 200, made.content
    assert made.json()["group"] == "BOSTON"
    assert made.json()["created"] == 3
    assert Task.objects.filter(student=pupils["stranger"]).count() == 0
    assert Task.objects.filter(student=pupils["aliya"]).count() == 1

    everyone = client.post("/api/curator/documents/remind/", {}, format="json")
    assert everyone.json()["group"] == "all"
    assert Task.objects.filter(student=pupils["stranger"]).count() == 1


def test_card_attendance_comes_from_lessons(curator, teacher, lesson, pupils, calendar):
    """Процент и дни с пропусками в карточке — по урокам, а не по прежней отметке дня."""
    marking.save_attendance(
        lesson, [{"student": pupils["aliya"].pk, "mark": "absent"}], actor=teacher, calendar=calendar
    )
    card = login(curator).get(f"/api/curator/students/{pupils['aliya'].pk}/").json()
    block = card["behavior"]
    assert block["attendance_percent"] == 0 and block["attendance_lessons"] == 1
    assert [row["date"] for row in block["days"]] == [str(lesson.date)]
    assert "не был" in block["days"][0]["reason"] and block["days"][0]["absent"] == 1
    assert block["unexcused_days"] == [], "одно «н» за день — ещё не день без причины"

    other = login(curator).get(f"/api/curator/students/{pupils['damir'].pk}/").json()["behavior"]
    assert other["attendance_percent"] == 100 and other["days"] == []


def test_day_marking_is_closed_to_the_curator(curator, boston, pupils):
    """Отметка дня закрыта шлюзом (403), лист дня открыт на чтение без права отмечать."""
    client = login(curator)
    body = {"group": boston.pk, "date": "2026-09-01", "rows": [{"student": pupils["aliya"].pk, "present": False}]}
    assert client.post("/api/attendance/save/", body, format="json").status_code == 403
    assert not AttendanceDay.objects.exists()
    sheet = client.get(f"/api/attendance/?group={boston.pk}")
    assert sheet.status_code == 200 and sheet.json()["may_mark"] is False
