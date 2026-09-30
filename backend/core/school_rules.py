"""Настраиваемые правила школы: пороги, окна, сроки, лимиты.

Всё, что школа решает сама — с какой посещаемости ученик в риске, какая
четвертная значит «отстаёт», за сколько дней искать «нет оценок», — это
настройка администратора, а не константа в коде и не переменная окружения
(решение владельца, 30.09.2026). Реестр ниже — единственное место, где
правило описано: подпись, единица, значение по умолчанию и границы.
Значение, которое поменял администратор, лежит строкой `core.SchoolRule`;
строки нет — действует значение по умолчанию.

Значение читается из базы на каждый вызов: поменял — действует со
следующего запроса, без перезапуска и без кэша, который надо сбрасывать.
Каждая правка и сброс пишутся в журнал: кто, когда, было → стало.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import transaction

from core.domains import SCHOOL_SETTINGS, Source

#: модель в журнале: по ней история правил отличается от правок учеников
AUDIT_LABEL = "core.SchoolRule"


@dataclass(frozen=True)
class Rule:
    """Одно правило: что значит, в чём меряется, какое по умолчанию, в каких границах."""

    code: str
    title: str
    hint: str
    unit: str
    default: int
    minimum: int
    maximum: int
    group: str = "Учёба"
    #: `int` — число в границах; `bool` — «да» или «нет», хранится 1 и 0
    kind: str = "int"


#: Посещаемость ниже порога — ученик в «Рисках», процент красным на экранах
ATTENDANCE_BELOW = "attendance_below"
#: Расчётная четвертная ниже — ученик отстаёт по предмету
QUARTER_GRADE_BELOW = "quarter_grade_below"
#: Средний ФО ниже этой доли от максимума — отстаёт по предмету «Только ФО»
FO_ONLY_BELOW = "fo_only_below"
#: За сколько дней искать учеников без оценок
NO_GRADES_DAYS = "no_grades_days"
#: Урок по уважительной причине снижает процент (0 минут, урок в знаменателе)
EXCUSED_LOWERS_ATTENDANCE = "excused_lowers_attendance"
#: Длина урока, у номера которого нет звонка в сетке группы
LESSON_MINUTES_DEFAULT = "lesson_minutes_default"

RULES: tuple[Rule, ...] = (
    Rule(
        ATTENDANCE_BELOW,
        "Порог посещаемости",
        "Ниже — ученик в «Рисках», процент выделен на экранах посещаемости, "
        "успеваемости группы, в карточке и в ответах помощника",
        "%",
        85,
        0,
        100,
    ),
    Rule(
        QUARTER_GRADE_BELOW,
        "Порог четвертной оценки",
        "Расчётная четвертная ниже — помощник учителя называет ученика отстающим по предмету",
        "балл",
        4,
        2,
        5,
    ),
    Rule(
        FO_ONLY_BELOW,
        "Порог для предметов «Только ФО»",
        "Средний ФО ниже этой доли от максимума — отстаёт по предмету без четвертной",
        "%",
        60,
        0,
        100,
    ),
    Rule(
        NO_GRADES_DAYS,
        "Окно «нет оценок»",
        "За сколько последних дней помощник учителя ищет учеников, которые были на уроках, но без оценок",
        "дней",
        14,
        1,
        90,
    ),
    Rule(
        EXCUSED_LOWERS_ATTENDANCE,
        "Пропуск по уважительной причине снижает процент посещаемости",
        "«Да» — урок по уважительной причине идёт в процент как пропуск; «нет» — такой урок "
        "в процент не входит вовсе",
        "",
        1,
        0,
        1,
        kind="bool",
    ),
    Rule(
        LESSON_MINUTES_DEFAULT,
        "Длина урока по умолчанию",
        "Для урока, у номера которого нет звонка в сетке группы: столько минут он весит " "в проценте посещаемости",
        "мин",
        40,
        10,
        180,
    ),
)

BY_CODE: dict[str, Rule] = {rule.code: rule for rule in RULES}


class RuleRejected(ValueError):
    """Значение не подходит правилу. Текст пригоден для показа человеку."""


def rule_of(code: str) -> Rule | None:
    return BY_CODE.get(code)


def value(code: str) -> int:
    """Действующее значение правила: заданное администратором или по умолчанию."""
    from core.models import SchoolRule

    rule = BY_CODE[code]
    stored = SchoolRule.objects.filter(code=code).values_list("value", flat=True).first()
    return rule.default if stored is None else stored


def values() -> dict[str, int]:
    """Все действующие значения одним запросом."""
    from core.models import SchoolRule

    stored = dict(SchoolRule.objects.filter(code__in=BY_CODE).values_list("code", "value"))
    return {rule.code: stored.get(rule.code, rule.default) for rule in RULES}


#: как человек и экран пишут «да» и «нет»
YES = {"да", "true", "1", "yes"}
NO = {"нет", "false", "0", "no"}


def check(rule: Rule, raw) -> int:
    """Проверить значение: целое число в границах правила; у «да/нет» — 1 или 0."""
    if rule.kind == "bool":
        word = str(raw).strip().lower()
        if raw is True or word in YES:
            return 1
        if raw is False or word in NO:
            return 0
        raise RuleRejected(f"«{rule.title}»: нужно «да» или «нет»")
    text = str(raw).strip() if isinstance(raw, int | str) and not isinstance(raw, bool) else ""
    if not re.fullmatch(r"-?\d{1,9}", text):
        raise RuleRejected(f"«{rule.title}»: нужно целое число")
    number = int(text)
    if not rule.minimum <= number <= rule.maximum:
        raise RuleRejected(f"«{rule.title}»: значение от {rule.minimum} до {rule.maximum}")
    return number


def words(rule: Rule, number: int) -> str:
    """Значение для журнала и экрана: у «да/нет» — словом."""
    if rule.kind == "bool":
        return "да" if number else "нет"
    return str(number)


def _log(rule: Rule, old: int, new: int, *, actor) -> None:
    from core.models import AuditLog

    AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_role=getattr(actor, "role", "") or "",
        model_label=AUDIT_LABEL,
        object_id=rule.code,
        field_name=rule.code,
        domain_code=SCHOOL_SETTINGS.code,
        old_value=words(rule, old),
        new_value=words(rule, new),
        source=Source.MANUAL,
    )


@transaction.atomic
def set_value(code: str, raw, *, actor) -> int:
    """Задать значение. То же, что было, — записи в журнале нет."""
    from core.models import SchoolRule

    rule = BY_CODE.get(code)
    if rule is None:
        raise RuleRejected("Такого правила нет")
    number = check(rule, raw)
    old = value(code)
    SchoolRule.objects.update_or_create(code=code, defaults={"value": number, "updated_by": actor})
    if old != number:
        _log(rule, old, number, actor=actor)
    return number


@transaction.atomic
def reset(code: str, *, actor) -> int:
    """Вернуть значение по умолчанию: строка удаляется, правка — в журнал."""
    from core.models import SchoolRule

    rule = BY_CODE.get(code)
    if rule is None:
        raise RuleRejected("Такого правила нет")
    old = value(code)
    SchoolRule.objects.filter(code=code).delete()
    if old != rule.default:
        _log(rule, old, rule.default, actor=actor)
    return rule.default


def history(limit: int = 20) -> list[dict]:
    """Последние правки правил: кто, когда, было → стало."""
    from core.models import AuditLog

    rows = (
        AuditLog.objects.filter(model_label=AUDIT_LABEL).select_related("actor").order_by("-created_at", "-id")[:limit]
    )
    out = []
    for row in rows:
        rule = BY_CODE.get(row.field_name)
        who = (row.actor.full_name or row.actor.email) if row.actor_id else row.actor_title
        out.append(
            {
                "id": row.pk,
                "code": row.field_name,
                "title": rule.title if rule else row.field_name,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "actor": who or "",
                "created_at": row.created_at,
            }
        )
    return out


def payload() -> dict:
    """Экран «Настройки школы»: правила с текущим значением и история правок."""
    from core.models import SchoolRule

    stored = {row.code: row for row in SchoolRule.objects.filter(code__in=BY_CODE).select_related("updated_by")}
    rules = []
    for rule in RULES:
        row = stored.get(rule.code)
        rules.append(
            {
                "code": rule.code,
                "title": rule.title,
                "hint": rule.hint,
                "unit": rule.unit,
                "group": rule.group,
                "kind": rule.kind,
                "value": row.value if row is not None else rule.default,
                "default": rule.default,
                "minimum": rule.minimum,
                "maximum": rule.maximum,
                "is_default": row is None or row.value == rule.default,
            }
        )
    return {"rules": rules, "history": history()}
