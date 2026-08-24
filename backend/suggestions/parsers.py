"""Разбор вставленного текста.

Работает и без подключённой модели: баллы из переписки вытаскиваются
правилами. Модель подключается сверху и умеет больше, но школа не должна
вставать, если ключа нет или провайдер недоступен.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from suggestions.name_matching import find_many

#: «Ахметова Аружан — 6.5», «Сериков Дамир: SAT 1320», «Иванов 7,0»
LINE = re.compile(
    r"^\s*(?P<name>[^\d:—–\-|\t]+?)\s*[-—–:|\t]+\s*(?P<rest>.+?)\s*$",
    re.UNICODE,
)
IELTS = re.compile(r"(?:ielts|айлтс)?\s*\b([4-9](?:[.,]\d)?)\b", re.IGNORECASE)
SAT = re.compile(r"(?:sat)?\s*\b(\d{3,4})\b", re.IGNORECASE)


@dataclass
class ParsedRow:
    """Одна разобранная строка."""

    raw: str
    name: str
    values: dict[str, Any] = field(default_factory=dict)


def _looks_like_sat(value: int) -> bool:
    return 400 <= value <= 1600


def parse_scores(text: str) -> list[ParsedRow]:
    """Вытащить имена и баллы из куска переписки."""
    rows: list[ParsedRow] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = LINE.match(line)
        if not match:
            continue

        name = match.group("name").strip(" .•-–—\t")
        rest = match.group("rest")
        if not name:
            continue

        values: dict[str, Any] = {}

        # SAT ищем первым: трёх-четырёхзначное число не спутать с IELTS
        for candidate in re.findall(r"\b(\d{3,4})\b", rest):
            if _looks_like_sat(int(candidate)):
                values["sat_current"] = int(candidate)
                break

        # IELTS: одна цифра 4–9, иногда с половиной. Число вида 1320 сюда
        # не попадает — шаблон требует границ слова.
        ielts_match = re.search(r"\b([4-9](?:[.,]\d)?)\b", rest)
        if ielts_match:
            value = float(ielts_match.group(1).replace(",", "."))
            if 4.0 <= value <= 9.0:
                values["ielts_current"] = value

        if values:
            rows.append(ParsedRow(raw=line, name=name, values=values))
    return rows


FIELD_MODELS = {
    "ielts_current": "students.ExamProfile",
    "sat_current": "students.ExamProfile",
    "attendance_percent": "students.BehaviorProfile",
    "homework_percent": "students.BehaviorProfile",
}


SECOND_PASS_RULES = """Ты разбираешь кусок переписки, где сотрудники школы пишут баллы учеников.

Правила:
- бери только те строки, где есть и имя, и число; остальное пропускай;
- ничего не выдумывай: если балла нет, строки быть не должно;
- IELTS — от 0 до 9, SAT — от 400 до 1600, посещаемость и домашние задания — проценты;
- имена передавай так, как они написаны в тексте."""

SECOND_PASS_SCHEMA = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "field": {
                        "type": "string",
                        "enum": ["ielts_current", "sat_current", "attendance_percent", "homework_percent"],
                    },
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["name", "field", "value"],
            },
        }
    },
    "required": ["rows"],
}


def second_pass(text: str, *, handled: set[str], actor=None, role: str = "") -> list[ParsedRow]:
    """Отдать модели то, что не разобрали правила.

    Правила берут «Ахметова — 6.5» и подобное. Живая переписка бывает
    сложнее: «у Алии наконец 6.5, а Дамир написал сат на 1320». Модель
    подключается вторым проходом — и только к тем строкам, которые
    правила не тронули.
    """
    from suggestions.llm import LLMUnavailable, complete

    left = [line.strip() for line in text.splitlines() if line.strip() and line.strip() not in handled]
    if not left:
        return []

    try:
        response = complete(
            system=SECOND_PASS_RULES,
            user="Строки, которые не разобрались:\n" + "\n".join(left[:60]),
            purpose="paste_second_pass",
            actor=actor,
            role=role,
            schema=SECOND_PASS_SCHEMA,
            max_tokens=1200,
        )
    except LLMUnavailable:
        # модели нет или лимит выбран — остаёмся с тем, что разобрали правила
        return []

    rows: list[ParsedRow] = []
    for row in (response.parsed or {}).get("rows", [])[:60]:
        name = str(row.get("name") or "").strip()
        field_name = str(row.get("field") or "")
        if not name or field_name not in FIELD_MODELS:
            continue
        value = _as_number(row.get("value"))
        if value is None:
            continue
        rows.append(ParsedRow(raw=str(row.get("quote") or name), name=name, values={field_name: value}))
    return rows


def _as_number(raw: Any) -> float | int | None:
    """Число из строки. Мусор пропускаем: лучше строки не будет, чем кривая."""
    try:
        number = float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def rows_for_suggestion(
    text: str, *, actor=None, role: str = "", use_model: bool = True
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Собрать строки предложения и список неоднозначностей.

    Уверенность строки складывается из уверенности сопоставления имени:
    сомнительное имя даёт сомнительную строку, и в предпросмотре она
    окажется сверху.
    """
    parsed = parse_scores(text)
    if use_model:
        parsed += second_pass(text, handled={row.raw for row in parsed}, actor=actor, role=role)
    outcomes = find_many([row.name for row in parsed])

    rows: list[dict[str, Any]] = []
    ambiguities: list[dict[str, Any]] = []

    for row, outcome in zip(parsed, outcomes, strict=True):
        if not outcome.is_confident:
            ambiguities.append({**outcome.as_dict(), "raw": row.raw, "values": row.values})
            continue
        for field_name, value in row.values.items():
            rows.append(
                {
                    "student": outcome.best.student_id,
                    "model": FIELD_MODELS[field_name],
                    "field": field_name,
                    "value": value,
                    "confidence": round(outcome.best.confidence, 3),
                    "source_quote": row.raw,
                }
            )
    return rows, ambiguities
