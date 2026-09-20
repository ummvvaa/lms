"""Блок «Поступление»: Асем и администратор правят каждую строку.

До разбора кабинетов карандаш у Асем стоял у шести полей её профиля, а срок
паспорта, GPA, шесть попыток и три ссылки на документы оставались без него:
поля формально живут в других местах. Владелец блока — Асем, и правит она
его целиком; администратор — тоже. Право берётся из реестра доменов
(`ADMISSION_BLOCK_EXTRA`, `keeps_admission_block`), здесь проверяется:

* каждая строка блока пишется Асем и администратором, журнал называет автора;
* попытка блока — строка таблицы поступления: чужие попытки Асем не правит;
* куратор и остальные директора на этих ручках получают отказ, чужой
  куратору ученик — 404, ученик — отказ;
* граница значений: балл по шкале, слотов три, ссылка — целиком.
"""

# ruff: noqa: F811 — фикстуры двух групп импортированы по имени
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from core.domains import ADMISSION_BLOCK_EXTRA, DOMAINS, can_write, domain_of_field, keeps_admission_block
from core.models import AuditLog
from students import admission_block
from students.models import AttemptFormat, AttemptSource, DocumentStatus, ExamAttempt, StudentDocument
from students.tests.test_phase65 import (  # noqa: F401 — фикстуры двух групп и куратора одной из них
    admin,
    asem,
    boston,
    chicago,
    curator,
    klass,
    kymbat,
    login,
    stranger,
)

pytestmark = pytest.mark.django_db


def block_of(user, student) -> dict:
    """Блок так, как его собирает сервер для этого человека (карточка любой роли)."""
    student.refresh_from_db()
    return admission_block.build(user, type(student).objects.get(pk=student.pk))


# --- Реестр -------------------------------------------------------------------------


def test_the_exception_lives_in_the_registry_and_names_foreign_fields_only():
    """Исключение — про чужие поля блока; свои домены Асем в нём не повторяются."""
    for label, names in ADMISSION_BLOCK_EXTRA.items():
        for name in names:
            owner = domain_of_field(label, name)
            assert owner is not None, (label, name)
            assert owner.role != DOMAINS["admission"].role, (label, name)
            assert can_write("director_admission", label, name)
            # остальным директорам исключение ничего не даёт
            assert not can_write("director_sport", label, name)
    assert keeps_admission_block("director_admission") and keeps_admission_block("admin")
    assert not any(keeps_admission_block(role) for role in ("curator", "student", "director_exam"))
    # служебные поля попытки Асем не получила
    assert not can_write("director_admission", "students.ExamAttempt", "attempt_format")
    assert not can_write("director_admission", "students.ExamProfile", "ielts_target")


# --- Каждая строка блока ------------------------------------------------------------


@pytest.mark.parametrize("who", ["asem", "admin"])
def test_every_row_of_the_block_is_written_by_the_keeper(who, request, klass):
    user = request.getfixturevalue(who)
    student = klass[0]
    block = block_of(user, student)
    assert block["may_edit"] and block["may_edit_whole"] and block["may_edit_gpa"] and block["may_edit_credentials"]

    client = login(user)
    profile = {
        "student_phone": "+77015550101",
        "personal_email": "danik@example.kz",
        "common_app_email": "danik.ca@example.kz",
        "drive_folder_url": "https://drive.example.org/f/1",
        "passport_expires_at": "2031-05-01",
    }
    for name, value in profile.items():
        answer = client.patch(f"/api/profiles/admission/{student.pk}/", {name: value}, format="json")
        assert answer.status_code == 200, (name, answer.content)
    assert client.patch(f"/api/profiles/exam/{student.pk}/", {"gpa": "4.7"}, format="json").status_code == 200
    for kind in ("email", "common_app"):
        answer = client.post(
            f"/api/students/{student.pk}/credentials/set/", {"kind": kind, "password": "Pass-2031"}, format="json"
        )
        assert answer.status_code == 200, answer.content
    for exam, score in (("IELTS", "7.5"), ("SAT", "1480")):
        answer = client.post(
            f"/api/students/{student.pk}/admission-block/attempt/", {"exam": exam, "score": score}, format="json"
        )
        assert answer.status_code == 200, answer.content
    for code in ("passport", "transcript", "recommendation"):
        answer = client.post(
            f"/api/students/{student.pk}/admission-block/link/",
            {"code": code, "url": f"https://drive.example.org/{code}"},
            format="json",
        )
        assert answer.status_code == 200, answer.content

    block = block_of(user, student)
    assert block["student_phone"] == "+77015550101"
    assert str(block["passport_expires_at"]) == "2031-05-01"
    assert block["gpa"] == 4.7
    assert all(row["present"] for row in block["credentials"])
    scores = {slot["exam"]: [row["score"] for row in slot["rows"]] for slot in block["attempts"]}
    assert scores == {"IELTS": [7.5], "SAT": [1480.0]}
    assert all(doc["document"] is not None and doc["state"] in ("confirmed", "expiring") for doc in block["documents"])


