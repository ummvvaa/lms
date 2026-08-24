"""Валидатор предложений.

Строки с полями чужого домена отбрасываются **в коде**, а не в промпте:
модель может ошибиться, промпт можно обойти, а этот фильтр — нет
(инварианты №1 и №3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.domains import can_write, can_write_shared, domain_of_field, domain_of_role
from core.labels import field_title, model_title

#: Модели, в которые предложение вообще может писать.
ALLOWED_MODELS = {
    "students.BehaviorProfile",
    "students.AdmissionProfile",
    "students.ExamProfile",
    "students.TalentProfile",
    "students.SportProfile",
    "students.ExamAttempt",
    "students.Activity",
    "students.Competition",
    "universities.University",
    "universities.Program",
    "universities.AdmissionRound",
    "universities.AdmissionRequirement",
    "universities.StudentUniversity",
    # сквозные модели: владельца-домена нет, но предлагать их вправе
    # любой директор — иначе массовую постановку задач нельзя было бы
    # провести через предложение (инвариант №3)
    "roadmap.Task",
}


@dataclass
class ValidationOutcome:
    """Что прошло, что отброшено и почему."""

    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"accepted": self.accepted, "rejected": self.rejected}


def validate_changes(rows: list[dict[str, Any]], *, role: str) -> ValidationOutcome:
    """Отсеять строки, которые роль не вправе предлагать."""
    outcome = ValidationOutcome()
    own = domain_of_role(role)

    for row in rows:
        model_label = str(row.get("model") or "")
        field_name = str(row.get("field") or "")

        if own is None:
            outcome.rejected.append({**row, "reason": "У роли нет домена"})
            continue
        if model_label not in ALLOWED_MODELS:
            outcome.rejected.append({**row, "reason": f"«{model_title(model_label)}» нельзя менять предложением"})
            continue
        if can_write_shared(role, model_label):
            outcome.accepted.append(row)
            continue
        if not can_write(role, model_label, field_name):
            owner = domain_of_field(model_label, field_name)
            reason = (
                f"«{field_title(model_label, field_name)}» ведёт домен «{owner.title}» ({owner.owner_name})"
                if owner
                else "Такого поля нет в реестре доменов"
            )
            outcome.rejected.append({**row, "reason": reason})
            continue
        outcome.accepted.append(row)

    return outcome
