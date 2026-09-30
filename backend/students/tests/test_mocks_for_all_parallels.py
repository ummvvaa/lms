"""Пробники у всех параллелей — только для сотрудников (решение владельца, 30.09.2026).

Граница, которую здесь легко сломать тихо:

* пробник 8–10 ведут сотрудники — файл на группу, ручной ввод, история
  в карточке, — а домен «экзамены» у 8–10 закрыт: официальную попытку
  ученику 8–10 не завести ни формой, ни пачкой;
* ученик 8–10 по-прежнему не видит раздела экзаменов: маршрут попыток
  отвечает ему 403 `parallel_closed`, и пробник он не вносит никогда;
* чужой группе куратора — 404, как везде;
* у 11 всё прежнее.
"""

from __future__ import annotations

import datetime as dt

import pytest
from rest_framework.test import APIClient

from accounts.curators import assign
from accounts.models import User
from students.models import AttemptFormat, ExamAttempt, MockImport, StudyGroup
from students.tests.test_mock_import_and_ielts_sections import MOCK_DATE, days, ielts_file, make_student, wizard


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def lisbon(db) -> StudyGroup:
    return StudyGroup.objects.create(code="LISBON", parallel=9)


@pytest.fixture
def boston(db) -> StudyGroup:
    return StudyGroup.objects.create(code="BOSTON", parallel=10)


@pytest.fixture
def chicago(db) -> StudyGroup:
    return StudyGroup.objects.create(code="CHICAGO", parallel=11)


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin", "admin.mocks@example.kz", full_name="Администратор")


@pytest.fixture
def kymbat(make_user) -> User:
    return make_user("director_exam", "kymbat.mocks@example.kz", full_name="Кымбат")


@pytest.fixture
def boston_curator(make_user, boston, admin) -> User:
    user = make_user("curator", "boston.curator@example.kz", full_name="Куратор Бостона")
    assign(group=boston, curator=user, since=days(-30), actor=admin)
    return user


@pytest.fixture
def chicago_curator(make_user, chicago, admin) -> User:
    user = make_user("curator", "chicago.curator@example.kz", full_name="Куратор Чикаго")
    assign(group=chicago, curator=user, since=days(-30), actor=admin)
    return user


@pytest.fixture
def ninth(lisbon, make_user):
    return make_student(lisbon, "Сериков", "Данияр", "ninth.mocks@example.kz", make_user)


@pytest.fixture
def tenth(boston, make_user):
    return make_student(boston, "Ержанова", "Малика", "tenth.mocks@example.kz", make_user)


@pytest.fixture
def eleventh(chicago, make_user):
    return make_student(chicago, "Оспанов", "Тимур", "eleventh.mocks@example.kz", make_user)


def mock_body(student, **extra) -> dict:
    return {
        "student": student.pk,
        "exam_type": "IELTS",
        "attempt_format": "mock",
        "date": str(MOCK_DATE),
        "total_score": "6.0",
        **extra,
    }


@pytest.mark.django_db
def test_kymbat_uploads_a_mock_file_for_a_ninth_grade_group(ninth, kymbat, chicago):
    """Файл пробника на группу 9 параллели: группа в выборе, попытки легли пробниками."""
    student, _ = ninth
    boss = login(kymbat)

    listing = boss.get("/api/mock-imports/").json()
    assert {row["code"]: row["parallel"] for row in listing["groups"]} == {"LISBON": 9, "CHICAGO": 11}

    rows = [["Сериков Данияр", 6.5, 7.0, 6.0, 6.5, 6.5, ""]]
    preview = wizard(boss, file=ielts_file(rows), group="LISBON")
    assert preview.status_code == 200, preview.content
    assert preview.json()["counts"]["ready"] == 1

    applied = wizard(boss, file=ielts_file(rows), group="LISBON", step="apply")
    assert applied.status_code == 201, applied.content
    attempt = ExamAttempt.objects.get(student=student)
    assert attempt.attempt_format == AttemptFormat.MOCK and float(attempt.total_score) == 6.5
    assert attempt.mock_import.group.code == "LISBON"

    # задач у 8–10 нет: напомнить о пробнике задачей нечем
    record = applied.json()["import"]
    assert boss.get(f"/api/mock-imports/{record}/").json()["may_remind"] is False
    assert boss.post(f"/api/mock-imports/{record}/remind/", {}, format="json").status_code == 400
    # история пробников — в списке попыток ученика у сотрудника
    rows = boss.get("/api/attempts/", {"student": student.pk, "attempt_format": "mock"}).json()["results"]
    assert [row["id"] for row in rows] == [attempt.pk]


