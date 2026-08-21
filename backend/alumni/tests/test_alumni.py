"""Выпускники, менторство через школу, архив эссе, переход ученик → выпускник."""

from __future__ import annotations

from datetime import date

import pytest
from rest_framework.test import APIClient

from accounts.models import Identity, IdentityProvider
from alumni.models import Alumnus, ApplicationOutcome, ArchivedEssay, MentorshipStatus
from alumni.services import MentorshipDenied, needs_identity_offer, promote, promote_due, request_mentorship
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    TalentProfile,
)
from universities.models import ApplicationStatus, Program, StudentUniversity, University


def make(last: str, first: str, email: str, group, year: int = 2027) -> Student:
    s = Student.objects.create(
        last_name=last, first_name=first, email=email, grade=11, group=group, graduation_year=year
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=s)
    return s


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def asem(make_user):
    return make_user("director_admission", "asem@school.kz", full_name="Асем")


@pytest.fixture
def toronto(db):
    university = University.objects.create(name="University of Toronto", country="Канада", domain="utoronto.ca")
    return Program.objects.create(university=university, name="Computer Science")


@pytest.fixture
def graduate(db, group, toronto):
    """Ученик, которого поступили и пора выпускать."""
    student = make("Ахметова", "Аружан", "aruzhan@school.kz", group, year=2026)
    student.exam.gpa = "3.80"
    student.exam.ielts_current = "7.5"
    student.exam.sat_current = 1420
    student.exam.save()
    StudentUniversity.objects.create(
        student=student, program=toronto, tier="target", application_status=ApplicationStatus.ACCEPTED
    )
    return student


# --- Переход ученик → выпускник ---


@pytest.mark.django_db
def test_promote_snapshots_admission_profile(graduate, toronto):
    """Профиль на момент поступления — исторический срез, он не меняется потом."""
    alumnus = promote(graduate)

    assert alumnus.graduation_year == 2026
    assert str(alumnus.admission_gpa) == "3.80"
    assert str(alumnus.admission_ielts) == "7.5"
    assert alumnus.admission_sat == 1420
    assert alumnus.university == toronto.university
    assert alumnus.country == "Канада"

    # правка карточки ученика не переписывает историю
    graduate.exam.ielts_current = "5.0"
    graduate.exam.save()
    alumnus.refresh_from_db()
    assert str(alumnus.admission_ielts) == "7.5"


@pytest.mark.django_db
def test_promote_carries_application_outcomes(graduate, toronto):
    alumnus = promote(graduate)
    application = alumnus.applications.get(program=toronto)
    assert application.outcome == ApplicationOutcome.ADMITTED


@pytest.mark.django_db
def test_promote_deactivates_student_card(graduate):
    promote(graduate)
    graduate.refresh_from_db()
    assert graduate.is_active is False


@pytest.mark.django_db
def test_promote_is_idempotent(graduate):
    promote(graduate)
    promote(graduate)
    assert Alumnus.objects.count() == 1


@pytest.mark.django_db
def test_automatic_promotion_by_graduation_date(graduate):
    """Автоперевод по дате выпуска."""
    before = promote_due(today=date(2026, 5, 1))
    assert before["promoted"] == 0

    after = promote_due(today=date(2026, 6, 1))
    assert after["promoted"] == 1
    assert Alumnus.objects.filter(student=graduate).exists()


@pytest.mark.django_db
def test_identity_offer_two_months_before_graduation(graduate, make_user):
    """За два месяца до выпуска предлагаем привязать личную почту."""
    user = make_user("student", graduate.email)
    graduate.user = user
    graduate.save(update_fields=["user"])

    assert needs_identity_offer(graduate, today=date(2026, 3, 1)) is False
    assert needs_identity_offer(graduate, today=date(2026, 4, 10)) is True

    # почта уже привязана — предлагать нечего
    Identity.objects.create(user=user, provider=IdentityProvider.EMAIL_LINK, email="personal@gmail.com")
    assert needs_identity_offer(graduate, today=date(2026, 5, 20)) is False


# --- Менторство: запрос проходит через сотрудника ---


@pytest.fixture
def mentor(db, group, toronto):
    student = make("Сериков", "Дамир", "damir@school.kz", group, year=2024)
    alumnus = promote(student)
    alumnus.mentorship_consent = True
    alumnus.university = toronto.university
    alumnus.country = "Канада"
    alumnus.save()
    return alumnus


@pytest.fixture
def applicant(db, group, make_user):
    student = make("Тлеубаева", "Жанна", "zhanna@school.kz", group)
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return student


@pytest.mark.django_db
def test_request_is_invisible_until_school_approves(applicant, mentor):
    """Критерий приёмки: запрос доходит до выпускника только после одобрения."""
    created = request_mentorship(student=applicant, alumnus=mentor, topic="Как поступить на CS")

    assert created.status == MentorshipStatus.REQUESTED
    assert created.is_visible_to_alumnus is False

    from alumni.services import visible_to_alumnus

    assert visible_to_alumnus(mentor).count() == 0


@pytest.mark.django_db
def test_approval_makes_request_visible(applicant, mentor, asem):
    from alumni.services import approve, visible_to_alumnus

    created = request_mentorship(student=applicant, alumnus=mentor, topic="Как поступить")
    approved = approve(created, reviewer=asem, note="Хороший вопрос")

    assert approved.status == MentorshipStatus.SENT
    assert approved.is_visible_to_alumnus is True
    assert approved.reviewed_by == asem
    assert visible_to_alumnus(mentor).count() == 1


