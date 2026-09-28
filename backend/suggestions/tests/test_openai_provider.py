"""Провайдер OpenAI (Responses API): что уходит в запросе и что делается с ответом.

Настоящего провайдера нет — подменяется HTTP-слой, как в
`test_web_search_whitelist.py`. Проверяем границы, а не формулировки:
белый список поиска не расширяется и не режется молча, нехранение
уходит флагом `store`, рассуждению оставлен запас, деньги не повторяются.
Формат запроса и ответа — по документации OpenAI (Responses API,
Structured Outputs, Web search, Reasoning, Error codes).
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from suggestions import websearch
from suggestions.providers import (
    OPENAI_MAX_DOMAINS,
    Attachment,
    LLMUnavailable,
    OpenAIProvider,
    get_provider,
)

LIVE = {
    "PROVIDER": "openai",
    "API_KEY": "test-key",
    "BASE_URL": "https://api.example",
    "MODEL": "gpt-6-sol",
    "TIMEOUT": 5,
    "RETRIES": 0,
    "RETRY_DELAY": 0,
    "NO_RETENTION": True,
    "SEARCH": True,
    "SEARCH_MAX_USES": 5,
    "REASONING_EFFORT": "low",
    "REASONING_RESERVE": 25000,
}


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, headers: dict | None = None) -> None:
        self.payload, self.status_code, self.headers = payload, status_code, headers or {}

    def json(self) -> dict:
        return self.payload


def reply(*, text: str = "", searched: list[str] | None = None, cited: list[str] | None = None, **extra) -> dict:
    """Ответ в том виде, в каком его отдаёт Responses API."""
    output: list[dict] = []
    if searched is not None:
        output.append(
            {
                "type": "web_search_call",
                "id": "ws_1",
                "status": "completed",
                "action": {"type": "search", "query": "q", "sources": [{"type": "url", "url": u} for u in searched]},
            }
        )
    output.append(
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": text,
                    "annotations": [{"type": "url_citation", "url": u, "title": "стр."} for u in cited or []],
                }
            ],
        }
    )
    return {
        "id": "resp_1",
        "model": "gpt-6-sol",
        "status": "completed",
        "output": output,
        "usage": {"input_tokens": 1000, "output_tokens": 300, "output_tokens_details": {"reasoning_tokens": 100}},
        **extra,
    }


@pytest.fixture
def sent(monkeypatch):
    """Подменить HTTP: запомнить запрос и вернуть заготовленный ответ."""
    import requests

    def install(payload: dict, status_code: int = 200):
        box: dict = {"calls": 0}

        def fake(url, json=None, headers=None, timeout=None):
            box.update(url=url, json=json, headers=headers)
            box["calls"] += 1
            return FakeResponse(payload, status_code)

        monkeypatch.setattr(requests, "post", fake)
        return box

    return install


# --- Запрос ------------------------------------------------------------------


@override_settings(LLM=LIVE)
def test_request_goes_to_responses_api_with_bearer_key_and_instructions(sent):
    box = sent(reply(text="ок"))
    OpenAIProvider().complete(system="роль", user="вопрос", max_tokens=1500)

    assert box["url"] == "https://api.example/v1/responses"
    assert box["headers"]["Authorization"] == "Bearer test-key"
    body = box["json"]
    assert body["model"] == "gpt-6-sol"
    assert body["instructions"] == "роль"
    assert body["input"] == [{"role": "user", "content": [{"type": "input_text", "text": "вопрос"}]}]
    # рассуждение тратит тот же бюджет — к пределу операции добавлен запас
    assert body["max_output_tokens"] == 1500 + 25000
    assert body["reasoning"] == {"effort": "low"}
    # без поиска инструментов нет вовсе
    assert "tools" not in body


@override_settings(LLM=LIVE)
def test_no_retention_sends_store_false(sent):
    box = sent(reply(text="ок"))
    OpenAIProvider().complete(system="s", user="u")
    assert box["json"]["store"] is False


@override_settings(LLM={**LIVE, "NO_RETENTION": False})
def test_store_is_left_on_when_retention_is_not_forbidden(sent):
    box = sent(reply(text="ок"))
    OpenAIProvider().complete(system="s", user="u")
    assert box["json"]["store"] is True


@override_settings(LLM={**LIVE, "REASONING_EFFORT": ""})
def test_model_without_reasoning_gets_no_reasoning_field_and_no_reserve(sent):
    box = sent(reply(text="ок"))
    OpenAIProvider().complete(system="s", user="u", max_tokens=800)
    assert "reasoning" not in box["json"]
    assert box["json"]["max_output_tokens"] == 800


@override_settings(LLM=LIVE)
def test_image_goes_as_data_url_before_the_text(sent):
    box = sent(reply(text="ок"))
    OpenAIProvider().complete(system="s", user="что на фото", images=[Attachment(media_type="image/png", data="QUJD")])
    parts = box["json"]["input"][0]["content"]
    assert parts[0] == {"type": "input_image", "image_url": "data:image/png;base64,QUJD"}
    assert parts[-1] == {"type": "input_text", "text": "что на фото"}


@override_settings(LLM=LIVE)
def test_schema_goes_as_json_schema_text_format(sent):
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    box = sent(reply(text='{"name": "Вуз"}'))
    answer = OpenAIProvider().complete(system="s", user="u", schema=schema)

    fmt = box["json"]["text"]["format"]
    assert fmt == {"type": "json_schema", "name": "result", "schema": schema, "strict": False}
    assert answer.parsed == {"name": "Вуз"}


# --- Поиск по белому списку ---------------------------------------------------


@override_settings(LLM=LIVE)
def test_search_is_restricted_to_whitelist_and_asks_for_sources(sent):
    box = sent(reply(text="{}", searched=["https://www.utoronto.ca/admissions"]))
    search = websearch.tool(["utoronto.ca", "commonapp.org"])
    answer = OpenAIProvider().complete(system="s", user="u", schema={"type": "object"}, search=search)

    body = box["json"]
    assert body["tools"] == [{"type": "web_search", "filters": {"allowed_domains": ["utoronto.ca", "commonapp.org"]}}]
    assert body["tool_choice"] == "auto"
    assert body["max_tool_calls"] == 5
    assert body["include"] == ["web_search_call.action.sources"]
    # поиск оплачивается за вызов: один `web_search_call` — один поиск
    assert answer.usage.searches == 1


@override_settings(LLM=LIVE)
def test_search_without_domains_is_refused_not_widened(sent):
    box = sent(reply(text="ок"))
    with pytest.raises(LLMUnavailable, match="без белого списка"):
        OpenAIProvider().complete(system="s", user="u", search={"allowed_domains": []})
    assert box["calls"] == 0, "поиск по всему интернету не уходит даже попыткой"


@override_settings(LLM=LIVE)
def test_too_long_whitelist_is_refused_not_cut(sent):
    box = sent(reply(text="ок"))
    domains = [f"u{i}.edu" for i in range(OPENAI_MAX_DOMAINS + 1)]
    with pytest.raises(LLMUnavailable, match="длиннее"):
        OpenAIProvider().complete(system="s", user="u", search={"allowed_domains": domains})
    assert box["calls"] == 0


def test_visited_urls_read_openai_sources_pages_and_citations():
    raw = reply(text="x", searched=["https://utoronto.ca/a"], cited=["https://forum.example/b"])
    raw["output"].insert(0, {"type": "web_search_call", "action": {"type": "open_page", "url": "https://mit.edu/c"}})
    visited = websearch.visited_urls(raw)
    assert visited == ["https://mit.edu/c", "https://utoronto.ca/a", "https://forum.example/b"]


def test_visited_urls_still_read_anthropic_answers():
    raw = {"content": [{"type": "web_search_tool_result", "content": [{"url": "https://mit.edu/x"}]}]}
    assert websearch.visited_urls(raw) == ["https://mit.edu/x"]


# --- Ответ -------------------------------------------------------------------


@override_settings(LLM=LIVE)
def test_refusal_gives_no_parsed_answer(sent):
    payload = reply(text="")
    payload["output"][-1]["content"] = [{"type": "refusal", "refusal": "не могу"}]
    sent(payload)
    answer = OpenAIProvider().complete(system="s", user="u", schema={"type": "object"})
    assert answer.parsed is None


@override_settings(LLM=LIVE)
def test_incomplete_answer_with_broken_json_is_not_parsed(sent):
    sent(reply(text='{"name": "Ву', status="incomplete", incomplete_details={"reason": "max_output_tokens"}))
    answer = OpenAIProvider().complete(system="s", user="u", schema={"type": "object"})
    assert answer.parsed is None


@override_settings(LLM=LIVE)
def test_usage_counts_reasoning_inside_output_tokens(sent):
    sent(reply(text="ок"))
    answer = OpenAIProvider().complete(system="s", user="u")
    assert (answer.usage.tokens_in, answer.usage.tokens_out) == (1000, 300)
    assert answer.external_id == "resp_1"


# --- Повторы -----------------------------------------------------------------


@override_settings(LLM={**LIVE, "RETRIES": 2})
def test_exhausted_quota_is_not_retried(monkeypatch):
    """429 от кончившихся денег повтором не лечится — один вызов, а не три."""
    import requests

    calls = {"n": 0}

    def broke(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        return FakeResponse({"error": {"code": "insufficient_quota", "message": "..."}}, 429)

    monkeypatch.setattr(requests, "post", broke)
    with pytest.raises(LLMUnavailable):
        OpenAIProvider().complete(system="s", user="u")
    assert calls["n"] == 1


@override_settings(LLM={**LIVE, "RETRIES": 1})
def test_rate_limit_is_retried_after_the_pause_the_provider_asks_for(monkeypatch):
    import time

    import requests

    answers = [
        FakeResponse({"error": {"code": "rate_limit_exceeded"}}, 429, headers={"retry-after": "7"}),
        FakeResponse(reply(text="ок")),
    ]
    pauses: list[float] = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: answers.pop(0))
    monkeypatch.setattr(time, "sleep", pauses.append)

    assert OpenAIProvider().complete(system="s", user="u").content == "ок"
    assert pauses and pauses[0] >= 7


# --- Провайдер по умолчанию ---------------------------------------------------


@override_settings(LLM={k: v for k, v in LIVE.items() if k != "PROVIDER"})
def test_openai_is_the_default_provider():
    assert isinstance(get_provider(), OpenAIProvider)


@override_settings(LLM={**LIVE, "PROVIDER": "anthropic"})
def test_anthropic_stays_one_variable_away():
    assert get_provider().name == "anthropic"
