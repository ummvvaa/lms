"""Уровень английского ученика (A1–C2): кто вносит, история строками.

Вносят учитель GE/EEP своего состава, Кымбат, куратор группы и администратор
(решение владельца, 30.09.2026). Из балла IELTS уровень не выводится.
Ученику уровень не показывается: это оценка учителя для отчёта родителям.
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction

from academics.calendar import today
from academics.models import CefrLevel, Course, EnglishLevel, ReportRole
from core.domains import ROLE_ADMIN, ROLE_CURATOR, ROLE_STUDENT

EXAM_DIRECTOR = "director_exam"


class LevelRefused(ValueError):
    """Внести так нельзя — текст объясняет почему."""


def teaches_english(user, student_id: int) -> bool:
    """Учитель ведёт журнал GE/EEP, где ученик состоит сегодня."""
    from academics.cohorts import cohorts_of_student

    cohorts = cohorts_of_student(student_id, today())
    return Course.objects.filter(teacher=user, report_role=ReportRole.EEP, cohort_id__in=cohorts).exists()


def may_set(user, student) -> bool:
    """Кто вносит уровень. Границу «свои ученики» держит `core.scope` у вызывающего."""
    role = getattr(user, "role", "")
    if role in (ROLE_ADMIN, EXAM_DIRECTOR):
        return True
    if role == ROLE_CURATOR:
        from accounts.curators import curated_group_ids

        return bool(student.group_id) and student.group_id in curated_group_ids(user)
    if role == ROLE_STUDENT or not getattr(user, "pk", None):
        return False
    # учитель — и директор, который сам ведёт английский, как «Мои уроки»
    return teaches_english(user, student.pk)


def payload(student, user) -> dict:
    from academics.payloads import user_name

    rows = list(EnglishLevel.objects.filter(student=student).select_related("set_by").order_by("-since", "-id")[:10])
    current = rows[0] if rows else None
    return {
        "level": current.level if current else "",
        "since": current.since if current else None,
        "history": [
            {"level": row.level, "since": row.since, "by": user_name(row.set_by) if row.set_by_id else ""}
            for row in rows
        ],
        "levels": list(CefrLevel.values),
        "may_edit": may_set(user, student),
    }


@transaction.atomic
def set_level(student, *, level: str, since: dt.date | None, actor) -> EnglishLevel:
    """Новый уровень с даты; тот же день — правка строки, а не вторая строка."""
    from core.audit import record_event

    if level not in CefrLevel.values:
        raise LevelRefused("Уровень — от A1 до C2")
    day = since or today()
    if day > today():
        raise LevelRefused("Дата уровня — не позже сегодняшней")
    row, created = EnglishLevel.objects.update_or_create(
        student=student, since=day, defaults={"level": level, "set_by": actor if getattr(actor, "pk", None) else None}
    )
    record_event(student=student, code="english_level", text=f"{level} с {day:%d.%m.%Y}", actor=actor)
    return row
