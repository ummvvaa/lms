"""Массовый ввод результатов экзаменов.

После общешкольного пробного результаты вносят десятками. По одной
карточке это неделя работы, и работа, которую никто не сделает: числа
так и останутся в чужой таблице.

Правила те же, что у импорта (фаза 15): значение проверяется до
сохранения, кривая строка называется по номеру и не отменяет остальные,
всё применённое пишется в журнал с источником `manual` — вносил-то
человек руками, просто много строк сразу.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from core.audit import ValueRejected, apply_changes, coerce
from core.domains import Source
from students.models import AttemptFormat, ExamAttempt, ExamType, Student

#: Колонки, которые вносит человек. `student` и формат — обязательные.
VALUE_FIELDS = ("total_score", "listening", "reading", "writing", "speaking", "math", "verbal")


@transaction.atomic
def save_rows(*, rows: list[dict[str, Any]], actor=None) -> dict[str, Any]:
    """Сохранить результаты пачкой. Возвращает, что легло и что нет."""
    known = {student.pk: student for student in Student.objects.filter(pk__in=[row.get("student") for row in rows])}

    created = 0
    rejected: list[dict[str, Any]] = []

    for number, row in enumerate(rows, start=1):
        student = known.get(row.get("student"))
        if student is None:
            rejected.append({"row": number, "reason": "в строке не указан ученик или его нет в списке"})
            continue

        exam_type = str(row.get("exam_type") or "").strip()
        if exam_type not in ExamType.values:
            rejected.append({"row": number, "student": student.full_name, "reason": "не выбран вид экзамена"})
            continue

        attempt_format = str(row.get("attempt_format") or AttemptFormat.MOCK).strip()
        if attempt_format not in AttemptFormat.values:
            rejected.append({"row": number, "student": student.full_name, "reason": "не выбран формат сдачи"})
            continue

        date = str(row.get("date") or "").strip()
        if not date:
            rejected.append({"row": number, "student": student.full_name, "reason": "не указана дата сдачи"})
            continue

        attempt = ExamAttempt(student=student, exam_type=exam_type, attempt_format=attempt_format, source=Source.MANUAL)
        values: dict[str, Any] = {"date": date}
        problem = ""
        for name in VALUE_FIELDS:
            raw = row.get(name)
            if raw in (None, ""):
                continue
            try:
                values[name] = coerce(attempt, name, raw)
            except ValueRejected as error:
                problem = str(error)
                break
        if problem:
            rejected.append({"row": number, "student": student.full_name, "reason": problem})
            continue

        if not any(name in values for name in VALUE_FIELDS):
            rejected.append(
                {"row": number, "student": student.full_name, "reason": "не заполнен ни один балл — вносить нечего"}
            )
            continue

        # через `apply_changes`: результат экзамена — доменное поле,
        # и в журнале он обязан появиться с источником (инвариант №9)
        apply_changes(attempt, values, actor=actor, source=Source.MANUAL)
        created += 1

    detail = f"Внесено результатов: {created}"
    if rejected:
        detail += f", строк с ошибкой: {len(rejected)}"
    return {"created": created, "rejected": rejected, "detail": detail}