def test_an_attempt_of_the_block_is_a_table_row_with_the_author_in_the_log(asem, klass):
    student = klass[0]
    made = login(asem).post(
        f"/api/students/{student.pk}/admission-block/attempt/", {"exam": "IELTS", "score": "6.5"}, format="json"
    )
    attempt = ExamAttempt.objects.get(pk=made.data["id"])
    assert (attempt.source, attempt.attempt_format) == (AttemptSource.ADMISSION_IMPORT, AttemptFormat.OFFICIAL)
    assert attempt.date_unknown is True

    # правка того же слота: балл и настоящая дата, флаг «уточняется» снят
    fixed = login(asem).post(
        f"/api/students/{student.pk}/admission-block/attempt/",
        {"id": attempt.pk, "exam": "IELTS", "score": "7.0", "date": "2026-05-16"},
        format="json",
    )
    assert fixed.status_code == 200, fixed.content
    attempt.refresh_from_db()
    assert (attempt.total_score, attempt.date, attempt.date_unknown) == (Decimal("7.0"), dt.date(2026, 5, 16), False)
    assert ExamAttempt.objects.filter(student=student).count() == 1

    entries = AuditLog.objects.filter(model_label="students.ExamAttempt", object_id=str(attempt.pk))
    assert set(entries.values_list("field_name", flat=True)) >= {"total_score", "date"}
    assert {(e.actor_id, e.actor_role, e.source) for e in entries} == {(asem.pk, "director_admission", "manual")}


def test_values_are_checked_and_slots_are_three(asem, klass):
    student = klass[0]
    url = f"/api/students/{student.pk}/admission-block/attempt/"
    client = login(asem)
    for body in (
        {"exam": "IELTS", "score": "9.7"},
        {"exam": "SAT", "score": "1601"},
        {"exam": "TOEFL", "score": "100"},
    ):
        assert client.post(url, body, format="json").status_code == 400, body
    assert client.post(url, {"exam": "IELTS", "score": "7", "date": "16.05.2026"}, format="json").status_code == 400
    for _ in range(admission_block.ATTEMPT_SLOTS):
        assert client.post(url, {"exam": "IELTS", "score": "7"}, format="json").status_code == 200
    full = client.post(url, {"exam": "IELTS", "score": "7"}, format="json")
    assert full.status_code == 400 and "заняты" in full.data["detail"]

    link = f"/api/students/{student.pk}/admission-block/link/"
    assert client.post(link, {"code": "passport", "url": "drive.example.org/x"}, format="json").status_code == 400
    assert client.post(link, {"code": "photo", "url": "https://example.org/x"}, format="json").status_code == 400
    assert not StudentDocument.objects.filter(student=student).exists()


def test_a_second_link_edits_the_same_document(asem, klass):
    student = klass[0]
    link = f"/api/students/{student.pk}/admission-block/link/"
    first = login(asem).post(link, {"code": "transcript", "url": "https://drive.example.org/t1"}, format="json")
    second = login(asem).post(link, {"code": "transcript", "url": "https://drive.example.org/t2"}, format="json")
    assert first.data["document"] == second.data["document"]
    document = StudentDocument.objects.get(pk=first.data["document"])
    assert (document.external_url, document.status) == ("https://drive.example.org/t2", DocumentStatus.CONFIRMED)


def test_asem_does_not_touch_attempts_outside_her_table(asem, kymbat, klass):
    """Попытка, которую ведёт домен экзаменов, Асем закрыта — и ручкой блока, и общей."""
    student = klass[0]
    foreign = ExamAttempt.objects.create(
        student=student,
        exam_type="IELTS",
        attempt_format=AttemptFormat.OFFICIAL,
        source=AttemptSource.MANUAL,
        date=dt.date(2026, 3, 1),
        total_score=Decimal("6.0"),
    )
    by_block = login(asem).post(
        f"/api/students/{student.pk}/admission-block/attempt/",
        {"id": foreign.pk, "exam": "IELTS", "score": "8"},
        format="json",
    )
    assert by_block.status_code == 400
    by_viewset = login(asem).patch(f"/api/attempts/{foreign.pk}/", {"total_score": "8"}, format="json")
    assert by_viewset.status_code == 403
    foreign.refresh_from_db()
    assert foreign.total_score == Decimal("6.0")
    # владелец домена правит её как правил
    assert login(kymbat).patch(f"/api/attempts/{foreign.pk}/", {"total_score": "6.5"}, format="json").status_code == 200


def test_the_rest_get_a_refusal_and_a_stranger_gets_404(curator, kymbat, klass, stranger):
    mine = klass[0]
    body = {"exam": "IELTS", "score": "7"}
    assert block_of(curator, mine)["may_edit_whole"] is False
    assert block_of(kymbat, mine)["may_edit_whole"] is False
    for user in (curator, kymbat, mine.user):
        assert login(user).post(
            f"/api/students/{mine.pk}/admission-block/attempt/", body, format="json"
        ).status_code in (
            403,
            404,
        ), user.role
        answer = login(user).post(
            f"/api/students/{mine.pk}/admission-block/link/",
            {"code": "passport", "url": "https://example.org/p"},
            format="json",
        )
        assert answer.status_code in (403, 404), user.role
    assert login(curator).post(
        f"/api/students/{stranger.pk}/admission-block/attempt/", body, format="json"
    ).status_code in (
        403,
        404,
    )
    assert not ExamAttempt.objects.exists() and not StudentDocument.objects.exists()
