"""Блок «Кружки» в карточке ученика: куратор своих групп видит кружки, даты и выход; посещение — только при отметке."""

from __future__ import annotations

import pytest

from clubs import services
from clubs.tests.conftest import login

pytestmark = pytest.mark.django_db


def test_curator_sees_clubs_dates_and_leaving_of_own_student(people, pupils, lab, robots):
    senior, _junior = pupils  # senior — в группе куратора
    services.enroll(student=senior, club=lab, actor=None)
    services.enroll(student=senior, club=robots, actor=None)
    services.leave(student=senior, club=robots, actor=None)
    rows = login(people["curator"]).get(f"/api/clubs/students/{senior.pk}/").json()["rows"]
    assert [(r["club"], r["left"]) for r in rows] == [("AI Startup Lab", False), ("Робототехника", True)]
    assert rows[0]["enrolled_at"] and rows[1]["ended_at"]
    assert all("percent" not in r for r in rows), "отметка выключена — посещения нет"


def test_curator_of_another_group_gets_not_found(people, pupils, lab):
    _senior, junior = pupils  # чужая группа
    services.enroll(student=junior, club=lab, actor=None)
    assert login(people["curator"]).get(f"/api/clubs/students/{junior.pk}/").status_code == 404


def test_attendance_shows_only_when_marks_are_on(people, pupils, lab):
    senior, _junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    lab.marks_enabled = True
    lab.save(update_fields=["marks_enabled"])
    row = login(people["curator"]).get(f"/api/clubs/students/{senior.pk}/").json()["rows"][0]
    assert "percent" in row


def test_directors_and_teacher_do_not_read_the_block(people, pupils, lab):
    senior, _junior = pupils
    for role in ("director_behavior", "director_exam", "director_sport", "teacher"):
        assert login(people[role]).get(f"/api/clubs/students/{senior.pk}/").status_code in (403, 404), role
    assert login(people["admin"]).get(f"/api/clubs/students/{senior.pk}/").status_code == 200
