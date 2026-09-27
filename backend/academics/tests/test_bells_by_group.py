"""Звонки по группам: несколько расписаний звонков, время урока — из звонков его группы,
поток из групп с разными звонками — накладка (решение владельца, 27.09.2026)."""

from __future__ import annotations

import datetime as dt

import pytest

from academics import calendar as school_calendar
from academics import schedule
from academics.cohorts import make_stream
from academics.models import Bell, BellSchedule
from academics.tests.conftest import school_day

pytestmark = pytest.mark.django_db


@pytest.fixture
def late_bells(year, chicago):
    """Второе расписание: у CHICAGO уроки начинаются на час позже."""
    late = BellSchedule.objects.create(year=year, title="Старшие")
    for number, starts, ends in school_calendar.DEFAULT_BELLS:
        Bell.objects.create(
            year=year,
            schedule=late,
            number=number,
            starts=(dt.datetime.combine(dt.date.today(), dt.time.fromisoformat(starts)) + dt.timedelta(hours=1)).time(),
            ends=(dt.datetime.combine(dt.date.today(), dt.time.fromisoformat(ends)) + dt.timedelta(hours=1)).time(),
        )
    late.groups.add(chicago)
    return late


def test_migration_left_the_old_bells_in_a_default_schedule(year):
    default = school_calendar.default_schedule(year)
    assert default.is_default
    assert Bell.objects.filter(year=year, schedule=default).count() == len(school_calendar.DEFAULT_BELLS)


def test_lesson_time_comes_from_the_bells_of_its_group(year, boston, chicago, late_bells):
    calendar = school_calendar.load(year)
    assert calendar.bell(1, [boston.pk]) == (dt.time(8, 30), dt.time(9, 15))
    assert calendar.bell(1, [chicago.pk]) == (dt.time(9, 30), dt.time(10, 15))
    # разные звонки у групп состава — берётся общее
    assert calendar.bell(1, [boston.pk, chicago.pk]) == (dt.time(8, 30), dt.time(9, 15))
    assert school_calendar.bell_text(calendar, 1, [chicago.pk]) == "09:30–10:15"


def test_lesson_state_follows_its_group_bells(year, boston, chicago, late_bells):
    calendar = school_calendar.load(year)
    day = school_calendar.today()
    at = dt.datetime.combine(day, dt.time(9, 0), tzinfo=school_calendar.now_local().tzinfo)
    assert calendar.slot_state(day, 1, at=at, groups=[boston.pk]) == "now"
    assert calendar.slot_state(day, 1, at=at, groups=[chicago.pk]) == "future"


def test_stream_of_groups_with_different_bells_is_a_conflict(year, subjects, teacher, cohorts, late_bells, calendar):
    stream = make_stream(name="BOSTON + CHICAGO", parts=[cohorts["boston"], cohorts["chicago"]])
    day = school_day(1, calendar)
    found = schedule.conflicts_for(date=day, slot=3, teacher_id=teacher.pk, cohort=stream, room="")
    assert [c.kind for c in found] == ["bells"]
    assert "CHICAGO — «Старшие»" in found[0].text and "BOSTON — «общее»" in found[0].text
    # одна группа — накладки нет
    assert schedule.conflicts_for(date=day, slot=3, teacher_id=teacher.pk, cohort=cohorts["chicago"], room="") == []


def test_year_screen_shows_schedules_as_cards_and_saves_them(year, boston, chicago, as_kymbat):
    payload = as_kymbat.get("/api/acad/year/").json()
    assert [row["is_default"] for row in payload["bell_schedules"]] == [True]
    saved = as_kymbat.patch(
        "/api/acad/year/",
        {
            "bell_schedules": [
                {
                    "title": "Старшие",
                    "groups": [chicago.code],
                    "bells": [
                        {"number": 1, "starts": "09:30", "ends": "10:15"},
                        {"number": 2, "starts": "10:25", "ends": "11:10"},
                    ],
                }
            ]
        },
        format="json",
    ).json()
    late = next(row for row in saved["bell_schedules"] if not row["is_default"])
    assert late["title"] == "Старшие" and late["groups"] == [chicago.code]
    assert [b["number"] for b in late["bells"]] == [1, 2]
    calendar = school_calendar.load(year)
    assert calendar.bell(1, [chicago.pk]) == (dt.time(9, 30), dt.time(10, 15))
    # общее расписание не удаляется, своё — уходит вместе с назначением групп
    default = next(row for row in saved["bell_schedules"] if row["is_default"])
    assert as_kymbat.patch("/api/acad/year/", {"drop_bell_schedule": default["id"]}, format="json").status_code == 400
    dropped = as_kymbat.patch("/api/acad/year/", {"drop_bell_schedule": late["id"]}, format="json").json()
    assert [row["is_default"] for row in dropped["bell_schedules"]] == [True]
    assert school_calendar.load(year).bell(1, [chicago.pk]) == (dt.time(8, 30), dt.time(9, 15))