@pytest.mark.django_db
def test_declined_request_never_reaches_alumnus(applicant, mentor, asem):
    from alumni.services import decline, visible_to_alumnus

    created = request_mentorship(student=applicant, alumnus=mentor, topic="Тема")
    declined = decline(created, reviewer=asem, note="Ученик ещё не готов")

    assert declined.status == MentorshipStatus.DECLINED
    assert declined.is_visible_to_alumnus is False
    assert visible_to_alumnus(mentor).count() == 0


@pytest.mark.django_db
def test_cannot_request_mentor_without_consent(applicant, mentor):
    mentor.mentorship_consent = False
    mentor.save(update_fields=["mentorship_consent"])
    with pytest.raises(MentorshipDenied):
        request_mentorship(student=applicant, alumnus=mentor, topic="Тема")


@pytest.mark.django_db
def test_full_mentorship_flow_through_api(api, applicant, mentor, asem):
    """Тот же путь через HTTP: ученик просит, школа одобряет, выпускник видит."""
    api.force_authenticate(applicant.user)
    created = api.post(
        "/api/mentorship/request/",
        {"alumnus": mentor.pk, "topic": "Как поступить на CS", "message": "Хочу в Торонто"},
        format="json",
    )
    assert created.status_code == 201
    request_id = created.data["id"]
    assert created.data["is_visible_to_alumnus"] is False

    # ученик не может одобрить сам себя
    assert api.post(f"/api/mentorship/{request_id}/approve/", {}, format="json").status_code == 403

    api.force_authenticate(asem)
    approved = api.post(f"/api/mentorship/{request_id}/approve/", {"note": "ок"}, format="json")
    assert approved.status_code == 200
    assert approved.data["is_visible_to_alumnus"] is True
    assert approved.data["status"] == "sent"


@pytest.mark.django_db
def test_alumnus_sees_only_approved_requests(api, applicant, mentor, asem, make_user):
    """Выпускник заходит и видит только то, что школа пропустила."""
    hidden = request_mentorship(student=applicant, alumnus=mentor, topic="Скрытый")
    shown = request_mentorship(student=applicant, alumnus=mentor, topic="Одобренный")
    from alumni.services import approve

    approve(shown, reviewer=asem)

    mentor_user = make_user("student", mentor.student.email)
    mentor.student.user = mentor_user
    mentor.student.save(update_fields=["user"])

    api.force_authenticate(mentor_user)
    topics = {row["topic"] for row in api.get("/api/mentorship/").data["results"]}
    assert "Одобренный" in topics
    assert "Скрытый" not in topics
    assert hidden.is_visible_to_alumnus is False


# --- Каталог ---


@pytest.mark.django_db
def test_catalogue_filters(api, mentor, asem, group, toronto):
    other_student = make("Калиев", "Арсен", "arsen@school.kz", group, year=2023)
    other = promote(other_student)
    other.country = "США"
    other.save()

    api.force_authenticate(asem)
    canada = api.get("/api/alumni/?country=Канада").data["results"]
    assert {row["full_name"] for row in canada} == {"Сериков Дамир"}

    mentors = api.get("/api/alumni/?mentors_only=true").data["results"]
    assert len(mentors) == 1


@pytest.mark.django_db
def test_student_cannot_edit_catalogue(api, applicant, mentor):
    api.force_authenticate(applicant.user)
    assert api.patch(f"/api/alumni/{mentor.pk}/", {"country": "Марс"}, format="json").status_code == 403


# --- Архив эссе ---


@pytest.mark.django_db
def test_archive_shows_only_consented_essays(api, applicant, mentor, toronto, asem):
    consented = ArchivedEssay.objects.create(
        alumnus=mentor,
        program=toronto,
        essay_type="personal_statement",
        title="Как я выбрал CS",
        text="Текст эссе",
        consent_given=True,
    )
    ArchivedEssay.objects.create(
        alumnus=mentor,
        program=toronto,
        essay_type="supplemental",
        title="Без согласия",
        text="Секрет",
        consent_given=False,
    )

    api.force_authenticate(applicant.user)
    titles = {row["title"] for row in api.get("/api/archived-essays/").data["results"]}
    assert titles == {"Как я выбрал CS"}

    # сотрудник видит всё
    api.force_authenticate(asem)
    assert len(api.get("/api/archived-essays/").data["results"]) == 2

    # у эссе указано, куда человек поступил
    api.force_authenticate(applicant.user)
    row = api.get(f"/api/archived-essays/{consented.pk}/").data
    assert row["university_name"] == "University of Toronto"
    assert row["author_label"] == "Сериков Дамир, выпуск 2024"


@pytest.mark.django_db
def test_anonymous_archive_hides_the_name(mentor, toronto):
    essay = ArchivedEssay.objects.create(
        alumnus=mentor,
        program=toronto,
        essay_type="personal_statement",
        title="Аноним",
        text="Текст",
        consent_given=True,
        is_anonymous=True,
    )
    assert essay.author_label == "Выпуск 2024"
    assert "Сериков" not in essay.author_label
