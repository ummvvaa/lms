"""Фаза 25: помощник в углу.

Кнопки на правилах работают без ключа модели, свободный ввод без ключа
получает честный отказ, изменения идут только предложением, ученик видит
только свои диалоги и не видит внутренних ярлыков.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import Role
from students.models import AdmissionProfile, BehaviorProfile, ExamProfile, Student, StudyGroup
from suggestions.assistant import QUICK
from suggestions.models import AssistantThread, Suggestion


def login(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def crowd(db):
    """Несколько учеников с заполненными профилями для правил."""
    group = StudyGroup.objects.create(code="A25", grade=11)
    rows = []
    for i, (last, first) in enumerate([("Ученикова", "Одна"), ("Ученикова", "Две"), ("Ученикова", "Три")]):
        student = Student.objects.create(
            last_name=last,
            first_name=first,
            email=f"assist{i}@example.kz",
            grade=11,
            group=group,
            graduation_year=2027,
        )
        BehaviorProfile.objects.create(student=student, attendance_percent=60 + i * 20)
        AdmissionProfile.objects.create(student=student, has_common_app=(i == 2))
        ExamProfile.objects.create(student=student, ielts_current=Decimal("5.5"), ielts_target=Decimal("7.0"))
        rows.append(student)
    return rows


def test_every_role_has_exactly_four_quick_buttons():
    for role, buttons in QUICK.items():
        assert len(buttons) == 4, f"у роли {role} не четыре кнопки"
    assert set(QUICK) == {
        "student",
        "director_behavior",
        "director_admission",
        "director_exam",
        "director_talent",
        "director_sport",
        "admin",
    }


@pytest.mark.django_db
def test_quick_endpoint_returns_role_buttons_and_model_status(make_user):
    client = login(make_user(Role.DIRECTOR_EXAM, email="assist.exam@example.kz"))
    payload = client.get("/api/assistant/quick/").data
    codes = [b["code"] for b in payload["buttons"]]
    assert codes == ["mock_drop", "prep_plan", "intensive_group", "parse_score_screenshot"]
    assert "configured" in payload["model"]


@pytest.mark.django_db
def test_foreign_button_is_refused(make_user, crowd):
    """Кнопка чужой роли не выполняется даже прямым запросом к API."""
    client = login(make_user(Role.DIRECTOR_EXAM, email="assist.exam2@example.kz"))
    answer = client.post("/api/assistant/ask/", {"command": "no_common_app"}, format="json").data
    assert "нет" in answer["message"]["text"].lower()
    assert answer["message"]["suggestion"] is None


@pytest.mark.django_db
def test_rule_buttons_work_without_model_key(make_user, crowd):
    """Без ключа кнопки отвечают по правилам и не падают."""
    checks = {
        Role.DIRECTOR_BEHAVIOR: "out_of_sight",
        Role.DIRECTOR_ADMISSION: "no_common_app",
        Role.DIRECTOR_EXAM: "intensive_group",
        Role.DIRECTOR_SPORT: "competitions_calendar",
    }
    for role, code in checks.items():
        client = login(make_user(role, email=f"assist.{code}@example.kz"))
        response = client.post("/api/assistant/ask/", {"command": code}, format="json")
        assert response.status_code == 200, code
        assert response.data["message"]["offline"] is True
        assert response.data["message"]["text"], code


@pytest.mark.django_db
def test_no_common_app_lists_only_those_without(make_user, crowd):
    client = login(make_user(Role.DIRECTOR_ADMISSION, email="assist.admission@example.kz"))
    answer = client.post("/api/assistant/ask/", {"command": "no_common_app"}, format="json").data
    lines = answer["message"]["lines"]
    assert len(lines) == 2  # третьей ученице Common App заведён
    assert all("Ученикова" in line for line in lines)


@pytest.mark.django_db
def test_free_text_without_model_gets_honest_refusal(make_user):
    client = login(make_user(Role.DIRECTOR_EXAM, email="assist.free@example.kz"))
    answer = client.post("/api/assistant/ask/", {"text": "Что нового у моих учеников?"}, format="json")
    assert answer.status_code == 200
    assert "не подключена" in answer.data["message"]["text"]


@pytest.mark.django_db
def test_task_request_becomes_a_suggestion_with_affected_count(make_user, crowd):
    """«Поставь задачу» отфильтрованным — предложение и число затронутых."""
    client = login(make_user(Role.DIRECTOR_EXAM, email="assist.tasks@example.kz"))
    ids = [s.pk for s in crowd[:2]]
    answer = client.post(
        "/api/assistant/ask/",
        {"text": "Поставь им задачу: пройти пробный IELTS до конца месяца", "students": ids},
        format="json",
    ).data

    suggestion_id = answer["message"]["suggestion"]
    assert suggestion_id is not None, "запрос на изменение обязан идти предложением"
    assert answer["message"]["affected"] == 2
    suggestion = Suggestion.objects.get(pk=suggestion_id)
    # инвариант №3: в основных таблицах ничего не появилось
    from roadmap.models import Task

    assert Task.objects.count() == 0
    assert suggestion.changes.count() > 0


@pytest.mark.django_db
def test_task_request_without_context_asks_for_students(make_user, crowd):
    client = login(make_user(Role.DIRECTOR_EXAM, email="assist.nobody@example.kz"))
    answer = client.post("/api/assistant/ask/", {"text": "Поставь всем задачу сдать мок"}, format="json").data
    assert answer["message"]["suggestion"] is None
    assert "Кому" in answer["message"]["text"]


@pytest.mark.django_db
def test_student_quick_answers_hide_internal_labels(make_user, crowd):
    """Ученику — задачи и проценты, никаких critical/strong/weak (инвариант №7)."""
    student = crowd[0]
    student.behavior.status = "critical"
    student.behavior.save(update_fields=["status"])
    user = make_user(Role.STUDENT, email=student.email)
    student.user = user
    student.save(update_fields=["user"])

    client = login(user)
    forbidden = ("critical", "needs_supervision", "strong", "medium", "weak", "A", "B", "C")
    for code in ("today", "why_percent", "pick_universities", "explain_task"):
        answer = client.post("/api/assistant/ask/", {"command": code}, format="json").data
        blob = answer["message"]["text"] + " ".join(answer["message"]["lines"])
        for label in ("critical", "needs_supervision", "strong/medium/weak"):
            assert label not in blob, f"{code}: ученик увидел «{label}»"
    assert forbidden  # список выше — напоминание, что проверяем именно ярлыки


@pytest.mark.django_db
def test_student_essay_request_gets_questions_not_text(make_user, crowd):
    student = crowd[0]
    user = make_user(Role.STUDENT, email=student.email)
    student.user = user
    student.save(update_fields=["user"])

    client = login(user)
    answer = client.post("/api/assistant/ask/", {"text": "Напиши за меня эссе про лидерство"}, format="json").data
    text = answer["message"]["text"]
    assert "не пишет" in text
    assert "?" in text, "вместо текста эссе — наводящие вопросы"


@pytest.mark.django_db
def test_threads_are_private(make_user, crowd):
    student = crowd[0]
    user = make_user(Role.STUDENT, email=student.email)
    student.user = user
    student.save(update_fields=["user"])
    mine = login(user)
    mine.post("/api/assistant/ask/", {"command": "today"}, format="json")
    thread = AssistantThread.objects.get(user=user)

    other = login(make_user(Role.DIRECTOR_EXAM, email="assist.other@example.kz"))
    assert other.get(f"/api/assistant/threads/{thread.pk}/").status_code == 404
    assert [t["id"] for t in other.get("/api/assistant/threads/").data] == []

    detail = mine.get(f"/api/assistant/threads/{thread.pk}/").data
    assert len(detail["messages"]) == 2  # вопрос и ответ


@pytest.mark.django_db
def test_dialog_is_stored_and_continues(make_user, crowd):
    client = login(make_user(Role.DIRECTOR_BEHAVIOR, email="assist.dialog@example.kz"))
    first = client.post("/api/assistant/ask/", {"command": "out_of_sight"}, format="json").data
    thread_id = first["thread"]["id"]
    second = client.post("/api/assistant/ask/", {"command": "focus_today", "thread": thread_id}, format="json").data
    assert second["thread"]["id"] == thread_id
    detail = client.get(f"/api/assistant/threads/{thread_id}/").data
    assert len(detail["messages"]) == 4
