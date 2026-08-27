"""Фаза 15: понятность — границы значений, ошибки импорта, «Начало работы».

Проверяем не тексты ради текстов, а то, что отказ называет строку,
колонку и допустимый диапазон, а одна кривая клетка не отменяет файл.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.passwords import set_password
from core.audit import ValueRejected, coerce
from core.domains import spec_of_field
from core.onboarding import build as build_checklist
from students.import_service import apply_preview, build_preview
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)

PASSWORD = "Понятность!Проверка2026"


@pytest.fixture
def learners(db) -> list[Student]:
    people = []
    for i in range(3):
        person = Student.objects.create(
            last_name=f"Ученик{i}", first_name="Тест", email=f"clear{i}@school.kz", grade=11, graduation_year=2027
        )
        for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
            model.objects.create(student=person)
        people.append(person)
    return people


def make_user(email: str, role: str) -> User:
    user = User.objects.create_user(email=email, password=None, role=role)
    set_password(user, PASSWORD)
    return user


def login(user: User) -> APIClient:
    client = APIClient()
    client.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    return client


# --- границы значений -----------------------------------------------------


@pytest.mark.django_db
def test_out_of_scale_value_is_refused_with_the_scale_named():
    with pytest.raises(ValueRejected) as error:
        coerce(ExamProfile(), "ielts_current", "12.5")

    text = str(error.value)
    assert "12.5" in text
    assert "9" in text
    assert "максимальный балл" in text
    # ни кода ошибки, ни английского
    assert "ValidationError" not in text


@pytest.mark.django_db
def test_value_at_the_edge_of_the_scale_passes():
    assert coerce(ExamProfile(), "ielts_current", "9") == Decimal("9.0")
    assert coerce(ExamProfile(), "ielts_current", "0") == Decimal("0.0")


def test_range_hint_reads_like_russian():
    assert spec_of_field("students.ExamProfile", "ielts_current").range_hint == "от 0 до 9 баллов"
    assert spec_of_field("students.BehaviorProfile", "attendance_percent").range_hint == "от 0 до 100%"


def test_registry_has_no_english_left_in_titles():
    """Подписи полей — по-русски, кроме названий экзаменов и терминов."""
    from core.domains import iter_field_specs

    allowed = {
        "IELTS",
        "TOEFL",
        "SAT",
        "ACT",
        "GPA",
        "Common App",
        "Listening",
        "Reading",
        "Writing",
        "Speaking",
        "Math",
        "Verbal",
    }
    for _domain, _model, spec in iter_field_specs():
        words = [w for w in spec.title.replace(",", " ").split() if w.isascii() and w.isalpha()]
        for word in words:
            assert any(word in term for term in allowed), f"{spec.name}: английское слово «{word}» в подписи"


# --- ошибки импорта -------------------------------------------------------


def _preview(learners, values):
    header = ["email", "ielts"]
    rows = [[person.email, value] for person, value in zip(learners, values, strict=False)]
    return build_preview(
        header=header,
        rows=rows,
        mapping={"email": "student", "ielts": "students.ExamProfile.ielts_current"},
        domain_code="exam",
    )


@pytest.mark.django_db
def test_one_bad_row_does_not_reject_the_whole_file(learners):
    preview = _preview(learners, ["7.0", "12.5", "6.5"])
    payload = preview.as_dict()

    assert payload["broken"] == 1
    assert payload["ready"] == 2
    problem = payload["problems"][0]
    # строка, колонка, что не так и как исправить
    assert problem["row"] == 3
    assert problem["column"] == "ielts"
    assert "12.5" in problem["message"]
    assert problem["hint"] == "от 0 до 9 баллов"
    assert problem["student_name"] == learners[1].full_name


@pytest.mark.django_db
def test_correct_rows_apply_while_broken_ones_wait(learners):
    preview = _preview(learners, ["7.0", "12.5", "6.5"])
    director = make_user("clear.exam@school.kz", Role.DIRECTOR_EXAM)

    result = apply_preview(preview_rows=preview.ready_rows, domain_code="exam", actor=director, file_name="баллы.csv")

    assert result["applied"] == 2
    learners[0].exam.refresh_from_db()
    learners[1].exam.refresh_from_db()
    assert learners[0].exam.ielts_current == Decimal("7.0")
    # ошибочную строку не тронули
    assert learners[1].exam.ielts_current is None


@pytest.mark.django_db
def test_missing_key_column_explains_what_to_pick(learners):
    preview = build_preview(
        header=["email", "ielts"],
        rows=[["a@b.kz", "7.0"]],
        mapping={"ielts": "students.ExamProfile.ielts_current"},
        domain_code="exam",
    )
    assert any("Ученик (email)" in message for message in preview.errors)


@pytest.mark.django_db
def test_foreign_column_suggests_picking_another_field(learners):
    preview = build_preview(
        header=["email", "посещаемость"],
        rows=[[learners[0].email, "90"]],
        mapping={"email": "student", "посещаемость": "students.BehaviorProfile.attendance_percent"},
        domain_code="exam",
    )
    assert any("не из домена" in message for message in preview.errors)
    assert any("Выберите" in message for message in preview.errors)


# --- «Начало работы» ------------------------------------------------------


@pytest.mark.django_db
def test_checklist_on_an_empty_school_says_nothing_is_done(db):
    director = make_user("clear.behavior@school.kz", Role.DIRECTOR_BEHAVIOR)

    checklist = build_checklist(director).as_dict()

    assert checklist["total"] > 0
    assert checklist["done"] == 0
    assert checklist["complete"] is False
    students_step = next(s for s in checklist["steps"] if s["code"] == "students")
    assert students_step["done"] is False
    # каждая строка ведёт на экран, где шаг и выполняется
    assert all(step["path"].startswith("/") for step in checklist["steps"])


@pytest.mark.django_db
def test_checklist_marks_students_done_once_they_appear(learners):
    director = make_user("clear.sport@school.kz", Role.DIRECTOR_SPORT)

    checklist = build_checklist(director).as_dict()

    students_step = next(s for s in checklist["steps"] if s["code"] == "students")
    assert students_step["done"] is True
    assert students_step["count"] == 3


@pytest.mark.django_db
def test_checklist_of_admission_director_covers_the_catalog(learners):
    director = make_user("clear.admission@school.kz", Role.DIRECTOR_ADMISSION)

    codes = [s["code"] for s in build_checklist(director).as_dict()["steps"]]

    assert "universities" in codes
    assert "requirements" in codes


@pytest.mark.django_db
def test_admin_checklist_counts_groups_and_users(learners):
    admin = make_user("clear.admin@school.kz", Role.ADMIN)
    StudyGroup.objects.create(code="11A", grade=11)

    checklist = build_checklist(admin).as_dict()

    groups_step = next(s for s in checklist["steps"] if s["code"] == "groups")
    assert groups_step["done"] is True


@pytest.mark.django_db
def test_checklist_endpoint_answers_for_every_role(learners):
    for email, role in (
        ("api.behavior@school.kz", Role.DIRECTOR_BEHAVIOR),
        ("api.admission@school.kz", Role.DIRECTOR_ADMISSION),
        ("api.exam@school.kz", Role.DIRECTOR_EXAM),
        ("api.talent@school.kz", Role.DIRECTOR_TALENT),
        ("api.sport@school.kz", Role.DIRECTOR_SPORT),
        ("api.admin@school.kz", Role.ADMIN),
    ):
        response = login(make_user(email, role)).get("/api/getting-started/")
        assert response.status_code == 200, role
        assert response.data["total"] > 0, role
