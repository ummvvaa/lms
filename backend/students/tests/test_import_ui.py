"""Импорт через интерфейс: предпросмотр, чужой домен, применение.

С фазы 35 файлы грузит администратор, выбрав домен: директор получает
отказ и по прямому запросу, а не только теряет кнопку.
"""

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


@pytest.fixture
def admin(make_user):
    return make_user("admin", "admin.import@school.kz", full_name="Администратор")


def csv_file(text: str, name: str = "moks.csv"):
    buffer = io.BytesIO(text.encode("utf-8"))
    buffer.name = name
    return buffer


@pytest.mark.django_db
def test_preview_matches_students_and_shows_changes(api, admin, student):
    api.force_authenticate(admin)
    mapping = '{"email": "student", "ielts": "students.ExamProfile.ielts_current"}'
    response = api.post(
        "/api/import/preview/",
        {
            "file": csv_file(f"email,ielts\n{student.email},6.5\nchuzhoy@nowhere.kz,7.0\n"),
            "mapping": mapping,
            "domain": "exam",
        },
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
def test_foreign_domain_column_is_refused(api, admin, student):
    """Загрузка за домен «Экзамены» не примет поле поступления."""
    api.force_authenticate(admin)
    mapping = '{"email": "student", "st": "students.AdmissionProfile.status"}'
    response = api.post(
        "/api/import/preview/",
        {"file": csv_file(f"email,st\n{student.email},A\n"), "mapping": mapping, "domain": "exam"},
        format="multipart",
    )
    assert response.data["errors"]
    assert all(row["changes"] == [] for row in response.data["rows"])


@pytest.mark.django_db
def test_apply_writes_values_and_audit(api, admin, student):
    api.force_authenticate(admin)
    mapping = '{"email": "student", "ielts": "students.ExamProfile.ielts_current"}'
    preview = api.post(
        "/api/import/preview/",
        {"file": csv_file(f"email,ielts\n{student.email},7.5\n"), "mapping": mapping, "domain": "exam"},
        format="multipart",
    ).data

    applied = api.post("/api/import/apply/", {"rows": preview["rows"], "domain": "exam"}, format="json").data
    assert applied["applied"] == 1

    student.exam.refresh_from_db()
    assert str(student.exam.ielts_current) == "7.5"
    log = AuditLog.objects.get(field_name="ielts_current")
    assert log.source == Source.IMPORT
    assert log.actor == admin
    # правку внёс администратор за домен «Экзамены» — это видно по записи
    assert log.acting_for == "exam"


@pytest.mark.django_db
def test_director_cannot_upload_a_file(api, kymbat, student):
    """Директор получает отказ по прямому запросу, а не только теряет кнопку."""
    api.force_authenticate(kymbat)
    response = api.post(
        "/api/import/preview/",
        {"file": csv_file(f"email,ielts\n{student.email},6.5\n"), "domain": "exam"},
        format="multipart",
    )
    assert response.status_code == 403
    assert "администратор" in response.data["detail"]


@pytest.mark.django_db
def test_admin_must_choose_a_domain_first(api, admin, student):
    """Без домена загрузки нет: непонятно, чьи данные и что отсекать."""
    api.force_authenticate(admin)
    response = api.post(
        "/api/import/preview/", {"file": csv_file(f"email,ielts\n{student.email},6.5\n")}, format="multipart"
    )
    assert response.status_code == 400
    assert "домен" in response.data["detail"]


@pytest.mark.django_db
def test_student_cannot_import(api, make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    api.force_authenticate(user)
    response = api.post("/api/import/preview/", {"file": csv_file("email\nx@y.kz\n")}, format="multipart")
    assert response.status_code == 403
