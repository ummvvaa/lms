"""Фаза 63: пробники файлом и секции IELTS.

Три вещи, которые здесь легко сломать тихо:

* балл уезжает не тому ученику — поэтому разбор проверяется на каждой
  ошибке строки поимённо, а сопоставление ищет только внутри группы;
* пробник подменяет официальный балл — поэтому «текущий» проверяется
  и после файла, и после засчитанного платформенного мока;
* средний по группе утекает ученику — страж обходит его ответы и ищет
  число, как для заметок куратора в фазе 62.
"""

from __future__ import annotations

import datetime as dt
import io
import json
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient

from accounts.curators import assign
from accounts.models import User
from core.models import AuditLog
from students import attention, mocks
from students.models import (
    AdmissionProfile,
    AttemptFormat,
    AttemptSource,
    BehaviorProfile,
    ExamAttempt,
    ExamGoal,
    ExamProfile,
    MockImport,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)

TODAY = timezone.localdate()
MOCK_DATE = TODAY - dt.timedelta(days=3)


def days(n: int) -> dt.date:
    return TODAY + dt.timedelta(days=n)


@pytest.fixture
def chicago(db) -> StudyGroup:
    return StudyGroup.objects.create(code="CHICAGO", grade=11)


@pytest.fixture
def boston(db) -> StudyGroup:
    return StudyGroup.objects.create(code="BOSTON", grade=11)


def make_student(group: StudyGroup, last_name: str, first_name: str, email: str, make_user) -> tuple[Student, User]:
    student = Student.objects.create(
        last_name=last_name,
        first_name=first_name,
        email=email,
        grade=11,
        group=group,
        graduation_year=2027,
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=student)
    user = make_user("student", email, full_name=f"{last_name} {first_name}")
    student.user = user
    student.save(update_fields=["user"])
    return student, user


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin", "admin63@example.kz", full_name="Администратор")


@pytest.fixture
def curator(make_user, chicago, admin) -> User:
    user = make_user("curator", "curator63@example.kz", full_name="Асель Ермекова")
    assign(group=chicago, curator=user, since=days(-30), actor=admin)
    return user


@pytest.fixture
def kymbat(make_user) -> User:
    return make_user("director_exam", "kymbat63@example.kz", full_name="Кымбат")


@pytest.fixture
def saltanat(make_user) -> User:
    return make_user("director_behavior", "saltanat63@example.kz", full_name="Салтанат")


@pytest.fixture
def klass(chicago, make_user):
    """Трое своих: их ФИО стоят в файле пробника."""
    return [
        make_student(chicago, "Сериков", "Данияр", "serikov63@example.kz", make_user),
        make_student(chicago, "Ержанова", "Малика", "erzhanova63@example.kz", make_user),
        make_student(chicago, "Оспанов", "Тимур", "ospanov63@example.kz", make_user),
    ]


@pytest.fixture
def stranger(boston, make_user):
    return make_student(boston, "Чужой", "Ученик", "stranger63@example.kz", make_user)


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def sheet(rows: list[list], header: list[str], name: str = "mock.xlsx") -> SimpleUploadedFile:
    """Файл учителя книгой XLSX — как он приходит из школы."""
    book = Workbook()
    page = book.active
    page.append(header)
    for row in rows:
        page.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


IELTS_HEADER = ["ФИО", "Listening", "Reading", "Writing", "Speaking", "Балл", "Примечание"]
SAT_HEADER = ["ФИО", "Балл"]


def ielts_file(rows: list[list], name: str = "ielts.xlsx") -> SimpleUploadedFile:
    return sheet(rows, IELTS_HEADER, name)


def wizard(client, *, file, group="CHICAGO", exam="IELTS", date=None, fixes=None, step="preview"):
    payload = {
        "exam_type": exam,
        "group": group,
        "date": (date or MOCK_DATE).isoformat(),
        "teacher": "Айгуль Сергеевна",
        "file": file,
    }
    if fixes is not None:
        payload["fixes"] = json.dumps(fixes)
    return client.post(f"/api/mock-imports/{step}/", payload, format="multipart")


# --- Разбор файла: каждая ошибка строки -----------------------------------------------


