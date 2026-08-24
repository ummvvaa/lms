"""Разбор того, что человек принёс: название вуза, описание активности, фото.

Всё, что здесь получается, складывается в предложение и ждёт человека
(инвариант №3). Записи справочника, разобранные моделью, заводятся
с источником `ai` и признаком «не подтверждено» — сверяет их директор
по поступлению по официальному сайту (инвариант №14).

Без модели работают только те разборы, которым хватает правил: текст
с баллами. Распознавание фото без модели невозможно, и интерфейс говорит
об этом прямо, а не показывает пустой результат.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone

from core.domains import domain_of_role
from suggestions.llm import Attachment, LLMUnavailable, complete, image_from_bytes, is_available

UNIVERSITY_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Официальное название вуза"},
        "country": {"type": "string"},
        "website": {"type": "string"},
        "domain": {"type": "string", "description": "Домен сайта без схемы"},
        "programs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "level": {"type": "string", "enum": ["bachelor", "master"]},
                    "min_gpa": {"type": "string"},
                    "min_ielts": {"type": "string"},
                    "min_toefl": {"type": "string"},
                    "min_sat": {"type": "string"},
                    "deadline": {"type": "string", "description": "Дедлайн в формате ГГГГ-ММ-ДД"},
                    "round_type": {"type": "string", "enum": ["ED", "EA", "RD", "RO"]},
                },
                "required": ["name"],
            },
        },
    },
    "required": ["name"],
}

UNIVERSITY_RULES = """Ты помогаешь завести карточку вуза в справочник школы.

Правила:
- если чего-то не знаешь точно — оставь поле пустым, не додумывай;
- пороги и дедлайны указывай только те, в которых уверен: их будет
  проверять человек, и выдуманное число дороже пустого поля;
- дедлайн отдавай в формате ГГГГ-ММ-ДД."""

ACTIVITY_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": [
                "olympiad",
                "project",
                "research",
                "startup",
                "leadership",
                "volunteering",
                "competition",
                "award",
            ],
        },
        "subject": {"type": "string", "description": "Предмет олимпиады, если это олимпиада"},
        "title": {"type": "string"},
        "date": {"type": "string", "description": "Дата в формате ГГГГ-ММ-ДД"},
        "description": {"type": "string"},
        "strength": {"type": "string", "description": "Чем эта активность сильна для заявки, одна фраза"},
        "missing": {"type": "string", "description": "Чего не хватает, чтобы она считалась подтверждённой"},
    },
    "required": ["category", "title"],
}

CERTIFICATE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Название соревнования или олимпиады"},
        "date": {"type": "string", "description": "Дата в формате ГГГГ-ММ-ДД"},
        "result": {"type": "string", "description": "Место или результат"},
        "confidence": {"type": "number", "description": "Насколько уверенно прочитано, 0..1"},
    },
    "required": ["name"],
}

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "exam_type": {"type": "string", "enum": ["IELTS", "TOEFL", "SAT", "ACT"]},
        "total_score": {"type": "string"},
        "date": {"type": "string", "description": "Дата сдачи в формате ГГГГ-ММ-ДД"},
        "listening": {"type": "string"},
        "reading": {"type": "string"},
        "writing": {"type": "string"},
        "speaking": {"type": "string"},
        "math": {"type": "string"},
        "verbal": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["exam_type"],
}

IMAGE_RULES = """Ты читаешь то, что на картинке, и ничего не добавляешь от себя.

