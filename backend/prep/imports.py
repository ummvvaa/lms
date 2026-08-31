"""Импорт банка заданий из файла (фаза 42: полный формат).

Формат человекочитаемый: одна строка — одно задание. Обязательное:
exam_type, section, topic, text, correct. Всё остальное — по необходимости,
и его хватает для настоящих банков семи экзаменов. Полное описание колонок,
как класть аудио и как связать текст с группой вопросов — в
`docs/QUESTION_BANK.md`.

Файлы аудио и изображений грузятся отдельно и подхватываются по имени:
в колонках `audio_file` и `image_file` стоит имя файла, а сам файл — среди
приложенных. Один текст (или один аудиофайл) на несколько вопросов
выражается общим `passage_key`.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from django.db import transaction

from prep.models import (
    Difficulty,
    PassageKind,
    Question,
    QuestionOption,
    QuestionPassage,
    QuestionType,
    Section,
)
from students.models import ExamType

#: `correct` обязателен только у заданий с выбором — проверяется отдельно
REQUIRED = ("exam_type", "section", "topic", "text")
LETTERS = ("A", "B", "C", "D", "E", "F")


@dataclass
class ImportResult:
    created: int = 0
    passages: int = 0
    skipped: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"created": self.created, "passages": self.passages, "skipped": self.skipped}


def read_rows(text: str) -> list[dict]:
    if not text.strip():
        return []
    dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


def _clip(text: str, n: int) -> str:
    return (text or "")[:n]


@transaction.atomic
def import_questions(content: str, *, media: dict[str, tuple[bytes, str]] | None = None, dry_run: bool = False):
    """Загрузить задания. Строка с ошибкой не роняет весь файл.

    `content` — текст файла с заданиями; `media` — приложенные аудио
    и картинки (`{имя_файла: (байты, тип)}`). `dry_run` откатывает
    транзакцию: предпросмотр показывает, что заведётся, до записи.
    """
    result = ImportResult()
    media = media or {}
    passages: dict[str, QuestionPassage] = {}

    for number, row in enumerate(read_rows(content), start=2):
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        missing = [name for name in REQUIRED if not clean.get(name)]
        if missing:
            result.skipped.append({"row": number, "reason": f"не заполнено: {', '.join(missing)}"})
            continue

        exam = clean["exam_type"].upper()
        # ЕНТ и HSK пишутся как есть; остальное — заглавными
        exam = next((v for v in ExamType.values if v.upper() == exam), clean["exam_type"])
        if exam not in ExamType.values:
            result.skipped.append({"row": number, "reason": f"неизвестный экзамен «{clean['exam_type']}»"})
            continue
        section = clean["section"].lower()
        if section not in Section.values:
            result.skipped.append({"row": number, "reason": f"неизвестная секция «{clean['section']}»"})
            continue

        qtype = clean.get("question_type", "").lower()
        qtype = qtype if qtype in QuestionType.values else QuestionType.SINGLE

        # варианты и верный ответ нужны только для выбора; у письменных
        # и коротких заданий проверяет человек — там их может не быть
        options = [(letter, clean.get(letter.lower(), "")) for letter in LETTERS]
        options = [(letter, text) for letter, text in options if text]
        correct_raw = clean.get("correct", "")
        correct_letters = {c.strip().upper() for c in correct_raw.replace(";", ",").split(",") if c.strip()}

        if qtype in (QuestionType.SINGLE, QuestionType.MULTIPLE):
            if not correct_letters:
                result.skipped.append({"row": number, "reason": "не указан верный вариант"})
                continue
            if len(options) < 2:
                result.skipped.append({"row": number, "reason": "нужно минимум два варианта ответа"})
                continue
            if not correct_letters <= {letter for letter, _ in options}:
                result.skipped.append({"row": number, "reason": f"верный вариант «{correct_raw}» не среди ответов"})
                continue

        # источник-группа: текст чтения или аудио. Первый раз с этим ключом —
        # создаём, дальше вопросы к нему присоединяются
        passage = None
        passage_key = clean.get("passage_key", "")
        if passage_key:
            passage = passages.get(passage_key)
            if passage is None:
                kind = clean.get("passage_kind", "").lower()
                kind = kind if kind in PassageKind.values else PassageKind.READING
                audio_name = clean.get("audio_file", "")
                passage = QuestionPassage.objects.create(
                    exam_type=exam,
                    section=section,
                    kind=kind,
                    title=_clip(clean.get("passage_title", ""), 200),
                    body=clean.get("passage_text", ""),
                    source=_clip(clean.get("source", ""), 250),
                )
                if audio_name and audio_name in media:
                    blob, ctype = media[audio_name]
                    from django.core.files.base import ContentFile

                    passage.audio.save(audio_name, ContentFile(blob), save=False)
                    passage.audio_content_type = ctype
                    passage.save(update_fields=["audio", "audio_content_type"])
                passages[passage_key] = passage
                result.passages += 1

        difficulty = clean.get("difficulty", "").lower()
        question = Question.objects.create(
            exam_type=exam,
            section=section,
            topic=_clip(clean["topic"], 120),
            subtopic=_clip(clean.get("subtopic", ""), 120),
            difficulty=difficulty if difficulty in Difficulty.values else Difficulty.MEDIUM,
            question_type=qtype,
            text=clean["text"],
            explanation=clean.get("explanation", ""),
            criteria=clean.get("criteria", ""),
            sample_answer=clean.get("sample_answer", ""),
            expected_seconds=_int(clean.get("expected_seconds")),
            source=_clip(clean.get("source", ""), 250),
            source_year=_int(clean.get("source_year")),
            passage=passage,
        )
        image_name = clean.get("image_file", "")
        if image_name and image_name in media:
            blob, ctype = media[image_name]
            from django.core.files.base import ContentFile

            question.image.save(image_name, ContentFile(blob), save=False)
            question.image_content_type = ctype
            question.save(update_fields=["image", "image_content_type"])
        for letter, text in options:
            QuestionOption.objects.create(
                question=question, letter=letter, text=_clip(text, 500), is_correct=letter in correct_letters
            )
        result.created += 1

    if dry_run:
        transaction.set_rollback(True)
    return result


def _int(value) -> int | None:
    try:
        return int(str(value).strip()) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
