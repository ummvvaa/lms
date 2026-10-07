"""Банк заданий: полный предпросмотр и журнал загрузки без новой отмены."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from core.models import ImportBatch
from prep.models import Question


def upload():
    rows = ["exam_type,section,topic,question_type,text,A,B,correct"]
    rows.extend(f"IELTS,reading,Topic,single,Question {number},a,b,A" for number in range(59))
    rows.extend(["IELTS,reading,Topic,single,No correct,a,b,", "unknown,reading,Topic,single,Bad exam,a,b,A"])
    return SimpleUploadedFile("questions.csv", "\n".join(rows).encode())


@pytest.mark.django_db
def test_full_preview_apply_and_history_keep_exact_counts_and_author(make_user):
    admin = make_user("admin")
    api = APIClient()
    api.force_authenticate(admin)
    preview = api.post("/api/prep/questions/import/", {"file": upload(), "dry_run": "true"}, format="multipart")

    assert preview.status_code == 200
    assert not Question.objects.exists()
    assert not ImportBatch.objects.exists()
    assert len(preview.data["rows"]) == 61
    assert preview.data["created"] == 59
    assert len(preview.data["skipped"]) == 2
    assert [row["status"] for row in preview.data["rows"]] == ["created"] * 59 + ["error"] * 2
    assert [row["reason"] for row in preview.data["rows"][-2:]] == [row["reason"] for row in preview.data["skipped"]]

    applied = api.post("/api/prep/questions/import/", {"file": upload()}, format="multipart")
    assert applied.status_code == 200
    assert applied.data["rows"] == preview.data["rows"]
    batch = ImportBatch.objects.get(pk=applied.data["batch"])
    assert (batch.actor, batch.file_name, batch.kind, batch.domain_code) == (
        admin,
        "questions.csv",
        "questions",
        "exam",
    )
    assert (batch.rows_total, batch.rows_created, batch.rows_updated, batch.rows_failed) == (61, 59, 0, 2)
    assert Question.objects.count() == 59
    history = api.get("/api/imports/", {"kind": "questions"}).data
    assert len(history) == 1
    assert history[0]["kind_title"] == "Банк заданий"
    assert history[0]["actor_name"]
    assert history[0]["can_revert"] is False
    assert api.post(f"/api/imports/{batch.pk}/revert/").status_code == 400
    assert Question.objects.count() == 59
    batch.refresh_from_db()
    assert batch.status == ImportBatch.Status.APPLIED

    api.force_authenticate(make_user("director_exam"))
    assert len(api.get("/api/imports/", {"kind": "questions"}).data) == 1
    assert api.post(f"/api/imports/{batch.pk}/revert/").status_code == 400
    api.force_authenticate(make_user("director_admission"))
    assert api.get("/api/imports/", {"kind": "questions"}).data == []
    assert api.post(f"/api/imports/{batch.pk}/revert/").status_code == 403
