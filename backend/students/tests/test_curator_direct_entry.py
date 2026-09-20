"""Куратор вносит данные ученика напрямую — по своим группам, без очереди.

Рядом с путём «ученик вносит — куратор подтверждает» стоит второй: куратор
вносит сам, и значение сразу настоящее. Здесь проверяется:

* матрица прав — каждое ученическое поле куратор своей группы пишет, чужой
  ученик отвечает 404, ученик напрямую не пишет, служебные поля домена
  и названные исключения куратору закрыты;
* строки — завести, изменить, убрать в архив; пробник из файла руками
  не правится; документ куратор не удаляет;
* журнал — автор, роль и источник на каждой прямой записи;
* перекрытие — висящее предложение ученика по тому же полю закрывается
  статусом «перекрыто записью куратора», обратный порядок работает как обычно;
* документы, вузы, импорт и подпись «внёс куратор».
"""

# ruff: noqa: F811 — фикстуры двух групп импортированы по имени
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.domains import CURATOR_DOES_NOT_ENTER, PROFILE_MODELS, curator_entry_map
from core.models import AuditLog
from directories.models import ExamKind, SportType
from students import documents
from students.models import (
    Activity,
    AdmissionProfile,
    AttemptFormat,
    Competition,
    DocumentStatus,
    ExamAttempt,
    ExamGoal,
    ExamProfile,
    SportProfile,
    StudentDocument,
)
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
from suggestions.engine import create_student_suggestions
from suggestions.models import Suggestion, SuggestionStatus
from suggestions.student_queue import mine_payload
from universities.models import Program, StudentUniversity, University

pytestmark = pytest.mark.django_db

PROFILE_URL = {
    "students.AdmissionProfile": "admission",
    "students.ExamProfile": "exam",
    "students.SportProfile": "sport",
}

#: значение для проверки записи — по имени поля
SAMPLE = {
    "student_phone": "+77011234567",
    "common_app_email": "danik.commonapp@example.kz",
    "drive_folder_url": "https://drive.example.org/folder/1",
    "personal_email": "danik@example.kz",
    "passport_expires_at": "2031-05-01",
    "ielts_target": "7.5",
    "sat_target": "1500",
    "gpa": "4.5",
    "level": "school",
    "rank": "КМС",
    "leadership_role": "капитан",
}


def png() -> SimpleUploadedFile:
    # минимальный корректный PNG: проверка файла смотрит на содержимое, а не на имя
    data = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
    )
    return SimpleUploadedFile("passport.png", data, content_type="image/png")


@pytest.fixture
def ielts(db) -> ExamKind:
    return ExamKind.objects.get_or_create(name="IELTS")[0]


@pytest.fixture
def program(db) -> Program:
    university = University.objects.create(name="Университет проверки", country="Канада")
    return Program.objects.create(university=university, name="Информатика")


# --- Матрица прав: профили ---------------------------------------------------------


def profile_cases() -> list[tuple[str, str]]:
    return [
        (label, name)
        for label, entry in curator_entry_map().items()
        if label in PROFILE_MODELS
        for name in entry["fields"]
        if name in SAMPLE
    ]


@pytest.mark.parametrize(("label", "name"), profile_cases())
def test_profile_field_matrix(label, name, curator, klass, stranger):
    """Своя группа — пишет сразу и с журналом; чужая — 404; ученик — только очередью."""
    mine = klass[0]
    url = f"/api/profiles/{PROFILE_URL[label]}/{mine.pk}/"
    answer = login(curator).patch(url, {name: SAMPLE[name]}, format="json")
    assert answer.status_code == 200, (label, name, answer.data)

    entry = AuditLog.objects.filter(model_label=label, field_name=name, student_id=mine.pk).latest("id")
    assert (entry.actor, entry.actor_role, entry.source) == (curator, "curator", "manual")
    assert name in answer.data["entered_by_curator"]

    foreign = f"/api/profiles/{PROFILE_URL[label]}/{stranger.pk}/"
    assert login(curator).patch(foreign, {name: SAMPLE[name]}, format="json").status_code == 404
    assert login(mine.user).patch(url, {name: SAMPLE[name]}, format="json").status_code == 403


