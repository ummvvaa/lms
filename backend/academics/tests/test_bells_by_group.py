"""Звонки по группам: у каждой группы своё расписание звонков, общего на всех нет.

Время урока — из звонков его группы (решение владельца, 27.09.2026). Группа
без звонков, состав без групп и поток из групп с разными звонками остаются
без времени, и это видно: ошибка над неделей «Расписания», запись в
накладках, строка на экране года, ошибка поля «Урок» (решение владельца,
05.10.2026). Запись «Общее» разбирает миграция по данным.
"""

from __future__ import annotations

import datetime as dt

import pytest

from academics import calendar as school_calendar
from academics import schedule
from academics.cohorts import make_stream
from academics.models import BellSchedule
from academics.schedule import create_once
from academics.tests.conftest import TEST_BELLS, give_bells, school_day

pytestmark = pytest.mark.django_db

LATE = [
    (number, f"{int(starts[:2]) + 1:02d}{starts[2:]}", f"{int(ends[:2]) + 1:02d}{ends[2:]}")
    for number, starts, ends in school_calendar.DEFAULT_BELLS
]


@pytest.fixture
def late_bells(year, chicago):
    """Второе расписание: у CHICAGO уроки начинаются на час позже."""
    return give_bells(year, "Старшие", [chicago], LATE)


@pytest.fixture
def bare_chicago(year, chicago):
    """CHICAGO без звонков: её сняли со всех расписаний."""
    for row in BellSchedule.objects.filter(year=year):
        row.groups.remove(chicago)
    return chicago


def test_lesson_time_comes_from_the_bells_of_its_group(year, boston, chicago, late_bells):
    calendar = school_calendar.load(year)
    assert calendar.bell(1, [boston.pk]) == (dt.time(8, 30), dt.time(9, 15))
    assert calendar.bell(1, [chicago.pk]) == (dt.time(9, 30), dt.time(10, 15))
    assert school_calendar.bell_text(calendar, 1, [chicago.pk]) == "09:30–10:15"


def test_there_is_no_common_grid_to_fall_back_on(year, boston, chicago, late_bells):
    calendar = school_calendar.load(year)
    # разные звонки у групп состава, состав без групп, группа не названа — времени нет
    assert calendar.bell(1, [boston.pk, chicago.pk]) is None
    assert calendar.bell(1, []) is None
    assert calendar.bell(1) is None
    assert calendar.bells_of(None) == {}
    assert not hasattr(calendar, "bells")


def test_group_without_bells_has_no_lesson_time(year, boston, bare_chicago):
    calendar = school_calendar.load(year)
    assert calendar.bell(1, [bare_chicago.pk]) is None
    assert school_calendar.bell_text(calendar, 1, [bare_chicago.pk]) == ""
    assert calendar.without_bells([boston.pk, bare_chicago.pk]) == [bare_chicago.pk]
    # урок без времени сегодня не начался: отметку откроют назначенные звонки
    assert calendar.slot_state(school_calendar.today(), 1, groups=[bare_chicago.pk]) == "future"


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
    assert "CHICAGO — «Старшие»" in found[0].text and f"BOSTON — «{TEST_BELLS}»" in found[0].text
    # одна группа — накладки нет
    assert schedule.conflicts_for(date=day, slot=3, teacher_id=teacher.pk, cohort=cohorts["chicago"], room="") == []


def test_group_without_bells_is_a_conflict_when_saving_a_lesson(
    year, subjects, teacher, cohorts, bare_chicago, calendar
):
    day = school_day(1, calendar)
    found = schedule.conflicts_for(date=day, slot=3, teacher_id=teacher.pk, cohort=cohorts["chicago"], room="")
    assert [c.kind for c in found] == ["bells"]
    assert "Не назначены звонки: CHICAGO" in found[0].text
    # поток, где звонки есть только у одной группы, называет обе стороны
    stream = make_stream(name="BOSTON + CHICAGO", parts=[cohorts["boston"], cohorts["chicago"]])
    mixed = schedule.conflicts_for(date=day, slot=3, teacher_id=teacher.pk, cohort=stream, room="")
    assert "CHICAGO — не назначены" in mixed[0].text and f"BOSTON — «{TEST_BELLS}»" in mixed[0].text


