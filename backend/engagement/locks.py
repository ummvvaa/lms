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

    exam = getattr(student, "exam", None)
    has_numbers = any(
        getattr(exam, name, None) not in (None, "")
        for name in ("gpa", "ielts_current", "sat_current", "ielts_target", "sat_target")
    )
    has_goals = student.exam_goals.exists() if hasattr(student, "exam_goals") else False
    has_universities = StudentUniversity.objects.filter(student=student).exists()
    has_run = MatchRun.objects.filter(student=student).exists()

    rows = [
        {
            "path": "/selection",
            "locked": not (has_numbers or has_goals),
            "reason": "Откроется, когда внесёте баллы или цели по экзаменам",
            "hint": "Подбор считает соответствие требованиям по вашим числам: без них считать нечего",
            "action": "Заполнить портфолио",
            "to": "/my-data",
        },
        {
            "path": "/plan",
            "locked": not (has_universities or has_run),
            "reason": "Откроется, когда выберете вузы",
            "hint": "План собирается под конкретную программу: её дедлайн и её требования",
            "action": "Открыть подбор",
            "to": "/selection",
        },
    ]
    return rows


def state_for(student: Student) -> dict:
    """Ответ для интерфейса: только замки, без чужих данных."""
    return {"locks": locks_for(student)}
