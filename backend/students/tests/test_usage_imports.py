"""Применение считается пакетом; сопоставление, предпросмотр и пустой результат — нет."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def tracked(monkeypatch):
    tracker = Mock()
    monkeypatch.setattr("core.usage.track", tracker)
    return tracker


@pytest.fixture
def api(make_user):
    client = APIClient()
    client.force_authenticate(make_user("admin"))
    return client


@pytest.mark.parametrize("kind", ["requirements", "scholarships", "questions"])
def test_file_preview_is_zero_and_actual_bulk_apply_is_one(api, tracked, kind):
    if kind == "requirements":
        path = "/api/requirements/import/"
        content = "university,program,min_ielts\nExample University,One,6\nExample University,Two,6\n"
        mapping = {name: name for name in ("university", "program", "min_ielts")}
    elif kind == "scholarships":
        path = "/api/scholarships-import/"
        content = "name,organizer,amount_min\nFirst,Example Fund,600\nSecond,Example Fund,600\n"
        mapping = {name: name for name in ("name", "organizer", "amount_min")}
    else:
        path = "/api/prep/questions/import/"
        content = (
            "exam_type,section,topic,text,A,B,correct\nIELTS,reading,Topic,One,a,b,A\nIELTS,reading,Topic,Two,a,b,A\n"
        )
        mapping = {}

    def payload(**extra):
        return {"file": SimpleUploadedFile("upload.csv", content.encode()), "mapping": json.dumps(mapping), **extra}

    preview = api.post(path, payload(dry_run="true"), format="multipart")
    assert preview.status_code == 200, preview.data
    tracked.assert_not_called()
    applied = api.post(path, payload(), format="multipart")
    assert applied.status_code == 200 and applied.data["created"] == 2
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == f"import.{kind}.apply"
    if kind != "questions":
        repeated = api.post(path, payload(), format="multipart")
        assert repeated.status_code == 200 and repeated.data["unchanged"] == 2
        assert tracked.call_count == 1


@pytest.mark.parametrize("kind", ["contacts", "competitions"])
def test_row_import_counts_a_whole_batch_once(api, student, tracked, kind):
    if kind == "contacts":
        rows = [{"student": student.pk, "full_name": f"Родитель {number}"} for number in range(2)]
    else:
        rows = [{"student": student.pk, "name": f"Соревнование {number}"} for number in range(2)]
    path = f"/api/{kind}/import/apply/"
    response = api.post(path, {"rows": rows}, format="json")
    assert response.status_code == 200 and response.data["created"] == 2, response.data
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == f"import.{kind}.apply"
    empty = api.post(path, {"rows": []}, format="json")
    assert empty.status_code == 400
    assert tracked.call_count == 1


@pytest.mark.parametrize("changed", [False, True])
def test_wizard_counts_successful_changes_but_not_an_unchanged_record(api, tracked, monkeypatch, changed):
    from students import admission_import

    record = SimpleNamespace(
        students_updated=int(changed), attempts_created=0, documents_created=0, credentials_saved=0
    )
    monkeypatch.setattr(admission_import, "apply", lambda *args, **kwargs: record)
    monkeypatch.setattr(admission_import, "record_payload", lambda row: {"students_updated": row.students_updated})
    response = api.post(
        "/api/admission-imports/apply/",
        {"file": SimpleUploadedFile("upload.csv", b"data")},
        format="multipart",
    )
    assert response.status_code == 201, response.data
    assert tracked.call_count == int(changed)
    if changed:
        assert tracked.call_args.args[1] == "import.wizard.apply"


def test_import_denial_emits_no_event(make_user, tracked):
    api = APIClient()
    api.force_authenticate(make_user("student"))
    response = api.post("/api/contacts/import/apply/", {"rows": []}, format="json")
    assert response.status_code == 403
    tracked.assert_not_called()
