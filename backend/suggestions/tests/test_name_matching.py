"""Сопоставление имён — главный источник тихих ошибок, покрываем плотно."""

from __future__ import annotations

import pytest

from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    TalentProfile,
)
from suggestions.name_matching import find, find_many, normalize, similarity, stem


def make(last: str, first: str, email: str, group, middle: str = "") -> Student:
    s = Student.objects.create(
        last_name=last,
        first_name=first,
        middle_name=middle,
        email=email,
        grade=11,
        group=group,
        graduation_year=2027,
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=s)
    return s


@pytest.fixture
def school(db, group):
    """Школа с однофамильцами и разными алфавитами."""
    return {
        "aruzhan": make("Ахметова", "Аружан", "aruzhan@school.kz", group),
        "aliya": make("Ахметова", "Алия", "aliya@school.kz", group),
        "alikhan": make("Абдрахманов", "Алихан", "alikhan@school.kz", group, middle="Ерланович"),
        "damir": make("Сериков", "Дамир", "damir@school.kz", group),
        "zhanna": make("Тлеубаева", "Жанна", "zhanna@school.kz", group),
    }


# --- Нормализация и основы ---


def test_normalize_handles_three_alphabets():
    assert normalize("Ахметова") == "ahmetova"
    assert normalize("AHMETOVA") == "ahmetova"
    assert normalize("Әбдірахманов") == "abdirahmanov"
    assert normalize("  Ахметова,  Аружан ") == "ahmetova aruzhan"


def test_stem_drops_case_endings():
    assert stem(normalize("Ахметову")) == stem(normalize("Ахметова"))
    assert stem(normalize("Ахметовой")) == stem(normalize("Ахметова"))


def test_similarity_ignores_word_order():
    assert similarity("Ахметова Аружан", "Ахметова Аружан") == 1.0
    assert similarity("Аружан Ахметова", "Ахметова Аружан") == 1.0


# --- Уверенное совпадение ---


@pytest.mark.django_db
def test_exact_full_name_is_confident(school):
    outcome = find("Ахметова Аружан")
    assert outcome.is_confident
    assert outcome.best.student_id == school["aruzhan"].pk
    assert outcome.best.confidence == 1.0


@pytest.mark.django_db
def test_email_is_always_confident(school):
    outcome = find("damir@school.kz")
    assert outcome.is_confident
    assert outcome.best.student_id == school["damir"].pk


@pytest.mark.django_db
def test_latin_spelling_matches_cyrillic_record(school):
    outcome = find("Serikov Damir")
    assert outcome.is_confident, outcome.as_dict()
    assert outcome.best.student_id == school["damir"].pk


@pytest.mark.django_db
def test_declension_still_matches(school):
    """«Ахметовой Аружан» — та же ученица."""
    outcome = find("Ахметовой Аружан")
    assert outcome.is_confident, outcome.as_dict()
    assert outcome.best.student_id == school["aruzhan"].pk


@pytest.mark.django_db
def test_middle_name_in_record_does_not_break_match(school):
    outcome = find("Абдрахманов Алихан")
    assert outcome.is_confident
    assert outcome.best.student_id == school["alikhan"].pk


@pytest.mark.django_db
def test_reversed_order_matches(school):
    outcome = find("Дамир Сериков")
    assert outcome.is_confident
    assert outcome.best.student_id == school["damir"].pk


# --- Неоднозначность: главное, ради чего всё это ---


@pytest.mark.django_db
def test_surname_only_with_namesakes_is_ambiguous(school):
    """Две Ахметовой — молча выбирать нельзя."""
    outcome = find("Ахметова")
    assert not outcome.is_confident
    assert outcome.is_ambiguous
    ids = {c.student_id for c in outcome.candidates}
    assert {school["aruzhan"].pk, school["aliya"].pk} <= ids
    assert outcome.as_dict()["student"] is None


@pytest.mark.django_db
def test_initial_does_not_disambiguate_namesakes(school):
    """«Ахметова А.» подходит и Аружан, и Алие — спрашиваем человека."""
    outcome = find("Ахметова А.")
    assert outcome.is_ambiguous, outcome.as_dict()
    assert len({c.student_id for c in outcome.candidates}) >= 2


@pytest.mark.django_db
def test_initial_disambiguates_when_only_one_fits(school):
    """«Сериков Д.» однозначен: другого Серикова нет."""
    outcome = find("Сериков Д.")
    assert outcome.is_confident, outcome.as_dict()
    assert outcome.best.student_id == school["damir"].pk


@pytest.mark.django_db
def test_unknown_name_returns_nothing(school):
    outcome = find("Иванов Пётр")
    assert outcome.is_missing
    assert outcome.best is None
    assert not outcome.is_confident


@pytest.mark.django_db
def test_typo_is_matched_but_not_blindly(school):
    """Опечатка находит кандидата, но проверяем, что это правильный человек."""
    outcome = find("Тлеубаева Жана")
    assert outcome.best is not None
    assert outcome.best.student_id == school["zhanna"].pk


@pytest.mark.django_db
def test_candidates_are_sorted_by_confidence(school):
    outcome = find("Ахметова Ару")
    confidences = [c.confidence for c in outcome.candidates]
    assert confidences == sorted(confidences, reverse=True)
    assert outcome.best.student_id == school["aruzhan"].pk


@pytest.mark.django_db
def test_empty_query_is_missing(school):
    assert find("").is_missing
    assert find("   ").is_missing


@pytest.mark.django_db
def test_find_many_processes_a_batch(school):
    outcomes = find_many(["Ахметова Аружан", "Ахметова", "Иванов Пётр"])
    assert outcomes[0].is_confident
    assert outcomes[1].is_ambiguous
    assert outcomes[2].is_missing


@pytest.mark.django_db
def test_inactive_students_are_not_matched(school):
    school["damir"].is_active = False
    school["damir"].save(update_fields=["is_active"])
    assert find("Сериков Дамир").is_missing


@pytest.mark.django_db
def test_far_behind_candidates_are_not_offered(school):
    """В диалоге «выберите одного» не должно быть явно чужих людей."""
    outcome = find("Ахметова А.")
    names = {c.full_name for c in outcome.candidates}
    assert "Абдрахманов Алихан" not in names
    assert names == {"Ахметова Аружан", "Ахметова Алия"}
