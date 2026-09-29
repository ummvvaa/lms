"""Кабинет ученика 8–10: главная про учёбу и помощник без поступления.

Главная считает сервер: средний балл за четверть, посещаемость, ближайший
СОР, достижения, уроки сегодня, «Скоро», последние оценки. Помощник у 8–10
знает четыре кнопки про учёбу; кнопки поступления не выполняются и прямым
запросом, а в модель не уходит ни поступление, ни имена учителей.
"""

from __future__ import annotations

import pytest

from academics import marks as marking
from academics.calendar import scale_of
from academics.tests.conftest import login
from suggestions import assistant
from suggestions.llm import LLMUnavailable

pytestmark = pytest.mark.django_db


@pytest.fixture
def junior(boston, pupils, lesson, teacher, calendar):
    """Алия в девятой параллели, с оценкой и комментарием учителя по алгебре."""
    boston.parallel = 9
    boston.save(update_fields=["parallel"])
    marking.set_grade(
        lesson,
        pupils["aliya"],
        6,
        comment="Повторить формулы сокращённого умножения",
        actor=teacher,
        calendar=calendar,
        scale=scale_of(calendar.year),
    )
    return pupils["aliya"]


def test_home_counts_study_not_admission(junior):
    api = login(junior.user)
    home = api.get("/api/acad/me/home/")
    assert home.status_code == 200, home.content
    body = home.json()
    assert [kpi["code"] for kpi in body["kpis"]] == ["average", "attendance", "sor", "achievements"]
    assert body["recent"][0]["subject"] == "Алгебра"
    assert body["recent"][0]["value"] == 6
    text = str(body).lower()
    for word in ("ielts", "sat", "вуз", "готовност"):
        assert word not in text


def test_assistant_buttons_are_about_study(junior):
    api = login(junior.user)
    buttons = api.get("/api/assistant/quick/").json()["buttons"]
    assert [row["code"] for row in buttons] == ["week", "improve_subject", "quarter_formula", "soch_plan"]
    assert buttons[1]["hint"].startswith("Алгебра")

    refused = api.post("/api/assistant/ask/", {"command": "pick_universities"}, format="json").json()
    assert refused["message"]["text"] == "Такой кнопки у вашей роли нет."
    assert assistant.run_quick("why_percent", actor=junior.user, role="student")["text"].startswith("Такой кнопки")


def test_model_gets_own_marks_without_names_or_admission(junior, monkeypatch):
    sent: list[dict] = []

    def fake_complete(**kwargs):
        sent.append(kwargs)
        raise LLMUnavailable("нет модели")

    monkeypatch.setattr(assistant, "complete", fake_complete)
    answer = assistant.run_quick("improve_subject", actor=junior.user, role="student")
    facts = "\n".join([answer["text"], *answer["lines"]])
    assert "Алгебра" in facts
    assert "Повторить формулы сокращённого умножения" in facts
    assert "Сапарова" not in facts  # имя учителя в модель не уходит
    prompt = sent[0]["user"] + sent[0]["system"]
    assert "Сапарова" not in prompt
    assert "IELTS" in sent[0]["system"]  # только как запрет: «не упоминай IELTS и SAT»
    assert "IELTS" not in sent[0]["user"]

    monkeypatch.setattr(assistant, "is_configured", lambda: True)
    sent.clear()
    assistant.free_text(text="Как готовиться к контрольной?", actor=junior.user, role="student", screen="Оценки")
    assert sent[0]["user"] == "Экран: Оценки.\nКак готовиться к контрольной?"
    assert "8–10" in sent[0]["system"]


def test_quarter_formula_comes_from_the_school_scale(junior):
    answer = assistant.run_quick("quarter_formula", actor=junior.user, role="student")
    lines = "\n".join(answer["lines"])
    assert "вес 25%" in lines and "вес 50%" in lines
    assert "от 85% — 5" in lines
