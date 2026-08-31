"""Фаза 38: портфолио — процент заполнения, документы, CV.

Процент — «сколько ученик о себе рассказал», не Readiness. Документы
лежат вне корня веб-сервера и отдаются только после проверки прав.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from students import portfolio
from students.models import Activity, StudentDocument

PDF = b"%PDF-1.4\n%test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.fixture
def other_student_user(db, group, make_user):
    from students.models import (
        AdmissionProfile,
        BehaviorProfile,
        ExamProfile,
        SportProfile,
        Student,
        TalentProfile,
    )

    s = Student.objects.create(
        last_name="Второй", first_name="Ученик", email="second@example.kz", grade=11, group=group, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=s)
    user = make_user("student", s.email)
    s.user = user
    s.save(update_fields=["user"])
    return user


def upload(api, user, doc_type="attestat", **extra):
    api.force_authenticate(user)
    payload = {"doc_type": doc_type, "file": SimpleUploadedFile("scan.pdf", PDF, "application/pdf"), **extra}
    return api.post("/api/documents/", payload, format="multipart")


# --- Процент заполнения ----------------------------------------------------


@pytest.mark.django_db
def test_percent_grows_with_data_and_is_not_readiness(student):
    from core.readiness import compute as compute_readiness

    empty = portfolio.state(student)["percent"]
    assert empty == 0

    student.admission.target_country = "Канада"
    student.admission.target_major = "CS"
    student.admission.cost_priority = "moderate"
    student.admission.target_level = "bachelor"
    student.admission.target_year = 2027
    student.admission.save()

    filled = portfolio.state(student)["percent"]
    assert filled > empty
    # профиль целиком — ровно его вес: 20 из 100
    assert filled == 20

    # это не Readiness: тот про готовность к подаче и считается иначе
    readiness = compute_readiness(student).as_dict()["score"]
    assert filled != readiness or readiness == 0


@pytest.mark.django_db
def test_pending_proposal_counts_as_told(student, make_user):
    """Значение на проверке — ученик свою часть сделал."""
    from suggestions.engine import create_student_suggestions

    before = portfolio.state(student)["percent"]
    create_student_suggestions(
        author=None,
        student=student,
        rows=[{"model": "students.ExamProfile", "field": "gpa", "value": "3.6"}],
    )
    assert portfolio.state(student)["percent"] > before


@pytest.mark.django_db
def test_next_steps_lead_to_tabs(student):
    steps = portfolio.state(student)["next_steps"]
    assert 1 <= len(steps) <= 4
    assert all(step["tab"] for step in steps)


# --- Документы -------------------------------------------------------------


@pytest.mark.django_db
def test_student_uploads_document_and_checklist_updates(api, student_user, student):
    assert not portfolio.state(student)["documents"][0]["done"]
    response = upload(api, student_user, "attestat", note="Копия")
    assert response.status_code == 201, response.data

    row = StudentDocument.objects.get()
    assert row.student == student
    assert row.content_type == "application/pdf"

    checklist = portfolio.state(student)["documents"]
    assert next(r for r in checklist if r["code"] == "attestat")["done"]


@pytest.mark.django_db
def test_file_is_private(api, student_user, other_student_user, make_user):
    upload(api, student_user)
    row = StudentDocument.objects.get()

    # без входа файла нет
    anonymous = APIClient()
    assert anonymous.get(f"/api/documents/{row.pk}/file/").status_code in (401, 403)

    # хозяин видит
    api.force_authenticate(student_user)
    assert api.get(f"/api/documents/{row.pk}/file/").status_code == 200

    # чужой ученик получает 404, а не 403: по 403 видно, что документ есть
    api.force_authenticate(other_student_user)
    assert api.get(f"/api/documents/{row.pk}/file/").status_code == 404

    # директор читает документы своих учеников
    api.force_authenticate(make_user("director_admission", "asem@school.kz"))
    assert api.get(f"/api/documents/{row.pk}/file/").status_code == 200


@pytest.mark.django_db
def test_student_sees_only_own_documents(api, student_user, other_student_user):
    upload(api, student_user)
    api.force_authenticate(other_student_user)
    listing = api.get("/api/documents/").json()
    rows = listing["results"] if isinstance(listing, dict) else listing
    assert rows == []


@pytest.mark.django_db
def test_only_owner_archives_document(api, student_user, other_student_user):
    upload(api, student_user)
    row = StudentDocument.objects.get()

    api.force_authenticate(other_student_user)
    assert api.delete(f"/api/documents/{row.pk}/").status_code in (403, 404)

    api.force_authenticate(student_user)
    assert api.delete(f"/api/documents/{row.pk}/").status_code == 200
    assert StudentDocument.objects.count() == 0
    assert StudentDocument.all_objects.count() == 1  # мягкое удаление (инвариант №13)


@pytest.mark.django_db
def test_upload_rejects_wrong_file(api, student_user):
    api.force_authenticate(student_user)
    response = api.post(
        "/api/documents/",
        {"doc_type": "passport", "file": SimpleUploadedFile("x.pdf", b"MZ not a pdf", "application/pdf")},
        format="multipart",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_staff_does_not_upload_documents(api, make_user):
    response = upload(api, make_user("director_exam", "k@school.kz"))
    assert response.status_code == 403


# --- Достижения и спорт: куда уходит предложение ---------------------------


@pytest.mark.django_db
def test_achievement_goes_to_talent_and_competition_to_sport(api, student_user):
    api.force_authenticate(student_user)
    api.post(
        "/api/suggestions/propose/",
        {
            "rows": [
                {"model": "students.Activity", "field": "title", "value": "Хакатон", "new_object_key": "a"},
                {"model": "students.Activity", "field": "category", "value": "project", "new_object_key": "a"},
                {"model": "students.Competition", "field": "name", "value": "Кубок города", "new_object_key": "c"},
            ]
        },
        format="json",
    )
    from suggestions.models import Suggestion

    domains = set(Suggestion.objects.values_list("domain_code", flat=True))
    assert domains == {"talent", "sport"}


@pytest.mark.django_db
def test_confirmed_achievement_shows_in_portfolio_section(api, student_user, student, make_user):
    api.force_authenticate(student_user)
    api.post(
        "/api/suggestions/propose/",
        {
            "rows": [
                {"model": "students.Activity", "field": "title", "value": "Хакатон", "new_object_key": "a"},
                {"model": "students.Activity", "field": "category", "value": "project", "new_object_key": "a"},
            ]
        },
        format="json",
    )
    # раздел «Достижения» уже считается заполненным: своё ученик сделал
    assert next(s for s in portfolio.state(student)["sections"] if s["code"] == "achievements")["value"] == 100

    from suggestions.models import Suggestion

    arman = make_user("director_talent", "arman@school.kz")
    api.force_authenticate(arman)
    suggestion = Suggestion.objects.get(domain_code="talent")
    result = api.post(f"/api/suggestions/{suggestion.pk}/review/", {"decision": "confirm"}, format="json")
    assert result.status_code == 200
    assert Activity.objects.filter(student=student, title="Хакатон").exists()


# --- CV --------------------------------------------------------------------


@pytest.mark.django_db
def test_cv_contains_entered_data_and_no_internal_labels(api, student_user, student):
    student.admission.target_major = "Computer Science"
    student.admission.status = "C"
    student.admission.save()
    student.exam.ielts_current = 7.0
    student.exam.save()
    Activity.objects.create(student=student, title="Городской хакатон", category="project", is_confirmed=True)

    api.force_authenticate(student_user)
    response = api.get("/api/portfolio/cv/")
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment")
    html = response.content.decode()
    assert "Computer Science" in html
    assert "Городской хакатон" in html
    assert "7.0" in html
    # внутренних ярлыков в CV нет (инвариант №7)
    assert "критический" not in html.lower()
    assert ">C<" not in html


@pytest.mark.django_db
def test_cv_and_portfolio_are_for_students(api, make_user):
    api.force_authenticate(make_user("director_exam", "k2@school.kz"))
    assert api.get("/api/portfolio/").status_code == 403
    assert api.get("/api/portfolio/cv/").status_code == 403
