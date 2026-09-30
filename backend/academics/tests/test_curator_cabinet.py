"""Кабинет куратора после перехода на учебную часть.

«Напомнить всем» о документах
уважает выбранную группу (D64), посещаемость в карточке считается по урокам,
а отметка дня осталась на чтение.
"""

from __future__ import annotations

import datetime as dt

import pytest

from academics import calendar as school_calendar
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


def test_worst_attendance_on_the_school_dashboard_counts_lessons(saltanat, teacher, lesson, pupils, calendar):
    """Худшая посещаемость у Салтанат — по отметкам уроков, одним запросом на всех.

    `attendance_by_students` считает то же, что `student_attendance` по одному:
    урок без отметки в счёт не идёт, «у» снижает процент, ученик без отмеченных
    уроков в список не попадает.
    """
    from academics.results import attendance_by_students, student_attendance
    from core.dashboards import behavior_dashboard

    marking.save_attendance(
        lesson,
        # 2 урок 9:25–10:10: пришёл в 9:34 — 36 минут из 45, это 80 %
        [
            {"student": pupils["aliya"].pk, "mark": "absent"},
            {"student": pupils["damir"].pk, "mark": "late", "arrived": "09:34"},
        ],
        actor=teacher,
        calendar=calendar,
    )
    ids = [pupils["aliya"].pk, pupils["damir"].pk, pupils["nurai"].pk, pupils["stranger"].pk]
    start, end = days(-30), days(0)
    by_student = attendance_by_students(ids, start, end)
    for sid in ids:
        assert by_student[sid].as_dict() == student_attendance(sid, start, end).as_dict()
    assert by_student[pupils["aliya"].pk].pct == 0 and by_student[pupils["damir"].pk].pct == 80
    assert by_student[pupils["stranger"].pk].total == 0

    rows = behavior_dashboard()["worst_attendance"]
    assert [row["student_id"] for row in rows][:1] == [pupils["aliya"].pk], "худшая — первой"
    # трое BOSTON отмечены (Нурай — «был»), ученик CHICAGO без уроков в список не попал
    assert {row["student_id"] for row in rows} == {pupils["aliya"].pk, pupils["damir"].pk, pupils["nurai"].pk}
    assert rows[0]["attendance_percent"] == 0 and rows[0]["absent"] == 1 and rows[0]["lessons"] == 1


def test_attendance_without_a_date_opens_on_the_last_school_day(year, calendar, boston, as_curator, monkeypatch):
    """В воскресенье лист посещаемости открывается на пятницу, а не на «не учебный»."""
    from academics import views

    sunday = next(
        day for day in (school_calendar.today() - dt.timedelta(days=n) for n in range(7)) if day.weekday() == 6
    )
    monkeypatch.setattr(views, "today", lambda: sunday)
    payload = as_curator.get("/api/acad/attendance/").json()
    assert dt.date.fromisoformat(payload["date"]).weekday() == 4
    assert calendar.is_school_day(dt.date.fromisoformat(payload["date"]))
