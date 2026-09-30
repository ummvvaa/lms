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
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.domains import SCHOOL_SETTINGS, Source

#: модель в журнале: по ней история правил отличается от правок учеников
AUDIT_LABEL = "core.SchoolRule"

#: раздел экрана настроек, куда правило попадает, если не сказано иное
STUDY = gettext_lazy("Учёба")


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
    group: str = STUDY
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
#: Сдача ДЗ: предел одного файла, видео и число файлов в сдаче
HOMEWORK_FILE_MB = "homework_file_mb"
HOMEWORK_VIDEO_MB = "homework_video_mb"
HOMEWORK_MAX_FILES = "homework_max_files"
#: Оценки за ДЗ входят в четвертную и с каким весом к оценке ФО
HOMEWORK_IN_QUARTER = "homework_in_quarter"
HOMEWORK_WEIGHT = "homework_weight"
#: «Не сдаёт ДЗ вовремя»: выполнение ниже порога или столько несданных
HOMEWORK_BEHIND_PCT = "homework_behind_pct"
HOMEWORK_BEHIND_MISSED = "homework_behind_missed"

RULES: tuple[Rule, ...] = (
    Rule(
        ATTENDANCE_BELOW,
        gettext_lazy("Порог посещаемости"),
        gettext_lazy(
            "Ниже — ученик в «Рисках», процент выделен на экранах посещаемости, "
            "успеваемости группы, в карточке и в ответах помощника"
        ),
        "%",
        85,
        0,
        100,
    ),
    Rule(
        QUARTER_GRADE_BELOW,
        gettext_lazy("Порог четвертной оценки"),
        gettext_lazy("Расчётная четвертная ниже — помощник учителя называет ученика отстающим по предмету"),
        gettext_lazy("балл"),
        4,
        2,
        5,
    ),
    Rule(
        FO_ONLY_BELOW,
        gettext_lazy("Порог для предметов «Только ФО»"),
        gettext_lazy("Средний ФО ниже этой доли от максимума — отстаёт по предмету без четвертной"),
        "%",
        60,
        0,
        100,
    ),
    Rule(
        NO_GRADES_DAYS,
        gettext_lazy("Окно «нет оценок»"),
        gettext_lazy("За сколько последних дней помощник учителя ищет учеников, которые были на уроках, но без оценок"),
        gettext_lazy("дней"),
        14,
        1,
        90,
    ),
    Rule(
        EXCUSED_LOWERS_ATTENDANCE,
        gettext_lazy("Пропуск по уважительной причине снижает процент посещаемости"),
        gettext_lazy(
            "«Да» — урок по уважительной причине идёт в процент как пропуск; «нет» — такой урок "
            "в процент не входит вовсе"
        ),
        "",
        1,
        0,
        1,
        kind="bool",
    ),
    Rule(
        LESSON_MINUTES_DEFAULT,
        gettext_lazy("Длина урока по умолчанию"),
        gettext_lazy(
            "Для урока, у номера которого нет звонка в сетке группы: столько минут он весит в проценте посещаемости"
        ),
        gettext_lazy("мин"),
        40,
        10,
        180,
    ),
    Rule(
        HOMEWORK_FILE_MB,
        gettext_lazy("Предел файла в сдаче ДЗ"),
        gettext_lazy("Один файл ученика или учителя — не больше; для видео свой предел ниже"),
        gettext_lazy("МБ"),
        50,
        1,
        500,
        group=gettext_lazy("Домашние задания"),
    ),
    Rule(
        HOMEWORK_VIDEO_MB,
        gettext_lazy("Предел видео в сдаче ДЗ"),
        gettext_lazy("Видео с телефона весит много — для него предел отдельный"),
        gettext_lazy("МБ"),
        500,
        10,
        2000,
        group=gettext_lazy("Домашние задания"),
    ),
    Rule(
        HOMEWORK_MAX_FILES,
        gettext_lazy("Файлов в одной сдаче ДЗ"),
        gettext_lazy("Сколько файлов ученик прикладывает к одной работе (фото, склеенные в PDF, — один файл)"),
        gettext_lazy("шт."),
        10,
        1,
        50,
        group=gettext_lazy("Домашние задания"),
    ),
    Rule(
        HOMEWORK_IN_QUARTER,
        gettext_lazy("Оценки за ДЗ входят в четвертную"),
        gettext_lazy(
            "«Нет» — оценка за ДЗ стоит в журнале отдельной колонкой «ДЗ» и в четвертную не идёт; "
            "«да» — идёт в среднюю ФО с весом ниже"
        ),
        "",
        0,
        0,
        1,
        group=gettext_lazy("Домашние задания"),
        kind="bool",
    ),
    Rule(
        HOMEWORK_WEIGHT,
        gettext_lazy("Вес оценки за ДЗ в четвертной"),
        gettext_lazy(
            "Доля одной оценки ФО: 100 — как обычная оценка ФО, 50 — вдвое легче. Действует, "
            "только когда оценки за ДЗ входят в четвертную"
        ),
        "%",
        100,
        10,
        100,
        group=gettext_lazy("Домашние задания"),
    ),
    Rule(
        HOMEWORK_BEHIND_PCT,
        gettext_lazy("Порог «не сдаёт ДЗ вовремя»"),
        gettext_lazy("Выполнение ДЗ за четверть ниже — ученик в списке куратора «Не сдают ДЗ вовремя»"),
        "%",
        60,
        0,
        100,
        group=gettext_lazy("Домашние задания"),
    ),
    Rule(
        HOMEWORK_BEHIND_MISSED,
        gettext_lazy("Несданных ДЗ до списка «не сдаёт»"),
        gettext_lazy("Столько несданных заданий за четверть — ученик в списке куратора, даже если процент выше порога"),
        gettext_lazy("шт."),
        2,
        1,
        50,
        group=gettext_lazy("Домашние задания"),
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
YES = {"да", "true", "1", "yes"}  # i18n-skip: разбор ввода
NO = {"нет", "false", "0", "no"}  # i18n-skip: разбор ввода


def check(rule: Rule, raw) -> int:
    """Проверить значение: целое число в границах правила; у «да/нет» — 1 или 0."""
    if rule.kind == "bool":
        word = str(raw).strip().lower()
        if raw is True or word in YES:
            return 1
        if raw is False or word in NO:
            return 0
        raise RuleRejected(_("«{rule}»: нужно «да» или «нет»").format(rule=rule.title))
    text = str(raw).strip() if isinstance(raw, int | str) and not isinstance(raw, bool) else ""
    if not re.fullmatch(r"-?\d{1,9}", text):
        raise RuleRejected(_("«{rule}»: нужно целое число").format(rule=rule.title))
    number = int(text)
    if not rule.minimum <= number <= rule.maximum:
        raise RuleRejected(
            _("«{rule}»: значение от {minimum} до {maximum}").format(
                rule=rule.title, minimum=rule.minimum, maximum=rule.maximum
            )
        )
    return number


def words(rule: Rule, number: int) -> str:
    """Значение для журнала и экрана: у «да/нет» — словом.

    Слово пишется в журнал и читается оттуда как данные — не переводится.
    """
    if rule.kind == "bool":
        return "да" if number else "нет"  # i18n-skip: значение записи журнала в базе
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
        raise RuleRejected(_("Такого правила нет"))
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
        raise RuleRejected(_("Такого правила нет"))
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
