"""«Разобрать» у накладки ведёт туда, где её чинят (06.10.2026).

Накладки считаются по всей школе, а неделя расписания показывает один вид —
группу, учителя или кабинет. Кнопка «Разобрать» искала урок накладки среди
уроков показанного вида, не находила и молчала. Теперь каждая накладка
говорит, в каком виде недели её видно целиком (`where`): у учителя — его
неделя, у кабинета — кабинет, у общих учеников — группа, которая есть у обоих
составов; урок без звонков — группа его состава.
"""

from __future__ import annotations

import datetime as dt

import pytest

from academics import calendar as school_calendar
from academics import schedule
from academics.cohorts import group_cohort, make_stream
from academics.models import BellSchedule
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
    return {"kioto": group_cohort(kioto), "cornell": group_cohort(cornell), "groups": (kioto, cornell)}


@pytest.fixture
def day(year, school):
    return school_day(1, school_calendar.load(year))


def lesson(subjects, who, cohort, day, slot, room):
    return create_once(subject=subjects["alg"], teacher=who, cohort=cohort, date=day, slot=slot, room=room)


def test_teacher_clash_points_to_the_teachers_week(subjects, teacher, school, day):
    first = lesson(subjects, teacher, school["kioto"], day, 3, "204")  # 9:40–10:25
    second = lesson(subjects, teacher, school["cornell"], day, 1, "305")  # 10:15–11:00
    [found] = schedule.conflicts_between(day, day)
    assert found["kind"] == "teacher"
    assert {found["lesson"], found["other"]} == {first.pk, second.pk}
    assert found["where"] == {"view": "teacher", "key": str(teacher.pk)}


def test_room_clash_points_to_the_room(subjects, teacher, other_teacher, school, day):
    lesson(subjects, teacher, school["kioto"], day, 4, "506")
    lesson(subjects, other_teacher, school["cornell"], day, 1, "506")
    [found] = schedule.conflicts_between(day, day)
    assert found["kind"] == "room"
    assert found["where"] == {"view": "room", "key": "506"}


def test_shared_students_clash_points_to_the_common_group(year, subjects, teacher, other_teacher, school, day):
    """Поток из KIOTO и YALE и сама KIOTO в одно время: общая группа — KIOTO."""
    kioto, _cornell = school["groups"]
    yale = StudyGroup.objects.create(code="YALE", parallel=8)
    BellSchedule.objects.get(title="8–9 классы").groups.add(yale)
    make_student(kioto, "Ким", "Алия", "alia@test.local")
    stream = make_stream(name="KIOTO + YALE", parts=[school["kioto"], group_cohort(yale)])
    lesson(subjects, teacher, school["kioto"], day, 2, "101")
    lesson(subjects, other_teacher, stream, day, 2, "102")
    [found] = schedule.conflicts_between(day, day)
    assert found["kind"] == "students"
    assert found["where"] == {"view": "group", "key": "KIOTO"}


def test_lesson_without_bells_points_to_its_group(year, subjects, teacher, day):
    bare = StudyGroup.objects.create(code="BARE", parallel=9)
    for found in BellSchedule.objects.filter(year=year):
        found.groups.remove(bare)
    lesson(subjects, teacher, group_cohort(bare), day, 1, "")
    found = [row for row in schedule.conflicts_between(day, day) if row["kind"] == "bells"]
    assert found and found[0]["where"] == {"view": "group", "key": "BARE"}


def test_week_answers_with_where_and_the_view_shows_both_lessons(subjects, teacher, school, day, kymbat):
    first = lesson(subjects, teacher, school["kioto"], day, 3, "204")
    second = lesson(subjects, teacher, school["cornell"], day, 1, "305")
    api = login(kymbat)
    week = api.get(f"/api/acad/schedule/?from={day - dt.timedelta(days=day.weekday())}").json()
    [found] = week["conflicts"]
    where = found["where"]
    # в виде по группе второго урока нет — потому кнопка и молчала
    assert {lesson["id"] for lesson in week["lessons"]} < {first.pk, second.pk} or week["view"] == "group"
    shown = api.get(
        f"/api/acad/schedule/?from={day - dt.timedelta(days=day.weekday())}&view={where['view']}&key={where['key']}"
    ).json()
    assert {first.pk, second.pk} <= {lesson["id"] for lesson in shown["lessons"]}
    assert set(shown["conflict_ids"]) == {first.pk, second.pk}
