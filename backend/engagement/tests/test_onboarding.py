"""Фаза 11: квиз при первом входе.

Данные от ученика не приравниваются к проверенным: в аудите они идут
источником `student_onboarding`, а директор домена видит их отдельно.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.passwords import set_password
from core.domains import Source
from core.models import AuditLog
from engagement import onboarding
from engagement.models import OnboardingStatus, XPKind
from students.models import AdmissionProfile, ExamProfile, Student

PASSWORD = "Онбординг!Проверка26"


def make_student(email="quiz@school.kz") -> Student:
    user = User.objects.create_user(email=email, password=None, role=Role.STUDENT)
    set_password(user, PASSWORD)
    student = Student.objects.create(
        last_name="Ким", first_name="Дана", email=email, grade=10, graduation_year=2027, user=user
    )
    AdmissionProfile.objects.create(student=student)
    ExamProfile.objects.create(student=student)
    return student


def as_client(student: Student) -> APIClient:
    client = APIClient()
    client.post("/api/auth/login/", {"email": student.email, "password": PASSWORD}, format="json")
    return client


@pytest.fixture
def student(db):
    return make_student()


@pytest.mark.django_db
def test_quiz_has_eight_questions(student):
    state = onboarding.state(student)

    assert state["total"] == 8
    assert state["answered"] == 0
    assert state["next"]["code"] == "target_country"


@pytest.mark.django_db
def test_answer_fills_the_profile(student):
    onboarding.answer(student, code="target_country", value="Канада")
    onboarding.answer(student, code="english_score", value="6.5")

    student.admission.refresh_from_db()
    student.exam.refresh_from_db()
    assert student.admission.target_country == "Канада"
    assert student.exam.ielts_current == Decimal("6.5")


@pytest.mark.django_db
def test_audit_marks_the_source_as_the_student_quiz(student):
    """По журналу должно быть видно, что число назвал ученик."""
    onboarding.answer(student, code="gpa", value="3.6")

    entry = AuditLog.objects.get(field_name="gpa")
    assert entry.source == Source.STUDENT_ONBOARDING


@pytest.mark.django_db
def test_progress_is_saved_step_by_step(student):
    onboarding.answer(student, code="target_country", value="США")
    onboarding.answer(student, code="grade", value="11")

    state = onboarding.state(student)
    assert state["answered"] == 2
    assert state["answers"]["target_country"] == "США"
    # следующий вопрос — первый неотвеченный, а не первый вообще
    assert state["next"]["code"] == "target_major"


@pytest.mark.django_db
def test_quiz_can_be_skipped_and_resumed(student):
    onboarding.answer(student, code="target_country", value="Канада")
    assert onboarding.skip(student)["status"] == OnboardingStatus.SKIPPED

    resumed = onboarding.answer(student, code="target_major", value="Economics")["state"]

    assert resumed["status"] == OnboardingStatus.IN_PROGRESS
    assert resumed["answered"] == 2


@pytest.mark.django_db
def test_finishing_the_quiz_awards_xp_once(student):
    from engagement.models import XPEvent

    for question in onboarding.QUESTIONS:
        onboarding.answer(student, code=question.code, value="да" if question.kind == "bool" else "")

    assert onboarding.state(student)["status"] == OnboardingStatus.COMPLETED
    assert XPEvent.objects.filter(student=student, kind=XPKind.ONBOARDING_DONE).count() == 1


@pytest.mark.django_db
def test_bad_number_is_refused_with_a_readable_reason(student):
    with pytest.raises(ValueError, match="не подходит"):
        onboarding.answer(student, code="gpa", value="совсем не число")


@pytest.mark.django_db
def test_each_director_sees_only_his_domain(student):
    onboarding.answer(student, code="target_country", value="Канада")
    onboarding.answer(student, code="english_score", value="6.5")

    admission = onboarding.pending_for(Role.DIRECTOR_ADMISSION)
    exam = onboarding.pending_for(Role.DIRECTOR_EXAM)

    assert [row["question"] for row in admission] == ["target_country"]
    assert [row["question"] for row in exam] == ["english_score"]


@pytest.mark.django_db
def test_director_confirms_and_the_value_becomes_manual(student, db):
    director = User.objects.create_user(email="asem@school.kz", password=None, role=Role.DIRECTOR_ADMISSION)
    onboarding.answer(student, code="target_country", value="Канада")
    row = onboarding.pending_for(Role.DIRECTOR_ADMISSION)[0]

    result = onboarding.review(row["id"], decision="confirm", actor=director)

    assert result["status"] == "confirmed"
    assert onboarding.pending_for(Role.DIRECTOR_ADMISSION) == []
    student.admission.refresh_from_db()
    assert student.admission.target_country == "Канада"


@pytest.mark.django_db
def test_director_can_correct_the_value(student, db):
    director = User.objects.create_user(email="k@school.kz", password=None, role=Role.DIRECTOR_EXAM)
    onboarding.answer(student, code="english_score", value="7.5")
    row = onboarding.pending_for(Role.DIRECTOR_EXAM)[0]

    onboarding.review(row["id"], decision="confirm", value="6.5", actor=director)

    student.exam.refresh_from_db()
    assert student.exam.ielts_current == Decimal("6.5")


@pytest.mark.django_db
def test_declining_clears_the_field_but_keeps_the_history(student, db):
    director = User.objects.create_user(email="k2@school.kz", password=None, role=Role.DIRECTOR_EXAM)
    onboarding.answer(student, code="english_score", value="9.0")
    row = onboarding.pending_for(Role.DIRECTOR_EXAM)[0]

    onboarding.review(row["id"], decision="decline", actor=director)

    student.exam.refresh_from_db()
    assert student.exam.ielts_current is None
    # запись ответа осталась: видно, что ученик отвечал
    from engagement.models import OnboardingAnswer

    assert OnboardingAnswer.objects.filter(question="english_score").exists()


@pytest.mark.django_db
def test_student_cannot_see_the_confirmation_queue(student):
    api = as_client(student)

    assert api.get("/api/onboarding/pending/").status_code == 403


@pytest.mark.django_db
def test_staff_cannot_take_the_quiz(db):
    director = User.objects.create_user(email="staff@school.kz", password=None, role=Role.DIRECTOR_SPORT)
    set_password(director, PASSWORD)
    api = APIClient()
    api.post("/api/auth/login/", {"email": director.email, "password": PASSWORD}, format="json")

    assert api.get("/api/onboarding/").status_code == 403