def test_every_student_field_is_either_entered_by_the_curator_or_named_as_an_exception():
    """Ученическое поле без права куратора обязано стоять в исключениях с причиной."""
    from core.domains import DOMAINS, curator_may_write

    for domain in DOMAINS.values():
        for model in domain.models:
            for spec in model.fields:
                if not spec.student_proposable:
                    continue
                allowed = curator_may_write(model.label, spec.name)
                excepted = (model.label, spec.name) in CURATOR_DOES_NOT_ENTER
                assert allowed != excepted, (model.label, spec.name)


@pytest.mark.parametrize(
    ("area", "payload"),
    [
        ("exam", {"ielts_current": "8.0"}),  # текущий балл считается по попыткам
        ("admission", {"target_country": "Канада"}),  # цели спрашивает анкета
        ("admission", {"status": "critical"}),  # служебное поле домена
        ("talent", {"portfolio_status": "strong"}),  # оценка директора
    ],
)
def test_curator_does_not_write_beyond_what_the_student_enters(area, payload, curator, klass):
    assert login(curator).patch(f"/api/profiles/{area}/{klass[0].pk}/", payload, format="json").status_code == 403


# --- Строки: завести, изменить, убрать ----------------------------------------------


def test_curator_enters_an_official_attempt_and_removes_it(curator, klass, stranger):
    mine = klass[0]
    client = login(curator)
    made = client.post(
        "/api/attempts/",
        {
            "student": mine.pk,
            "exam_type": "IELTS",
            # формат сдачи — не поле куратора: он вносит то же, что ученик, — сертификат
            "attempt_format": "mock",
            "date": "2026-06-10",
            "total_score": "7.0",
            "listening": "7.5",
        },
        format="json",
    )
    assert made.status_code == 201, made.data
    attempt = ExamAttempt.objects.get(pk=made.data["id"])
    assert attempt.attempt_format == AttemptFormat.OFFICIAL
    assert made.data["entered_by_curator"]
    log = AuditLog.objects.filter(model_label="students.ExamAttempt", object_id=str(attempt.pk))
    assert {e.field_name for e in log} >= {"exam_type", "date", "total_score"}
    assert {(e.actor_role, e.source) for e in log} == {("curator", "manual")}

    assert client.patch(f"/api/attempts/{attempt.pk}/", {"total_score": "7.5"}, format="json").status_code == 200
    attempt.refresh_from_db()
    assert attempt.total_score == Decimal("7.5")

    # чужой ученик — 404 и при заведении, и при правке
    assert (
        client.post(
            "/api/attempts/",
            {"student": stranger.pk, "exam_type": "IELTS", "date": "2026-06-10", "total_score": "7.0"},
            format="json",
        ).status_code
        == 404
    )
    foreign = ExamAttempt.objects.create(
        student=stranger, exam_type="IELTS", attempt_format=AttemptFormat.OFFICIAL, date=dt.date(2026, 5, 1)
    )
    assert client.patch(f"/api/attempts/{foreign.pk}/", {"total_score": "9"}, format="json").status_code == 404

    # «Убрать» — в архив, а не насовсем
    gone = client.delete(f"/api/attempts/{attempt.pk}/")
    assert gone.status_code == 200, gone.data
    assert "в архиве" in gone.data["detail"]
    assert not ExamAttempt.objects.filter(pk=attempt.pk).exists()
    assert ExamAttempt.all_objects.filter(pk=attempt.pk).exists()


def test_curator_does_not_touch_mock_attempts_by_hand(curator, klass):
    mock = ExamAttempt.objects.create(
        student=klass[0], exam_type="IELTS", attempt_format=AttemptFormat.MOCK, date=dt.date(2026, 4, 1)
    )
    client = login(curator)
    assert client.patch(f"/api/attempts/{mock.pk}/", {"total_score": "9"}, format="json").status_code == 403
    assert client.delete(f"/api/attempts/{mock.pk}/").status_code == 403


