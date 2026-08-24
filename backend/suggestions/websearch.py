"""Поиск в интернете для модели — только по официальным сайтам.

Дедлайн, приехавший с форума, попадёт в систему как факт, и ученик подаст
документы не в тот срок. Поэтому модель ищет не «в интернете», а в белом
списке: домены вузов из справочника плюс Common App.

Белый список здесь не заводится второй раз — он живёт в `universities.sync`
и уже используется фоновой сверкой. Дублировать его нельзя: разойдутся.

Ограничение стоит в двух местах, и оба в коде, а не в промпте:

1. в запрос уходит `allowed_domains` — провайдер сам не пойдёт дальше;
2. каждый вернувшийся источник проверяется ещё раз на нашей стороне,
   и факт с чужой ссылкой выбрасывается вместе со ссылкой.

Второе нужно потому, что первое — обещание чужой стороны. Проверку
обещания мы делаем сами.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from universities.sync import host_of, is_allowed

log = logging.getLogger("llm")

#: Имя серверного инструмента поиска у провайдера.
TOOL_TYPE = "web_search_20250305"
TOOL_NAME = "web_search"


@dataclass(frozen=True)
class Source:
    """Факт из интернета: где взято, каким текстом подтверждается, когда."""

    url: str
    quote: str = ""
    checked_at: str = ""
    title: str = ""

    def as_dict(self) -> dict:
        return {"url": self.url, "quote": self.quote, "checked_at": self.checked_at, "title": self.title}

    def as_reference(self) -> str:
        """Строка-источник для предложения: ссылка и дата проверки."""
        return f"{self.url} · сверено {self.checked_at}" if self.checked_at else self.url


def is_allowed_url(url: str) -> bool:
    """Разрешён ли адрес. Правило одно и живёт в `universities.sync`."""
    return is_allowed(url)


def allowed_domains() -> list[str]:
    """Белый список доменов для запроса. Пусто — искать негде."""
    from universities.sync import allowed_hosts

    return sorted(allowed_hosts())


def is_enabled() -> bool:
    """Разрешён ли поиск настройками контура."""
    return bool(settings.LLM.get("SEARCH"))


def tool(domains: list[str] | None = None) -> dict[str, Any] | None:
    """Описание инструмента поиска для провайдера.

    `None` значит «искать нечем»: поиск выключен или белый список пуст.
    Пустой список доменов не отправляем никогда — это был бы поиск
    по всему интернету, то есть ровно то, что запрещено.
    """
    if not is_enabled():
        return None
    domains = domains if domains is not None else allowed_domains()
    if not domains:
        return None
    return {
        "type": TOOL_TYPE,
        "name": TOOL_NAME,
        "max_uses": int(settings.LLM.get("SEARCH_MAX_USES", 5)),
        "allowed_domains": domains,
    }


def domains_for_university(university) -> list[str]:
    """Белый список под конкретный вуз: его домен и Common App.

    Искать требования Гарварда по сайту соседнего вуза незачем, а лишний
    домен в списке — лишняя возможность привезти чужое число.
    """
    from universities.sync import COMMON_HOSTS

    hosts = {host.lower() for host in COMMON_HOSTS}
    own = (getattr(university, "domain", "") or "").strip().lower()
    if not own:
        own = host_of(getattr(university, "website", "") or "")
    if own:
        hosts.add(own.removeprefix("www."))
    return sorted(hosts)


def keep_allowed(sources: list[Source]) -> tuple[list[Source], list[str]]:
    """Отсеять источники вне белого списка.

    Возвращает оставленные и отброшенные адреса — последние попадают
    в журнал и в ответ операции: молча потерянный источник выглядит так,
    будто факта не было вовсе.
    """
    kept, dropped = [], []
    for source in sources:
        if source.url and is_allowed(source.url):
            kept.append(source)
        else:
            dropped.append(source.url or "(без ссылки)")
            log.warning("Источник вне белого списка отброшен: %s", source.url)
    return kept, dropped


def sources_from_payload(rows: list[dict] | None) -> list[Source]:
    """Источники из структурированного ответа модели."""
    result = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        url = (row.get("source_url") or row.get("url") or "").strip()
        if not url:
            continue
        result.append(
            Source(
                url=url,
                quote=(row.get("quote") or "")[:400],
                checked_at=(row.get("checked_at") or "").strip(),
                title=(row.get("title") or "")[:200],
            )
        )
    return result


def visited_urls(raw: Any) -> list[str]:
    """Адреса, по которым провайдер реально сходил.

    Нужны, чтобы проверить обещание `allowed_domains` по факту, а не по
    описанию инструмента.
    """
    urls: list[str] = []
    if not isinstance(raw, dict):
        return urls
    for block in raw.get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "web_search_tool_result":
            continue
        for item in block.get("content") or []:
            if isinstance(item, dict) and item.get("url"):
                urls.append(item["url"])
    return urls


def offenders(raw: Any) -> list[str]:
    """Адреса вне белого списка среди тех, куда провайдер сходил."""
    return [url for url in visited_urls(raw) if not is_allowed(url)]
