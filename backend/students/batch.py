"""Батч-сохранение изменений из табличного режима.

Принимает список изменений, валидирует домен по реестру, применяет одной
транзакцией и пишет аудит. Директор правит 20 учеников и уходит одним
запросом — а не двадцатью.

Чужие поля отбрасываются на сервере (инвариант №1), каждое применённое
изменение попадает в `AuditLog` (инвариант №9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.apps import apps
from django.db import transaction

from core.audit import ValueRejected, apply_changes, coerce, to_text
from core.domains import Source, can_write

#: Модели, которые батч умеет править — только профили пяти доменов.
ALLOWED_MODELS = {
    "students.BehaviorProfile",
    "students.AdmissionProfile",
    "students.ExamProfile",
    "students.TalentProfile",
    "students.SportProfile",
}


@dataclass
class BatchResult:
    """Что применилось, что отвергнуто и почему."""

    applied: int = 0
    skipped: int = 0
    audit_entries: int = 0
    rejected: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "applied": self.applied,
            "skipped": self.skipped,
            "audit_entries": self.audit_entries,
            "rejected": self.rejected,
            "conflicts": self.conflicts,
        }


def _profile_for(model_label: str, student_id: int):
    model = apps.get_model(model_label)
    return model.objects.filter(student_id=student_id).select_related("student").first()


@transaction.atomic
def apply_batch(*, changes: list[dict[str, Any]], role: str, actor=None) -> BatchResult:
    """Применить пакет изменений.

    Каждый элемент: `{student, model, field, value}`, необязательно
    `expected` — прежнее значение. Если `expected` пришло и разошлось
    с тем, что в базе, строка помечается конфликтом и пропускается:
    значит, кто-то успел поправить это поле раньше.
    """
    result = BatchResult()

    # группируем по (модель, ученик), чтобы сохранить объект один раз
    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    expectations: dict[tuple[str, int], dict[str, str]] = {}

    for row in changes:
        model_label = str(row.get("model", ""))
        field_name = str(row.get("field", ""))
        student_id = row.get("student")

        if model_label not in ALLOWED_MODELS:
            result.rejected.append({**row, "reason": "Эта модель не правится через таблицу"})
            continue
        if not can_write(role, model_label, field_name):
            # чужой домен — отбрасываем на сервере, не в интерфейсе
            result.rejected.append({**row, "reason": "Поле чужого домена"})
            continue
        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            result.rejected.append({**row, "reason": "Не указан ученик"})
            continue

        key = (model_label, student_id)
        grouped.setdefault(key, {})[field_name] = row.get("value")
        if "expected" in row:
            expectations.setdefault(key, {})[field_name] = to_text(row.get("expected"))

    for (model_label, student_id), values in grouped.items():
        instance = _profile_for(model_label, student_id)
        if instance is None:
            result.rejected.append(
                {"student": student_id, "model": model_label, "reason": "Нет профиля у этого ученика"}
            )
            continue

        expected = expectations.get((model_label, student_id), {})
        to_apply: dict[str, Any] = {}
        for field_name, value in values.items():
            if field_name in expected:
                current = to_text(getattr(instance, field_name, None))
                if current != expected[field_name]:
                    result.conflicts.append(
                        {
                            "student": student_id,
                            "model": model_label,
                            "field": field_name,
                            "expected": expected[field_name],
                            "actual": current,
                        }
                    )
                    result.skipped += 1
                    continue
            try:
                to_apply[field_name] = coerce(instance, field_name, value)
            except ValueRejected as error:
                # буквы в числовой ячейке — повод отклонить строку, а не упасть
                result.rejected.append(
                    {
                        "student": student_id,
                        "model": model_label,
                        "field": field_name,
                        "value": value,
                        "reason": str(error),
                    }
                )
                result.skipped += 1

        if not to_apply:
            continue
        entries = apply_changes(instance, to_apply, actor=actor, source=Source.MANUAL)
        result.audit_entries += len(entries)
        result.applied += len(to_apply)

    return result