def test_week_and_conflicts_name_the_groups_without_bells(
    year, subjects, teacher, other_teacher, cohorts, bare_chicago, calendar, as_kymbat, as_curator, as_student
):
    day = school_day(0, calendar)
    monday = school_calendar.week_start(day)
    for slot in (2, 3):
        create_once(subject=subjects["alg"], teacher=teacher, cohort=cohorts["chicago"], date=day, slot=slot, room="1")
    create_once(subject=subjects["eng"], teacher=other_teacher, cohort=cohorts["boston"], date=day, slot=2, room="2")
    week = as_kymbat.get(f"/api/acad/schedule/?from={monday}&view=group&key=CHICAGO").json()
    assert week["no_bells"] == ["CHICAGO"]
    # уроки без времени стоят в рядах «по номеру», рядов чужой сетки на экране нет
    assert [row["key"] for row in week["rows"]] == ["#2", "#3"]
    bells = [c for c in week["conflicts"] if c["kind"] == "bells"]
    # одна запись на состав, а не на каждый его урок; сосед со звонками в неё не попал
    assert len(bells) == 1 and "Не назначены звонки: CHICAGO" in bells[0]["text"]
    assert as_kymbat.get(f"/api/acad/schedule/?from={monday}&view=group&key=BOSTON").json()["no_bells"] == []
    # куратору своей группы ошибки чужой группы нет; ученику настройка школы не показывается вовсе
    assert as_curator.get(f"/api/acad/lessons/?from={monday}").json()["no_bells"] == []
    assert as_student.get(f"/api/acad/lessons/?from={monday}").json()["no_bells"] == []


def test_lesson_form_says_why_the_cohort_has_no_bells(year, cohorts, bare_chicago, as_kymbat):
    own = as_kymbat.get(f"/api/acad/bells/?cohort={cohorts['boston'].pk}").json()
    assert len(own["bells"]) == len(school_calendar.DEFAULT_BELLS) and own["problem"] == ""
    bare = as_kymbat.get(f"/api/acad/bells/?cohort={cohorts['chicago'].pk}").json()
    assert bare["bells"] == [] and "Не назначены звонки: CHICAGO" in bare["problem"]
    # состав не выбран — списка нет: общих звонков, которые подставлялись раньше, не существует
    assert as_kymbat.get("/api/acad/bells/").json() == {"bells": [], "problem": ""}


def test_year_screen_shows_schedules_as_cards_and_saves_them(year, boston, chicago, as_kymbat):
    payload = as_kymbat.get("/api/acad/year/").json()
    assert [row["title"] for row in payload["bell_schedules"]] == [TEST_BELLS]
    assert "is_default" not in payload["bell_schedules"][0] and "bells" not in payload
    assert payload["groups_without_bells"] == []
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
    late = next(row for row in saved["bell_schedules"] if row["title"] == "Старшие")
    assert late["groups"] == [chicago.code]
    assert [b["number"] for b in late["bells"]] == [1, 2]
    # группа живёт по одному расписанию: из прежнего она ушла
    first = next(row for row in saved["bell_schedules"] if row["title"] == TEST_BELLS)
    assert first["groups"] == [boston.code]
    calendar = school_calendar.load(year)
    assert calendar.bell(1, [chicago.pk]) == (dt.time(9, 30), dt.time(10, 15))
    # удаляется любое расписание; его группы остаются без звонков, и экран года их называет
    dropped = as_kymbat.patch("/api/acad/year/", {"drop_bell_schedule": late["id"]}, format="json").json()
    assert [row["title"] for row in dropped["bell_schedules"]] == [TEST_BELLS]
    assert dropped["groups_without_bells"] == [chicago.code]
    assert school_calendar.load(year).bell(1, [chicago.pk]) is None


def test_opening_the_year_screen_does_not_create_a_schedule(year, as_kymbat):
    BellSchedule.objects.filter(year=year).delete()
    payload = as_kymbat.get("/api/acad/year/").json()
    assert payload["bell_schedules"] == [] and BellSchedule.objects.count() == 0
    # сохранение года тоже не заводит сетку «для всех»
    assert as_kymbat.patch("/api/acad/year/", {"scale": {"edit_days": 5}}, format="json").status_code == 200
    assert BellSchedule.objects.count() == 0
