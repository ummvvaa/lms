"""Импорт через интерфейс: предпросмотр, чужой домен, применение."""

from __future__ import annotations

import io

import pytest
from rest_framework.test import APIClient

from core.domains import Source
from core.models import AuditLog


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def kymbat(make_user):
    return make_user("director_exam", "kymbat@school.kz", full_name="Кымбат")


def csv_file(text: str, name: str = "moks.csv"):
    buffer = io.BytesIO(text.encode("utf-8"))
    buffer.name = name
    return buffer


@pytest.mark.django_db
def test_preview_matches_students_and_shows_changes(api, kymbat, student):
    api.force_authenticate(kymbat)
    mapping = '{"email": "student", "ielts": "students.ExamProfile.ielts_current"}'
    response = api.post(
        "/api/import/preview/",
        {"file": csv_file(f"email,ielts\n{student.email},6.5\nchuzhoy@nowhere.kz,7.0\n"), "mapping": mapping},
        format="multipart",
    )
    body = response.data
    assert body["matched"] == 1
    assert len(body["unmatched"]) == 1
    assert body["rows"][0]["changes"][0]["new"] == "6.5"
    # предпросмотр ничего не меняет
    student.exam.refresh_from_db()
    assert student.exam.ielts_current is None


@pytest.mark.django_db
def test_foreign_domain_column_is_refused(api, kymbat, student):
    """Директор экзаменов не может импортировать поле поступления."""
    api.force_authenticate(kymbat)
    mapping = '{"email": "student", "st": "students.AdmissionProfile.status"}'
    response = api.post(
        "/api/import/preview/",
        {"file": csv_file(f"email,st\n{student.email},A\n"), "mapping": mapping},
        format="multipart",
    )
    assert response.data["errors"]
    assert all(row["changes"] == [] for row in response.data["rows"])


@pytest.mark.django_db
def test_apply_writes_values_and_audit(api, kymbat, student):
    api.force_authenticate(kymbat)
    mapping = '{"email": "student", "ielts": "students.ExamProfile.ielts_current"}'
    preview = api.post(
        "/api/import/preview/",
        {"file": csv_file(f"email,ielts\n{student.email},7.5\n"), "mapping": mapping},
        format="multipart",
    ).data

    applied = api.post("/api/import/apply/", {"rows": preview["rows"]}, format="json").data
    assert applied["applied"] == 1

    student.exam.refresh_from_db()
    assert str(student.exam.ielts_current) == "7.5"
    log = AuditLog.objects.get(field_name="ielts_current")
    assert log.source == Source.IMPORT
    assert log.actor == kymbat


@pytest.mark.django_db
def test_student_cannot_import(api, make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    api.force_authenticate(user)
    response = api.post("/api/import/preview/", {"file": csv_file("email\nx@y.kz\n")}, format="multipart")
    assert response.status_code == 403