def test_curator_enters_goal_activity_and_competition(curator, klass, ielts):
    mine = klass[0]
    client = login(curator)
    sport = SportType.objects.create(name="Плавание")

    goal = client.post(
        "/api/exam-goals/",
        {"student": mine.pk, "exam": ielts.pk, "target_score": "7.5", "exam_date": "2026-12-01"},
        format="json",
    )
    assert goal.status_code == 201, goal.data
    activity = client.post(
        "/api/activities/",
        {"student": mine.pk, "category": "volunteering", "title": "Волонтёр форума", "date": "2026-03-01"},
        format="json",
    )
    assert activity.status_code == 201, activity.data
    competition = client.post(
        "/api/competitions/",
        {"student": mine.pk, "name": "Кубок города", "sport_type": sport.pk, "level": "city", "date": "2026-02-01"},
        format="json",
    )
    assert competition.status_code == 201, competition.data

    for model, row in ((ExamGoal, goal), (Activity, activity), (Competition, competition)):
        assert model.objects.filter(pk=row.data["id"], student=mine).exists()
        assert row.data["entered_by_curator"]

    assert (
        client.patch(f"/api/activities/{activity.data['id']}/", {"title": "Волонтёр"}, format="json").status_code == 200
    )
    # служебное поле строки куратору закрыто
    assert (
        client.patch(f"/api/activities/{activity.data['id']}/", {"is_confirmed": True}, format="json").status_code
        == 403
    )
    for path, row in (("exam-goals", goal), ("activities", activity), ("competitions", competition)):
        assert client.delete(f"/api/{path}/{row.data['id']}/").status_code == 200


def test_student_still_cannot_write_rows_directly(klass, ielts):
    client = login(klass[0].user)
    assert (
        client.post(
            "/api/attempts/",
            {"student": klass[0].pk, "exam_type": "IELTS", "date": "2026-06-10", "total_score": "7.0"},
            format="json",
        ).status_code
        == 403
    )
    assert client.post("/api/exam-goals/", {"student": klass[0].pk, "exam": ielts.pk}, format="json").status_code == 403


# --- Перекрытие предложения ученика -------------------------------------------------


def propose(student, rows):
    created, rejected = create_student_suggestions(author=student.user, student=student, rows=rows)
    assert not rejected, rejected
    return created


def test_curator_entry_supersedes_the_pending_proposal(curator, klass):
    mine = klass[0]
    [suggestion] = propose(
        mine,
        [
            {"model": "students.ExamProfile", "field": "gpa", "value": "4.0", "student": mine.pk},
            {"model": "students.ExamProfile", "field": "ielts_target", "value": "7.0", "student": mine.pk},
        ],
    )
    assert login(curator).patch(f"/api/profiles/exam/{mine.pk}/", {"gpa": "4.5"}, format="json").status_code == 200

    # перекрыта только совпавшая строка; вторая ждёт решения как ждала
    suggestion.refresh_from_db()
    assert suggestion.status == SuggestionStatus.PENDING
    assert [c.field_name for c in suggestion.changes.all()] == ["ielts_target"]
    closed = Suggestion.objects.get(status=SuggestionStatus.SUPERSEDED)
    [change] = closed.changes.all()
    assert (change.field_name, closed.author) == ("gpa", mine.user)
    assert Decimal(change.superseded_value) == Decimal("4.5")
    assert ExamProfile.objects.get(student=mine).gpa == Decimal("4.5")

    # ученик видит: не «отклонено», а что внёс куратор; имени куратора нет
    mine_rows = {row["id"]: row for row in mine_payload(mine.user)}
    shown = mine_rows[closed.pk]
    assert shown["status"] == "superseded" and shown["reject_reason"] == ""
    assert Decimal(shown["changes"][0]["superseded_value"]) == Decimal("4.5")
    assert curator.full_name not in str(shown)


def test_reverse_order_goes_to_the_queue_as_usual(curator, klass):
    mine = klass[0]
    assert login(curator).patch(f"/api/profiles/exam/{mine.pk}/", {"gpa": "4.5"}, format="json").status_code == 200
    [suggestion] = propose(
        mine, [{"model": "students.ExamProfile", "field": "gpa", "value": "4.8", "student": mine.pk}]
    )
    assert suggestion.status == SuggestionStatus.PENDING
    assert not Suggestion.objects.filter(status=SuggestionStatus.SUPERSEDED).exists()


