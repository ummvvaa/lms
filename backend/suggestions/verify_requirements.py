"""Сверка требований программы с официальным сайтом.

Фоновая сверка (`universities.sync`) читает страницу сама и умеет искать
дедлайны по знакомым формулировкам. Здесь тот же смысл, но по требованиям:
пороги IELTS, TOEFL, SAT и GPA написаны на сайтах словами и таблицами,
и разобрать их правилами не выходит.

Правила те же, что и везде:

* ищем только по белому списку — сайт этого вуза и Common App;
* каждый факт хранит ссылку, дату и фрагмент-источник;
* ничего не пишется в справочник: расхождение уходит предложением
  директору по поступлению, применяет человек (инвариант №3).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from suggestions import websearch
from suggestions.llm import LLMUnavailable, complete, is_available

log = logging.getLogger("llm")

#: Поля требований, которые умеем сверять: имя в схеме → имя в модели.
FIELDS = ("min_gpa", "min_ielts", "min_toefl", "min_sat", "min_act")

SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean", "description": "Нашлась ли страница с требованиями"},
        "source_url": {"type": "string", "description": "Страница официального сайта с требованиями"},
        "quote": {"type": "string", "description": "Дословный фрагмент страницы с числами"},
        "checked_at": {"type": "string", "description": "Дата обращения, ГГГГ-ММ-ДД"},
        "min_gpa": {"type": "string"},
        "min_ielts": {"type": "string"},
        "min_toefl": {"type": "string"},
        "min_sat": {"type": "string"},
        "min_act": {"type": "string"},
        "note": {"type": "string", "description": "Одна фраза: что именно написано на странице"},
    },
    "required": ["found"],
}

RULES = """Ты сверяешь требования к поступлению с официальным сайтом вуза.

Правила:
- пользуйся поиском: числа бери только со страниц, которые открыл;
- обязательно верни `source_url` (страницу с требованиями), `quote`
  (дословный фрагмент с числами) и `checked_at` (сегодняшняя дата);
- если на странице требования не названы — верни `found: false`
  и пустые поля. Пустое поле лучше выдуманного числа: по этому числу
  ученик будет решать, подавать документы или нет;
- ничего не пересчитывай и не переводи из шкалы в шкалу."""


class CannotVerify(Exception):
    """Сверить нечем. Текст пригоден для показа человеку."""


def _number(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def verify(*, program_id: int, actor, role: str) -> dict:
    """Сверить требования одной программы. Ничего не меняет сам."""
    from suggestions.engine import create_suggestion
    from universities.models import AdmissionRequirement, Program

    program = Program.objects.select_related("university").filter(pk=program_id).first()
    if program is None:
        raise CannotVerify("Такой программы нет в справочнике")

    university = program.university
    # без домена сверять не с чем: Common App в белом списке есть всегда,
    # но требований конкретной программы там не написано
    if not (university.domain or university.website):
        raise CannotVerify(
            f"Сверять нечем: у вуза «{university.name}» не указан домен официального сайта. "
            f"Впишите его в карточку вуза — по форумам и агрегаторам мы не ходим"
        )

    domains = websearch.domains_for_university(university)
    search = websearch.tool(domains)
    if search is None:
        raise CannotVerify(
            "Поиск по официальным сайтам выключен в настройках контура — сверять нечем. "
            "Включите LLM_SEARCH или проверьте требования вручную по сайту вуза"
        )
    if not is_available():
        raise CannotVerify(
            "Для сверки нужна подключённая модель. Сейчас она недоступна — "
            "проверьте требования вручную по сайту вуза или обратитесь к администратору"
        )

    try:
        response = complete(
            system=RULES,
            user=(
                f"Вуз: {university.name}\n"
                f"Сайт: {university.website or university.domain}\n"
                f"Программа: {program.name} ({program.get_level_display()})\n\n"
                f"Найди требования к поступлению: GPA, IELTS, TOEFL, SAT, ACT."
            ),
            purpose="verify_requirements",
            actor=actor,
            role=role,
            schema=SCHEMA,
            max_tokens=1200,
            search=search,
        )
    except LLMUnavailable as error:
        raise CannotVerify(f"Модель не ответила: {error}") from error

    payload = response.parsed or {}
    if not payload.get("found"):
        return {
            "ok": True,
            "found": False,
            "searches": response.searches,
            "detail": (
                f"На официальном сайте требования к «{program.name}» не названы. "
                f"Ничего не меняем: пустой порог значит «требования нет», а не ноль"
            ),
        }

    source = websearch.sources_from_payload([payload])
    kept, dropped = websearch.keep_allowed(source)
    if not kept:
        return {
            "ok": False,
            "found": False,
            "searches": response.searches,
            "detail": (
                "Числа пришли без ссылки на официальный сайт"
                + (f" (отброшено: {', '.join(dropped[:3])})" if dropped else "")
                + ". Без источника мы такие данные не принимаем"
            ),
        }

    fact = kept[0]
    requirement = AdmissionRequirement.objects.filter(program=program).first()
    rows, unchanged = [], []
    for field in FIELDS:
        value = _number(payload.get(field))
        if value is None:
            continue
        current = _number(getattr(requirement, field, None)) if requirement is not None else None
        if current is not None and current == value:
            unchanged.append(field)
            continue
        row = {
            "model": "universities.AdmissionRequirement",
            "field": field,
            "value": str(value),
            "confidence": 0.8,
            "source_ref": fact.as_reference()[:250],
            "source_quote": fact.quote[:400],
        }
        if requirement is not None:
            row["object_id"] = requirement.pk
        else:
            row["new_object_key"] = f"req-{program.pk}"
        rows.append(row)

    if requirement is None and rows:
        rows.insert(
            0,
            {
                "model": "universities.AdmissionRequirement",
                "field": "program",
                "value": program.pk,
                "new_object_key": f"req-{program.pk}",
                "confidence": 1,
                "source_ref": fact.as_reference()[:250],
            },
        )

    if not rows:
        return {
            "ok": True,
            "found": True,
            "changed": 0,
            "searches": response.searches,
            "source": fact.as_dict(),
            "detail": f"Требования совпадают с сайтом. Сверено {fact.checked_at or timezone.localdate().isoformat()}",
        }

    suggestion, rejected = create_suggestion(
        author=actor,
        role=role,
        domain_code="admission",
        source_type="web_sync",
        command="verify_requirements",
        rows=rows,
        source_ref=fact.as_reference()[:250],
    )
    return {
        "ok": True,
        "found": True,
        "changed": len(rows) - len(rejected),
        "unchanged": unchanged,
        "searches": response.searches,
        "source": fact.as_dict(),
        "suggestion": suggestion.pk,
        "detail": (
            f"Расхождение с сайтом: {len(rows) - len(rejected)} значений. "
            f"Ссылка и фрагмент приложены к каждой строке — примените, если согласны"
        ),
    }