@pytest.mark.django_db
def test_clean_file_parses_and_applies(klass, curator):
    """Ровный файл: три строки, все готовы, применение пишет попытки и журнал."""
    client = login(curator)
    rows = [
        ["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""],
        ["Ержанова Малика", 5.5, 5.5, 5.5, 6.0, 5.5, "опоздала"],
        ["Оспанов Тимур", 7.0, 7.5, 7.0, 7.0, 7.0, ""],
    ]
    preview = wizard(client, file=ielts_file(rows))
    assert preview.status_code == 200, preview.content
    body = preview.json()
    assert body["counts"] == {"total": 3, "ready": 3, "broken": 0, "skipped": 0}
    assert body["can_apply"] is True
    assert [row["student_name"] for row in body["rows"]] == ["Сериков Данияр", "Ержанова Малика", "Оспанов Тимур"]

    applied = wizard(client, file=ielts_file(rows), step="apply")
    assert applied.status_code == 201, applied.content
    record = MockImport.objects.get(pk=applied.json()["import"])
    assert record.rows_applied == 3 and record.rows_skipped == 0
    assert record.teacher == "Айгуль Сергеевна" and record.file_name == "ielts.xlsx"

    attempt = ExamAttempt.objects.get(student=klass[0][0])
    assert attempt.attempt_format == AttemptFormat.MOCK
    assert attempt.source == AttemptSource.IMPORT
    assert float(attempt.total_score) == 6.5
    assert [float(getattr(attempt, name)) for name in ("listening", "reading", "writing", "speaking")] == [
        6.5,
        7.0,
        6.0,
        6.5,
    ]
    assert attempt.mock_import_id == record.pk
    # загрузка видна в журнале — по строке на каждого ученика
    assert AuditLog.objects.filter(field_name="mock_import").count() == 3


@pytest.mark.django_db
def test_row_errors_are_named_one_by_one(klass, curator, chicago, make_user):
    """Каждая кривая строка называется своей ошибкой, а не «файл плохой»."""
    client = login(curator)
    # у Оспанова уже есть пробник на эту дату — строка про него станет «already»
    ExamAttempt.objects.create(
        student=klass[2][0],
        exam_type="IELTS",
        attempt_format=AttemptFormat.MOCK,
        source=AttemptSource.IMPORT,
        date=MOCK_DATE,
        total_score=6,
    )
    rows = [
        ["Неизвестный Человек", 6.0, 6.0, 6.0, 6.0, 6.0, ""],  # not_found
        ["Сериков Данияр", 9.5, 6.0, 6.0, 6.0, 9.5, ""],  # sections_range
        ["Ержанова Малика", 6.0, 6.0, 6.0, 6.0, 8.0, ""],  # sections_mismatch
        ["Ержанова Малика", 6.0, 6.0, 6.0, 6.0, 6.0, ""],  # duplicate
        ["Оспанов Тимур", 7.0, 7.0, 7.0, 7.0, 7.0, ""],  # already
        ["", 6.0, 6.0, 6.0, 6.0, 6.0, ""],  # no_name
    ]
    body = wizard(client, file=ielts_file(rows)).json()
    assert [row["error"] for row in body["rows"]] == [
        "not_found",
        "sections_range",
        "sections_mismatch",
        "duplicate",
        "already",
        "no_name",
    ]
    assert body["can_apply"] is False
    assert body["counts"]["broken"] == 6
    # у каждой ошибки есть подпись и подсказка, что делать
    assert all(row["error_title"] and row["fix"] for row in body["rows"])

    # применить такой файл нельзя, пока строки не разобраны
    refused = wizard(client, file=ielts_file(rows), step="apply")
    assert refused.status_code == 400
    assert "№1" in refused.json()["detail"]
    assert not MockImport.objects.exists()


@pytest.mark.django_db
def test_sat_score_out_of_scale(klass, curator):
    """Балл вне шкалы SAT — ошибка строки со шкалой словами."""
    client = login(curator)
    rows = [["Сериков Данияр", 1700], ["Ержанова Малика", 1310]]
    body = wizard(client, file=sheet(rows, SAT_HEADER), exam="SAT").json()
    assert [row["error"] for row in body["rows"]] == ["score_range", ""]
    assert body["scale"] == "SAT: от 400 до 1600 с шагом 10"
    # шаг тоже держится: 1315 не бывает
    step = wizard(client, file=sheet([["Сериков Данияр", 1315]], SAT_HEADER), exam="SAT").json()
    assert step["rows"][0]["error"] == "score_range"


@pytest.mark.django_db
def test_ielts_sections_are_required_and_checked_against_the_band(klass, curator):
    """Для IELTS нужны все четыре секции, и общий балл сверяется со средним."""
    client = login(curator)
    # нет колонок секций вовсе — файл не разбирается
    refused = wizard(client, file=sheet([["Сериков Данияр", 6.5]], ["ФИО", "Балл"]))
    assert refused.status_code == 400
    assert "четыре секции" in refused.json()["detail"]

    # колонки есть, а в строке пусто — ошибка строки, не файла
    body = wizard(client, file=ielts_file([["Сериков Данияр", 6.5, "", 6.0, 6.5, 6.5, ""]])).json()
    assert body["rows"][0]["error"] == "sections_missing"

    # балла в файле нет — считаем сами из секций
    computed = wizard(client, file=ielts_file([["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, "", ""]])).json()
    assert computed["rows"][0]["error"] == ""
    assert computed["rows"][0]["total"] == 6.5

    # шаг 0.5 у секции
    step = wizard(client, file=ielts_file([["Сериков Данияр", 6.25, 7.0, 6.0, 6.5, 6.5, ""]])).json()
    assert step["rows"][0]["error"] == "sections_range"


@pytest.mark.django_db
def test_band_rounds_halves_up():
    """Среднее округляется как в бланке: 6.25 → 6.5, а не к чётному."""

    def band(*values: str) -> float:
        return float(mocks.band_of(dict(zip(mocks.IELTS_SECTIONS, [Decimal(v) for v in values], strict=True))))

    assert band("6", "6", "6.5", "6.5") == 6.5, "6.25 округляется вверх, как в бланке"
    assert band("6", "6", "6", "6.5") == 6.0, "6.125 округляется вниз"
    assert band("7", "7", "6.5", "7") == 7.0


@pytest.mark.django_db
def test_fuzzy_match_finds_declined_name_inside_the_group(klass, curator, boston, make_user):
    """ФИО со склонением и в другом порядке находится; чужая группа — нет."""
    # однофамилец в чужой группе не должен перехватить строку
    make_student(boston, "Сериков", "Данияр", "twin63@example.kz", make_user)
    client = login(curator)
    body = wizard(client, file=ielts_file([["Данияру Серикову", 6.5, 7.0, 6.0, 6.5, 6.5, ""]])).json()
    assert body["rows"][0]["student"] == klass[0][0].pk
    assert body["rows"][0]["error"] == ""


@pytest.mark.django_db
def test_manual_fixes_resolve_rows(klass, curator):
    """Правки человека: назначить ученика, поправить балл, пропустить строку."""
    client = login(curator)
    rows = [
        ["Кто-то Неизвестный", 6.0, 6.0, 6.0, 6.0, 6.0, ""],
        ["Ержанова Малика", 9.5, 6.0, 6.0, 6.0, 9.5, ""],
        ["Оспанов Тимур", 7.0, 7.0, 7.0, 7.0, 7.0, ""],
    ]
    fixes = [
        {"index": 1, "student": klass[0][0].pk},
        {"index": 2, "sections": {"listening": "6.0"}, "total": "6.0"},
        {"index": 3, "skip": True},
    ]
    body = wizard(client, file=ielts_file(rows), fixes=fixes).json()
    assert body["counts"] == {"total": 3, "ready": 2, "broken": 0, "skipped": 1}
    assert body["can_apply"] is True

    applied = wizard(client, file=ielts_file(rows), fixes=fixes, step="apply")
    assert applied.status_code == 201
    record = MockImport.objects.get(pk=applied.json()["import"])
    assert record.rows_applied == 2 and record.rows_skipped == 1
    assert "№3" in record.skipped_report and "Оспанов" in record.skipped_report
    assert set(record.attempts.values_list("student_id", flat=True)) == {klass[0][0].pk, klass[1][0].pk}


@pytest.mark.django_db
def test_second_upload_of_the_same_group_and_date_is_refused(klass, curator):
    """Тот же пробник второй раз — отказ до разбора, а не удвоенные баллы."""
    client = login(curator)
    rows = [["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]
    assert wizard(client, file=ielts_file(rows), step="apply").status_code == 201

    again = wizard(client, file=ielts_file(rows))
    assert again.status_code == 400
    assert "уже загружен" in again.json()["detail"]
    assert MockImport.objects.count() == 1


@pytest.mark.django_db
def test_nothing_is_written_when_a_row_breaks_midway(klass, curator, monkeypatch):
    """Сбой посередине не оставляет половину класса с баллами."""
    client = login(curator)
    rows = [
        ["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""],
        ["Ержанова Малика", 5.5, 5.5, 5.5, 6.0, 5.5, ""],
    ]
    original = ExamAttempt.save
    calls = {"n": 0}

    def explode(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("база отвалилась на второй строке")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ExamAttempt, "save", explode)
    with pytest.raises(RuntimeError):
        wizard(client, file=ielts_file(rows), step="apply")

    monkeypatch.setattr(ExamAttempt, "save", original)
    assert not MockImport.objects.exists()
    assert not ExamAttempt.objects.exists()


# --- Текущий балл: только официальные попытки -----------------------------------------


@pytest.mark.django_db
def test_mock_does_not_touch_the_current_score(klass, curator):
    """Пробник 6.0 не перекрывает сертификат 7.0."""
    student, _ = klass[0]
    profile = student.exam
    profile.ielts_current = 7
    profile.save(update_fields=["ielts_current"])

    client = login(curator)
    assert (
        wizard(client, file=ielts_file([["Сериков Данияр", 6.0, 6.0, 6.0, 6.0, 6.0, ""]]), step="apply").status_code
        == 201
    )
    profile.refresh_from_db()
    assert float(profile.ielts_current) == 7.0


@pytest.mark.django_db
def test_counted_platform_mock_no_longer_writes_the_profile(klass, kymbat):
    """Засчитанный платформенный мок с фазы 63 профиль не трогает."""
    from prep.models import MockExam, MockRun
    from prep.services import review_mock

    student, _ = klass[0]
    profile = student.exam
    profile.ielts_current = 7
    profile.save(update_fields=["ielts_current"])

    from prep.models import PracticeSession

    exam = MockExam.objects.create(title="Пробный IELTS", exam_type="IELTS")
    attempt = ExamAttempt.objects.create(
        student=student,
        exam_type="IELTS",
        attempt_format=AttemptFormat.MOCK,
        source=AttemptSource.PLATFORM,
        date=TODAY,
        total_score=6,
    )
    session = PracticeSession.objects.create(student=student, exam_type="IELTS")
    run = MockRun.objects.create(student=student, mock=exam, session=session, exam_attempt=attempt)

    outcome = review_mock(run, count_it=True, actor=kymbat)
    assert outcome["counted_in_profile"] is True
    profile.refresh_from_db()
    assert float(profile.ielts_current) == 7.0


@pytest.mark.django_db
def test_mock_counts_for_the_bucket_and_the_dynamics(klass, curator, chicago):
    """Корзина «пробника не было» считается по мокам любого источника."""
    student, _ = klass[0]
    state = attention.state_of(Student.objects.filter(pk=student.pk))[student.pk]
    assert "nomock" in state["buckets"]

    client = login(curator)
    wizard(client, file=ielts_file([["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]), step="apply")
    fresh = attention.state_of(Student.objects.filter(pk=student.pk))[student.pk]
    assert "nomock" not in fresh["buckets"]
    assert fresh["last_mock_date"] == MOCK_DATE


# --- Ученик: смотрит, но не правит ------------------------------------------------------


@pytest.mark.django_db
def test_student_sees_the_mock_but_cannot_touch_it(klass, curator):
    """Ученик видит пробник с пометкой и не может его ни создать, ни изменить."""
    student, user = klass[0]
    client = login(curator)
    wizard(client, file=ielts_file([["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]), step="apply")
    attempt = ExamAttempt.objects.get(student=student)

    mine = login(user)
    rows = mine.get("/api/attempts/").json()["results"]
    assert len(rows) == 1
    assert rows[0]["is_mock"] is True and rows[0]["attempt_format"] == "mock"
    assert rows[0]["writing"] == "6.0"

    # правка своей мок-попытки — отказ и словами, и кодом
    assert mine.patch(f"/api/attempts/{attempt.pk}/", {"total_score": "9.0"}, format="json").status_code == 403
    assert mine.post("/api/attempts/", {"student": student.pk, "exam_type": "IELTS"}, format="json").status_code == 403

    proposed = mine.post(
        "/api/suggestions/propose/",
        {
            "rows": [
                {
                    "model": "students.ExamAttempt",
                    "field": "total_score",
                    "value": "9.0",
                    "object_id": str(attempt.pk),
                }
            ]
        },
        format="json",
    )
    assert proposed.status_code == 400
    assert "пробника школы" in proposed.json()["rejected"][0]["reason"]
    attempt.refresh_from_db()
    assert float(attempt.total_score) == 6.5


@pytest.mark.django_db
def test_student_proposes_official_attempt_with_certificate_sections(klass, kymbat):
    """Секции с сертификата идут одной строкой очереди вместе с баллом."""
    student, user = klass[0]
    mine = login(user)
    made = mine.post(
        "/api/suggestions/propose/",
        {
            "rows": [
                {"model": "students.ExamProfile", "field": "ielts_current", "value": "7.5"},
                {"model": "students.ExamAttempt", "field": "exam_type", "value": "IELTS", "new_object_key": "cert"},
                {"model": "students.ExamAttempt", "field": "date", "value": str(days(-10)), "new_object_key": "cert"},
                {"model": "students.ExamAttempt", "field": "total_score", "value": "7.5", "new_object_key": "cert"},
                {"model": "students.ExamAttempt", "field": "writing", "value": "7.0", "new_object_key": "cert"},
                {"model": "students.ExamAttempt", "field": "speaking", "value": "8.0", "new_object_key": "cert"},
                {"model": "students.ExamAttempt", "field": "reading", "value": "7.5", "new_object_key": "cert"},
                {"model": "students.ExamAttempt", "field": "listening", "value": "7.5", "new_object_key": "cert"},
            ]
        },
        format="json",
    )
    assert made.status_code == 201, made.content
    # балл и секции — одна строка очереди: домен один
    assert len(made.json()["suggestions"]) == 1

    suggestion = made.json()["suggestions"][0]
    decided = login(kymbat).post(f"/api/suggestions/{suggestion}/review/", {"decision": "confirm"}, format="json")
    assert decided.status_code == 200, decided.content

    attempt = ExamAttempt.objects.get(student=student, exam_type="IELTS")
    assert attempt.attempt_format == AttemptFormat.OFFICIAL, "попытка от ученика — официальная, не пробник"
    assert float(attempt.writing) == 7.0 and float(attempt.speaking) == 8.0
    student.exam.refresh_from_db()
    assert float(student.exam.ielts_current) == 7.5


@pytest.mark.django_db
def test_student_cannot_claim_a_section_outside_the_scale(klass):
    """Секция 9.25 не проходит: шкала IELTS — шаг 0.5."""
    _student, user = klass[0]
    refused = login(user).post(
        "/api/suggestions/propose/",
        {
            "rows": [
                {"model": "students.ExamAttempt", "field": "exam_type", "value": "IELTS", "new_object_key": "c"},
                {"model": "students.ExamAttempt", "field": "writing", "value": "9.25", "new_object_key": "c"},
            ]
        },
        format="json",
    )
    # строка с секцией отбита, экзамен принят: пакет не пропадает целиком
    rejected = refused.json()["rejected"]
    assert [row["field"] for row in rejected] == ["writing"]
    assert "шагом 0.5" in rejected[0]["reason"]


# --- Права: своя группа, чужая группа, ученик ------------------------------------------


@pytest.mark.django_db
def test_curator_of_another_group_gets_404(klass, stranger, curator, kymbat, boston):
    """Чужая группа для куратора не существует: ни загрузить, ни открыть."""
    client = login(kymbat)
    made = wizard(
        client, file=ielts_file([["Чужой Ученик", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]), group="BOSTON", step="apply"
    )
    assert made.status_code == 201, made.content
    record = made.json()["import"]

    outsider = login(curator)
    assert outsider.get(f"/api/mock-imports/{record}/").status_code == 404
    assert outsider.get(f"/api/mock-imports/{record}/file/").status_code == 404
    assert outsider.post(f"/api/mock-imports/{record}/archive/", {}, format="json").status_code == 404
    # и в списке чужой загрузки нет
    assert outsider.get("/api/mock-imports/").json()["results"] == []
    # загрузить в чужую группу — тоже 404, а не 403
    refused = wizard(outsider, file=ielts_file([["Чужой Ученик", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]), group="BOSTON")
    assert refused.status_code == 404


@pytest.mark.django_db
def test_kymbat_uploads_to_any_group_and_student_to_none(klass, stranger, kymbat, saltanat):
    """Кымбат грузит в любую группу; ученику и чужому директору закрыто."""
    boss = login(kymbat)
    for group, name in (("CHICAGO", "Сериков Данияр"), ("BOSTON", "Чужой Ученик")):
        made = wizard(boss, file=ielts_file([[name, 6.5, 7.0, 6.0, 6.5, 6.5, ""]]), group=group, step="apply")
        assert made.status_code == 201, made.content
    assert MockImport.objects.count() == 2

    _student, user = klass[0]
    assert login(user).get("/api/mock-imports/").status_code == 403
    assert wizard(login(user), file=ielts_file([["Сериков Данияр", 6, 6, 6, 6, 6, ""]])).status_code == 403
    # чужой директор пробники видит (это школьные данные), но не грузит
    assert login(saltanat).get("/api/mock-imports/").status_code == 200
    assert wizard(login(saltanat), file=ielts_file([["Сериков Данияр", 6, 6, 6, 6, 6, ""]])).status_code == 403


@pytest.mark.django_db
def test_file_is_served_after_login_only(klass, curator, api_client=None):
    """Исходник отдаётся только вошедшему и только своей группе."""
    client = login(curator)
    made = wizard(client, file=ielts_file([["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]), step="apply")
    record = made.json()["import"]

    assert client.get(f"/api/mock-imports/{record}/file/").status_code == 200
    assert APIClient().get(f"/api/mock-imports/{record}/file/").status_code in (401, 403)


# --- Результаты и напоминания -----------------------------------------------------------


@pytest.mark.django_db
def test_results_page_counts_and_hides_the_average_from_the_student(klass, curator, kymbat):
    """Сдавали, не сдавали, средний по группе — и ни одного из них ученику."""
    from directories.models import ExamKind

    student, user = klass[0]
    kind, _ = ExamKind.objects.get_or_create(name="IELTS")
    ExamGoal.objects.create(student=student, exam=kind, target_score=7.5)

    client = login(curator)
    rows = [
        ["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""],
        ["Ержанова Малика", 5.5, 5.5, 5.5, 6.0, 5.5, ""],
    ]
    record = wizard(client, file=ielts_file(rows), step="apply").json()["import"]

    page = client.get(f"/api/mock-imports/{record}/").json()
    assert page["took"] == 2 and page["missed"] == 1
    assert page["average"] == 6.0
    mine = next(row for row in page["results"] if row["student"] == student.pk)
    assert mine["target"] == 7.5 and mine["below_target"] is True
    assert mine["sections"]["writing"] == 6.0

    # ученик страницу не открывает вовсе, и среднего нет ни в одном его ответе
    assert login(user).get(f"/api/mock-imports/{record}/").status_code == 403
    text = ""
    for path in ("/api/students/me/", "/api/attempts/", "/api/portfolio/", "/api/prep/state/", "/api/journey/"):
        response = login(user).get(path)
        if response.status_code == 200:
            text += json.dumps(response.json(), ensure_ascii=False)
    assert "average" not in text and "средний" not in text.lower()


@pytest.mark.django_db
def test_remind_makes_tasks_for_those_who_missed(klass, curator):
    """«Напомнить» ставит задачу тем, кто пробник не сдавал."""
    from roadmap.models import Task

    client = login(curator)
    record = wizard(client, file=ielts_file([["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]), step="apply").json()[
        "import"
    ]

    made = client.post(f"/api/mock-imports/{record}/remind/", {}, format="json")
    assert made.status_code == 200
    assert made.json()["created"] == 2
    titles = set(Task.objects.values_list("title", flat=True))
    assert titles == {"Сдать пробник IELTS"}
    assert Task.objects.filter(student=klass[0][0]).count() == 0, "сдавшему задача не уходит"


@pytest.mark.django_db
def test_export_is_a_workbook(klass, curator):
    """Выгрузка результатов — настоящая книга, а не HTML с ошибкой."""
    client = login(curator)
    record = wizard(client, file=ielts_file([["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]), step="apply").json()[
        "import"
    ]
    response = client.get(f"/api/mock-imports/{record}/export/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")
    assert response.content[:2] == b"PK", "книга XLSX — это zip, а не HTML с ошибкой"


@pytest.mark.django_db
def test_template_is_generated_per_exam(klass, curator):
    """Шаблон собирается под экзамен и подставляет ФИО группы."""
    client = login(curator)
    for exam in ("IELTS", "SAT"):
        response = client.get(f"/api/mock-imports/template/?exam={exam}&group=CHICAGO")
        assert response.status_code == 200, exam
    assert client.get("/api/mock-imports/template/?exam=TOEFL").status_code == 400
    assert mocks.template_columns("IELTS")[1:5] == ["Listening", "Reading", "Writing", "Speaking"]
    assert mocks.template_columns("SAT") == ["ФИО", "Балл", "Примечание"]


# --- Архив -------------------------------------------------------------------------------


@pytest.mark.django_db
def test_archive_hides_results_and_restore_brings_them_back(klass, curator, kymbat, admin):
    """Архив уносит попытки, возврат поднимает — и то и другое целиком."""
    student, user = klass[0]
    client = login(curator)
    record_id = wizard(client, file=ielts_file([["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]), step="apply").json()[
        "import"
    ]

    assert client.post(f"/api/mock-imports/{record_id}/archive/", {}, format="json").status_code == 200
    assert ExamAttempt.objects.filter(student=student).count() == 0, "у ученика балл пропал"
    # а на странице самой загрузки видно, что в ней было: иначе перед возвратом
    # из архива человек смотрит на пустую таблицу
    archived_page = client.get(f"/api/mock-imports/{record_id}/").json()
    assert archived_page["status"] == "archived" and archived_page["took"] == 1
    assert ExamAttempt.all_objects.filter(student=student).count() == 1, "но остался в базе"
    assert login(user).get("/api/attempts/").json()["results"] == []
    state = attention.state_of(Student.objects.filter(pk=student.pk))[student.pk]
    assert "nomock" in state["buckets"], "в корзинах архивного пробника нет"
    assert client.get("/api/mock-imports/").json()["results"] == []
    assert [row["id"] for row in client.get("/api/mock-imports/?archived=true").json()["results"]] == [record_id]

    # куратор вернуть не может, Кымбат — может
    assert client.post(f"/api/mock-imports/{record_id}/restore/", {}, format="json").status_code == 403
    restored = login(kymbat).post(f"/api/mock-imports/{record_id}/restore/", {}, format="json")
    assert restored.status_code == 200, restored.content
    assert ExamAttempt.objects.filter(student=student).count() == 1
    assert MockImport.objects.filter(pk=record_id).exists()


@pytest.mark.django_db
def test_archived_upload_frees_the_date_for_a_new_one(klass, curator):
    """Убрали в архив — тот же пробник можно залить заново исправленным."""
    client = login(curator)
    rows = [["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]
    first = wizard(client, file=ielts_file(rows), step="apply").json()["import"]
    client.post(f"/api/mock-imports/{first}/archive/", {}, format="json")

    again = wizard(client, file=ielts_file([["Сериков Данияр", 7.0, 7.0, 7.0, 7.0, 7.0, ""]]), step="apply")
    assert again.status_code == 201, again.content
    assert ExamAttempt.objects.get(student=klass[0][0]).total_score == 7


# --- Экраны куратора ---------------------------------------------------------------------


@pytest.mark.django_db
def test_card_shows_sections_and_who_uploaded(klass, curator):
    """В карточке — секции последнего пробника, динамика и кто загрузил."""
    student, _ = klass[0]
    client = login(curator)
    for shift, band in ((10, 6.0), (5, 6.5)):
        wizard(
            client,
            file=ielts_file([["Сериков Данияр", band, band, band, band, band, ""]]),
            date=TODAY - dt.timedelta(days=shift),
            step="apply",
        )

    card = client.get(f"/api/curator/students/{student.pk}/").json()
    assert card["sections"]["last"] == {"listening": 6.5, "reading": 6.5, "writing": 6.5, "speaking": 6.5}
    assert card["sections"]["trend"]["writing"] == [6.0, 6.5], "искра рисуется от двух пробников"
    assert card["mocks"][-1]["teacher"] == "Айгуль Сергеевна"
    assert card["mocks"][-1]["uploaded_by"] == "Асель Ермекова"
    assert card["mocks"][-1]["sections"]["reading"] == 6.5