def attempt_rows(student, date: str, key: str = "certificate") -> list[dict]:
    base = {"model": "students.ExamAttempt", "student": student.pk, "new_object_key": key}
    return [
        {**base, "field": "exam_type", "value": "IELTS"},
        {**base, "field": "date", "value": date},
        {**base, "field": "total_score", "value": "6.5"},
    ]


def test_new_attempt_supersedes_the_same_proposed_attempt_only(curator, klass):
    mine = klass[0]
    [same] = propose(mine, attempt_rows(mine, "2026-06-10"))
    [other] = propose(mine, attempt_rows(mine, "2026-01-15"))
    made = login(curator).post(
        "/api/attempts/",
        {"student": mine.pk, "exam_type": "IELTS", "date": "2026-06-10", "total_score": "7.0"},
        format="json",
    )
    assert made.status_code == 201, made.data
    same.refresh_from_db()
    other.refresh_from_db()
    assert same.status == SuggestionStatus.SUPERSEDED
    assert Decimal({c.field_name: c.superseded_value for c in same.changes.all()}["total_score"]) == Decimal("7.0")
    assert other.status == SuggestionStatus.PENDING


def test_activities_are_never_superseded(curator, klass):
    mine = klass[0]
    base = {"model": "students.Activity", "student": mine.pk, "new_object_key": "a1"}
    [suggestion] = propose(
        mine,
        [
            {**base, "field": "category", "value": "volunteering"},
            {**base, "field": "title", "value": "Волонтёр форума"},
        ],
    )
    made = login(curator).post(
        "/api/activities/", {"student": mine.pk, "category": "volunteering", "title": "Волонтёр форума"}, format="json"
    )
    assert made.status_code == 201, made.data
    suggestion.refresh_from_db()
    assert suggestion.status == SuggestionStatus.PENDING


def test_confirming_from_the_queue_is_not_a_direct_entry(curator, klass):
    """Решение по очереди — путь ученика: оно ничего не перекрывает."""
    mine = klass[0]
    [suggestion] = propose(
        mine, [{"model": "students.ExamProfile", "field": "ielts_target", "value": "7.0", "student": mine.pk}]
    )
    answer = login(curator).post(
        "/api/suggestions/from-students/confirm/", {"suggestions": [suggestion.pk]}, format="json"
    )
    assert answer.status_code == 200, answer.data
    suggestion.refresh_from_db()
    assert suggestion.status == SuggestionStatus.APPLIED


# --- Документы ----------------------------------------------------------------------


def test_document_uploaded_by_the_curator_is_confirmed_at_once(curator, klass, stranger):
    mine = klass[0]
    # ученик успел загрузить паспорт — он ждёт проверки
    waiting = StudentDocument.objects.create(student=mine, doc_type="passport", title="Паспорт ученика")
    queued = documents.submit(waiting, author=mine.user)

    client = login(curator)
    made = client.post(
        "/api/documents/",
        {"student": mine.pk, "doc_type": "passport", "expires_at": "2031-05-01", "file": png()},
        format="multipart",
    )
    assert made.status_code == 201, made.data
    row = StudentDocument.objects.get(pk=made.data["id"])
    assert (row.status, row.reviewed_by, made.data["entered_by_curator"]) == (DocumentStatus.CONFIRMED, curator, True)
    assert documents.open_suggestion(row) is None

    from students.models import Student

    cell = documents.state_of(Student.objects.filter(pk=mine.pk))[mine.pk]["cells"]["passport"]
    assert cell["state"] in ("confirmed", "expiring")

    # документ ученика не «отклонён», а заменён; его строка очереди закрыта
    waiting.refresh_from_db()
    queued.refresh_from_db()
    assert waiting.status == DocumentStatus.SUPERSEDED
    assert queued.status == SuggestionStatus.SUPERSEDED

    entry = AuditLog.objects.filter(
        model_label="students.StudentDocument", object_id=str(row.pk), field_name="status"
    ).latest("id")
    assert (entry.actor_role, entry.source, entry.new_value) == ("curator", "manual", "confirmed")

    # срок действия — правкой; удалить документ куратор не может
    assert client.patch(f"/api/documents/{row.pk}/", {"expires_at": "2032-01-01"}, format="json").status_code == 200
    assert client.delete(f"/api/documents/{row.pk}/").status_code == 403
    assert StudentDocument.objects.filter(pk=row.pk).exists()

    foreign = client.post(
        "/api/documents/", {"student": stranger.pk, "doc_type": "passport", "file": png()}, format="multipart"
    )
    assert foreign.status_code == 404


