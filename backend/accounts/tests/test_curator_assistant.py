"""Помощник у куратора: кнопки под его права и только ученики его групп.

Фикстуры — из матрицы прав куратора: две группы, по ученику в каждой,
куратор ведёт одну (CHICAGO). Модели нет — ответы собирают правила,
поэтому по тексту видно, о ком помощник говорил.
"""

# фикстуры берутся из матрицы прав куратора: параметры тестов их «переопределяют»
# ruff: noqa: F811
from __future__ import annotations

import pytest
from django.test import override_settings

from accounts.tests.test_curator_role_matrix import (  # noqa: F401 — фикстуры
    admin,
    api,
    as_curator,
    boston,
    chicago,
    curator,
    foreign,
    mine,
)
from suggestions import assistant

OFFLINE = {"PROVIDER": "none", "API_KEY": "", "SEARCH": False}


@pytest.mark.django_db
def test_curator_gets_four_buttons_of_his_own(as_curator):
    answer = as_curator.get("/api/assistant/quick/")
    assert answer.status_code == 200
    codes = [row["code"] for row in answer.json()["buttons"]]
    assert codes == ["focus_today", "group_summary", "out_of_sight", "deadlines_soon"]
    assert as_curator.get("/api/assistant/threads/").status_code == 200


@pytest.mark.django_db
@override_settings(LLM=OFFLINE)
def test_curator_quick_answers_speak_only_of_his_groups(as_curator, mine, foreign):
    for code in ("focus_today", "group_summary", "out_of_sight"):
        answer = as_curator.post("/api/assistant/ask/", {"command": code}, format="json")
        assert answer.status_code == 200, answer.content
        text = answer.content.decode()
        assert "Чужой" not in text, f"{code}: помощник заговорил о чужой группе"


@pytest.mark.django_db
def test_foreign_student_in_the_request_drops_out(curator, mine, foreign):
    assert assistant.curator_scope(curator, [mine.pk, foreign.pk]) == [mine.pk]
    assert assistant.curator_scope(curator, None) == [mine.pk]


@pytest.mark.django_db
@override_settings(LLM=OFFLINE)
def test_curator_is_sent_to_the_cabinet_for_tasks(as_curator, mine):
    answer = as_curator.post(
        "/api/assistant/ask/", {"text": "поставь задачу сдать транскрипт", "students": [mine.pk]}, format="json"
    )
    assert answer.status_code == 200
    assert "Задача группе" in answer.content.decode()
