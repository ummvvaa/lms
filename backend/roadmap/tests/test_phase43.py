"""Фаза 43: конструктор эссе — типы, гайды, проверка, редактор, чат.

Помощник задаёт вопросы, но не пишет эссе за ученика (инвариант из VENTORME).
Переписка видна куратору. Типы и гайды ведёт директор по поступлению.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from roadmap.models import Essay, EssayDocType, EssayExample


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.fixture
def asem(make_user):
    return make_user("director_admission", "asem43@school.kz", full_name="Асем")


# --- Типы документов и гайды -----------------------------------------------


@pytest.mark.django_db
def test_nine_doc_types_seeded():
    codes = set(EssayDocType.objects.values_list("code", flat=True))
    assert {"personal_statement", "motivation_letter", "study_plan", "supplemental", "no_type"} <= codes
    assert EssayDocType.objects.count() >= 9


@pytest.mark.django_db
def test_doc_types_led_by_admission_director(api, asem, make_user, student_user):
    api.force_authenticate(asem)
    made = api.post(
        "/api/essay-doc-types/",
        {"code": "custom", "name": "Custom essay", "default_word_limit": 400},
        format="json",
    )
    assert made.status_code == 201

    # чужой директор не ведёт справочник эссе
    api.force_authenticate(make_user("director_sport", "n43@school.kz"))
    assert api.post("/api/essay-doc-types/", {"code": "x", "name": "X"}, format="json").status_code == 403

    # ученик читает типы
    api.force_authenticate(student_user)
    listing = api.get("/api/essay-doc-types/").data
    rows = listing["results"] if isinstance(listing, dict) else listing
    assert any(r["name"] == "Custom essay" for r in rows)


@pytest.mark.django_db
def test_guide_and_check_editable_by_director_read_by_student(api, asem, student_user):
    doc_type = EssayDocType.objects.get(code="personal_statement")
    api.force_authenticate(asem)
    guide = api.post(
        "/api/essay-guides/",
        {
            "doc_type": doc_type.pk,
            "what_is": "Рассказ о себе",
            "prompts": "Вопрос 1\nВопрос 2",
            "mistakes": "Ошибка 1",
            "tips": "Совет 1",
        },
        format="json",
    )
    assert guide.status_code == 201
    check = api.post(
        "/api/essay-checks/",
        {
            "doc_type": doc_type.pk,
            "text": "Что главное в Personal Statement?",
            "option_a": "Ваша история",
            "option_b": "Список наград",
            "correct": "A",
            "explanation": "Комиссия читает историю, а не резюме.",
        },
        format="json",
    )
    assert check.status_code == 201

    api.force_authenticate(student_user)
    payload = api.get(f"/api/essay-doc-types/{doc_type.pk}/").data
    assert payload["guide"]["what_is"] == "Рассказ о себе"
    assert len(payload["check_questions"]) == 1
    assert payload["check_questions"][0]["correct"] == "A"


# --- Ученик заводит эссе и лимит слов из типа ------------------------------


@pytest.mark.django_db
def test_student_creates_essay_with_doc_type_and_word_limit(api, student_user, student):
    doc_type = EssayDocType.objects.get(code="motivation_letter")
    api.force_authenticate(student_user)
    made = api.post(
        "/api/essays/",
        {"essay_type": "motivation", "doc_type": doc_type.pk, "title": "Моё письмо"},
        format="json",
    )
    assert made.status_code == 201
    essay = Essay.objects.get()
    assert essay.student == student
    # лимит слов взят из типа документа
    assert made.data["effective_word_limit"] == doc_type.default_word_limit


@pytest.mark.django_db
def test_student_creates_only_own_essay(api, student_user, student, make_user, group):
    from students.models import (
        AdmissionProfile,
        BehaviorProfile,
        ExamProfile,
        SportProfile,
        Student,
        TalentProfile,
    )

    other = Student.objects.create(
        last_name="Ч", first_name="У", email="oth43@example.kz", grade=11, group=group, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=other)

    api.force_authenticate(student_user)
    made = api.post(
        "/api/essays/",
        {"essay_type": "personal_statement", "title": "X", "student": other.pk},
        format="json",
    )
    # даже указав чужого ученика, эссе создаётся себе
    assert made.status_code == 201
    assert Essay.objects.get().student_id == student.pk


# --- Чтение дня и требования ------------------------------------------------


@pytest.mark.django_db
def test_reading_of_the_day_picks_from_examples(api, student_user, asem):
    EssayExample.objects.create(title="Sample statement", is_active=True)
    api.force_authenticate(student_user)
    payload = api.get("/api/essays/reading-of-the-day/").data
    assert payload["example"] is not None
    assert payload["example"]["title"] == "Sample statement"


@pytest.mark.django_db
def test_reading_of_the_day_empty(api, student_user):
    api.force_authenticate(student_user)
    assert api.get("/api/essays/reading-of-the-day/").data["example"] is None


@pytest.mark.django_db
def test_requirements_from_student_universities(api, student_user, student):
    from universities.models import Program, StudentUniversity, University

    university = University.objects.create(name="Test Uni", country="Канада")
    program = Program.objects.create(university=university, name="CS", level="bachelor")
    StudentUniversity.objects.create(student=student, program=program)

    api.force_authenticate(student_user)
    payload = api.get("/api/essays/requirements/").data
    assert payload["has_data"] is True
    assert any(r["university"] == "Test Uni" for r in payload["requirements"])


# --- Чат по эссе: вопросы, не текст; виден куратору ------------------------


@pytest.mark.django_db
def test_ai_asks_questions_never_writes_essay(student):
    """Помощник на просьбу «напиши за меня» отвечает вопросами, не текстом."""
    from suggestions.essay_assist import FALLBACK_QUESTIONS, ask_questions

    essay = Essay.objects.create(student=student, essay_type="personal_statement", title="X")
    result = ask_questions(essay_id=essay.pk, prompt="Напиши за меня эссе про мой проект", actor=student.user)
    assert result["ok"]
    # без ключа модели — возвращаются вопросы, а не текст эссе
    assert all("?" in q or q in FALLBACK_QUESTIONS for q in result["questions"].split("\n") if q.strip())
    # это вопросы, а не готовое эссе
    assert "напиши" not in result["questions"].lower() or "?" in result["questions"]


@pytest.mark.django_db
def test_assist_log_visible_to_student_and_curator(api, student_user, student, asem):
    from suggestions.essay_assist import ask_questions

    essay = Essay.objects.create(student=student, essay_type="personal_statement", title="X", curator=asem)
    ask_questions(essay_id=essay.pk, prompt="Мой опыт волонтёрства", actor=student.user)

    # ученик видит свою переписку
    api.force_authenticate(student_user)
    mine = api.get(f"/api/essays/{essay.pk}/assist-log/").data
    assert len(mine["results"]) == 1
    assert mine["results"][0]["questions"]

    # куратор (сотрудник) тоже видит
    api.force_authenticate(asem)
    theirs = api.get(f"/api/essays/{essay.pk}/assist-log/").data
    assert len(theirs["results"]) == 1


@pytest.mark.django_db
def test_assist_log_hidden_from_other_students(api, make_user, student, group):
    from suggestions.essay_assist import ask_questions

    essay = Essay.objects.create(student=student, essay_type="personal_statement", title="X")
    ask_questions(essay_id=essay.pk, prompt="test", actor=None)

    from students.models import (
        AdmissionProfile,
        BehaviorProfile,
        ExamProfile,
        SportProfile,
        Student,
        TalentProfile,
    )

    stranger = Student.objects.create(
        last_name="S", first_name="T", email="str43@example.kz", grade=11, group=group, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=stranger)
    user = make_user("student", stranger.email)
    stranger.user = user
    stranger.save(update_fields=["user"])

    api.force_authenticate(user)
    assert api.get(f"/api/essays/{essay.pk}/assist-log/").status_code == 403