# --- Вузы ---------------------------------------------------------------------------


def test_curator_keeps_the_university_list_of_own_student(curator, klass, stranger, program):
    mine = klass[0]
    client = login(curator)
    other_program = Program.objects.create(university=program.university, name="Экономика")
    by_student = StudentUniversity.objects.create(
        student=mine, program=other_program, added_by="student", is_confirmed=False
    )

    made = client.post("/api/catalog/add/", {"student": mine.pk, "program": program.pk, "tier": "reach"}, format="json")
    assert made.status_code == 201, made.data
    entry = StudentUniversity.objects.get(pk=made.data["id"])
    assert (entry.student, entry.tier, entry.is_confirmed) == (mine, "reach", True)
    assert AuditLog.objects.filter(
        model_label="universities.StudentUniversity", object_id=str(entry.pk), actor_role="curator", source="manual"
    ).exists()

    # приоритетный — ровно один
    assert client.post(f"/api/catalog/priority/{entry.pk}/", {"student": mine.pk}, format="json").status_code == 200
    assert (
        client.post(f"/api/catalog/priority/{by_student.pk}/", {"student": mine.pk}, format="json").status_code == 200
    )
    assert list(StudentUniversity.objects.filter(student=mine, is_priority=True)) == [by_student]

    assert (
        client.post(f"/api/catalog/tier/{entry.pk}/", {"student": mine.pk, "tier": "safety"}, format="json").status_code
        == 200
    )
    # строку, добавленную учеником, куратор убирает — в архив
    assert client.delete(f"/api/catalog/remove/{by_student.pk}/?student={mine.pk}").status_code == 204
    assert not StudentUniversity.objects.filter(pk=by_student.pk).exists()
    assert StudentUniversity.all_objects.filter(pk=by_student.pk).exists()

    # чужой ученик — 404; чужая строка под видом своей — тоже
    assert (
        client.post("/api/catalog/add/", {"student": stranger.pk, "program": program.pk}, format="json").status_code
        == 404
    )
    theirs = StudentUniversity.objects.create(student=stranger, program=program, added_by="student")
    assert client.delete(f"/api/catalog/remove/{theirs.pk}/?student={mine.pk}").status_code == 404


# --- Импорт и подпись ---------------------------------------------------------------


def test_curator_sees_only_own_uploads_in_the_history(curator, asem, klass):
    from students.tests.test_phase71 import book_of

    assert (
        login(asem).post("/api/admission-imports/apply/", {"file": book_of(klass)}, format="multipart").status_code
        == 201
    )
    assert login(curator).get("/api/admission-imports/").data["rows"] == []
    assert (
        login(curator).post("/api/admission-imports/apply/", {"file": book_of(klass)}, format="multipart").status_code
        == 201
    )
    rows = login(curator).get("/api/admission-imports/").data["rows"]
    assert len(rows) == 1
    assert len(login(asem).get("/api/admission-imports/").data["rows"]) == 2


def test_the_label_is_seen_by_the_student_and_leaves_when_the_owner_edits(curator, kymbat, klass):
    mine = klass[0]
    assert login(curator).patch(f"/api/profiles/exam/{mine.pk}/", {"gpa": "4.5"}, format="json").status_code == 200
    seen = login(mine.user).get(f"/api/profiles/exam/{mine.pk}/")
    assert seen.status_code == 200
    assert seen.data["entered_by_curator"] == ["gpa"]
    # ученик видит подпись, но не имя куратора
    assert curator.full_name not in str(seen.data)

    assert login(kymbat).patch(f"/api/profiles/exam/{mine.pk}/", {"gpa": "4.6"}, format="json").status_code == 200
    assert login(mine.user).get(f"/api/profiles/exam/{mine.pk}/").data["entered_by_curator"] == []


def test_admission_and_sport_profiles_exist_for_the_matrix(klass):
    """Матрица выше опирается на профили — фикстура обязана их заводить."""
    assert AdmissionProfile.objects.filter(student=klass[0]).exists()
    assert SportProfile.objects.filter(student=klass[0]).exists()
