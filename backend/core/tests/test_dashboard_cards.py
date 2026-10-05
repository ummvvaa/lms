"""Дашборды Кымбат и Асем: дубль плитки и окно героя (фаза 80).

«Мок просел» у Кымбат стоял дважды — плиткой сверху и списком ниже; оставлен
список, где по ученику есть действие. Герой Асем стоит, только пока в ближайшие
30 дней есть дедлайн, на который кто-то подаётся: пустой блок «дедлайнов нет»
занимал пол-экрана и ничего не сообщал.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from core.cabinets import admission_cabinet, exam_cabinet, urgent_days
from students.models import Student
from universities.models import AdmissionRound, Program, RoundType, StudentUniversity, University


@pytest.fixture
def pupil(db) -> Student:
    return Student.objects.create(
        last_name="Дедлайнов", first_name="Ученик", email="deadline80@example.kz", graduation_year=2027
    )


def _round(name: str, days: int) -> AdmissionRound:
    program = Program.objects.create(university=University.objects.create(name=name, country="US"), name="CS")
    deadline = timezone.localdate() + dt.timedelta(days=days)
    return AdmissionRound.objects.create(program=program, round_type=RoundType.RD, deadline=deadline)


def _apply(student: Student, admission_round: AdmissionRound) -> None:
    StudentUniversity.objects.create(student=student, program=admission_round.program, admission_round=admission_round)


@pytest.mark.django_db
def test_mock_drop_is_a_list_and_not_a_tile_as_well():
    cabinet = exam_cabinet()
    assert [stat["code"] for stat in cabinet["stats"]] == ["ielts", "sat", "queue"]
    assert "drops" in cabinet, "список просевших остаётся: по каждому есть действие"


@pytest.mark.django_db
def test_no_deadlines_no_hero(pupil):
    # дедлайн за окном и дедлайн без подающих — героя не держат
    _apply(pupil, _round("Far University", urgent_days() + 10))
    _round("Nobody University", 5)

    urgent = admission_cabinet()["urgent"]
    assert urgent["rounds"] == 0 and urgent["applicants"] == 0 and urgent["nearest"] is None
    assert urgent["window_days"] == urgent_days() == 30


@pytest.mark.django_db
def test_deadline_within_the_month_holds_the_hero_even_past_the_week(pupil):
    _apply(pupil, _round("Later University", 25))
    _apply(pupil, _round("Sooner University", 12))

    urgent = admission_cabinet()["urgent"]
    assert urgent["applying"] == 0, "на этой неделе никто не подаёт"
    assert urgent["rounds"] == 2 and urgent["applicants"] == 2
    assert urgent["nearest"]["university"] == "Sooner University" and urgent["nearest"]["days"] == 12


@pytest.mark.django_db
def test_deadline_this_week_is_the_urgent_part_of_the_window(pupil):
    _apply(pupil, _round("This Week University", 3))

    urgent = admission_cabinet()["urgent"]
    assert urgent["applying"] == 1 and urgent["rounds"] == 1
    assert urgent["first"]["university"] == urgent["nearest"]["university"] == "This Week University"


@pytest.mark.django_db
def test_deadline_colour_and_windows_are_school_settings(pupil):
    """Цвет дедлайна считает сервер по окнам школы; окно поменяли — цвет и герой считают по новому."""
    from core.dashboards import admission_dashboard
    from core.models import SchoolRule

    for name, ahead in (("Near University", 20), ("Mid University", 45), ("Far University", 90)):
        _apply(pupil, _round(name, ahead))

    tones = {row["university"]: row["tone"] for row in admission_dashboard()["deadlines"]}
    assert tones == {"Near University": "bad", "Mid University": "warn", "Far University": "neutral"}
    assert admission_cabinet()["urgent"]["rounds"] == 1

    SchoolRule.objects.create(code="deadline_soon_days", value=10)
    SchoolRule.objects.create(code="deadline_dashboard_days", value=60)
    tones = {row["university"]: row["tone"] for row in admission_dashboard()["deadlines"]}
    assert tones == {"Near University": "warn", "Mid University": "warn"}, "за горизонтом дашборда дедлайна нет"
    urgent = admission_cabinet()["urgent"]
    assert urgent["rounds"] == 0 and urgent["window_days"] == 10