Правила:
- пиши только то, что видно; нечитаемое поле оставляй пустым;
- если не уверен в цифре, снижай `confidence` — человек проверит;
- ничего не переводи и не «исправляй»: как написано, так и передавай."""


class NeedsModel(Exception):
    """Операция без модели невозможна. Текст пригоден для показа человеку."""


def _guard_model() -> None:
    if not is_available():
        raise NeedsModel(
            "Для распознавания нужна подключённая модель. Сейчас она недоступна — "
            "заведите запись руками или попросите администратора проверить ключ и лимит расходов"
        )


# --- Вуз по названию или ссылке -------------------------------------------


def parse_university(*, text: str, actor, role: str) -> dict:
    """Из названия или ссылки достать программы, раунды, дедлайны, требования.

    Ничего не пишет в справочник напрямую: собирает предложение, а записи
    появятся, когда человек его применит — с плашкой «не подтверждено».
    """
    from suggestions.engine import create_suggestion

    _guard_model()
    try:
        response = complete(
            system=UNIVERSITY_RULES,
            user=f"Вуз: {text.strip()}\n\nСобери карточку: название, страну, сайт, программы и их требования.",
            purpose="parse_university",
            actor=actor,
            role=role,
            schema=UNIVERSITY_SCHEMA,
            max_tokens=1500,
        )
    except LLMUnavailable as error:
        raise NeedsModel(f"Модель не ответила: {error}") from error

    payload = response.parsed or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return {"ok": False, "detail": "Не удалось понять, о каком вузе речь. Попробуйте полное название или ссылку"}

    rows = _university_rows(payload, source=text.strip())
    suggestion, rejected = create_suggestion(
        author=actor,
        role=role,
        domain_code=(domain_of_role(role).code if domain_of_role(role) else ""),
        source_type="manual",
        command="parse_university",
        rows=rows,
        source_ref=text.strip()[:250],
    )
    return {
        "ok": True,
        "suggestion": suggestion.pk,
        "rows": len(rows) - len(rejected),
        "university": name,
        "detail": (
            f"Карточка «{name}» разобрана. Записи заведутся неподтверждёнными: "
            f"сверьте пороги и дедлайны с сайтом вуза перед тем, как снимать плашку"
        ),
    }


def _university_rows(payload: dict, *, source: str) -> list[dict[str, Any]]:
    """Разобранный вуз в строки предложения со ссылками между ними."""
    key = uuid.uuid4().hex[:12]
    uni_key = f"{key}-u"
    rows: list[dict[str, Any]] = []

    def add(model: str, obj_key: str, field: str, value: Any, confidence: float = 0.6) -> None:
        if value in (None, ""):
            return
        rows.append(
            {
                "model": model,
                "field": field,
                "value": value,
                "new_object_key": obj_key,
                "confidence": confidence,
                "source_ref": source[:250],
            }
        )

    add("universities.University", uni_key, "name", payload.get("name"), 0.8)
    add("universities.University", uni_key, "country", payload.get("country"))
    add("universities.University", uni_key, "website", payload.get("website"))
    add("universities.University", uni_key, "domain", payload.get("domain"))
    # запись от модели всегда неподтверждённая (инвариант №14)
    add("universities.University", uni_key, "data_source", "ai", 1)
    add("universities.University", uni_key, "is_verified", False, 1)

    for i, program in enumerate(payload.get("programs") or [], start=1):
        program_key = f"{key}-p{i}"
        add("universities.Program", program_key, "university", f"@{uni_key}", 0.8)
        add("universities.Program", program_key, "name", program.get("name"), 0.8)
        add("universities.Program", program_key, "level", program.get("level") or "bachelor")
        add("universities.Program", program_key, "data_source", "ai", 1)
        add("universities.Program", program_key, "is_verified", False, 1)

        thresholds = {
            "min_gpa": program.get("min_gpa"),
            "min_ielts": program.get("min_ielts"),
            "min_toefl": program.get("min_toefl"),
            "min_sat": program.get("min_sat"),
        }
        if any(value for value in thresholds.values()):
            requirement_key = f"{key}-r{i}"
            add("universities.AdmissionRequirement", requirement_key, "program", f"@{program_key}", 0.8)
            for field_name, value in thresholds.items():
                add("universities.AdmissionRequirement", requirement_key, field_name, value, 0.5)
            add("universities.AdmissionRequirement", requirement_key, "source_url", payload.get("website") or "")
            add("universities.AdmissionRequirement", requirement_key, "data_source", "ai", 1)
            add("universities.AdmissionRequirement", requirement_key, "is_verified", False, 1)

        if program.get("deadline"):
            round_key = f"{key}-d{i}"
            add("universities.AdmissionRound", round_key, "program", f"@{program_key}", 0.8)
            add("universities.AdmissionRound", round_key, "round_type", program.get("round_type") or "RD")
            add("universities.AdmissionRound", round_key, "deadline", program.get("deadline"), 0.5)
            add("universities.AdmissionRound", round_key, "source_url", payload.get("website") or "")
            add("universities.AdmissionRound", round_key, "data_source", "ai", 1)
            add("universities.AdmissionRound", round_key, "is_verified", False, 1)

    return rows


# --- Активность по описанию -----------------------------------------------


def parse_activity(*, text: str, student_id: int, actor, role: str) -> dict:
    """Из описания определить категорию, предмет, силу для заявки и пробелы."""
    from suggestions.engine import create_suggestion

    _guard_model()
    subjects = _known_subjects()
    try:
        response = complete(
            system=(
                "Ты разбираешь описание внеучебной активности ученика.\n"
                "Правила: опирайся только на текст; предмет выбирай из списка школы, "
                "а если подходящего нет — оставь пустым; ничего не выдумывай."
            ),
            user=(
                f"Описание: {text.strip()}\n\n"
                f"Предметы школы (выбирать только отсюда): {', '.join(subjects) or 'список пуст'}"
            ),
            purpose="parse_activity",
            actor=actor,
            role=role,
            schema=ACTIVITY_SCHEMA,
            max_tokens=700,
        )
    except LLMUnavailable as error:
        raise NeedsModel(f"Модель не ответила: {error}") from error

    payload = response.parsed or {}
    title = (payload.get("title") or "").strip()
    if not title:
        return {"ok": False, "detail": "Не удалось понять, что это за активность — опишите подробнее"}

    key = uuid.uuid4().hex[:12]
    rows = [
        {
            "student": student_id,
            "model": "students.Activity",
            "field": "title",
            "value": title,
            "new_object_key": key,
            "confidence": 0.8,
            "source_quote": text.strip()[:250],
        },
        {
            "student": student_id,
            "model": "students.Activity",
            "field": "category",
            "value": payload.get("category") or "project",
            "new_object_key": key,
            "confidence": 0.7,
        },
    ]
    if payload.get("description"):
        rows.append(
            {
                "student": student_id,
                "model": "students.Activity",
                "field": "description",
                "value": payload["description"],
                "new_object_key": key,
                "confidence": 0.7,
            }
        )
    if payload.get("date"):
        rows.append(
            {
                "student": student_id,
                "model": "students.Activity",
                "field": "date",
                "value": payload["date"],
                "new_object_key": key,
                "confidence": 0.6,
            }
        )
    subject = _subject_by_name(payload.get("subject"))
    if subject is not None:
        rows.append(
            {
                "student": student_id,
                "model": "students.Activity",
                "field": "subject",
                "value": subject.pk,
                "new_object_key": key,
                "confidence": 0.7,
            }
        )

    suggestion, rejected = create_suggestion(
        author=actor,
        role=role,
        domain_code=(domain_of_role(role).code if domain_of_role(role) else ""),
        source_type="manual",
        command="parse_activity",
        rows=rows,
        source_ref=text.strip()[:250],
    )
    return {
        "ok": True,
        "suggestion": suggestion.pk,
        "rows": len(rows) - len(rejected),
        "strength": (payload.get("strength") or "").strip(),
        "missing": (payload.get("missing") or "").strip(),
        "detail": f"Активность «{title}» разобрана — проверьте и примените",
    }


def _known_subjects() -> list[str]:
    from directories.models import OlympiadSubject

    return list(OlympiadSubject.objects.filter(is_active=True).values_list("name", flat=True))


def _subject_by_name(name: str | None):
    if not name:
        return None
    from core.references import find
    from directories.models import OlympiadSubject

    try:
        return find(OlympiadSubject, name)
    except LookupError:
        # предмета нет в справочнике — молча его не заводим (фаза 18)
        return None


# --- Фото грамоты и скриншот с баллами ------------------------------------


def parse_certificate(*, payload: bytes, media_type: str, student_id: int, actor, role: str) -> dict:
    """Фото грамоты → соревнование, дата, результат."""
    from suggestions.engine import create_suggestion

    _guard_model()
    parsed = _read_image(
        payload=payload,
        media_type=media_type,
        schema=CERTIFICATE_SCHEMA,
        purpose="parse_certificate",
        prompt="На картинке грамота или диплом. Прочитай название соревнования, дату и результат.",
        actor=actor,
        role=role,
    )
    name = (parsed.get("name") or "").strip()
    if not name:
        return {"ok": False, "detail": "На картинке не удалось прочитать название — попробуйте снимок почётче"}

    confidence = float(parsed.get("confidence") or 0.5)
    key = uuid.uuid4().hex[:12]
    rows = [
        {
            "student": student_id,
            "model": "students.Competition",
            "field": "name",
            "value": name,
            "new_object_key": key,
            "confidence": confidence,
            "source_quote": "распознано с изображения",
        },
        {
            "student": student_id,
            "model": "students.Competition",
            "field": "has_certificate",
            "value": True,
            "new_object_key": key,
            "confidence": 0.9,
        },
    ]
    for field_name in ("date", "result"):
        if parsed.get(field_name):
            rows.append(
                {
                    "student": student_id,
                    "model": "students.Competition",
                    "field": field_name,
                    "value": parsed[field_name],
                    "new_object_key": key,
                    "confidence": confidence,
                }
            )

    suggestion, rejected = create_suggestion(
        author=actor,
        role=role,
        domain_code=(domain_of_role(role).code if domain_of_role(role) else ""),
        source_type="image",
        command="parse_certificate",
        rows=rows,
        source_ref="фото грамоты",
    )
    return {
        "ok": True,
        "suggestion": suggestion.pk,
        "rows": len(rows) - len(rejected),
        "detail": f"С грамоты прочитано: «{name}». Проверьте и примените",
    }


def parse_score_screenshot(*, payload: bytes, media_type: str, student_id: int, actor, role: str) -> dict:
    """Скриншот с баллами → попытка экзамена."""
    from suggestions.engine import create_suggestion

    _guard_model()
    parsed = _read_image(
        payload=payload,
        media_type=media_type,
        schema=SCORE_SCHEMA,
        purpose="parse_score_screenshot",
        prompt="На картинке результат экзамена. Прочитай вид экзамена, общий балл, дату и баллы по секциям.",
        actor=actor,
        role=role,
    )
    exam = (parsed.get("exam_type") or "").strip()
    if not exam:
        return {"ok": False, "detail": "На картинке не видно, что это за экзамен — заведите попытку руками"}

    confidence = float(parsed.get("confidence") or 0.5)
    key = uuid.uuid4().hex[:12]
    rows = [
        {
            "student": student_id,
            "model": "students.ExamAttempt",
            "field": "exam_type",
            "value": exam,
            "new_object_key": key,
            "confidence": confidence,
            "source_quote": "распознано со скриншота",
        },
        {
            "student": student_id,
            "model": "students.ExamAttempt",
            "field": "attempt_format",
            "value": "official",
            "new_object_key": key,
            "confidence": 0.6,
        },
        {
            "student": student_id,
            "model": "students.ExamAttempt",
            "field": "source",
            "value": "ai",
            "new_object_key": key,
            "confidence": 0.9,
        },
        {
            "student": student_id,
            "model": "students.ExamAttempt",
            "field": "date",
            "value": parsed.get("date") or timezone.localdate().isoformat(),
            "new_object_key": key,
            "confidence": confidence,
        },
    ]
    for field_name in ("total_score", "listening", "reading", "writing", "speaking", "math", "verbal"):
        if parsed.get(field_name):
            rows.append(
                {
                    "student": student_id,
                    "model": "students.ExamAttempt",
                    "field": field_name,
                    "value": parsed[field_name],
                    "new_object_key": key,
                    "confidence": confidence,
                }
            )

    suggestion, rejected = create_suggestion(
        author=actor,
        role=role,
        domain_code=(domain_of_role(role).code if domain_of_role(role) else ""),
        source_type="image",
        command="parse_certificate",
        rows=rows,
        source_ref="скриншот с баллами",
    )
    return {
        "ok": True,
        "suggestion": suggestion.pk,
        "rows": len(rows) - len(rejected),
        "detail": (
            f"Со скриншота прочитан {exam}. Балл попадёт в карточку только после того, как вы примените предложение"
        ),
    }


def _read_image(*, payload: bytes, media_type: str, schema: dict, purpose: str, prompt: str, actor, role: str) -> dict:
    image: Attachment = image_from_bytes(payload, media_type)
    try:
        response = complete(
            system=IMAGE_RULES,
            user=prompt,
            purpose=purpose,
            actor=actor,
            role=role,
            schema=schema,
            images=[image],
            max_tokens=700,
        )
    except LLMUnavailable as error:
        raise NeedsModel(f"Модель не ответила: {error}") from error
    return response.parsed or {}