@pytest.mark.django_db
def test_admin_uploads_for_a_tenth_grade_group_and_curator_uploads_nothing(tenth, admin, boston_curator):
    """Администратор — в любую группу; куратору загрузка файлом закрыта и у своей 10-й."""
    rows = [["Ержанова Малика", 5.5, 5.5, 5.5, 6.0, 5.5, ""]]
    made = wizard(login(admin), file=ielts_file(rows), group="BOSTON", step="apply")
    assert made.status_code == 201, made.content
    assert wizard(login(boston_curator), file=ielts_file(rows), group="BOSTON").status_code == 403
    assert MockImport.objects.count() == 1


@pytest.mark.django_db
def test_curator_enters_a_mock_for_a_tenth_grade_student_by_hand(tenth, boston_curator):
    """Куратор группы 10 параллели вносит пробник руками, правит и убирает; официальный — нет."""
    student, _ = tenth
    own = login(boston_curator)

    made = own.post("/api/attempts/", mock_body(student), format="json")
    assert made.status_code == 201, made.content
    row = ExamAttempt.objects.get(pk=made.json()["id"])
    assert row.attempt_format == AttemptFormat.MOCK and row.mock_import_id is None

    card = own.get(f"/api/curator/students/{student.pk}/").json()
    assert card["has_admission"] is False and card["admission"] is None
    assert [mock["id"] for mock in card["mocks"]] == [row.pk]
    assert card["exams"]["mocks_total"] == 1

    assert own.patch(f"/api/attempts/{row.pk}/", {"total_score": "6.5"}, format="json").status_code == 200
    # официальных попыток у 8–10 нет — ни новой, ни переделкой пробника
    official = own.post("/api/attempts/", mock_body(student, attempt_format="official"), format="json")
    assert official.status_code == 400 and "attempt_format" in official.json()
    assert own.delete(f"/api/attempts/{row.pk}/").status_code in (200, 204)
    assert not ExamAttempt.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
def test_curator_of_another_group_gets_404(tenth, chicago_curator):
    """Чужой куратору ученик 10 параллели — 404, ни пробником, ни официальным."""
    student, _ = tenth
    other = login(chicago_curator)
    assert other.post("/api/attempts/", mock_body(student), format="json").status_code == 404
    assert other.post("/api/attempts/", mock_body(student, attempt_format="official"), format="json").status_code == 404
    assert other.get(f"/api/curator/students/{student.pk}/").status_code == 404
    assert not ExamAttempt.objects.exists()


@pytest.mark.django_db
def test_kymbat_keeps_only_mocks_for_juniors(ninth, eleventh, kymbat):
    """Кымбат: пробник 9-й — да, официальный 9-й — нет ни формой, ни пачкой; у 11 — как прежде."""
    junior, _ = ninth
    graduate, _ = eleventh
    boss = login(kymbat)

    assert boss.post("/api/attempts/", mock_body(junior), format="json").status_code == 201
    refused = boss.post("/api/attempts/", mock_body(junior, attempt_format="official"), format="json")
    assert refused.status_code == 400
    mock = ExamAttempt.objects.get(student=junior)
    turned = boss.patch(f"/api/attempts/{mock.pk}/", {"attempt_format": "official"}, format="json")
    assert turned.status_code == 400

    bulk = boss.post(
        "/api/attempts/bulk/",
        {
            "rows": [
                {**mock_body(junior, attempt_format="official")},
                {**mock_body(graduate, attempt_format="official")},
            ]
        },
        format="json",
    )
    assert bulk.status_code == 200, bulk.content
    assert bulk.json()["created"] == 1
    assert [row["row"] for row in bulk.json()["rejected"]] == [1]

    # у 11 — прежнее: и официальная попытка, и пробник
    assert boss.post("/api/attempts/", mock_body(graduate, attempt_format="official"), format="json").status_code == 201
    assert (
        boss.post(
            "/api/attempts/", mock_body(graduate, date=str(MOCK_DATE - dt.timedelta(days=1))), format="json"
        ).status_code
        == 201
    )
    assert ExamAttempt.objects.filter(student=graduate, attempt_format=AttemptFormat.OFFICIAL).count() == 2


@pytest.mark.django_db
def test_junior_student_still_has_no_exam_section(tenth, boston_curator):
    """Ученик 8–10: маршрут попыток — 403 `parallel_closed`, даже когда пробник у него есть."""
    student, user = tenth
    assert login(boston_curator).post("/api/attempts/", mock_body(student), format="json").status_code == 201
    mine = login(user)

    listing = mine.get("/api/attempts/")
    assert listing.status_code == 403 and listing.json()["code"] == "parallel_closed"
    made = mine.post("/api/attempts/", mock_body(student), format="json")
    assert made.status_code == 403 and made.json()["code"] == "parallel_closed"
    me = mine.get("/api/students/me/").json()
    assert "exam" not in me and me["readiness"] is None
    assert mine.get("/api/mock-imports/").status_code == 403
    assert ExamAttempt.objects.filter(student=student).count() == 1
