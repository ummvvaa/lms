"""Импорт банка заданий из файла.

Формат простой и человекочитаемый: одна строка — одно задание.
Колонки: exam_type, section, topic, difficulty, text, A, B, C, D,
correct, explanation, source. Пустые строки пропускаются.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from django.db import transaction

from prep.models import Difficulty, Question, QuestionOption, Section
from students.models import ExamType

REQUIRED = ("exam_type", "section", "topic", "text", "correct")
LETTERS = ("A", "B", "C", "D", "E")


@dataclass
class ImportResult:
    created: int = 0
    skipped: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"created": self.created, "skipped": self.skipped}


def read_rows(uploaded) -> list[dict]:
    raw = uploaded.read()
    text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else str(raw)
    dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t") if text.strip() else csv.excel
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


@transaction.atomic
def import_questions(uploaded) -> ImportResult:
    """Загрузить задания. Строка с ошибкой не роняет весь файл."""
    result = ImportResult()

    for number, row in enumerate(read_rows(uploaded), start=2):
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        missing = [name for name in REQUIRED if not clean.get(name)]
        if missing:
            result.skipped.append({"row": number, "reason": f"не заполнено: {', '.join(missing)}"})
            continue

        if clean["exam_type"].upper() not in ExamType.values:
            result.skipped.append({"row": number, "reason": f"неизвестный экзамен «{clean['exam_type']}»"})
            continue
        if clean["section"].lower() not in Section.values:
            result.skipped.append({"row": number, "reason": f"неизвестная секция «{clean['section']}»"})
            continue

        options = [(letter, clean.get(letter.lower(), "")) for letter in LETTERS]
        options = [(letter, text) for letter, text in options if text]
        if len(options) < 2:
            result.skipped.append({"row": number, "reason": "нужно минимум два варианта ответа"})
            continue

        correct = clean["correct"].upper()
        if correct not in {letter for letter, _ in options}:
            result.skipped.append({"row": number, "reason": f"верный вариант «{correct}» не найден среди ответов"})
            continue

        difficulty = clean.get("difficulty", "").lower()
        question = Question.objects.create(
            exam_type=clean["exam_type"].upper(),
            section=clean["section"].lower(),
            topic=clean["topic"][:120],
            difficulty=difficulty if difficulty in Difficulty.values else Difficulty.MEDIUM,
            text=clean["text"],
            explanation=clean.get("explanation", ""),
            source=clean.get("source", "")[:250],
        )
        for letter, text in options:
            QuestionOption.objects.create(
                question=question, letter=letter, text=text[:500], is_correct=letter == correct
            )
        result.created += 1

    return result
