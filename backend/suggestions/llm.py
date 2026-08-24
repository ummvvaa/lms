"""Единая точка обращения к модели.

Четыре правила, которые здесь соблюдаются жёстко:

* в модель уходят только поля, нужные конкретной задаче, а не профиль целиком;
* режим без хранения запросов на стороне провайдера;
* каждый вызов логируется: кто, когда, какая операция, сколько токенов и денег;
* при исчерпании месячного лимита операции отключаются с понятным текстом.

Если ключа нет, провайдер недоступен или лимит выбран — поднимается
`LLMUnavailable`, и вызывающий код продолжает работать правилами. Это не
заглушка ради тестов: школа не должна вставать из-за чужого сбоя.
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from suggestions.budget import BudgetExceeded, check_available, record
from suggestions.providers import Attachment, LLMUnavailable, get_provider

log = logging.getLogger("llm")

__all__ = [
    "Attachment",
    "BudgetExceeded",
    "LLMResponse",
    "LLMUnavailable",
    "complete",
    "image_from_bytes",
    "is_available",
    "is_configured",
    "status",
]


@dataclass(frozen=True)
class LLMResponse:
    """Ответ модели в том виде, в котором его ждёт код операций."""

    content: str
    parsed: Any = None
    model: str = ""
    offline: bool = False


def is_configured() -> bool:
    """Подключена ли модель вообще."""
    return get_provider().is_configured()


def is_available() -> bool:
    """Можно ли звать модель прямо сейчас: и ключ есть, и лимит не выбран."""
    from suggestions.budget import is_available as budget_ok

    return is_configured() and budget_ok()


def status() -> dict:
    """Состояние модели для интерфейса: почему кнопка работает или нет."""
    from suggestions.budget import is_available as budget_ok
    from suggestions.budget import monthly_limit, spent_this_month

    configured = is_configured()
    within_budget = budget_ok()
    if not configured:
        detail = (
            "Модель не подключена. Разбор идёт правилами, объяснения собираются "
            "из движка соответствия — формулировки проще, но всё работает"
        )
    elif not within_budget:
        detail = (
            f"Месячный лимит расходов выбран: потрачено ${spent_this_month():.2f} из ${monthly_limit():.2f}. "
            f"Операции с моделью отключены до первого числа, разбор продолжает работать правилами"
        )
    else:
        detail = "Модель подключена"
    return {
        "configured": configured,
        "within_budget": within_budget,
        "available": configured and within_budget,
        "provider": get_provider().name,
        "detail": detail,
    }


def image_from_bytes(payload: bytes, media_type: str) -> Attachment:
    """Изображение для запроса: фото грамоты, скриншот с баллами."""
    return Attachment(media_type=media_type, data=base64.b64encode(payload).decode("ascii"))


def complete(
    *,
    system: str,
    user: str,
    purpose: str,
    actor=None,
    role: str = "",
    schema: dict | None = None,
    images: list[Attachment] | None = None,
    max_tokens: int = 2000,
) -> LLMResponse:
    """Один вызов модели.

    `user` собирается вызывающим кодом и обязан содержать только то,
    что нужно задаче: баллы и идентификаторы, а не весь профиль ученика.
    """
    check_available()

    provider = get_provider()
    if not provider.is_configured():
        raise LLMUnavailable("Модель не настроена")

    started = time.monotonic()
    try:
        answer = provider.complete(system=system, user=user, schema=schema, images=images, max_tokens=max_tokens)
    except LLMUnavailable as error:
        record(
            actor=actor,
            role=role,
            purpose=purpose,
            provider=provider.name,
            model=settings.LLM.get("MODEL", ""),
            sent={"system": system, "user": user, "schema": bool(schema), "images": len(images or [])},
            duration_ms=int((time.monotonic() - started) * 1000),
            is_ok=False,
            error=str(error),
        )
        raise

    record(
        actor=actor,
        role=role,
        purpose=purpose,
        provider=provider.name,
        model=answer.model or settings.LLM.get("MODEL", ""),
        external_id=answer.external_id,
        sent={"system": system, "user": user, "schema": bool(schema), "images": len(images or [])},
        received=answer.raw,
        tokens_in=answer.usage.tokens_in,
        tokens_out=answer.usage.tokens_out,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return LLMResponse(content=answer.content, parsed=answer.parsed, model=answer.model)
