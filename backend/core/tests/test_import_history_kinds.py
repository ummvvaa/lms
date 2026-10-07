"""История показывает вид загрузки, весь выбранный период и прежние права."""

from datetime import datetime
from importlib import import_module
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps
from django.db import connection
from rest_framework.test import APIClient

from core.models import AuditLog, ImportBatch
from students.models import AdmissionImport


@pytest.mark.django_db
def test_history_has_no_hidden_row_cap_and_filters_type_and_period(make_user):
    admin = make_user("admin")
    api = APIClient()
    api.force_authenticate(admin)
    batches = ImportBatch.objects.bulk_create(
        [ImportBatch(actor=admin, kind="contacts", domain_code="behavior") for _ in range(205)]
    )
    moment = datetime(2026, 9, 30, 23, 30, tzinfo=ZoneInfo("Asia/Almaty"))
    ImportBatch.objects.filter(pk__in=[batch.pk for batch in batches]).update(created_at=moment)
    ImportBatch.objects.create(actor=admin, kind="competitions", domain_code="sport")

    response = api.get("/api/imports/", {"kind": "contacts", "since": "2026-09-30", "until": "2026-09-30"})
    assert response.status_code == 200
    assert len(response.data) == 205
    assert {row["kind_title"] for row in response.data} == {"Контакты родителей"}
    assert all(row["can_revert"] for row in response.data)
    assert api.get("/api/imports/", {"since": "2026-10-01", "kind": "contacts"}).data == []

    api.force_authenticate(make_user("director_sport"))
    assert {row["kind"] for row in api.get("/api/imports/").data} == {"competitions"}
    assert api.get("/api/imports/", {"kind": "contacts"}).data == []
    api.force_authenticate(make_user("student"))
    assert api.get("/api/imports/").status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("params", [{"since": "yesterday"}, {"until": "2026-13-01"}, {"kind": "unknown"}])
def test_history_rejects_invalid_filters(make_user, params):
    api = APIClient()
    api.force_authenticate(make_user("admin"))
    assert api.get("/api/imports/", params).status_code == 400


@pytest.mark.django_db
def test_wizard_history_includes_older_rows_and_filters_period(make_user):
    admin = make_user("admin")
    api = APIClient()
    api.force_authenticate(admin)
    rows = AdmissionImport.objects.bulk_create([AdmissionImport(uploaded_by=admin) for _ in range(23)])
    moment = datetime(2026, 9, 30, 23, 30, tzinfo=ZoneInfo("Asia/Almaty"))
    AdmissionImport.objects.filter(pk__in=[row.pk for row in rows]).update(created_at=moment)
    AdmissionImport.objects.create(uploaded_by=admin)

    response = api.get("/api/admission-imports/", {"since": "2026-09-30", "until": "2026-09-30"})
    assert response.status_code == 200
    assert len(response.data["rows"]) == 23
    assert {row["kind_title"] for row in response.data["rows"]} == {"Мастер импорта"}
    assert api.get("/api/admission-imports/", {"since": "invalid"}).status_code == 400


@pytest.mark.django_db
def test_legacy_kind_changes_only_when_all_audit_rows_prove_the_upload_type():
    migration = import_module("core.migrations.0022_import_upload_kinds")
    contacts = ImportBatch.objects.create(domain_code="behavior")
    competitions = ImportBatch.objects.create(domain_code="sport")
    mixed = ImportBatch.objects.create(domain_code="behavior")
    unknown = ImportBatch.objects.create(domain_code="behavior")
    for batch, labels in (
        (contacts, ["students.ParentContact"]),
        (competitions, ["students.Competition"]),
        (mixed, ["students.ParentContact", "students.BehaviorProfile"]),
    ):
        for label in labels:
            AuditLog.objects.create(import_batch=batch, model_label=label, object_id="1", field_name="name")

    migration.classify_uploads(apps, SimpleNamespace(connection=connection))

    for batch, kind in (
        (contacts, "contacts"),
        (competitions, "competitions"),
        (mixed, "students"),
        (unknown, "students"),
    ):
        batch.refresh_from_db()
        assert batch.kind == kind
