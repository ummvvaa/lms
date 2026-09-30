"""Накладки — по времени звонков группы, а не по номеру урока (дефект прода, 30.09.2026).

У 8–9 классов первый урок в 8:00, у 10–11 — в 10:15. Учитель с 1 уроком
в KIOTO и 1 уроком в CORNELL в один день ничего не накладывает: это разные
часы. Накладка — пересечение интервалов; замена предлагает учителя,
свободного по времени.
"""

from __future__ import annotations

import datetime as dt

import pytest

from academics import calendar as school_calendar
from academics import schedule
from academics.cohorts import group_cohort, make_stream
from academics.models import Bell, BellSchedule
from academics.schedule import create_once
from academics.tests.conftest import login, school_day
from students.models import StudyGroup

pytestmark = pytest.mark.django_db

#: звонки прода: 8–9 классы с 8:00, 10–11 — с 10:15
JUNIOR_BELLS = (("08:00", "08:45"), ("08:50", "09:35"), ("09:40", "10:25"), ("10:35", "11:20"))
SENIOR_BELLS = (("10:15", "11:00"), ("11:05", "11:50"), ("12:00", "12:45"), ("13:15", "14:00"))


def bells(year, title: str, rows, group) -> BellSchedule:
    found = BellSchedule.objects.create(year=year, title=title)
    for number, (starts, ends) in enumerate(rows, start=1):
        Bell.objects.create(
            year=year,
            schedule=found,
            number=number,
            starts=dt.time.fromisoformat(starts),
            ends=dt.time.fromisoformat(ends),
        )
    found.groups.add(group)
    return found


@pytest.fixture
def school(year):
    kioto = StudyGroup.objects.create(code="KIOTO", parallel=8)
    cornell = StudyGroup.objects.create(code="CORNELL", parallel=10)
    bells(year, "8–9 классы", JUNIOR_BELLS, kioto)
    bells(year, "10–11 классы", SENIOR_BELLS, cornell)
    return {"kioto": group_cohort(kioto), "cornell": group_cohort(cornell)}


@pytest.fixture
def day(year, school):
    return school_day(1, school_calendar.load(year))


def lesson(subjects, who, cohort, day, slot, room):
    return create_once(subject=subjects["alg"], teacher=who, cohort=cohort, date=day, slot=slot, room=room)


def test_first_lesson_at_eight_and_first_lesson_at_ten_fifteen_is_not_a_conflict(subjects, teacher, school, day):
    lesson(subjects, teacher, school["kioto"], day, 1, "204")
    # при заведении урока: тот же номер у другой параллели — другое время
    assert schedule.conflicts_for(date=day, slot=1, teacher_id=teacher.pk, cohort=school["cornell"], room="204") == []
    lesson(subjects, teacher, school["cornell"], day, 1, "204")
    assert schedule.conflicts_between(day, day) == []


def test_real_overlap_by_time_is_a_conflict_even_with_different_numbers(subjects, teacher, school, day):
    # 3 урок KIOTO 9:40–10:25 и 1 урок CORNELL 10:15–11:00 — десять минут вместе
    lesson(subjects, teacher, school["kioto"], day, 3, "204")
    probe = schedule.conflicts_for(date=day, slot=1, teacher_id=teacher.pk, cohort=school["cornell"], room="")
    assert [c.kind for c in probe] == ["teacher"]

    lesson(subjects, teacher, school["cornell"], day, 1, "305")
    found = schedule.conflicts_between(day, day)
    assert [(row["kind"], row["time"]) for row in found] == [("teacher", "10:15")]
    assert "ведёт два урока сразу" in found[0]["text"]


