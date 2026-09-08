"""Фаза 59 — ЕНТ убран насовсем: в архив, не удалён.

Справочник экзаменов — единственный справочник с архивом: экзамен тянет
за собой цели и баллы. Архивная запись не появляется ни в одном списке
выбора, ни в API, ни в импорте, и включить её галочкой обратно нельзя.
Миграция данных обратима: `reverse` поднимает из архива ровно то,
что она туда положила.
"""

from __future__ import annotations

import datetime as dt
import importlib
from decimal import Decimal

import pytest
from django.apps import apps
from rest_framework.test import APIClient

from accounts.models import Role
from directories.models import ExamKind
from prep.imports import import_questions
from prep.models import MockExam, Question, TheoryLesson
from students.models import ExamAttempt, ExamGoal

pytestmark = pytest.mark.django_db

DATA_MIGRATION = "directories.migrations.0005_phase59_ent_to_archive"


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user(Role.STUDENT, student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


def archived_ent() -> ExamKind:
    kind = ExamKind.all_objects.get(name="ЕНТ")
    assert kind.is_archived, "ЕНТ должен лежать в архиве после миграции фазы 59"
    return kind


def test_ent_is_archived_not_deleted():
    """Строка цела, но обычный менеджер её не видит (инвариант №13)."""
    assert ExamKind.all_objects.filter(name="ЕНТ").exists()
    assert not ExamKind.objects.filter(name="ЕНТ").exists()
    assert set(ExamKind.objects.values_list("name", flat=True)) == {"IELTS", "TOEFL", "SAT", "ACT", "Duolingo", "HSK"}


def test_archived_exam_is_absent_from_every_list(api, make_user, student_user):
    """Ни владелец справочника, ни ученик, ни реестр, ни подготовка, ни квиз."""
    archived_ent()
    kymbat = make_user(Role.DIRECTOR_EXAM, "kymbat@school.kz")

    api.force_authenticate(kymbat)
    names = {row["name"] for row in api.get("/api/exam-kinds/?page_size=100").data["results"]}
    assert "ЕНТ" not in names and "TOEFL" in names, "владелец видит скрытые, но не архивные"
    assert api.get(f"/api/exam-kinds/{archived_ent().pk}/").status_code == 404

    api.force_authenticate(student_user)
    names = {row["name"] for row in api.get("/api/exam-kinds/").data["results"]}
    assert names == {"SAT", "IELTS"}

    meta = api.get("/api/meta/domains/").data
    choices = {
        choice["title"]
        for domain in meta["domains"]
        for model in domain["models"]
        if model["label"] == "students.ExamGoal"
        for field in model["fields"]
        if field["name"] == "exam"
        for choice in field["choices"]
    }
    assert "ЕНТ" not in choices

    tiles = {row["exam_type"] for row in api.get("/api/prep/center/exams/").data["exams"]}
    assert "ENT" not in tiles
    quiz = {row["code"] for row in api.get("/api/prep/quiz/").data["exams"]}
    assert "ENT" not in quiz


def test_archived_exam_cannot_be_switched_back_on(api, make_user):
    """Галочка «Показывать в списке выбора» до архивной записи не дотягивается."""
    kind = archived_ent()
    api.force_authenticate(make_user(Role.DIRECTOR_EXAM, "kymbat@school.kz"))
    assert api.post(f"/api/exam-kinds/{kind.pk}/show/").status_code == 404
    assert api.patch(f"/api/exam-kinds/{kind.pk}/", {"is_active": True}, format="json").status_code == 404
    kind.refresh_from_db()
    assert kind.is_archived


def test_import_rejects_ent_rows_with_a_readable_reason():
    """Файл банка с ЕНТ не падает целиком: строка отклоняется, причина названа."""
    csv = "exam_type,section,topic,question_type,text,A,B,correct\nЕНТ,math,Алгебра,single,2+2?,3,4,B\n"
    result = import_questions(csv, dry_run=True)
    assert result.created == 0
    assert len(result.skipped) == 1
    assert "неизвестный экзамен" in result.skipped[0]["reason"] and "ЕНТ" in result.skipped[0]["reason"]


def test_bulk_attempts_reject_ent(api, make_user, student):
    """Массовый ввод результатов тоже не знает такого экзамена."""
    api.force_authenticate(make_user(Role.DIRECTOR_EXAM, "kymbat@school.kz"))
    response = api.post(
        "/api/attempts/bulk/",
        {"rows": [{"student": student.pk, "exam_type": "ENT", "date": "2026-09-01", "total_score": "100"}]},
        format="json",
    )
    assert response.status_code in (200, 400)
    body = response.data
    assert ExamAttempt.all_objects.filter(student=student, exam_type="ENT").count() == 0
    rejected = body.get("rejected") if isinstance(body, dict) else None
    if rejected is not None:
        assert rejected and "экзамен" in rejected[0]["reason"]


def _forward_and_back():
    module = importlib.import_module(DATA_MIGRATION)
    return module.archive_ent, module.restore_ent


def test_data_migration_is_reversible_on_data_with_ent(student):
    """Вперёд — всё с ЕНТ уходит в архив или гаснет; назад — возвращается как было."""
    archive_ent, restore_ent = _forward_and_back()
    # исходное состояние после миграции: ЕНТ в архиве. Возвращаем и заводим данные
    restore_ent(apps, None)
    ent = ExamKind.objects.get(name="ЕНТ")
    goal = ExamGoal.objects.create(student=student, exam=ent, target_score=Decimal("110"))
    attempt = ExamAttempt.objects.create(
        student=student, exam_type="ENT", date=dt.date(2026, 5, 1), total_score=Decimal("105")
    )
    question = Question.objects.create(exam_type="ENT", section="math", topic="Алгебра", text="2+2?")
    lesson = TheoryLesson.objects.create(exam_type="ENT", section="math", title="Дроби", level="basic")
    mock = MockExam.objects.create(exam_type="ENT", title="Пробный ЕНТ")

    archive_ent(apps, None)
    for row in (ent, goal, attempt):
        row.refresh_from_db()
        assert row.is_archived, f"{row} должен быть в архиве"
    assert ent.archive_batch == goal.archive_batch == attempt.archive_batch
    for row in (question, lesson, mock):
        row.refresh_from_db()
        assert row.is_active is False
    assert not ExamKind.objects.filter(name="ЕНТ").exists()

    restore_ent(apps, None)
    for row in (ent, goal, attempt):
        row.refresh_from_db()
        assert not row.is_archived and row.archive_batch is None
    for row in (question, lesson, mock):
        row.refresh_from_db()
        assert row.is_active is True

    # и снова вперёд — как оставит базу сама миграция
    archive_ent(apps, None)
    assert ExamKind.all_objects.get(name="ЕНТ").is_archived


def test_migration_does_not_touch_other_exams(student):
    """IELTS-цель и попытка живут своей жизнью: миграция их не задевает."""
    archive_ent, _ = _forward_and_back()
    ielts = ExamKind.objects.get(name="IELTS")
    goal = ExamGoal.objects.create(student=student, exam=ielts, target_score=Decimal("7.0"))
    attempt = ExamAttempt.objects.create(
        student=student, exam_type="IELTS", date=dt.date(2026, 5, 1), total_score=Decimal("6.5")
    )
    archive_ent(apps, None)
    goal.refresh_from_db()
    attempt.refresh_from_db()
    assert not goal.is_archived and not attempt.is_archived
