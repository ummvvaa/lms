"""Фаза 10: процент соответствия считается механически и ничего не обещает."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings

from students.models import ExamProfile, Student
from universities.matching import match
from universities.models import AdmissionRequirement, Program, University


@pytest.fixture
def student(db):
    person = Student.objects.create(
        last_name="Сериков", first_name="Дамир", email="percent@example.kz", grade=11, graduation_year=2027
    )
    ExamProfile.objects.create(student=person, ielts_current=Decimal("6.0"), sat_current=1250, gpa=Decimal("3.40"))
    return person


@pytest.fixture
def university(db):
    return University.objects.create(name="Тестовый вуз", country="Канада")


def program_with(university, **thresholds) -> Program:
    program = Program.objects.create(university=university, name=f"Программа {len(thresholds)}")
    AdmissionRequirement.objects.create(program=program, **thresholds)
    return program


@pytest.mark.django_db
def test_met_requirement_gives_full_position(student, university):
    program = program_with(university, min_ielts=Decimal("5.5"))

    result = match(student, program)

    assert result.percent == 100
    assert result.is_open


@pytest.mark.django_db
def test_gap_gives_partial_percent_counted_from_the_floor(student, university):
    """IELTS 6.0 при пороге 6.5 — это не 92%: шкала начинается не с нуля."""
    program = program_with(university, min_ielts=Decimal("6.5"))

    result = match(student, program)

    # (6.0 − 5.0) / (6.5 − 5.0) = 0.67
    assert result.percent == 67
    assert "0.5 IELTS" in result.summary()


@pytest.mark.django_db
def test_alternatives_count_as_one_position(student, university):
    """Сдан IELTS — TOEFL не требуется, и половина веса не теряется."""
    program = program_with(university, min_ielts=Decimal("5.5"), min_toefl=90)

    result = match(student, program)

    assert result.percent == 100
    assert len(result.breakdown()) == 1
    assert result.breakdown()[0]["code"] == "english"


@pytest.mark.django_db
def test_missing_data_does_not_pretend_to_be_zero_progress(student, university):
    """Нет данных — это «нет данных», и в разбивке так и написано."""
    program = program_with(university, min_act=30)

    result = match(student, program)

    position = result.breakdown()[0]
    assert position["is_unknown"] is True
    assert position["percent"] == 0
    assert "данных" in position["gap_phrase"]


@pytest.mark.django_db
def test_percent_never_leaves_the_scale(student, university):
    low = program_with(university, min_gpa=Decimal("4.0"), min_ielts=Decimal("9.0"), min_sat=1600)
    high = program_with(university, min_gpa=Decimal("2.0"), min_ielts=Decimal("5.0"))

    assert 0 <= match(student, low).percent <= 100
    assert match(student, high).percent == 100


@pytest.mark.django_db
def test_no_requirements_means_no_percent(student, university):
    program = Program.objects.create(university=university, name="Без требований")

    result = match(student, program)

    assert result.has_requirements is False
    assert result.percent == 0
    assert "не заведены" in result.summary()


@pytest.mark.django_db
@override_settings(MATCH_WEIGHTS={"gpa": 50.0, "english": 50.0, "standardized": 0.0, "portfolio": 0.0})
def test_formula_is_configurable(student, university):
    """Веса живут в настройках: школа меняет формулу без выката кода."""
    program = program_with(university, min_gpa=Decimal("3.4"), min_ielts=Decimal("6.5"))

    result = match(student, program)

    # GPA закрыт полностью, английский на 0.67 → (1.0 + 0.67) / 2
    assert result.percent == 83


@pytest.mark.django_db
def test_breakdown_names_the_gap_in_words(student, university):
    program = program_with(university, min_ielts=Decimal("6.5"), min_sat=1350)

    rows = {row["code"]: row for row in match(student, program).breakdown()}

    assert rows["english"]["gap_phrase"] == "0.5 IELTS"
    assert rows["standardized"]["gap_phrase"] == "100 SAT"