def test_room_is_checked_by_time_too(subjects, teacher, other_teacher, school, day):
    lesson(subjects, teacher, school["kioto"], day, 4, "506")  # 10:35–11:20
    lesson(subjects, other_teacher, school["cornell"], day, 1, "506")  # 10:15–11:00
    assert [row["kind"] for row in schedule.conflicts_between(day, day)] == ["room"]

    # тот же номер урока в том же кабинете, но в разные часы — не накладка
    other_day = day + dt.timedelta(days=7)
    lesson(subjects, teacher, school["kioto"], other_day, 2, "506")  # 8:50
    lesson(subjects, other_teacher, school["cornell"], other_day, 2, "506")  # 11:05
    assert schedule.conflicts_between(other_day, other_day) == []


def test_back_to_back_lessons_do_not_overlap(subjects, teacher, school, day):
    # подряд у одного учителя: 2 урок KIOTO 8:50–9:35 и 3 урок 9:40–10:25
    lesson(subjects, teacher, school["kioto"], day, 2, "204")
    lesson(subjects, teacher, school["kioto"], day, 3, "204")
    assert schedule.conflicts_between(day, day) == []


def test_joint_lesson_of_a_stream_is_not_a_conflict_with_itself(year, subjects, teacher, day):
    """Совместный урок — одна строка на поток: накладки с собой у него нет."""
    left = StudyGroup.objects.create(code="HARVARD", parallel=10)
    right = StudyGroup.objects.create(code="YALE", parallel=10)
    senior = BellSchedule.objects.get(title="10–11 классы")
    senior.groups.add(left, right)
    stream = make_stream(name="HARVARD + YALE", parts=[group_cohort(left), group_cohort(right)])
    lesson(subjects, teacher, stream, day, 1, "101")
    assert schedule.conflicts_between(day, day) == []


def test_substitute_is_offered_only_when_free_by_time(subjects, teacher, other_teacher, school, day, kymbat):
    wanted = lesson(subjects, other_teacher, school["cornell"], day, 1, "305")  # 10:15–11:00
    lesson(subjects, teacher, school["kioto"], day, 1, "204")  # 8:00 — свободен к 10:15

    rows = {row["id"]: row for row in schedule.substitute_candidates(wanted, [teacher, other_teacher])}
    assert rows[teacher.pk]["free"] is True
    assert other_teacher.pk not in rows, "основного учителя на замену не предлагаем"
    api = login(kymbat)
    body = api.get(f"/api/acad/lessons/{wanted.pk}/substitutes/").json()
    assert next(row for row in body["rows"] if row["id"] == teacher.pk)["free"] is True
    ok = api.post(
        f"/api/acad/lessons/{wanted.pk}/substitute/", {"teacher": teacher.pk, "reason": "болеет"}, format="json"
    )
    assert ok.status_code == 200, ok.json()


def test_substitute_busy_by_time_is_marked_and_refused(subjects, teacher, other_teacher, school, day, kymbat):
    wanted = lesson(subjects, other_teacher, school["cornell"], day, 1, "305")  # 10:15–11:00
    lesson(subjects, teacher, school["kioto"], day, 3, "204")  # 9:40–10:25 — занят

    rows = {row["id"]: row for row in schedule.substitute_candidates(wanted, [teacher])}
    assert rows[teacher.pk]["free"] is False
    assert "KIOTO" in rows[teacher.pk]["busy_with"] and "09:40" in rows[teacher.pk]["busy_with"]
    refused = login(kymbat).post(
        f"/api/acad/lessons/{wanted.pk}/substitute/", {"teacher": teacher.pk, "reason": "болеет"}, format="json"
    )
    assert refused.status_code == 400
    assert "ведёт урок" in refused.json()["detail"]


def test_teachers_day_goes_by_time_not_by_number(year, subjects, teacher, school):
    """«Сегодня» у учителя: 2 урок KIOTO (8:50) раньше 1 урока CORNELL (10:15)."""
    calendar = school_calendar.load(year)
    day = school_day(1, calendar)
    late = lesson(subjects, teacher, school["cornell"], day, 1, "204")
    early = lesson(subjects, teacher, school["kioto"], day, 2, "204")
    from academics import teachers

    ordered = school_calendar.by_time(teachers.lessons_of(teacher, day, day), calendar)
    assert [row.pk for row in ordered] == [early.pk, late.pk]
