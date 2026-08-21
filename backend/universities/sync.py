"""Фоновая сверка дедлайнов.

Обходим только официальные сайты вузов и Common App по белому списку
доменов. Никаких форумов и агрегаторов: там числа живут своей жизнью.

Каждый извлечённый факт хранит ссылку, дату и фрагмент-источник.
Без источника поле не меняется — расхождение уходит в `Suggestion`
директору по поступлению, применяет человек (инвариант №3).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

log = logging.getLogger(__name__)

#: Домены, всегда разрешённые вдобавок к доменам самих вузов.
COMMON_HOSTS = ("commonapp.org", "apply.commonapp.org")

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

#: «January 15, 2027», «15 January 2027», «2027-01-15»
DATE_PATTERNS = (
    re.compile(r"\b(?P<month>[A-Za-z]{3,9})\s+(?P<day>\d{1,2}),?\s+(?P<year>20\d{2})\b"),
    re.compile(r"\b(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]{3,9})\s+(?P<year>20\d{2})\b"),
    re.compile(r"\b(?P<year>20\d{2})-(?P<month_num>\d{2})-(?P<day>\d{2})\b"),
)

ROUND_HINTS = {
    "ED": ("early decision", "ed i", "ed ii", "ed1", "ed2"),
    "EA": ("early action", "restrictive early action", "rea"),
    "RD": ("regular decision", "regular deadline", "final deadline"),
    "Rolling": ("rolling admission", "rolling basis"),
}


class NotWhitelisted(Exception):
    """Домен не в белом списке."""


@dataclass(frozen=True)
class ExtractedFact:
    """Найденный факт: что, откуда и каким текстом подтверждается."""

    round_type: str
    deadline: date
    source_url: str
    quote: str

    def as_dict(self) -> dict:
        return {
            "round_type": self.round_type,
            "deadline": self.deadline.isoformat(),
            "source_url": self.source_url,
            "quote": self.quote,
        }


def host_of(url: str) -> str:
    """Хост адреса без ведущего www.

    Именно `removeprefix`, а не `lstrip`: последний срезает любые символы
    из набора «w» и «.», превращая wisconsin.edu в isconsin.edu.
    """
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def allowed_hosts() -> set[str]:
    """Белый список: домены вузов из справочника плюс Common App."""
    from universities.models import University

    hosts = {h.lower() for h in COMMON_HOSTS}
    hosts |= {h.lower() for h in settings.SYNC_EXTRA_HOSTS}
    hosts |= {d.lower() for d in University.objects.exclude(domain="").values_list("domain", flat=True) if d}
    return hosts


def is_allowed(url: str) -> bool:
    """Разрешён ли адрес. Поддомены официального домена вуза разрешены."""
    host = host_of(url)
    if not host:
        return False
    for allowed in allowed_hosts():
        if host == allowed or host.endswith(f".{allowed}"):
            return True
    return False


def fetch(url: str, *, timeout: int | None = None) -> str:
    """Скачать страницу. Не из белого списка — не ходим вовсе."""
    if not is_allowed(url):
        raise NotWhitelisted(f"{host_of(url)} не в белом списке — сверка не выполняется")

    import requests

    response = requests.get(
        url,
        timeout=timeout or settings.SYNC_TIMEOUT,
        headers={"User-Agent": settings.SYNC_USER_AGENT},
    )
    response.raise_for_status()
    return response.text


def strip_html(html: str) -> str:
    """Грубо вытащить текст: тегов нам не нужно, нужны предложения."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def parse_date(fragment: str) -> date | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(fragment)
        if not match:
            continue
        parts = match.groupdict()
        try:
            if parts.get("month_num"):
                return date(int(parts["year"]), int(parts["month_num"]), int(parts["day"]))
            month = MONTHS.get(parts["month"].lower())
            if month is None:
                continue
            return date(int(parts["year"]), month, int(parts["day"]))
        except ValueError:
            continue
    return None


def extract_facts(text: str, source_url: str) -> list[ExtractedFact]:
    """Найти дедлайны по типам раундов.

    Берём предложение целиком: оно и станет фрагментом-источником,
    по которому директор проверит, что число не выдумано.
    """
    facts: list[ExtractedFact] = []
    sentences = re.split(r"(?<=[.!?;])\s+|\n+", text)

    for sentence in sentences:
        low = sentence.lower()
        for round_type, hints in ROUND_HINTS.items():
            if not any(hint in low for hint in hints):
                continue
            deadline = parse_date(sentence)
            if deadline is None:
                continue
            facts.append(
                ExtractedFact(
                    round_type=round_type,
                    deadline=deadline,
                    source_url=source_url,
                    quote=sentence.strip()[:400],
                )
            )
            break
    return facts


def check_round(admission_round, *, url: str | None = None) -> dict:
    """Сверить один раунд с официальным сайтом.

    Возвращает найденный факт и признак расхождения. Ничего не меняет:
    решение — за директором по поступлению.
    """
    target = url or admission_round.source_url or admission_round.program.university.website
    if not target:
        return {"ok": False, "reason": "У раунда нет источника, сверять нечего"}
    if not is_allowed(target):
        return {"ok": False, "reason": f"{host_of(target)} не в белом списке"}

    try:
        text = strip_html(fetch(target))
    except Exception as exc:
        log.warning("Сверка %s не удалась: %s", target, exc)
        return {"ok": False, "reason": str(exc)}

    facts = [f for f in extract_facts(text, target) if f.round_type == admission_round.round_type]
    if not facts:
        return {"ok": True, "found": False, "reason": "Дедлайн на странице не найден"}

    fact = facts[0]
    admission_round.checked_at = timezone.now()
    admission_round.save(update_fields=["checked_at", "updated_at"])

    return {
        "ok": True,
        "found": True,
        "changed": fact.deadline != admission_round.deadline,
        "current": admission_round.deadline.isoformat(),
        "fact": fact.as_dict(),
    }


def now_iso() -> str:
    return datetime.now(tz=timezone.get_current_timezone()).isoformat()
