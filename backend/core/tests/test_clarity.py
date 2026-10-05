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
from students import admission_import
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
            last_name=f"Ученик{i}", first_name="Тест", email=f"clear{i}@school.kz", graduation_year=2027
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
        # решение владельца (30.09.2026): «пробник» не используется ни в одном языке —
        # «Mock Test», как в шаблонах школы и отчётах
        "Mock Test",
    }
    for _domain, _model, spec in iter_field_specs():
        words = [w for w in spec.title.replace(",", " ").split() if w.isascii() and w.isalpha()]
        for word in words:
            assert any(word in term for term in allowed), f"{spec.name}: английское слово «{word}» в подписи"


# --- ошибки импорта -------------------------------------------------------


def _list_file(learners, values, header=("email", "ielts")):
    """Файл-список мастера импорта: ключ — почта, по строке на ученика."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    lines = [",".join(header)] + [
        ",".join([person.email, *value]) if isinstance(value, list | tuple) else f"{person.email},{value}"
        for person, value in zip(learners, values, strict=False)
    ]
    return SimpleUploadedFile("баллы.csv", ("\n".join(lines) + "\n").encode("utf-8"), content_type="text/csv")


def _skip_errors(sheets) -> dict:
    return {
        f"{sheet.name}:{row.index}": admission_import.Fix(skip=True)
        for sheet in sheets
        for row in sheet.rows
        if row.error
    }


@pytest.mark.django_db
def test_one_bad_row_does_not_reject_the_whole_file(learners):
    sheets = admission_import.parse(_list_file(learners, ["7.0", "12.5", "6.5"]))
    payload = admission_import.preview_payload(sheets)

    assert payload["counts"]["errors"] == 1
    assert payload["counts"]["ready"] == 2
    good, bad, _last = payload["sheets"][0]["rows"]
    # строка, поле, что не так и как исправить
    assert bad["index"] == 2 and not good["error"]
    assert "Текущий балл IELTS" in bad["error"] and "12.5" in bad["error"]
    assert "от 0 до 9 баллов" in bad["error"]
    assert bad["student_name"] == learners[1].full_name


@pytest.mark.django_db
def test_correct_rows_apply_while_broken_ones_wait(learners):
    director = make_user("clear.exam@school.kz", Role.DIRECTOR_EXAM)
    sheets = admission_import.parse(_list_file(learners, ["7.0", "12.5", "6.5"]), actor=director)

    record = admission_import.apply(
        _list_file(learners, ["7.0", "12.5", "6.5"]), actor=director, fixes=_skip_errors(sheets)
    )

    assert record.students_updated == 2 and record.rows_skipped == 1
    learners[0].exam.refresh_from_db()
    learners[1].exam.refresh_from_db()
    assert learners[0].exam.ielts_current == Decimal("7.0")
    # ошибочную строку не тронули
    assert learners[1].exam.ielts_current is None


@pytest.mark.django_db
def test_missing_key_column_explains_what_to_pick(learners):
    sheets = admission_import.parse(_list_file(learners, ["7.0"], header=("кто", "ielts")))
    assert "нет колонки «ФИО»" in sheets[0].error and "почтой или логином" in sheets[0].error
    # и мастер даёт её назначить: в списке выбора есть «Ученик (почта или логин)»
    titles = [row["title"] for row in admission_import.assignable_payload()]
    assert "Ученик (почта или логин)" in titles


@pytest.mark.django_db
def test_column_of_a_domain_that_was_not_chosen_is_named_in_the_report(learners):
    admin = make_user("clear.admin2@school.kz", Role.ADMIN)
    uploaded = _list_file(learners, [["7.0", "90"]], header=("email", "ielts", "Посещаемость занятий"))
    record = admission_import.apply(uploaded, actor=admin, domains=["exam"])
    learners[0].behavior.refresh_from_db()
    assert learners[0].behavior.attendance_percent != 90
    assert "пропущена: домен «Профиль и дисциплина» не выбран" in record.report


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
    # у выполненного шага — что уже есть, а не подсказка пустой школы (D81)
    assert students_step["hint"] == ""
    assert students_step["summary"] == "3 ученика"


@pytest.mark.django_db
def test_hint_of_the_empty_school_stays_only_at_the_undone_step():
    director = make_user("clear.hint@school.kz", Role.DIRECTOR_ADMISSION)

    steps = build_checklist(director).as_dict()["steps"]

    students_step = next(s for s in steps if s["code"] == "students")
    assert students_step["done"] is False
    assert "нет ни одного ученика" in students_step["hint"] and students_step["summary"] == ""
    # правило общее: подсказка — о том, что сделать, и у сделанного её нет
    assert all(step["hint"] for step in steps if not step["done"])
    assert not any(step["hint"] for step in steps if step["done"])


@pytest.mark.django_db
def test_checklist_of_admission_director_covers_the_catalog(learners):
    director = make_user("clear.admission@school.kz", Role.DIRECTOR_ADMISSION)

    codes = [s["code"] for s in build_checklist(director).as_dict()["steps"]]

    assert "universities" in codes
    assert "requirements" in codes


@pytest.mark.django_db
def test_admin_checklist_counts_groups_and_users(learners):
    admin = make_user("clear.admin@school.kz", Role.ADMIN)
    StudyGroup.objects.create(code="11A", parallel=11)

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
