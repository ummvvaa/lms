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


def rows_for_suggestion(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Собрать строки предложения и список неоднозначностей.

    Уверенность строки складывается из уверенности сопоставления имени:
    сомнительное имя даёт сомнительную строку, и в предпросмотре она
    окажется сверху.
    """
    parsed = parse_scores(text)
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
