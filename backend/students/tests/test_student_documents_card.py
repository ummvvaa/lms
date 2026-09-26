"""«Мои документы» ученика: одна карточка по типам — что для неё отдаёт сервер.

Карточка собирается из двух ответов: чек-лист типов (`/portfolio/`) и все
файлы ученика (`/documents/`). Здесь проверяется то, на чём она стоит:
перезагрузка после отклонения оставляет прежний файл в списке (история под
строкой), состояние и причина отклонения видны ученику, а имени проверяющего
нет ни в одном из двух ответов.
"""

# ruff: noqa: F811 — фикстуры двух групп импортированы по имени
from __future__ import annotations

import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from students import documents
from students.models import DocumentStatus, StudentDocument
from students.tests.test_admission_import_and_credentials import (  # noqa: F401
    admin,
    asem,
    boston,
    chicago,
    curator,
    klass,
    login,
)

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n%test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def upload(user, doc_type: str = "passport") -> int:
    answer = login(user).post(
        "/api/documents/",
        {"doc_type": doc_type, "file": SimpleUploadedFile("scan.pdf", PDF, "application/pdf")},
        format="multipart",
    )
    assert answer.status_code == 201, answer.content
    return answer.json()["id"]


def test_a_reupload_keeps_the_rejected_file_as_history(klass, curator):
    student = klass[0]
    first = upload(student.user)
    suggestion = documents.open_suggestion(StudentDocument.objects.get(pk=first))
    rejected = login(curator).post(
        f"/api/suggestions/{suggestion.pk}/reject/", {"reason": "Скан нечитаемый"}, format="json"
    )
    assert rejected.status_code == 200, rejected.content
    second = upload(student.user)

    files = login(student.user).get("/api/documents/").data["results"]
    passports = sorted((item for item in files if item["doc_type"] == "passport"), key=lambda item: item["id"])
    assert [item["id"] for item in passports] == [first, second]
    assert (passports[0]["state"], passports[0]["reject_reason"]) == ("rejected", "Скан нечитаемый")
    assert passports[1]["state"] == "pending"

    # строка чек-листа показывает текущий файл, а не отклонённый
    checklist = login(student.user).get("/api/portfolio/").data["documents"]
    passport = next(item for item in checklist if item["code"] == "passport")
    assert passport["state"] == "pending" and passport["document"] == second


def test_the_student_never_sees_who_checked_the_document(klass, curator):
    student = klass[0]
    document_id = upload(student.user)
    document = StudentDocument.objects.get(pk=document_id)
    document.status = DocumentStatus.CONFIRMED
    document.reviewed_by = curator
    document.save(update_fields=["status", "reviewed_by"])

    for path in ("/api/documents/", "/api/portfolio/"):
        body = json.dumps(login(student.user).get(path).data, ensure_ascii=False, default=str)
        assert curator.full_name not in body, path
        assert "reviewed_by" not in body, path
