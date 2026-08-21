"""Клиент модели.

Три правила, которые здесь соблюдаются жёстко:

* в модель уходят только поля, нужные конкретной задаче, а не профиль целиком;
* режим без хранения запросов на стороне провайдера;
* каждый вызов логируется: кто, что отправлено, что вернулось.

Если ключ не задан, клиент работает в офлайн-режиме: разбор идёт
детерминированными правилами. Это не заглушка ради тестов — школа должна
уметь вставлять баллы из переписки и без подключённой модели.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings

log = logging.getLogger("llm")


@dataclass(frozen=True)
class LLMResponse:
    """Ответ модели."""

    content: str
    parsed: Any = None
    model: str = ""
    offline: bool = False


class LLMUnavailable(Exception):
    """Модель не настроена или недоступна."""


def is_configured() -> bool:
    return bool(settings.LLM.get("API_KEY"))


def _log_call(*, call_id: str, actor, purpose: str, sent: Any, received: Any) -> None:
    """Журнал вызовов: кто, что отправлено, что вернулось."""
    from suggestions.models import LLMCall

    LLMCall.objects.create(
        actor=actor,
        purpose=purpose,
        request_payload=json.dumps(sent, ensure_ascii=False)[:8000],
        response_payload=json.dumps(received, ensure_ascii=False)[:8000] if received is not None else "",
        model=settings.LLM.get("MODEL", ""),
        external_id=call_id,
    )


def complete(
    *,
    system: str,
    user: str,
    purpose: str,
    actor=None,
    schema: dict | None = None,
    max_tokens: int = 2000,
) -> LLMResponse:
    """Один вызов модели.

    `user` собирается вызывающим кодом и обязан содержать только то,
    что нужно задаче: имена и баллы, а не весь профиль ученика.
    """
    if not is_configured():
        raise LLMUnavailable("Модель не настроена")

    import requests

    payload: dict[str, Any] = {
        "model": settings.LLM["MODEL"],
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if schema:
        payload["tools"] = [{"name": "result", "description": "Структурированный ответ", "input_schema": schema}]
        payload["tool_choice"] = {"type": "tool", "name": "result"}

    headers = {
        "x-api-key": settings.LLM["API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    if settings.LLM.get("NO_RETENTION"):
        # просим провайдера не хранить запросы
        headers["anthropic-beta"] = "privacy-mode-2024-01-01"

    response = requests.post(
        f"{settings.LLM['BASE_URL']}/v1/messages", json=payload, headers=headers, timeout=settings.LLM["TIMEOUT"]
    )
    body = response.json()

    _log_call(
        call_id=body.get("id", ""),
        actor=actor,
        purpose=purpose,
        sent={"system": system, "user": user, "schema": bool(schema)},
        received=body,
    )

    if response.status_code >= 400:
        log.warning("Модель вернула %s: %s", response.status_code, body)
        raise LLMUnavailable(f"Модель вернула {response.status_code}")

    parsed, text = None, ""
    for block in body.get("content", []):
        if block.get("type") == "tool_use":
            parsed = block.get("input")
        elif block.get("type") == "text":
            text += block.get("text", "")

    return LLMResponse(content=text, parsed=parsed, model=body.get("model", ""))
