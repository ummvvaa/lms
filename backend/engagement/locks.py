"""Замки вместо пустоты: что откроется после шага (фаза 47).

Раньше недоступное у ученика либо пряталось, либо отвечало пустым экраном:
«Подбор вузов» без единого балла показывал форму, которая ничего не найдёт,
а «План поступления» — пустой список без объяснения, чего не хватает.

Теперь такой раздел показывается с замком и одной фразой: что сделать,
чтобы он открылся. Ученик видит, что его ждёт, и знает следующий шаг.

**К чужим доменам это не относится.** Раздел другой роли по-прежнему
отбивается без объяснений (`DOMAIN_ONLY`, `STAFF_ONLY`): там дело не в шагах,
а в приватности данных других детей, и инвариант №7 не смягчается.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext

from students.models import Student


@dataclass(frozen=True)
class Lock:
    """Один закрытый раздел: адрес, причина и куда идти за ключом."""

    path: str
    reason: str
    action: str
    to: str


def locks_for(student: Student) -> list[dict]:
    """Разделы ученика, закрытые до его же шага.

    Возвращаются все — и открытые тоже: интерфейс должен показать замок,
    а не спрятать пункт, и по этому же ответу снять его, когда шаг сделан.
    """
    from universities.models import MatchRun, StudentUniversity

    has_universities = StudentUniversity.objects.filter(student=student).exists()
    has_run = MatchRun.objects.filter(student=student).exists()

    # «Подбор вузов» открыт без условий (решение владельца, 07.10.2026): без баллов
    # и целей экран сам говорит, что считать не из чего
    rows = [
        {
            "path": "/plan",
            "locked": not (has_universities or has_run),
            "reason": gettext("Откроется, когда выберете вузы"),
            "hint": gettext("План собирается под конкретную программу: её дедлайн и её требования"),
            "action": gettext("Открыть подбор"),
            "to": "/selection",
        },
    ]
    return rows


def state_for(student: Student) -> dict:
    """Ответ для интерфейса: только замки, без чужих данных."""
    return {"locks": locks_for(student)}
