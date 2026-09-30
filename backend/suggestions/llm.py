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
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from suggestions.budget import BudgetExceeded, check_available, record
from suggestions.providers import Attachment, LLMUnavailable, get_provider

log = logging.getLogger("llm")

__all__ = [
    "Attachment",
    "BudgetExceeded",
    "InvalidImage",
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
    #: сколько раз модель ходила в интернет и по каким адресам
    searches: int = 0
    visited: tuple[str, ...] = ()


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
        detail = _(
            "Модель не подключена. Разбор идёт правилами, объяснения собираются "
            "из движка соответствия — формулировки проще, но всё работает"
        )
    elif not within_budget:
        detail = _(
            "Месячный лимит расходов выбран: потрачено ${spent} из ${limit}. "
            "Операции с моделью отключены до первого числа, разбор продолжает работать правилами"
        ).format(spent=f"{spent_this_month():.2f}", limit=f"{monthly_limit():.2f}")
    else:
        detail = _("Модель подключена")
    return {
        "configured": configured,
        "within_budget": within_budget,
        "available": configured and within_budget,
        "provider": get_provider().name,
        "detail": detail,
    }


#: что модель принимает картинкой (OpenAI, «Images and vision»): PNG, JPEG,
#: WEBP и GIF без анимации. Тип берётся из самих байтов, а не со слов клиента
MODEL_IMAGE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}

NOT_AN_IMAGE = gettext_lazy("Файл не читается как изображение — загрузите снимок в PNG, JPEG, WEBP или GIF")


class InvalidImage(ValueError):
    """Байты не складываются в картинку. Текст пригоден для показа человеку."""


def image_from_bytes(payload: bytes, media_type: str = "") -> Attachment:
    """Изображение для запроса: фото грамоты, скриншот с баллами.

    Картинка сначала целиком читается здесь: битый файл провайдер отвергает
    ответом 400 («not a valid image»), и человек видит сбой модели вместо
    «загрузите снимок ещё раз». Заявленный `media_type` приходит от клиента
    и не используется: тип в data-URL — по формату самих байтов. Формат,
    которого модель не принимает (BMP, TIFF, анимация), уходит первым кадром
    в PNG; фото телефона в MPO — первым кадром в JPEG.
    """
    from io import BytesIO

    from PIL import Image

    del media_type
    if not payload:
        raise InvalidImage(_("Файл пустой — загрузите снимок ещё раз"))
    try:
        # verify() сверяет контрольные суммы, load() — что данные раскрываются
        # до конца; после verify() объект негоден, поэтому открываем дважды
        with Image.open(BytesIO(payload)) as probe:
            probe.verify()
        with Image.open(BytesIO(payload)) as image:
            image.load()
            kind = image.format or ""
            animated = bool(getattr(image, "is_animated", False))
            if kind in MODEL_IMAGE_TYPES and not animated:
                return Attachment(media_type=MODEL_IMAGE_TYPES[kind], data=base64.b64encode(payload).decode("ascii"))
            image.seek(0)
            if kind == "MPO":
                frame, target = image.convert("RGB"), "JPEG"
            else:
                frame, target = image.convert("RGBA"), "PNG"
            out = BytesIO()
            frame.save(out, format=target)
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
        # UnidentifiedImageError — подкласс OSError
        raise InvalidImage(str(NOT_AN_IMAGE)) from error
    return Attachment(media_type=MODEL_IMAGE_TYPES[target], data=base64.b64encode(out.getvalue()).decode("ascii"))


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
    search: dict | None = None,
) -> LLMResponse:
    """Один вызов модели.

    `user` собирается вызывающим кодом и обязан содержать только то,
    что нужно задаче: баллы и идентификаторы, а не весь профиль ученика.

    `search` — описание поиска по белому списку (`suggestions.websearch`).
    Без него модель в интернет не ходит вовсе.
    """
    check_available()

    provider = get_provider()
    if not provider.is_configured():
        raise LLMUnavailable(_("Модель не настроена"))

    started = time.monotonic()
    try:
        answer = provider.complete(
            system=system, user=user, schema=schema, images=images, max_tokens=max_tokens, search=search
        )
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

    from suggestions import websearch

    # обещание `allowed_domains` проверяем сами: чужая сторона обещала,
    # а отвечать за дедлайн с форума нам
    visited = websearch.visited_urls(answer.raw)
    outside = [url for url in visited if not websearch.is_allowed_url(url)]
    # пустой ответ — не ответ: у рассуждающей модели так выглядит бюджет,
    # целиком ушедший на рассуждение, отказ или обрыв. Деньги за него
    # записаны, а вызывающий код получает причину, а не пустую строку
    empty = "" if (answer.content or "").strip() or answer.parsed is not None else empty_reason(answer.raw)

    record(
        actor=actor,
        role=role,
        purpose=purpose,
        provider=provider.name,
        model=answer.model or settings.LLM.get("MODEL", ""),
        external_id=answer.external_id,
        sent={
            "system": system,
            "user": user,
            "schema": bool(schema),
            "images": len(images or []),
            "search": bool(search),
        },
        received=answer.raw,
        tokens_in=answer.usage.tokens_in,
        tokens_out=answer.usage.tokens_out,
        searches=answer.usage.searches,
        duration_ms=int((time.monotonic() - started) * 1000),
        is_ok=not outside and not empty,
        error=_("поиск вышел за белый список: {urls}").format(urls=", ".join(outside[:3])) if outside else empty[:250],
    )
    if outside:
        # это не «немного не тот источник», а ровно то, из-за чего белый
        # список и заведён: ответ целиком уходит в корзину
        log.error("Поиск вышел за белый список: %s", outside)
        raise LLMUnavailable(
            _("Поиск вышел за список официальных сайтов — ответ отброшен. Сверьте данные вручную по сайту вуза")
        )
    if empty:
        log.warning("Модель вернула пустой ответ (%s): %s", purpose, empty)
        raise LLMUnavailable(empty)

    return LLMResponse(
        content=answer.content,
        parsed=answer.parsed,
        model=answer.model,
        searches=answer.usage.searches,
        visited=tuple(visited),
    )


def empty_reason(raw: Any) -> str:
    """Почему в ответе нет текста — словами, для журнала и для человека.

    OpenAI (Responses API): `status: incomplete` с `incomplete_details.reason`
    (`max_output_tokens` — бюджет кончился, чаще всего на рассуждении;
    `content_filter` — ответ остановлен фильтром) или отказ `refusal`.
    Anthropic: `stop_reason`.
    """
    body = raw if isinstance(raw, dict) else {}
    reason = str((body.get("incomplete_details") or {}).get("reason") or body.get("stop_reason") or "")
    if reason == "max_output_tokens" or reason == "max_tokens":
        return _("модель вернула пустой ответ: бюджет токенов ушёл на рассуждение")
    if reason == "content_filter":
        return _("модель вернула пустой ответ: ответ остановлен фильтром провайдера")
    for item in body.get("output") or []:
        for part in (item.get("content") or []) if isinstance(item, dict) else []:
            if isinstance(part, dict) and part.get("type") == "refusal":
                return _("модель отказалась отвечать")
    if body.get("status") == "incomplete" or reason:
        return _("модель вернула пустой ответ: {reason}").format(reason=reason or _("ответ оборван"))
    return _("модель вернула пустой ответ")
