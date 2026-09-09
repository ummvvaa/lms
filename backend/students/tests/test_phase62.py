"""Фаза 62: документы с проверкой, заметки, передача владельцу, уведомления, D37.

Документ идёт по той же очереди, что баллы: те же 409 и 400, тот же замок.
Заметка — то, чего ученик не видит никогда: страж обходит все ученические
ответы и ищет её текст. Передача — владельцу домена строки, а не всегда
Кымбат: документ уходит Асем.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.curators import assign
from accounts.models import User
from core.models import AuditLog, Notification
from students import attention, documents
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    CuratorNote,
    DocumentStatus,
    ExamProfile,
    SportProfile,
    Student,
    StudentDocument,
    StudyGroup,
    TalentProfile,
)
from suggestions.models import Suggestion, SuggestionSource

PDF = b"%PDF-1.4\n%test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
TODAY = timezone.localdate()
CURATOR_NAME = "Асель Ермекова"
SECRET_NOTE = "Родители разводятся, ребёнок переживает — не давить"


def days(n: int) -> dt.date:
    return TODAY + dt.timedelta(days=n)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def chicago(db) -> StudyGroup:
    return StudyGroup.objects.create(code="CHICAGO", grade=11)


@pytest.fixture
def boston(db) -> StudyGroup:
    return StudyGroup.objects.create(code="BOSTON", grade=11)


def make_student(group: StudyGroup, last_name: str, email: str, make_user) -> tuple[Student, User]:
    student = Student.objects.create(
        last_name=last_name, first_name="Ученик", email=email, grade=11, group=group, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=student)
    user = make_user("student", email, full_name=f"{last_name} Ученик")
    student.user = user
    student.save(update_fields=["user"])
    return student, user


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin", "admin62@example.kz", full_name="Администратор")


@pytest.fixture
def curator(make_user, chicago, admin) -> User:
    user = make_user("curator", "curator62@example.kz", full_name=CURATOR_NAME)
    assign(group=chicago, curator=user, since=days(-30), actor=admin)
    return user


@pytest.fixture
def asem(make_user) -> User:
    return make_user("director_admission", "asem62@example.kz", full_name="Асем")


@pytest.fixture
def kymbat(make_user) -> User:
    return make_user("director_exam", "kymbat62@example.kz", full_name="Кымбат")


@pytest.fixture
def saltanat(make_user) -> User:
    return make_user("director_behavior", "saltanat62@example.kz", full_name="Салтанат")


@pytest.fixture
def mine(chicago, make_user):
    return make_student(chicago, "Свой", "mine62@example.kz", make_user)


@pytest.fixture
def foreign(boston, make_user):
    return make_student(boston, "Чужой", "foreign62@example.kz", make_user)


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def upload(user, doc_type="passport", **extra) -> StudentDocument:
    client = login(user)
    payload = {"doc_type": doc_type, "file": SimpleUploadedFile("scan.pdf", PDF, "application/pdf"), **extra}
    response = client.post("/api/documents/", payload, format="multipart")
    assert response.status_code == 201, response.content
    return StudentDocument.objects.get(pk=response.json()["id"])


def queue_row(document: StudentDocument) -> Suggestion:
    return documents.open_suggestion(document)


# --- Документ: статусы и переходы ----------------------------------------------------


@pytest.mark.django_db
def test_upload_makes_a_pending_document_and_a_queue_row(mine):
    student, user = mine
    doc = upload(user, expires_at=str(days(400)))
    assert doc.status == DocumentStatus.PENDING
    row = queue_row(doc)
    assert row is not None and row.domain_code == "documents" and row.source_type == SuggestionSource.DOCUMENT
    change = row.changes.get()
    assert change.model_label == "students.StudentDocument" and change.field_name == "status"
    # файл «прочее» при достижении проверяется строкой самого достижения — очереди документов не получает
    other = upload(user, doc_type="other")
    assert queue_row(other) is None


@pytest.mark.django_db
def test_expiry_only_for_passport_and_certificates(mine):
    _student, user = mine
    client = login(user)
    bad = client.post(
        "/api/documents/",
        {
            "doc_type": "transcript",
            "expires_at": str(days(30)),
            "file": SimpleUploadedFile("t.pdf", PDF, "application/pdf"),
        },
        format="multipart",
    )
    assert bad.status_code == 400 and "expires_at" in bad.json()
    past = client.post(
        "/api/documents/",
        {
            "doc_type": "passport",
            "expires_at": str(days(-1)),
            "file": SimpleUploadedFile("p.pdf", PDF, "application/pdf"),
        },
        format="multipart",
    )
    assert past.status_code == 400
    listing = client.get("/api/documents/").json()
    assert listing["count"] == 0


@pytest.mark.django_db
def test_curator_confirms_and_rejects_with_reason_same_code_as_scores(mine, curator):
    student, user = mine
    doc = upload(user)
    row = queue_row(doc)
    client = login(curator)

    # без причины — 400, как у баллов
    assert client.post(f"/api/suggestions/{row.pk}/review/", {"decision": "decline"}, format="json").status_code == 400

    done = client.post(f"/api/suggestions/{row.pk}/review/", {"decision": "confirm"}, format="json")
    assert done.status_code == 200
    doc.refresh_from_db()
    assert doc.status == DocumentStatus.CONFIRMED and doc.reviewed_by == curator
    entry = AuditLog.objects.get(model_label="students.StudentDocument", object_id=str(doc.pk), field_name="status")
    assert entry.actor == curator and entry.actor_role == "curator" and entry.student_group == "CHICAGO"

    # второе решение — 409 с тем, кем и когда
    again = login(curator).post(
        f"/api/suggestions/{row.pk}/review/", {"decision": "decline", "reason": "нет"}, format="json"
    )
    assert again.status_code == 409

    second = upload(user, doc_type="transcript")
    declined = client.post(
        f"/api/suggestions/{queue_row(second).pk}/review/",
        {"decision": "decline", "reason": "Скан нечёткий"},
        format="json",
    )
    assert declined.status_code == 200
    second.refresh_from_db()
    assert second.status == DocumentStatus.REJECTED and second.reject_reason == "Скан нечёткий"


@pytest.mark.django_db
def test_asem_sees_the_documents_queue_and_decides(mine, asem, curator):
    student, user = mine
    doc = upload(user)
    client = login(asem)
    queue = client.get("/api/suggestions/from-students/").json()
    ids = [row["id"] for row in queue["results"]]
    assert queue_row(doc).pk in ids
    row = next(r for r in queue["results"] if r["id"] == queue_row(doc).pk)
    assert row["domain"] == "documents" and row["document"]["doc_type"] == "passport"
    assert row["document"]["file_url"].endswith(f"/api/documents/{doc.pk}/file/")

    assert (
        client.post(f"/api/suggestions/{queue_row(doc).pk}/review/", {"decision": "confirm"}, format="json").status_code
        == 200
    )
    # решение владельца — уведомление куратору группы
    note = Notification.objects.get(recipient=curator, kind=Notification.Kind.QUEUE_DECIDED)
    assert "Паспорт" in note.text and note.link == f"/students/{student.pk}"


@pytest.mark.django_db
def test_kymbat_does_not_get_the_documents_queue(mine, kymbat):
    _student, user = mine
    doc = upload(user)
    ids = [row["id"] for row in login(kymbat).get("/api/suggestions/from-students/").json()["results"]]
    assert queue_row(doc).pk not in ids
    assert login(kymbat).get(f"/api/suggestions/{queue_row(doc).pk}/").status_code == 404


@pytest.mark.django_db
def test_student_sees_status_and_reason_but_not_the_reviewer(mine, curator):
    student, user = mine
    doc = upload(user)
    login(curator).post(
        f"/api/suggestions/{queue_row(doc).pk}/review/",
        {"decision": "decline", "reason": "Не тот документ"},
        format="json",
    )
    client = login(user)
    rows = client.get("/api/documents/").json()["results"]
    assert rows[0]["status"] == "rejected" and rows[0]["reject_reason"] == "Не тот документ"
    checklist = client.get("/api/portfolio/").json()["documents"]
    passport = next(row for row in checklist if row["code"] == "passport")
    assert passport["done"] is False and passport["reject_reason"] == "Не тот документ"
    for path in ("/api/documents/", "/api/portfolio/", "/api/students/me/", "/api/suggestions/mine/"):
        body = client.get(path).content.decode()
        assert CURATOR_NAME not in body and "reviewed_by" not in body, path


@pytest.mark.django_db
def test_reupload_after_rejection_keeps_history_and_notifies_the_curator(mine, curator):
    student, user = mine
    first = upload(user)
    login(curator).post(
        f"/api/suggestions/{queue_row(first).pk}/review/", {"decision": "decline", "reason": "нечётко"}, format="json"
    )
    second = upload(user)

    assert StudentDocument.objects.filter(student=student, doc_type="passport").count() == 2
    first.refresh_from_db()
    assert first.status == DocumentStatus.REJECTED
    assert second.status == DocumentStatus.PENDING and queue_row(second) is not None
    assert Notification.objects.filter(recipient=curator, kind=Notification.Kind.DOCUMENT_REUPLOADED).exists()
    # последний документ типа решает состояние типа
    state = documents.state_of(Student.objects.filter(pk=student.pk))[student.pk]
    assert state["cells"]["passport"]["state"] == "pending" and "passport" not in state["missing"]


@pytest.mark.django_db
def test_revoke_returns_the_document_to_the_queue(mine, curator):
    student, user = mine
    doc = upload(user)
    client = login(curator)
    client.post(f"/api/suggestions/{queue_row(doc).pk}/review/", {"decision": "confirm"}, format="json")
    assert queue_row(doc) is None

    revoked = client.post(f"/api/curator/documents/{doc.pk}/revoke/", {}, format="json")
    assert revoked.status_code == 200
    doc.refresh_from_db()
    assert doc.status == DocumentStatus.PENDING and queue_row(doc) is not None
    assert AuditLog.objects.filter(object_id=str(doc.pk), field_name="status", new_value="pending").exists()
    # второй раз снять нечего
    assert client.post(f"/api/curator/documents/{doc.pk}/revoke/", {}, format="json").status_code == 400


@pytest.mark.django_db
def test_expiring_is_computed_from_the_threshold(mine, curator, settings):
    _student, user = mine
    soon = upload(user, expires_at=str(days(settings.CURATOR_RULES["DOCUMENT_EXPIRING_DAYS"] - 5)))
    far = upload(user, doc_type="exam_certificate", expires_at=str(days(400)))
    client = login(curator)
    for doc in (soon, far):
        client.post(f"/api/suggestions/{queue_row(doc).pk}/review/", {"decision": "confirm"}, format="json")
    soon.refresh_from_db()
    far.refresh_from_db()
    assert soon.state == "expiring" and far.state == "confirmed"


@pytest.mark.django_db
def test_curator_of_another_group_gets_404_on_the_file(foreign, curator):
    _student, user = foreign
    doc = upload(user)
    client = login(curator)
    assert client.get(f"/api/documents/{doc.pk}/file/").status_code == 404
    assert client.get(f"/api/documents/?student={doc.student_id}").json()["count"] == 0
    assert client.post(f"/api/curator/documents/{doc.pk}/revoke/", {}, format="json").status_code == 404
    assert client.get(f"/api/suggestions/{queue_row(doc).pk}/").status_code == 404


@pytest.mark.django_db
def test_curator_does_not_delete_documents(mine, curator):
    _student, user = mine
    doc = upload(user)
    assert login(curator).delete(f"/api/documents/{doc.pk}/").status_code == 403
    assert StudentDocument.objects.filter(pk=doc.pk).exists()


# --- Матрица, числа, корзина ---------------------------------------------------------------


@pytest.mark.django_db
def test_matrix_numbers_table_and_bucket_agree(mine, curator, chicago, make_user):
    student, user = mine
    other, other_user = make_student(chicago, "Полный", "full62@example.kz", make_user)
    client = login(curator)
    # у второго — полный набор, подтверждённый
    for code in ("attestat", "transcript", "exam_certificate", "recommendation", "passport"):
        doc = upload(
            other_user,
            doc_type=code,
            **({"expires_at": str(days(300))} if code in ("passport", "exam_certificate") else {}),
        )
        client.post(f"/api/suggestions/{queue_row(doc).pk}/review/", {"decision": "confirm"}, format="json")
    upload(user)  # у первого — один паспорт, ждёт

    matrix = client.get("/api/curator/documents/").json()
    by_id = {row["id"]: row for row in matrix["results"]}
    assert by_id[other.pk]["collected"] == 5 and by_id[student.pk]["collected"] == 0
    passport = next(c for c in matrix["counts"] if c["code"] == "passport")
    assert passport["collected"] == 1 and passport["total"] == 2
    assert matrix["missing_students"] == 1 and matrix["filters"]["pending"] == 1

    table = client.get("/api/curator/students/").json()
    rows = {row["id"]: row for row in table["results"]}
    assert rows[other.pk]["documents_collected"] == 5 and rows[student.pk]["documents_collected"] == 0
    chips = {row["code"]: row["count"] for row in table["buckets"]}
    assert chips["docs"] == 1
    home = login(curator).get("/api/curator/overview/").json()
    numbers = {row["code"]: row["value"] for row in home["numbers"]}
    assert numbers["docs"] == 1 and numbers["expiring"] == 0
    assert set(numbers) == {"queue", "nogoal", "docs", "expiring"}
    card = client.get(f"/api/curator/students/{student.pk}/").json()
    assert card["documents"]["collected"] == 0 and {b["code"] for b in card["buckets"]} >= {"docs"}
    assert "docs" in attention.buckets_of(student) and "docs" not in attention.buckets_of(other)

    # фильтры экрана
    assert [r["id"] for r in client.get("/api/curator/documents/?f=missing").json()["results"]] == [student.pk]
    assert [r["id"] for r in client.get("/api/curator/documents/?f=pending").json()["results"]] == [student.pk]
    assert client.get("/api/curator/documents/?f=expiring").json()["results"] == []


@pytest.mark.django_db
def test_remind_all_sends_one_task_per_student_with_own_missing_list(mine, curator, chicago, make_user):
    from roadmap.models import Task

    student, user = mine
    other, other_user = make_student(chicago, "Другой", "other62@example.kz", make_user)
    upload(user)  # паспорт ждёт — не «недостающий»
    upload(other_user, doc_type="attestat")
    client = login(curator)
    made = client.post("/api/curator/documents/remind/", {}, format="json")
    assert made.status_code == 200 and made.json()["created"] == 2

    mine_task = Task.objects.get(student=student)
    other_task = Task.objects.get(student=other)
    assert mine_task.title.startswith("Загрузить: ") and "Паспорт" not in mine_task.title
    assert "Аттестат" in mine_task.title and "Транскрипт" in mine_task.title
    assert "Аттестат" not in other_task.title and "Паспорт" in other_task.title
    assert mine_task.due_date == days(7) and mine_task.author_role == "curator"
    assert AuditLog.objects.filter(student_id=student.pk, field_name="document_reminder").exists()


@pytest.mark.django_db
def test_documents_export_is_a_workbook(mine, curator):
    from io import BytesIO

    from openpyxl import load_workbook

    _student, user = mine
    upload(user)
    response = login(curator).get("/api/curator/documents/export/")
    assert response.status_code == 200
    page = load_workbook(BytesIO(response.getvalue())).active
    rows = list(page.values)
    assert rows[0][0] == "Ученик" and rows[0][-1] == "Собрано" and "Паспорт" in rows[0]
    assert rows[1][-1] == "0 / 5"


# --- Заметки --------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_notes_visibility_by_role(mine, foreign, curator, kymbat, saltanat, asem, admin):
    student, user = mine
    client = login(curator)
    made = client.post("/api/notes/", {"student": student.pk, "text": SECRET_NOTE}, format="json")
    assert made.status_code == 201
    note = CuratorNote.objects.get()
    assert note.author == curator and note.author_role == "curator"

    for reader in (kymbat, saltanat):
        rows = login(reader).get(f"/api/notes/?student={student.pk}").json()["results"]
        assert [r["text"] for r in rows] == [SECRET_NOTE], reader.role
    # академический директор читает, но не пишет. Директор школы с фазы 66
    # пишет — это проверяется в `test_phase66`, вместе с уведомлением куратору
    assert login(kymbat).post("/api/notes/", {"student": student.pk, "text": "x"}, format="json").status_code == 403
    for stranger in (asem, admin):
        assert login(stranger).get(f"/api/notes/?student={student.pk}").status_code == 403, stranger.role

    # чужая группа — 404, пустая заметка — 400
    other_student, _ = foreign
    assert client.post("/api/notes/", {"student": other_student.pk, "text": "чужому"}, format="json").status_code == 404
    assert client.post("/api/notes/", {"student": student.pk, "text": "   "}, format="json").status_code == 400

    # в архив, не насовсем
    removed = client.delete(f"/api/notes/{note.pk}/")
    assert removed.status_code == 200
    assert CuratorNote.objects.count() == 0 and CuratorNote.all_objects.count() == 1


@pytest.mark.django_db
def test_notes_never_reach_the_student(mine, curator):
    """Страж: текст заметки не встречается ни в одном ученическом ответе."""
    student, user = mine
    login(curator).post("/api/notes/", {"student": student.pk, "text": SECRET_NOTE}, format="json")
    login(curator).post(
        f"/api/curator/students/{student.pk}/call/", {"text": "мама просила не звонить вечером"}, format="json"
    )
    client = login(user)
    assert client.get("/api/notes/").status_code == 403
    assert client.get(f"/api/notes/?student={student.pk}").status_code == 403
    for path in (
        "/api/students/me/",
        f"/api/students/{student.pk}/",
        "/api/portfolio/",
        "/api/tasks/my/",
        "/api/calendar/",
        "/api/notifications/",
        "/api/suggestions/mine/",
        "/api/journey/",
        "/api/documents/",
        "/api/game/me/",
    ):
        body = client.get(path).content.decode()
        assert SECRET_NOTE not in body and "не звонить" not in body and "Звонок родителям" not in body, path


# --- Звонок родителям --------------------------------------------------------------------------


@pytest.mark.django_db
def test_parent_call_writes_note_and_journal(mine, curator):
    student, _user = mine
    client = login(curator)
    assert (
        client.post(
            f"/api/curator/students/{student.pk}/call/", {"text": "договорились о встрече"}, format="json"
        ).status_code
        == 200
    )
    note = CuratorNote.objects.get()
    assert note.text == "Звонок родителям: договорились о встрече"
    assert AuditLog.objects.filter(student_id=student.pk, field_name="parent_call").count() == 1

    # без текста — только журнал
    client.post(f"/api/curator/students/{student.pk}/call/", {}, format="json")
    assert CuratorNote.objects.count() == 1
    assert AuditLog.objects.filter(student_id=student.pk, field_name="parent_call").count() == 2
    journal = client.get("/api/curator/journal/").json()["results"]
    assert any(row["what"] == "Звонок родителям" for row in journal)


# --- Передача владельцу домена --------------------------------------------------------------------


def propose_score(user, value="7.5") -> Suggestion:
    made = login(user).post(
        "/api/suggestions/propose/",
        {"rows": [{"model": "students.ExamProfile", "field": "ielts_current", "value": value}]},
        format="json",
    )
    assert made.status_code == 201, made.content
    return Suggestion.objects.get(pk=made.json()["suggestions"][0])


@pytest.mark.django_db
def test_escalation_goes_to_the_owner_of_the_rows_domain(mine, curator, kymbat, asem):
    student, user = mine
    score = propose_score(user)
    doc = upload(user)
    client = login(curator)

    # без комментария нельзя
    assert client.post(f"/api/suggestions/{score.pk}/escalate/", {"comment": " "}, format="json").status_code == 400

    assert (
        client.post(
            f"/api/suggestions/{score.pk}/escalate/", {"comment": "балл не сходится с сертификатом"}, format="json"
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/suggestions/{queue_row(doc).pk}/escalate/", {"comment": "паспорт истёк?"}, format="json"
        ).status_code
        == 200
    )

    # у куратора строки ушли в блок «Передано владельцу»
    mine_queue = client.get("/api/suggestions/from-students/").json()
    assert mine_queue["results"] == []
    assert {row["id"] for row in mine_queue["escalated"]} == {score.pk, queue_row(doc).pk}
    # и решать переданное куратор не может, пока не вернул
    assert (
        client.post(f"/api/suggestions/{score.pk}/review/", {"decision": "confirm"}, format="json").status_code == 409
    )

    # балл — Кымбат, документ — Асем, с комментарием и именем куратора
    kymbat_queue = login(kymbat).get("/api/suggestions/from-students/").json()["results"]
    top = kymbat_queue[0]
    assert top["id"] == score.pk and top["escalated"] and top["escalated_by_name"] == CURATOR_NAME
    assert top["escalation_comment"] == "балл не сходится с сертификатом"
    assert queue_row(doc).pk not in {row["id"] for row in kymbat_queue}
    asem_queue = login(asem).get("/api/suggestions/from-students/").json()["results"]
    assert asem_queue[0]["id"] == queue_row(doc).pk and asem_queue[0]["escalated"]

    assert Notification.objects.filter(recipient=kymbat, kind=Notification.Kind.ESCALATION_REQUEST).count() == 1
    assert Notification.objects.filter(recipient=asem, kind=Notification.Kind.ESCALATION_REQUEST).count() == 1
    assert AuditLog.objects.filter(student_id=student.pk, field_name="escalation").count() == 2


@pytest.mark.django_db
def test_curator_returns_the_row_until_the_owner_decides(mine, curator, kymbat):
    _student, user = mine
    score = propose_score(user)
    client = login(curator)
    client.post(f"/api/suggestions/{score.pk}/escalate/", {"comment": "смущает"}, format="json")
    assert client.post(f"/api/suggestions/{score.pk}/unescalate/", {}, format="json").status_code == 200
    score.refresh_from_db()
    assert not score.is_escalated
    assert [row["id"] for row in client.get("/api/suggestions/from-students/").json()["results"]] == [score.pk]

    # владелец решил — вернуть уже нельзя, а куратору пришёл ответ
    client.post(f"/api/suggestions/{score.pk}/escalate/", {"comment": "снова"}, format="json")
    assert (
        login(kymbat).post(f"/api/suggestions/{score.pk}/review/", {"decision": "confirm"}, format="json").status_code
        == 200
    )
    assert client.post(f"/api/suggestions/{score.pk}/unescalate/", {}, format="json").status_code == 400
    answer = Notification.objects.get(recipient=curator, kind=Notification.Kind.ESCALATION_ANSWERED)
    assert "ответ на переданное" in answer.text
    assert not Notification.objects.filter(recipient=curator, kind=Notification.Kind.QUEUE_DECIDED).exists()


@pytest.mark.django_db
def test_escalation_from_the_card_without_a_row(mine, curator, kymbat, asem):
    student, _user = mine
    client = login(curator)
    assert (
        client.post(
            f"/api/curator/students/{student.pk}/escalate/", {"domain": "exam", "comment": ""}, format="json"
        ).status_code
        == 400
    )
    sent = client.post(
        f"/api/curator/students/{student.pk}/escalate/",
        {"domain": "documents", "comment": "нужна консультация по паспорту"},
        format="json",
    )
    assert sent.status_code == 200 and sent.json()["sent"] == 1
    note = Notification.objects.get(recipient=asem, kind=Notification.Kind.ESCALATION_REQUEST)
    assert note.link == f"/students/{student.pk}" and CURATOR_NAME in note.text
    assert not Notification.objects.filter(recipient=kymbat).exists()
    assert AuditLog.objects.filter(student_id=student.pk, field_name="escalation").exists()


# --- Уведомления: четыре события ---------------------------------------------------------------------


@pytest.mark.django_db
def test_document_expiry_notice_two_weeks_ahead(mine, curator, settings):
    _student, user = mine
    notice = settings.CURATOR_RULES["DOCUMENT_NOTICE_DAYS"]
    doc = upload(user, expires_at=str(days(notice)))
    other = upload(user, doc_type="exam_certificate", expires_at=str(days(notice + 3)))
    client = login(curator)
    for row in (doc, other):
        client.post(f"/api/suggestions/{queue_row(row).pk}/review/", {"decision": "confirm"}, format="json")

    assert documents.send_expiry_notices(TODAY) == 1
    assert documents.send_expiry_notices(TODAY) == 0, "второй запуск в те же сутки молчит"
    note = Notification.objects.get(recipient=curator, kind=Notification.Kind.DOCUMENT_EXPIRING)
    assert "Паспорт" in note.text and note.link.endswith("tab=documents")


@pytest.mark.django_db
def test_notifications_are_readable_and_lead_somewhere(mine, curator, kymbat):
    student, user = mine
    score = propose_score(user)
    login(kymbat).post(f"/api/suggestions/{score.pk}/review/", {"decision": "confirm"}, format="json")
    client = login(curator)
    panel = client.get("/api/notifications/").json()
    assert panel["unread"] == 1 and panel["rows"][0]["link"] == f"/students/{student.pk}"
    assert client.post("/api/notifications/read/", {}, format="json").status_code == 200
    assert client.get("/api/notifications/").json()["unread"] == 0


# --- Журнал ----------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_journal_is_scoped_by_group_snapshot_and_exports(mine, foreign, curator, kymbat):
    student, user = mine
    other, other_user = foreign
    for person in (user, other_user):
        row = propose_score(person)
        login(kymbat).post(f"/api/suggestions/{row.pk}/review/", {"decision": "confirm"}, format="json")
    client = login(curator)
    journal = client.get("/api/curator/journal/").json()["results"]
    assert journal and all(row["group"] == "CHICAGO" for row in journal)
    assert any(row["who"] == "Кымбат" and row["what"] == "Текущий балл IELTS" for row in journal)
    assert other.full_name not in str(journal)
    assert client.get("/api/curator/journal/export/").status_code == 200


# --- D37 ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_theory_lesson_is_hidden_by_kymbat_only(kymbat, asem, mine):
    from prep.models import TheoryLesson

    lesson = TheoryLesson.objects.create(exam_type="IELTS", title="Урок", is_active=True)
    assert login(asem).delete(f"/api/prep/theory/{lesson.pk}/").status_code == 403
    done = login(kymbat).delete(f"/api/prep/theory/{lesson.pk}/")
    assert done.status_code == 200
    lesson.refresh_from_db()
    assert lesson.is_active is False, "урок скрыт, не удалён"
    _student, user = mine
    ids = [row["id"] for row in login(user).get("/api/prep/theory/?exam_type=IELTS").json()["results"]]
    assert lesson.pk not in ids
