"""Провайдер модели за интерфейсом.

Школа не должна оказаться привязанной к одному поставщику: смена провайдера
это переменная окружения, а не переписывание половины кода. Поэтому весь
код операций знает только `Provider.complete()` и `Usage`.

Здесь же живут таймауты и повторы: сеть моргает, провайдер отвечает 429
и 5xx — один такой ответ не повод показывать директору ошибку.

С 28.09.2026 школа работает через OpenAI (`OpenAIProvider`, Responses API).
`AnthropicProvider` оставлен в реестре: обратный переход — одна переменная
`LLM_PROVIDER=anthropic` и ключ, без правки кода.
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

    Школа отправляет данные детей, и держать их на чужой стороне незачем.
    Договориться об этом можно только с провайдером — на уровне учётной
    записи (zero data retention); заголовка, который включал бы это
    из запроса, у него нет.
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
        # Заголовка «не храните запросы» у провайдера нет: придуманное
        # значение `anthropic-beta` он отвергает целиком, и с включённым
        # NO_RETENTION не работал ни один вызов. Нехранение запросов —
        # условие договора и настройка учётной записи, а не заголовок
        # запроса; флаг остаётся как признак того, что оно оговорено

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


#: Сколько доменов принимает фильтр поиска OpenAI (`filters.allowed_domains`).
OPENAI_MAX_DOMAINS = 100


class OpenAIProvider(Provider):
    """Обращение к Responses API (`POST /v1/responses`).

    Запрос: системный текст — `instructions`, пользовательский — сообщение
    с частями `input_text` и `input_image` (картинка data-URL в base64).
    Структурированный ответ — `text.format` с `json_schema`; `strict` выключен,
    как и у прежнего провайдера: схемы операций написаны без обязательного
    перечисления всех полей, и строгий режим отверг бы половину из них.

    Нехранение: `store: false` при `LLM_NO_RETENTION` — ответ не остаётся
    в состоянии приложения у провайдера. Журнал злоупотреблений (до 30 дней)
    снимается только договором (Zero Data Retention) на уровне организации,
    из запроса он не выключается.

    Модели OpenAI рассуждающие: рассуждение тратит тот же бюджет
    `max_output_tokens`, что и ответ, и при нехватке ответ приходит пустым
    (`status: incomplete`). Поэтому к пределу операции добавляется запас
    `LLM_REASONING_RESERVE`, а глубина рассуждения — `LLM_REASONING_EFFORT`.
    """

    name = "openai"

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
            content.append({"type": "input_image", "image_url": f"data:{image.media_type};base64,{image.data}"})
        content.append({"type": "input_text", "text": user})

        effort = (settings.LLM.get("REASONING_EFFORT") or "").strip()
        reserve = int(settings.LLM.get("REASONING_RESERVE", 0) or 0) if effort else 0
        payload: dict[str, Any] = {
            "model": settings.LLM["MODEL"],
            "instructions": system,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": max_tokens + reserve,
            "store": not settings.LLM.get("NO_RETENTION", True),
        }
        if effort:
            payload["reasoning"] = {"effort": effort}
        if schema:
            payload["text"] = {"format": {"type": "json_schema", "name": "result", "schema": schema, "strict": False}}
        if search:
            payload.update(_openai_search(search))

        headers = {
            "Authorization": f"Bearer {settings.LLM['API_KEY']}",
            "Content-Type": "application/json",
        }
        body = _with_retries(
            lambda: requests.post(
                f"{settings.LLM['BASE_URL']}/v1/responses",
                json=payload,
                headers=headers,
                timeout=settings.LLM["TIMEOUT"],
            )
        )

        text, searches = "", 0
        for item in body.get("output") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "web_search_call":
                searches += 1
            elif item.get("type") == "message":
                for part in item.get("content") or []:
                    if part.get("type") == "output_text":
                        text += part.get("text", "")
                    elif part.get("type") == "refusal":
                        log.warning("Модель отказалась отвечать: %s", str(part.get("refusal", ""))[:300])

        if body.get("status") == "incomplete":
            reason = (body.get("incomplete_details") or {}).get("reason", "")
            log.warning("Ответ модели неполный: %s", reason or "причина не названа")

        parsed = None
        if schema and text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                log.warning("Структурированный ответ не разобран: %s", text[:300])

        usage = body.get("usage") or {}
        return Completion(
            content=text,
            parsed=parsed,
            model=body.get("model", ""),
            external_id=body.get("id", ""),
            usage=Usage(
                tokens_in=int(usage.get("input_tokens", 0) or 0),
                # рассуждение входит в `output_tokens` и оплачивается как вывод
                tokens_out=int(usage.get("output_tokens", 0) or 0),
                # поиск оплачивается за вызов: каждый `web_search_call` — один вызов
                searches=searches,
            ),
            raw=body,
        )


def _openai_search(search: dict) -> dict[str, Any]:
    """Поиск по белому списку в виде, который понимает Responses API.

    Белый список собирает `suggestions.websearch.tool()` — единственное место,
    где он живёт; здесь берутся только его домены и предел поисков.
    Пустой список не превращается в поиск по всему интернету, а список длиннее,
    чем принимает провайдер, не режется молча: оба случая — отказ с причиной.
    """
    domains = [str(domain).strip() for domain in search.get("allowed_domains") or [] if str(domain).strip()]
    if not domains:
        raise LLMUnavailable("Поиск без белого списка запрещён — искать негде")
    if len(domains) > OPENAI_MAX_DOMAINS:
        raise LLMUnavailable(
            f"Белый список поиска длиннее {OPENAI_MAX_DOMAINS} доменов — провайдер его не принимает. "
            "Выберите вуз: тогда поиск пойдёт по его сайту и Common App"
        )
    return {
        "tools": [{"type": "web_search", "filters": {"allowed_domains": domains}}],
        # с поиском ответ нельзя требовать сразу: сначала сайт, потом структура
        "tool_choice": "auto",
        "max_tool_calls": int(search.get("max_uses") or settings.LLM.get("SEARCH_MAX_USES", 5)),
        # без этого провайдер не скажет, по каким адресам ходил, а проверять
        # обещание белого списка мы должны по факту, не по описанию
        "include": ["web_search_call.action.sources"],
    }


#: коды, при которых имеет смысл повторить: перегрузка и временный сбой
#: (529 — перегрузка у Anthropic, у OpenAI его нет, но он и не мешает)
RETRY_CODES = {408, 409, 429, 500, 502, 503, 504, 529}

#: 429 бывает и перегрузкой, и кончившимися деньгами. Повтор деньги
#: не вернёт — такие коды ошибки OpenAI не повторяем
NO_RETRY_ERROR_CODES = {
    "insufficient_quota",
    "credit_balance_exhausted",
    "organization_spend_limit_exceeded",
    "project_spend_limit_exceeded",
}

#: дольше этого по `Retry-After` не ждём: запрос живёт внутри веб-запроса
MAX_RETRY_AFTER = 30.0


def _with_retries(call) -> dict:
    """Повторить вызов при временном сбое. Постоянную ошибку не повторяем."""
    attempts = int(settings.LLM.get("RETRIES", 2)) + 1
    delay = float(settings.LLM.get("RETRY_DELAY", 1.0))
    last = ""

    for attempt in range(attempts):
        wait_hint: float | None = None
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
            if response.status_code not in RETRY_CODES or _error_code(body) in NO_RETRY_ERROR_CODES:
                raise LLMUnavailable(last)
            wait_hint = _retry_after(response)

        if attempt + 1 < attempts:
            # небольшой разброс, чтобы несколько задач не били разом;
            # если провайдер сам сказал, сколько ждать, — ждём столько
            pause = delay * (2**attempt) + random.uniform(0, 0.3)
            if wait_hint is not None:
                pause = max(pause, wait_hint)
            time.sleep(pause)

    raise LLMUnavailable(last or "Модель не ответила")


def _error_code(body: Any) -> str:
    """Код ошибки из ответа OpenAI (`error.code`); у Anthropic его нет — пусто."""
    error = body.get("error") if isinstance(body, dict) else None
    return str(error.get("code") or "") if isinstance(error, dict) else ""


def _retry_after(response) -> float | None:
    """Сколько секунд просит подождать провайдер (`Retry-After`), не дольше предела."""
    headers = getattr(response, "headers", None) or {}
    value = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return min(float(value), MAX_RETRY_AFTER) if value is not None else None
    except (TypeError, ValueError):
        return None


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
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "none": NullProvider,
}


def get_provider() -> Provider:
    """Провайдер из настроек. Неизвестное имя — это отсутствие модели."""
    name = (settings.LLM.get("PROVIDER") or "openai").strip().lower()
    factory = PROVIDERS.get(name)
    if factory is None:
        log.warning("Неизвестный провайдер модели «%s» — работаем правилами", name)
        return NullProvider()
    return factory()
