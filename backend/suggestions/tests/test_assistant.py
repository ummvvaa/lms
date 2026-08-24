"""Фаза 25: помощник в углу.

Кнопки на правилах работают без ключа модели, свободный ввод без ключа
получает честный отказ, изменения идут только предложением, ученик видит
только свои диалоги и не видит внутренних ярлыков.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings
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


# --- Фаза 28: кнопки идут через модель, правила — запасной путь ------------


LIVE_LLM = {
    "PROVIDER": "anthropic",
    "API_KEY": "test-key",
    "BASE_URL": "https://api.example",
    "MODEL": "claude-sonnet-5",
    "TIMEOUT": 5,
    "RETRIES": 0,
    "RETRY_DELAY": 0,
    "NO_RETENTION": True,
    "SEARCH": False,
    "SEARCH_MAX_USES": 0,
}


class _Answer:
    """Ответ провайдера, каким его отдаёт Messages API."""

    def __init__(self, text: str) -> None:
        self.payload = {
            "id": "msg_1",
            "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 300, "output_tokens": 80},
        }
        self.status_code = 200

    def json(self) -> dict:
        return self.payload


@pytest.fixture
def model_says(monkeypatch):
    """Подменить HTTP-слой провайдера и запомнить, что ушло в модель."""
    box: dict = {}

    def install(text: str):
        def fake_post(url, json=None, headers=None, timeout=None):
            box["json"] = json
            return _Answer(text)

        import requests

        monkeypatch.setattr(requests, "post", fake_post)
        return box

    return install


@pytest.mark.django_db
@override_settings(LLM=LIVE_LLM)
def test_quick_button_goes_through_the_model(make_user, crowd, model_says):
    """С ключом кнопка отвечает моделью, и вызов виден в журнале расходов."""
    from suggestions.models import LLMCall

    model_says("Двое просели по посещаемости — начните с ученика 1.")
    client = login(make_user(Role.DIRECTOR_BEHAVIOR, email="assist.voice@example.kz"))

    answer = client.post("/api/assistant/ask/", {"command": "out_of_sight"}, format="json").data

    assert answer["message"]["offline"] is False
    assert "просели" in answer["message"]["text"]
    call = LLMCall.objects.latest("created_at")
    assert call.purpose == "assistant_quick"
    assert call.cost > 0


@pytest.mark.django_db
@override_settings(LLM=LIVE_LLM)
def test_names_are_hidden_from_the_model_and_returned_in_the_answer(make_user, crowd, model_says):
    """В модель уходят номера, а человек читает имена (решение фазы 20)."""
    box = model_says("Начните с ученика 2 — у него ниже всех посещаемость. И с ученика 9 тоже.")
    client = login(make_user(Role.DIRECTOR_BEHAVIOR, email="assist.hide@example.kz"))

    answer = client.post("/api/assistant/ask/", {"command": "out_of_sight"}, format="json").data

    sent = str(box["json"])
    assert "Ученикова" not in sent, "имя ученика ушло в модель"
    assert "ученик 2" in sent.lower()

    text = answer["message"]["text"]
    assert "Ученикова" in text, "имя не вернулось в ответ"
    # номер, которого в фактах не было, модель назвала сама — фамилию
    # туда подставлять нельзя: она была бы взята из воздуха
    assert "ученика 9" in text


@pytest.mark.django_db
@override_settings(LLM=LIVE_LLM)
def test_empty_model_answer_falls_back_to_rules(make_user, crowd, model_says):
    """Модель промолчала — отвечают правила, и это названо своим именем."""
    model_says("")
    client = login(make_user(Role.DIRECTOR_BEHAVIOR, email="assist.empty@example.kz"))

    answer = client.post("/api/assistant/ask/", {"command": "out_of_sight"}, format="json").data

    assert answer["message"]["offline"] is True
    assert answer["message"]["text"]
    assert "упрощённ" in answer["note"].lower()
    assert "не ответила" in answer["note"]


@pytest.mark.django_db
def test_without_a_key_the_button_says_it_works_in_a_simple_mode(make_user, crowd):
    """Без ключа кнопка отвечает правилами — и сообщает, почему проще."""
    client = login(make_user(Role.DIRECTOR_BEHAVIOR, email="assist.simple@example.kz"))

    answer = client.post("/api/assistant/ask/", {"command": "out_of_sight"}, format="json").data

    assert answer["message"]["offline"] is True
    assert "упрощённ" in answer["note"].lower()
    assert "не подключена" in answer["note"]


@pytest.mark.django_db
def test_answers_do_not_dump_long_lists(make_user, db):
    """Ответ — это вывод, а не выгрузка: длинный список сворачивается."""
    group = StudyGroup.objects.create(code="B25", grade=11)
    for i in range(12):
        student = Student.objects.create(
            last_name=f"Длинный{i}",
            first_name="Список",
            email=f"long{i}@school.kz",
            grade=11,
            group=group,
            graduation_year=2027,
        )
        BehaviorProfile.objects.create(student=student, attendance_percent=50)

    client = login(make_user(Role.DIRECTOR_BEHAVIOR, email="assist.long@example.kz"))
    answer = client.post("/api/assistant/ask/", {"command": "out_of_sight"}, format="json").data

    lines = answer["message"]["lines"]
    assert len(lines) <= 6, lines
    assert "ещё" in lines[-1]
