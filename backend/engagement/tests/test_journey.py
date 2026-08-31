"""Фаза 37: лестница шагов ученика."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from engagement.journey import build
from engagement.onboarding import QUESTIONS, answer


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


def by_code(payload):
    return {s["code"]: s for s in payload["steps"]}


@pytest.mark.django_db
def test_five_steps_and_plan_is_locked_at_start(student):
    payload = build(student)
    steps = by_code(payload)
    assert payload["total"] == 5
    assert payload["done"] == 0
    assert not payload["complete"]
    assert list(steps) == ["profile", "scores", "direction", "universities", "plan"]
    # плана не бывает без вузов: пятый шаг заперт и объясняет, чем открыть
    assert steps["plan"]["locked"]
    assert "вузов" in steps["plan"]["lock_reason"]


@pytest.mark.django_db
def test_steps_complete_from_db_state(student, make_user):
    from universities.models import Program, StudentUniversity, University

    # профиль: пройден весь квиз, значения — в границах шкал реестра
    values = {
        "target_country": "Казахстан",
        "target_major": "Computer Science",
        "grade": "11",
        "english_score": "6.5",
        "standardized_score": "1250",
        "gpa": "3.6",
        "cost_priority": "moderate",
        "has_university_list": "да",
    }
    for question in QUESTIONS:
        answer(student, code=question.code, value=values[question.code])
    # баллы уже в профиле
    student.exam.refresh_from_db()
    # направление
    student.admission.refresh_from_db()
    student.admission.target_major = "Computer Science"
    student.admission.save()
    # список вузов
    university = University.objects.create(name="Т1", country="Казахстан")
    program = Program.objects.create(university=university, name="CS", level="bachelor")
    StudentUniversity.objects.create(student=student, program=program)

    payload = build(student)
    steps = by_code(payload)
    assert steps["profile"]["done"]
    assert steps["direction"]["done"]
    assert steps["universities"]["done"]
    assert not steps["plan"]["locked"]


@pytest.mark.django_db
def test_pending_proposal_counts_for_scores_step(api, student_user, student):
    """Ученик свою часть сделал: балл на проверке — шаг выполнен."""
    assert not by_code(build(student))["scores"]["done"]
    api.force_authenticate(student_user)
    api.post(
        "/api/suggestions/propose/",
        {"rows": [{"model": "students.ExamProfile", "field": "ielts_current", "value": "7.0"}]},
        format="json",
    )
    assert by_code(build(student))["scores"]["done"]


@pytest.mark.django_db
def test_journey_endpoint_is_for_students(api, student_user, make_user):
    api.force_authenticate(make_user("director_exam", "k@school.kz"))
    assert api.get("/api/journey/").status_code == 403

    api.force_authenticate(student_user)
    payload = api.get("/api/journey/").data
    assert payload["total"] == 5
