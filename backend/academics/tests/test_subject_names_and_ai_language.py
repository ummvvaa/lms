"""Данные и ИИ на языке человека: название предмета и язык ответа модели.

Предмет показывается по-казахски или по-английски, если название внесено,
иначе по-русски; вносит его администратор или Кымбат в «Учебном году», рядом
с казахским. Модель отвечает на языке того, кто спросил: правило языка
добавляется к системному промпту, а запретные слова про «шанс поступления»
ловятся на всех трёх языках.
"""

from __future__ import annotations

import pytest
from django.utils import translation

from core.i18n import BANNED_ADMISSION_WORDS, answer_rule
from suggestions import llm
from suggestions.providers import Completion, Usage


def test_subject_name_follows_the_language(subjects):
    algebra = subjects["alg"]
    algebra.title_kk, algebra.title_en = "Алгебра (қаз)", "Algebra"
    with translation.override("kk"):
        assert (algebra.name, algebra.short) == ("Алгебра (қаз)", "Алгебра (қаз)")
    with translation.override("en"):
        assert (algebra.name, algebra.short) == ("Algebra", "Algebra")
    with translation.override("ru"):
        assert (algebra.name, algebra.short) == (algebra.title, algebra.short_title)
    algebra.title_en = ""
    with translation.override("en"):
        # английского названия нет — русское, и короткое тоже русское
        assert (algebra.name, algebra.short) == (algebra.title, algebra.short_title)


def test_english_names_are_edited_next_to_kazakh(subjects, as_kymbat, year):
    response = as_kymbat.patch(
        "/api/acad/year/",
        {"subjects": [{"code": "alg", "title_kk": "Алгебра (қаз)", "title_en": "Algebra"}]},
        format="json",
    )
    assert response.status_code == 200
    subjects["alg"].refresh_from_db()
    assert (subjects["alg"].title_kk, subjects["alg"].title_en) == ("Алгебра (қаз)", "Algebra")
    row = next(s for s in as_kymbat.get("/api/acad/year/").json()["subjects"] if s["code"] == "alg")
    assert row["title_en"] == "Algebra" and row["title_ru"] == subjects["alg"].title
    as_kymbat.patch("/api/auth/me/preferences/", {"language": "en"}, format="json")
    row = next(s for s in as_kymbat.get("/api/acad/year/").json()["subjects"] if s["code"] == "alg")
    assert row["title"] == "Algebra", "в интерфейсе на английском — английское название"


class RecordingProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def is_configured(self) -> bool:
        return True

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return Completion(
            content="ok", parsed=None, model="fake-1", external_id="m", usage=Usage(10, 5), raw={"id": "m"}
        )


@pytest.mark.django_db
def test_model_is_told_to_answer_in_the_language_of_the_person(monkeypatch):
    provider = RecordingProvider()
    monkeypatch.setattr("suggestions.llm.get_provider", lambda: provider)
    llm.complete(system="Правила.", user="Вопрос", purpose="test", language="kk")
    llm.complete(system="Правила.", user="Вопрос", purpose="test", language="en")
    llm.complete(system="Правила.", user="Вопрос", purpose="test")
    assert provider.calls[0]["system"].endswith(answer_rule("kk"))
    assert provider.calls[1]["system"].endswith(answer_rule("en"))
    # без языка — разбор файла или извлечение данных: промпт как есть
    assert provider.calls[2]["system"] == "Правила."


def test_admission_chance_words_are_caught_in_every_language():
    for text in ("шанс поступления 70%", "түсу мүмкіндігі жоғары", "your chance to get in", "admission probability"):
        assert BANNED_ADMISSION_WORDS.search(text), text
    assert not BANNED_ADMISSION_WORDS.search("соответствие требованиям 70%")
