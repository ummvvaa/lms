"""Провайдер Anthropic (Messages API): что уходит в запросе и что делается с ответом.

Настоящего провайдера нет — подменяется `requests.post`, как в
`test_web_search_whitelist.py`. Новые модели (`claude-opus-5-5`) отвергают
принудительный `tool_choice` с 400 и рассуждают всегда: блок `thinking`
приходит первым и тратит тот же `max_tokens`. Формат — по документации
Anthropic (Tool use, Structured outputs, Extended thinking).
"""

from __future__ import annotations

import logging

import pytest
from django.test import override_settings

from suggestions import websearch
from suggestions.llm import complete
from suggestions.providers import AnthropicProvider, LLMUnavailable

LIVE = {
    "PROVIDER": "anthropic",
    "API_KEY": "test-key",
    "BASE_URL": "https://api.example",
    "MODEL": "claude-opus-5-5",
    "TIMEOUT": 5,
    "RETRIES": 0,
    "RETRY_DELAY": 0,
    "NO_RETENTION": True,
    "SEARCH": True,
    "SEARCH_MAX_USES": 5,
    "REASONING_EFFORT": "low",
    "REASONING_RESERVE": 25000,
}

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}

THINKING = {"type": "thinking", "thinking": "", "signature": "sig"}


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload, self.status_code, self.headers = payload, status_code, {}

    def json(self) -> dict:
        return self.payload


def message(*blocks: dict, stop_reason: str = "end_turn") -> dict:
    """Ответ в том виде, в каком его отдаёт Messages API."""
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": list(blocks),
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 1000, "output_tokens": 400},
    }


@pytest.fixture
def sent(monkeypatch):
    """Перехватить HTTP-запрос к провайдеру и подсунуть ответ."""
    box: dict = {}

    def install(payload: dict, status_code: int = 200):
        def fake_post(url, json=None, headers=None, timeout=None):
            box["url"], box["json"], box["headers"] = url, json, headers
            return FakeResponse(payload, status_code)

        import requests

        monkeypatch.setattr(requests, "post", fake_post)
        return box

    return install


@override_settings(LLM=LIVE)
@pytest.mark.parametrize("search", [False, True])
def test_tool_choice_is_never_forced(sent, search):
    """`tool` и `any` модель отвергает с 400 — в запросе их нет ни с поиском, ни без."""
    box = sent(message(THINKING, {"type": "tool_use", "id": "t1", "name": "result", "input": {"title": "x"}}))
    tool = {"type": websearch.TOOL_TYPE, "name": "web_search", "allowed_domains": ["utoronto.ca"]}
    AnthropicProvider().complete(system="s", user="u", schema=SCHEMA, search=tool if search else None)

    assert box["json"]["tool_choice"] == {"type": "auto"}
    assert "result" in [t.get("name") for t in box["json"]["tools"]]
    assert "`result`" in box["json"]["system"]
    if search:
        assert any(t.get("type") == websearch.TOOL_TYPE for t in box["json"]["tools"])


@override_settings(LLM=LIVE)
def test_plain_text_request_carries_no_tools(sent):
    """Без схемы и поиска инструментов нет и выбирать нечего."""
    box = sent(message(THINKING, {"type": "text", "text": "Ответ"}))
    answer = AnthropicProvider().complete(system="s", user="u")

    assert "tools" not in box["json"] and "tool_choice" not in box["json"]
    assert box["json"]["system"] == "s"
    assert answer.content == "Ответ"


@override_settings(LLM=LIVE)
def test_reasoning_gets_a_reserve_on_top_of_the_operation_limit(sent):
    """Рассуждение тратит тот же `max_tokens`: к пределу операции добавлен запас."""
    box = sent(message(THINKING, {"type": "text", "text": "Ответ"}))
    AnthropicProvider().complete(system="s", user="u", max_tokens=900)

    assert box["json"]["max_tokens"] == 900 + 25000


@override_settings(LLM=LIVE)
def test_thinking_and_tool_use_are_parsed(sent):
    """Рассуждение первым блоком не мешает: структура берётся из `tool_use`."""
    sent(
        message(
            THINKING,
            {"type": "redacted_thinking", "data": "зашифровано"},
            {"type": "tool_use", "id": "t1", "name": "result", "input": {"title": "Эссе"}},
            stop_reason="tool_use",
        )
    )
    answer = AnthropicProvider().complete(system="s", user="u", schema=SCHEMA)

    assert answer.parsed == {"title": "Эссе"}
    assert answer.content == ""


