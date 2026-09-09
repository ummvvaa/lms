"""Валидатор предложений.

Строки с полями чужого домена отбрасываются **в коде**, а не в промпте:
модель может ошибиться, промпт можно обойти, а этот фильтр — нет
(инварианты №1 и №3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.domains import (
    DOMAINS,
    can_student_propose,
    can_write_for,
    can_write_shared,
    domain_of_field,
    domain_of_role,
    student_proposable_models,
)
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


def validate_changes(rows: list[dict[str, Any]], *, role: str, domain_code: str = "") -> ValidationOutcome:
    """Отсеять строки, которые роль не вправе предлагать.

    `domain_code` — за какой домен идёт предложение. Директору он не нужен:
    его домен известен по роли. Администратору — обязателен: он вставляет
    текст за выбранный домен, и строки за его пределами отбрасываются
    так же, как чужие у директора (фаза 35, `can_write_for`).
    """
    outcome = ValidationOutcome()
    own = domain_of_role(role)
    acting = own.code if own is not None else (domain_code if domain_code in DOMAINS else "")

    for row in rows:
        model_label = str(row.get("model") or "")
        field_name = str(row.get("field") or "")

        if not acting:
            outcome.rejected.append({**row, "reason": "У роли нет домена"})
            continue
        if model_label not in ALLOWED_MODELS:
            outcome.rejected.append({**row, "reason": f"«{model_title(model_label)}» нельзя менять предложением"})
            continue
        if can_write_shared(role, model_label):
            outcome.accepted.append(row)
            continue
        if not can_write_for(role, acting, model_label, field_name):
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


def validate_student_rows(rows: list[dict[str, Any]], *, student) -> ValidationOutcome:
    """Отсеять строки, которые ученик не вправе предлагать (фаза 37).

    Три правила, и все — в коде, а не в интерфейсе:

    * только про себя: строка про другого ученика отбрасывается;
    * только поля с флагом в реестре: баллы, активности, соревнования,
      цели по стране и специальности. Оценочные ярлыки, статусы,
      посещаемость и дисциплину ученик не предлагает вовсе;
    * запись, которую строка правит, обязана принадлежать самому ученику.
    """
    from django.apps import apps

    outcome = ValidationOutcome()
    allowed = student_proposable_models()
    exams = _proposed_exams(rows)

    for row in rows:
        model_label = str(row.get("model") or "")
        field_name = str(row.get("field") or "")

        target_student = row.get("student")
        if target_student not in (None, "", student.pk):
            outcome.rejected.append({**row, "reason": "Предложить изменение можно только про себя"})
            continue
        if model_label not in allowed:
            outcome.rejected.append(
                {**row, "reason": f"«{model_title(model_label)}» ученик не предлагает — эти данные ведёт школа"}
            )
            continue
        if not can_student_propose(model_label, field_name):
            owner = domain_of_field(model_label, field_name)
            reason = (
                f"«{field_title(model_label, field_name)}» ведёт школа — предложить это поле нельзя"
                if owner
                else "Такого поля нет в реестре доменов"
            )
            outcome.rejected.append({**row, "reason": reason})
            continue
        if row.get("object_id"):
            instance = apps.get_model(model_label).objects.filter(pk=row["object_id"]).first()
            if instance is None or getattr(instance, "student_id", None) != student.pk:
                outcome.rejected.append({**row, "reason": "Эта запись не про вас — предложить её изменение нельзя"})
                continue
            # пробник ученик не правит (фаза 63): его проводил учитель, и балл
            # пришёл файлом. Если результат неверный, это к куратору — иначе
            # смысл пробника пропадает вместе с возможностью его переписать
            if getattr(instance, "attempt_format", "") == "mock":
                outcome.rejected.append(
                    {**row, "reason": "Это результат пробника школы — если он неверный, скажите куратору"}
                )
                continue
        reason = _section_refusal(model_label, field_name, row, exams=exams)
        if reason:
            outcome.rejected.append({**row, "reason": reason})
            continue
        outcome.accepted.append({**row, "student": student.pk})

    return outcome


def _proposed_exams(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Какой экзамен ученик называет для каждой новой попытки в этом пакете."""
    return {
        str(row.get("new_object_key") or row.get("object_id") or ""): str(row.get("value") or "")
        for row in rows
        if (str(row.get("model") or ""), row.get("field"))
        in (("students.ExamAttempt", "exam_type"), ("students.ExamGoal", "exam"))
    }


def _section_refusal(model_label: str, field_name: str, row: dict[str, Any], *, exams: dict[str, str]) -> str:
    """Балл ученика — по шкале экзамена из реестра (D4, D17).

    Отказ здесь, при подаче: ученик видит причину сразу, а не после
    решения директора. Экзамен новой попытки берётся из соседней строки
    пакета, существующей — из записи, у профиля — из имени поля.
    """
    from django.apps import apps

    from core.domains import SECTION_FIELDS, scale_of

    if model_label not in ("students.ExamAttempt", "students.ExamProfile", "students.ExamGoal"):
        return ""
    value = row.get("value")
    if value in (None, ""):
        return ""
    exam = ""
    if model_label == "students.ExamAttempt":
        key = str(row.get("new_object_key") or row.get("object_id") or "")
        exam = exams.get(key, "")
        if not exam and row.get("object_id"):
            instance = apps.get_model(model_label).objects.filter(pk=row["object_id"]).first()
            exam = getattr(instance, "exam_type", "")
        if field_name not in {"total_score", *SECTION_FIELDS}:
            return ""
    elif model_label == "students.ExamProfile":
        exam = "IELTS" if field_name.startswith("ielts_") else "SAT" if field_name.startswith("sat_") else ""
    else:
        if field_name != "target_score":
            return ""
        key = str(row.get("new_object_key") or row.get("object_id") or "")
        exam = exams.get(key, "")
        if not exam and row.get("object_id"):
            instance = apps.get_model(model_label).objects.filter(pk=row["object_id"]).select_related("exam").first()
            exam = getattr(getattr(instance, "exam", None), "name", "")
    scale = scale_of(exam, section=field_name in SECTION_FIELDS)
    if scale is None:
        return ""
    return "" if scale.holds(value) else f"Шкала {exam} — {scale.hint}"
