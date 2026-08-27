"""Фаза 35: файлы грузит только администратор, за выбранный домен.

Проверяем инварианты, а не экраны: право на загрузку живёт в реестре
и отбивает директора по прямому запросу; администратор пересекает
границу доменов только за выбранный домен и только в него; каждая такая
правка помечена доменом в журнале; директор видит и отменяет загрузки
по своему домену, чужие ему не показываются.
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import Role
from core.domains import ALL_DIRECTORS, FILE_UPLOADERS, ROLE_ADMIN, can_upload_files, can_write_for
from core.models import AuditLog, ImportBatch
from core.onboarding import build as build_checklist
from students.import_service import apply_preview
from students.serializers import AuditEntrySerializer
from suggestions import commands
from suggestions.engine import apply_suggestion, create_suggestion
from suggestions.models import Suggestion


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, "p35.admin@school.kz", full_name="Мухаммед")


@pytest.fixture
def kymbat(make_user):
    return make_user(Role.DIRECTOR_EXAM, "p35.exam@school.kz", full_name="Кымбат")


@pytest.fixture
def arman(make_user):
    return make_user(Role.DIRECTOR_TALENT, "p35.talent@school.kz", full_name="Арман")


def csv_file(text: str, name: str = "данные.csv"):
    buffer = io.BytesIO(text.encode("utf-8"))
    buffer.name = name
    return buffer


def exam_rows(student, value: str) -> list[dict]:
    return [
        {
            "student": student.pk,
            "changes": [
                {"model": "students.ExamProfile", "field": "ielts_current", "old": "", "new": value, "raw": value}
            ],
        }
    ]


def behavior_rows(student, value: str) -> list[dict]:
    return [
        {
            "student": student.pk,
            "changes": [
                {
                    "model": "students.BehaviorProfile",
                    "field": "attendance_percent",
                    "old": "",
                    "new": value,
                    "raw": value,
                }
            ],
        }
    ]


# --- Право живёт в реестре -------------------------------------------------


def test_registry_names_the_only_file_uploader():
    """Один список в одном месте: кто грузит файлы. Директоров в нём нет."""
    assert FILE_UPLOADERS == (ROLE_ADMIN,)
    assert can_upload_files(ROLE_ADMIN)
    for role in (*ALL_DIRECTORS, "student"):
        assert not can_upload_files(role), role


def test_admin_crosses_the_border_only_for_the_chosen_domain():
    """Администратор пишет за выбранный домен и только в него; директору выбор ничего не даёт."""
    assert can_write_for(ROLE_ADMIN, "exam", "students.ExamProfile", "ielts_current")
    assert not can_write_for(ROLE_ADMIN, "exam", "students.AdmissionProfile", "status")
    assert not can_write_for(ROLE_ADMIN, "", "students.ExamProfile", "ielts_current")
    assert not can_write_for(ROLE_ADMIN, "nonexistent", "students.ExamProfile", "ielts_current")
    # директор — как и раньше: только своё, домен в запросе его не расширяет
    assert can_write_for(Role.DIRECTOR_EXAM, "", "students.ExamProfile", "ielts_current")
    assert can_write_for(Role.DIRECTOR_EXAM, "admission", "students.ExamProfile", "ielts_current")
    assert not can_write_for(Role.DIRECTOR_EXAM, "admission", "students.AdmissionProfile", "status")


#: Все точки, через которые в систему попадает файл с данными.
FILE_ENDPOINTS = [
    ("/api/import/preview/", "multipart"),
    ("/api/import/apply/", "json"),
    ("/api/contacts/import/preview/", "multipart"),
    ("/api/contacts/import/apply/", "json"),
    ("/api/competitions/import/preview/", "multipart"),
    ("/api/competitions/import/apply/", "json"),
    ("/api/requirements/import/", "multipart"),
    ("/api/prep/questions/import/", "multipart"),
    ("/api/commands/upload/", "multipart"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "fmt"), FILE_ENDPOINTS)
def test_every_file_endpoint_refuses_every_director(api, make_user, path, fmt):
    """Убрать пункт из меню мало: директор получает отказ и по прямому запросу."""
    for index, role in enumerate(ALL_DIRECTORS):
        api.force_authenticate(make_user(role, f"p35.{index}.{role}@school.kz"))
        if fmt == "multipart":
            payload = {"file": csv_file("email,ielts\nx@y.kz,6.5\n"), "domain": "exam"}
        else:
            payload = {"rows": [{"student": 1, "changes": []}], "domain": "exam"}
        response = api.post(path, payload, format=fmt)
        assert response.status_code == 403, (path, role, response.data)
        assert "администратор" in str(response.data.get("detail", "")).lower(), (path, role)


@pytest.mark.django_db
def test_admin_must_choose_a_domain_before_uploading(api, admin, student):
    """Без домена загрузки нет: файл ни к чьим полям не привязан."""
    api.force_authenticate(admin)
    preview = api.post("/api/import/preview/", {"file": csv_file(f"email,ielts\n{student.email},6.5\n")}, "multipart")
    assert preview.status_code == 400
    assert "домен" in preview.data["detail"]

    applied = api.post("/api/import/apply/", {"rows": exam_rows(student, "6.5")}, format="json")
    assert applied.status_code == 400


@pytest.mark.django_db
def test_upload_button_is_not_offered_to_directors():
    """Кнопка «Загрузить файл» в помощнике — только у администратора."""
    for role in ALL_DIRECTORS:
        assert "upload_file" not in {c["code"] for c in commands.for_role(role)}, role
        assert "paste_as_is" in {c["code"] for c in commands.for_role(role)}, role
    assert "upload_file" in {c["code"] for c in commands.for_role(ROLE_ADMIN)}


# --- Журнал помечает домен, за который действовал администратор -----------


@pytest.mark.django_db
def test_admin_upload_is_marked_with_the_domain_it_acted_for(student, admin, kymbat):
    """Не «изменил администратор», а «изменил администратор за домен «Экзамены»»."""
    apply_preview(preview_rows=exam_rows(student, "7.0"), domain_code="exam", actor=admin, file_name="баллы.csv")
    entry = AuditLog.objects.get(field_name="ielts_current")
    assert entry.actor == admin
    assert entry.acting_for == "exam"
    assert AuditEntrySerializer(entry).data["acting_for_title"] == "за домен «Экзамены»"

    # правка владельца домена пометки не несёт: она его собственная
    from core.audit import apply_changes

    student.exam.refresh_from_db()
    apply_changes(student.exam, {"ielts_current": Decimal("7.5")}, actor=kymbat)
    own = AuditLog.objects.filter(field_name="ielts_current", actor=kymbat).get()
    assert own.acting_for == ""
    assert AuditEntrySerializer(own).data["acting_for_title"] == ""


@pytest.mark.django_db
def test_upload_for_one_domain_never_touches_another(student, admin):
    """Загрузка за «Экзамены» не примет поле поступления, даже если оно в строках."""
    rows = [
        {
            "student": student.pk,
            "changes": [
                {"model": "students.ExamProfile", "field": "ielts_current", "old": "", "new": "7.0", "raw": "7.0"},
                {"model": "students.AdmissionProfile", "field": "target_country", "old": "", "new": "CA", "raw": "CA"},
            ],
        }
    ]
    result = apply_preview(preview_rows=rows, domain_code="exam", actor=admin, file_name="смесь.csv")
    assert result["applied"] == 1
    student.admission.refresh_from_db()
    assert student.admission.target_country == ""
    assert not AuditLog.objects.filter(field_name="target_country").exists()


# --- История загрузок: директор видит своё и отменяет чужую загрузку ------


@pytest.mark.django_db
def test_director_sees_only_uploads_of_his_domain(api, student, admin, kymbat, arman):
    exam = apply_preview(preview_rows=exam_rows(student, "7.0"), domain_code="exam", actor=admin, file_name="экз.csv")
    apply_preview(preview_rows=behavior_rows(student, "90"), domain_code="behavior", actor=admin, file_name="дисц.csv")

    api.force_authenticate(kymbat)
    mine = api.get("/api/imports/").data
    assert [row["id"] for row in mine] == [exam["batch"]]
    assert mine[0]["domain_title"] == "Экзамены"
    assert mine[0]["actor_role"] == ROLE_ADMIN
    assert mine[0]["on_behalf"] is True

    api.force_authenticate(arman)
    assert api.get("/api/imports/").data == []

    api.force_authenticate(admin)
    assert len(api.get("/api/imports/").data) == 2


@pytest.mark.django_db
def test_director_reverts_the_admins_upload_of_his_domain(api, student, admin, kymbat, arman):
    """Отмена — исправление своих данных: право у директора домена остаётся."""
    result = apply_preview(preview_rows=exam_rows(student, "7.0"), domain_code="exam", actor=admin, file_name="э.csv")
    batch_id = result["batch"]

    api.force_authenticate(arman)
    assert api.post(f"/api/imports/{batch_id}/revert/").status_code == 403

    api.force_authenticate(kymbat)
    response = api.post(f"/api/imports/{batch_id}/revert/")
    assert response.status_code == 200, response.data
    assert response.data["reverted"] == 1
    student.exam.refresh_from_db()
    assert student.exam.ielts_current is None
    assert ImportBatch.objects.get(pk=batch_id).status == ImportBatch.Status.REVERTED


@pytest.mark.django_db
def test_admin_reverts_his_own_upload(api, student, admin):
    result = apply_preview(preview_rows=exam_rows(student, "7.0"), domain_code="exam", actor=admin, file_name="э.csv")
    api.force_authenticate(admin)
    assert api.post(f"/api/imports/{result['batch']}/revert/").status_code == 200
    student.exam.refresh_from_db()
    assert student.exam.ielts_current is None


# --- Вставка текста: у директора свой домен, у администратора — выбранный --


@pytest.mark.django_db
def test_admin_paste_requires_a_domain_and_director_ignores_it(api, student, admin, kymbat):
    text = f"{student.last_name} {student.first_name} — 6.5"

    api.force_authenticate(admin)
    assert api.post("/api/commands/paste/", {"text": text}, format="json").status_code == 400
    accepted = api.post("/api/commands/paste/", {"text": text, "domain": "exam"}, format="json")
    assert accepted.status_code == 202, accepted.data
    suggestion = Suggestion.objects.latest("pk")
    assert suggestion.role == ROLE_ADMIN
    assert suggestion.domain_code == "exam"
    assert suggestion.changes.count() == 1

    # директору домен в запросе ничего не добавляет: предложение остаётся в его домене
    api.force_authenticate(kymbat)
    assert api.post("/api/commands/paste/", {"text": text, "domain": "admission"}, format="json").status_code == 202
    assert Suggestion.objects.latest("pk").domain_code == "exam"


@pytest.mark.django_db
def test_admin_suggestion_applies_only_inside_its_domain_and_is_marked(student, admin):
    """Строка чужого домена отбрасывается при создании; применённая — помечена доменом."""
    suggestion, rejected = create_suggestion(
        author=admin,
        role=ROLE_ADMIN,
        domain_code="exam",
        source_type="paste",
        rows=[
            {"model": "students.ExamProfile", "field": "ielts_current", "student": student.pk, "value": "6.5"},
            {"model": "students.AdmissionProfile", "field": "target_country", "student": student.pk, "value": "CA"},
        ],
    )
    assert len(rejected) == 1
    assert "Поступление" in rejected[0]["reason"]

    result = apply_suggestion(suggestion, actor=admin, change_ids=[c.pk for c in suggestion.changes.all()])
    assert result["applied"] == 1
    student.exam.refresh_from_db()
    assert student.exam.ielts_current == Decimal("6.5")
    entry = AuditLog.objects.get(field_name="ielts_current", suggestion=suggestion)
    assert entry.acting_for == "exam"


# --- «Начало работы» больше не зовёт директора грузить файл ---------------


@pytest.mark.django_db
def test_getting_started_never_sends_directors_to_file_upload(make_user):
    for index, role in enumerate(ALL_DIRECTORS):
        checklist = build_checklist(make_user(role, f"p35.gs.{index}@school.kz"))
        paths = {step.path for step in checklist.steps}
        actions = {step.action for step in checklist.steps}
        assert "/import" not in paths, role
        assert "Загрузить файл" not in actions, role