@override_settings(LLM=LIVE)
@pytest.mark.parametrize(
    "text",
    [
        '{"title": "Эссе"}',
        '```json\n{"title": "Эссе"}\n```',
        'Вот ответ:\n{"title": "Эссе"}\nГотово.',
    ],
)
def test_thinking_and_json_text_are_parsed_by_the_fallback(sent, text):
    """Модель ответила текстом, а не вызовом: JSON из текста разбирается."""
    sent(message({"type": "thinking", "thinking": "думаю…", "signature": "sig"}, {"type": "text", "text": text}))
    answer = AnthropicProvider().complete(system="s", user="u", schema=SCHEMA)

    assert answer.parsed == {"title": "Эссе"}
    # рассуждение текстом ответа не считается
    assert "думаю" not in answer.content


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_prose_instead_of_structure_is_a_clear_error(sent):
    """Ни вызова, ни JSON — понятная ошибка, а не пустой словарь у операции."""
    from suggestions.models import LLMCall

    sent(message(THINKING, {"type": "text", "text": "Не могу заполнить форму."}))
    with pytest.raises(LLMUnavailable) as error:
        complete(system="s", user="u", purpose="test", schema=SCHEMA)

    assert "структурированный" in str(error.value)
    call = LLMCall.objects.get()
    assert call.is_ok is False and call.tokens_out == 400


@override_settings(LLM=LIVE)
def test_cut_off_by_max_tokens_is_logged(sent, caplog):
    """Обрыв по `max_tokens` виден в журнале с пределом, который не хватил."""
    sent(message(THINKING, {"type": "text", "text": '{"title": "Эс'}, stop_reason="max_tokens"))
    with caplog.at_level(logging.WARNING, logger="llm"):
        answer = AnthropicProvider().complete(system="s", user="u", schema=SCHEMA, max_tokens=900)

    assert answer.parsed is None
    assert any("max_tokens" in record.getMessage() and "25900" in record.getMessage() for record in caplog.records)


@override_settings(LLM={**LIVE, "TIMEOUT": 600, "SYNC_TIMEOUT": 30, "RETRIES": 2})
def test_page_calls_wait_briefly_and_say_so_on_timeout(monkeypatch):
    """Человек ждёт на странице: короткий таймаут, без повторов, причина словами."""
    import requests

    seen: list[int] = []

    def slow(url, json=None, headers=None, timeout=None):
        seen.append(timeout)
        raise requests.exceptions.ReadTimeout("Read timed out. (read timeout=30)")

    monkeypatch.setattr(requests, "post", slow)
    with pytest.raises(LLMUnavailable) as error:
        AnthropicProvider().complete(system="s", user="u", timeout=30, retries=0)

    assert seen == [30], "один заход с коротким таймаутом"
    assert str(error.value) == "модель не ответила за 30 с"


@override_settings(LLM={**LIVE, "TIMEOUT": 600, "RETRIES": 0})
def test_background_calls_wait_the_long_timeout(sent):
    box = sent(message(THINKING, {"type": "text", "text": "Ответ"}))
    import requests

    seen: list[int] = []
    original = requests.post

    def spy(url, json=None, headers=None, timeout=None):
        seen.append(timeout)
        return original(url, json=json, headers=headers, timeout=timeout)

    requests.post = spy
    try:
        AnthropicProvider().complete(system="s", user="u")
    finally:
        requests.post = original
    assert seen == [600] and box["json"]["model"] == "claude-opus-5-5"


@pytest.mark.django_db
@override_settings(LLM={**LIVE, "SYNC_TIMEOUT": 30, "RETRIES": 2})
def test_complete_in_sync_mode_passes_the_short_limits(monkeypatch):
    """`llm.complete(sync=True)` — короткий таймаут и ни одного повтора."""
    from suggestions.providers import Completion, Usage

    got: dict = {}

    class Spy:
        name = "anthropic"

        def is_configured(self):
            return True

        def complete(self, **kwargs):
            got.update(kwargs)
            return Completion(content="ок", model="m", usage=Usage(1, 1), raw={})

    monkeypatch.setattr("suggestions.llm.get_provider", lambda: Spy())
    complete(system="s", user="u", purpose="test", sync=True)
    assert got["timeout"] == 30 and got["retries"] == 0
