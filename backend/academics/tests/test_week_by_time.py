"""Сетка недели — по времени звонков группы, а не по номеру урока (решение владельца, 01.10.2026).

У 8–9 классов первый урок в 8:00, у 10–11 — в 10:15. По номеру они
вставали в один ряд, и в неделе учителя в 8 утра стоял урок, который
идёт в 10:15. Ряд недели — время начала по звонкам группы урока, тем же,
по которым считаются накладки.
"""

from __future__ import annotations

import pytest

from academics import calendar as school_calendar
from academics import schedule
from academics.cohorts import group_cohort
from academics.schedule import create_once
from academics.tests.conftest import login, make_student, school_day
from academics.tests.test_conflicts_by_time import JUNIOR_BELLS, SENIOR_BELLS, bells
from students.models import StudyGroup

pytestmark = pytest.mark.django_db


@pytest.fixture
def school(year):
    kioto = StudyGroup.objects.create(code="KIOTO", parallel=8)
    cornell = StudyGroup.objects.create(code="CORNELL", parallel=10)
    bells(year, "8–9 классы", JUNIOR_BELLS, kioto)
    bells(year, "10–11 классы", SENIOR_BELLS, cornell)
    return {"kioto": kioto, "cornell": cornell}


@pytest.fixture
def day(year, school):
    return school_day(1, school_calendar.load(year))


def lesson(subjects, who, group, day, slot):
    return create_once(
        subject=subjects["alg"], teacher=who, cohort=group_cohort(group), date=day, slot=slot, room="204"
    )


def week(client, day, **params):
    response = client.get("/api/acad/lessons/", {"from": day.isoformat(), "to": day.isoformat(), **params})
    assert response.status_code == 200, response.content
    return response.json()


def test_first_lessons_of_two_parallels_stand_in_different_rows(subjects, teacher, school, day):
    early = lesson(subjects, teacher, school["kioto"], day, 1)
    late = lesson(subjects, teacher, school["cornell"], day, 1)
    data = week(login(teacher), day)
    starts = {row["id"]: row["starts"] for row in data["lessons"]}
    assert starts == {early.pk: "08:00", late.pk: "10:15"}
    keys = [row["key"] for row in data["rows"]]
    # ряды — время по порядку дня, оба урока в своих рядах
    assert keys == sorted(keys)
    assert {"08:00", "10:15"} <= set(keys)
    # на экране две сетки звонков: номер пишется у урока, а не у ряда
    assert data["mixed"] is True


def test_lessons_at_the_same_time_share_a_row_whatever_their_numbers(year, subjects, teacher, school, day):
    """4 урок 8–9 и 1 урок 10–11 в 10:15 — один ряд, номера у ряда нет."""
    tokyo = StudyGroup.objects.create(code="TOKYO", parallel=9)
    aligned = (("08:00", "08:40"), ("08:45", "09:25"), ("09:30", "10:10"), ("10:15", "10:55"))
    bells(year, "8–9 выровненные", aligned, tokyo)
    fourth = lesson(subjects, teacher, tokyo, day, 4)
    first = lesson(subjects, teacher, school["cornell"], day, 1)
    data = week(login(teacher), day)
    starts = {row["id"]: row["starts"] for row in data["lessons"]}
    assert starts[fourth.pk] == starts[first.pk] == "10:15"
    row = next(row for row in data["rows"] if row["key"] == "10:15")
    assert row["slot"] is None


def test_week_of_one_group_has_every_bell_of_its_group_even_empty(subjects, school, day, kymbat):
    response = login(kymbat).get("/api/acad/schedule/", {"from": day.isoformat(), "view": "group", "key": "KIOTO"})
    assert response.status_code == 200, response.content
    data = response.json()
    # пустой звонок — тоже ряд: в него добавляют урок
    assert [(row["starts"], row["ends"], row["slot"]) for row in data["rows"]] == [
        (starts, ends, number) for number, (starts, ends) in enumerate(JUNIOR_BELLS, start=1)
    ]
    assert data["mixed"] is False


def test_student_sees_the_rows_of_own_group(subjects, school, day, make_user):
    pupil = make_student(school["cornell"], "Тестова", "Ученица", "pupil@probe.local", make_user=make_user)
    data = week(login(pupil.user), day)
    assert [row["starts"] for row in data["rows"]] == [starts for starts, _ends in SENIOR_BELLS]
    assert [row["slot"] for row in data["rows"]] == [1, 2, 3, 4]


def test_moved_lesson_leaves_its_ghost_at_the_time_of_its_old_place(year, subjects, teacher, school, day):
    calendar = school_calendar.load(year)
    moved = lesson(subjects, teacher, school["cornell"], day, 1)
    schedule.move(moved, date=day, slot=3, reason="Перенос", calendar=calendar, force=True)
    data = week(login(teacher), day)
    ghost = next(row for row in data["ghosts"] if row["lesson"] == moved.pk)
    assert ghost["starts"] == "10:15"
    assert next(row["starts"] for row in data["lessons"] if row["id"] == moved.pk) == "12:00"


def test_rows_go_by_the_same_bells_as_the_conflict_check(year, subjects, teacher, school, day):
    """Урок встаёт в ряд того же времени, с которого проверка накладок считает его интервал."""
    calendar = school_calendar.load(year)
    rows = [lesson(subjects, teacher, school["kioto"], day, 2), lesson(subjects, teacher, school["cornell"], day, 2)]
    built = schedule.week_rows(calendar, rows)
    for row in rows:
        span = schedule.lesson_span(row, calendar)
        assert f"{span[0]:%H:%M}" in {r["key"] for r in built["rows"]}
    assert built["mixed"] is True
