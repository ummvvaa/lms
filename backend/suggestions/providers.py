"""Провайдер модели за интерфейсом.

Школа не должна оказаться привязанной к одному поставщику: смена провайдера
это переменная окружения, а не переписывание половины кода. Поэтому весь
код операций знает только `Provider.complete()` и `Usage`.

Здесь же живут таймауты и повторы: сеть моргает, провайдер отвечает 429
и 529 — один такой ответ не повод показывать директору ошибку.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

log = logging.getLogger("llm")


class LLMUnavailable(Exception):
    """Модель не настроена или недоступна. Работа продолжается правилами."""


@dataclass(frozen=True)
class Usage:
    """Сколько израсходовано на один вызов.

    Поиск считается отдельно: он оплачивается не токенами, а запросами.
    """

    tokens_in: int = 0
    tokens_out: int = 0
    searches: int = 0


@dataclass(frozen=True)
class Completion:
    """Ответ провайдера в едином виде, независимо от того, кто его дал."""

    content: str = ""
    parsed: Any = None
    model: str = ""
    external_id: str = ""
    usage: Usage = field(default_factory=Usage)
    raw: Any = None


@dataclass(frozen=True)
class Attachment:
    """Изображение к запросу: фото грамоты, скриншот с баллами."""

    media_type: str
    #: содержимое в base64 — провайдеру уходит именно оно
    data: str


class Provider:
    """Что должен уметь любой провайдер."""

    name = "base"

    def is_configured(self) -> bool:  # pragma: no cover — переопределяется
        return False

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict | None = None,
        images: list[Attachment] | None = None,
        max_tokens: int = 2000,
        search: dict | None = None,
    ) -> Completion:  # pragma: no cover — переопределяется
        raise NotImplementedError


class AnthropicProvider(Provider):
    """Обращение к Messages API.

    Режим без хранения запросов включается заголовком: школа отправляет
    данные детей, и держать их на чужой стороне незачем.
    """

    name = "anthropic"

    def is_configured(self) -> bool:
        return bool(settings.LLM.get("API_KEY"))

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict | None = None,
        images: list[Attachment] | None = None,
        max_tokens: int = 2000,
        search: dict | None = None,
    ) -> Completion:
        if not self.is_configured():
            raise LLMUnavailable("Ключ модели не задан")

        import requests

        content: list[dict[str, Any]] = []
        for image in images or []:
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": image.media_type, "data": image.data},
                }
            )
        content.append({"type": "text", "text": user})

        payload: dict[str, Any] = {
            "model": settings.LLM["MODEL"],
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
        }
        tools: list[dict[str, Any]] = []
        if search:
            # инструмент исполняется на стороне провайдера и уже несёт
            # список разрешённых доменов: дальше него он не пойдёт
            tools.append(search)
        if schema:
            tools.append({"name": "result", "description": "Структурированный ответ", "input_schema": schema})
        if tools:
            payload["tools"] = tools
        if schema and not search:
            payload["tool_choice"] = {"type": "tool", "name": "result"}
        elif schema:
            # с поиском ответ нельзя требовать сразу: модели надо сначала
            # сходить на сайт, а уже потом заполнить структуру
            payload["tool_choice"] = {"type": "auto"}

        headers = {
            "x-api-key": settings.LLM["API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if settings.LLM.get("NO_RETENTION"):
            headers["anthropic-beta"] = "privacy-mode-2024-01-01"

        body = _with_retries(
            lambda: requests.post(
                f"{settings.LLM['BASE_URL']}/v1/messages",
                json=payload,
                headers=headers,
                timeout=settings.LLM["TIMEOUT"],
            )
        )

        parsed, text = None, ""
        for block in body.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "result":
                parsed = block.get("input")
            elif block.get("type") == "text":
                text += block.get("text", "")

        usage = body.get("usage") or {}
        server_tools = usage.get("server_tool_use") or {}
        return Completion(
            content=text,
            parsed=parsed,
            model=body.get("model", ""),
            external_id=body.get("id", ""),
            usage=Usage(
                tokens_in=int(usage.get("input_tokens", 0)),
                tokens_out=int(usage.get("output_tokens", 0)),
                searches=int(server_tools.get("web_search_requests", 0)),
            ),
            raw=body,
        )


#: коды, при которых имеет смысл повторить: перегрузка и временный сбой
RETRY_CODES = {408, 409, 429, 500, 502, 503, 504, 529}


def _with_retries(call) -> dict:
    """Повторить вызов при временном сбое. Постоянную ошибку не повторяем."""
    attempts = int(settings.LLM.get("RETRIES", 2)) + 1
    delay = float(settings.LLM.get("RETRY_DELAY", 1.0))
    last = ""

    for attempt in range(attempts):
        try:
            response = call()
        except Exception as error:  # сеть моргнула
            last = str(error)
            log.warning("Модель недоступна (%s из %s): %s", attempt + 1, attempts, error)
        else:
            try:
                body = response.json()
            except json.JSONDecodeError:
                body, last = {}, f"ответ не разобран ({response.status_code})"
            if response.status_code < 400:
                return body
            last = f"провайдер вернул {response.status_code}"
            log.warning("Модель вернула %s: %s", response.status_code, str(body)[:500])
            if response.status_code not in RETRY_CODES:
                raise LLMUnavailable(last)

        if attempt + 1 < attempts:
            # небольшой разброс, чтобы несколько задач не били разом
            time.sleep(delay * (2**attempt) + random.uniform(0, 0.3))

    raise LLMUnavailable(last or "Модель не ответила")


class NullProvider(Provider):
    """Провайдер-заглушка: система живёт на правилах.

    Не ошибка конфигурации, а рабочий режим: школа не должна вставать
    из-за недоступного или неоплаченного провайдера.
    """

    name = "none"

    def is_configured(self) -> bool:
        return False

    def complete(self, **_kwargs) -> Completion:
        raise LLMUnavailable("Модель не подключена — работаем правилами")


PROVIDERS: dict[str, type[Provider]] = {
    "anthropic": AnthropicProvider,
    "none": NullProvider,
}


def get_provider() -> Provider:
    """Провайдер из настроек. Неизвестное имя — это отсутствие модели."""
    name = (settings.LLM.get("PROVIDER") or "anthropic").strip().lower()
    factory = PROVIDERS.get(name)
    if factory is None:
        log.warning("Неизвестный провайдер модели «%s» — работаем правилами", name)
        return NullProvider()
    return factory()
