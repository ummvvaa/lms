"""Инструменты модели.

Типизированные функции, а не свободный доступ к БД. Каждый вызов
проверяется против роли вызывающего: инструмент, которым роль не владеет,
не выполнится, что бы ни попросила модель (инварианты №1 и №3).

Ни один инструмент не пишет в основные таблицы: `propose_field_change`
складывает строки в предложение, применяет их человек.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.domains import can_write, domain_of_role
from students.models import Student
from suggestions.name_matching import find


class ToolDenied(Exception):
    """Роль не вправе вызывать этот инструмент."""


@dataclass
class ToolContext:
    """Кто вызывает и что уже накопилось."""

    actor: Any
    role: str
    #: строки будущего предложения
    rows: list[dict[str, Any]] = field(default_factory=list)
    #: имена, которые не удалось сопоставить однозначно
    ambiguities: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Tool:
    """Описание инструмента для модели и для проверки прав."""

    name: str
    description: str
    schema: dict
    handler: Callable[..., Any]
    #: роли, которым инструмент доступен; пусто — всем сотрудникам
    roles: tuple[str, ...] = ()


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, schema: dict, roles: tuple[str, ...] = ()):
    def wrap(fn):
        REGISTRY[name] = Tool(name=name, description=description, schema=schema, handler=fn, roles=roles)
        return fn

    return wrap


def call(name: str, context: ToolContext, **kwargs) -> Any:
    """Вызвать инструмент с проверкой прав."""
    spec = REGISTRY.get(name)
    if spec is None:
        raise ToolDenied(f"Инструмента {name} нет")
    if spec.roles and context.role not in spec.roles:
        raise ToolDenied(f"Роль {context.role} не вправе вызывать {name}")
    if domain_of_role(context.role) is None:
        raise ToolDenied("У роли нет домена")
    return spec.handler(context, **kwargs)


def schemas_for(role: str) -> list[dict]:
    """Инструменты, доступные роли — то, что уходит модели."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.schema}
        for t in REGISTRY.values()
        if not t.roles or role in t.roles
    ]


# --- Инструменты --------------------------------------------------------


@tool(
    "find_student",
    "Найти ученика по имени или почте. Возвращает кандидатов с уверенностью.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "ФИО или email"}},
        "required": ["query"],
    },
)
def find_student(context: ToolContext, query: str) -> dict:
    """Сопоставление имени. Неоднозначность не разрешается молча."""
    outcome = find(query)
    if outcome.is_ambiguous or outcome.is_missing:
        context.ambiguities.append(outcome.as_dict())
    return outcome.as_dict()


@tool(
    "propose_field_change",
    "Предложить изменение поля ученика. Ничего не записывает — только готовит строку предложения.",
    {
        "type": "object",
        "properties": {
            "student": {"type": "integer", "description": "id ученика"},
            "model": {"type": "string", "description": "например students.ExamProfile"},
            "field": {"type": "string"},
            "value": {"type": ["string", "number", "boolean", "null"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "source_quote": {"type": "string", "description": "фрагмент источника"},
        },
        "required": ["student", "model", "field", "value"],
    },
)
def propose_field_change(
    context: ToolContext,
    student: int,
    model: str,
    field: str,
    value: Any,
    confidence: float = 0.8,
    source_quote: str = "",
) -> dict:
    """Положить строку в предложение. В основные таблицы не пишет никогда."""
    if not can_write(context.role, model, field):
        # проверка в коде: промпт мог попросить что угодно
        return {"accepted": False, "reason": "Поле чужого домена"}
    context.rows.append(
        {
            "student": student,
            "model": model,
            "field": field,
            "value": value,
            "confidence": max(0.0, min(1.0, float(confidence))),
            "source_quote": source_quote,
        }
    )
    return {"accepted": True}


@tool(
    "get_program_requirements",
    "Получить требования программы из справочника. Если требований нет — так и сказано.",
    {"type": "object", "properties": {"program": {"type": "integer"}}, "required": ["program"]},
)
def get_program_requirements(context: ToolContext, program: int) -> dict:
    """Требования только из `AdmissionRequirement` — ничего не выдумываем."""
    from universities.models import AdmissionRequirement

    requirement = AdmissionRequirement.objects.filter(program_id=program).select_related("program__university").first()
    if requirement is None:
        return {"has_requirements": False, "detail": "Требования этой программы не заведены в справочнике"}
    return {
        "has_requirements": True,
        "university": requirement.program.university.name,
        "program": requirement.program.name,
        "min_gpa": str(requirement.min_gpa) if requirement.min_gpa else None,
        "min_ielts": str(requirement.min_ielts) if requirement.min_ielts else None,
        "min_toefl": requirement.min_toefl,
        "min_sat": requirement.min_sat,
        "min_act": requirement.min_act,
        "required_subjects": requirement.subjects_list,
        "portfolio_required": requirement.portfolio_required,
        "source_url": requirement.source_url,
    }


@tool(
    "get_student_summary",
    "Короткая выжимка по ученику для задачи соответствия: только баллы, без профиля целиком.",
    {"type": "object", "properties": {"student": {"type": "integer"}}, "required": ["student"]},
)
def get_student_summary(context: ToolContext, student: int) -> dict:
    """В модель уходит минимум: баллы и счётчик активностей, не весь профиль."""
    obj = Student.objects.filter(pk=student).select_related("exam").first()
    if obj is None:
        return {"found": False}
    exam = getattr(obj, "exam", None)
    return {
        "found": True,
        "ielts": str(exam.ielts_current) if exam and exam.ielts_current else None,
        "sat": exam.sat_current if exam else None,
        "gpa": str(exam.gpa) if exam and exam.gpa else None,
        "activities": obj.activities.count(),
    }


@tool(
    "create_tasks_for_group",
    "Предложить задачи группе учеников.",
    {
        "type": "object",
        "properties": {
            "students": {"type": "array", "items": {"type": "integer"}},
            "title": {"type": "string"},
            "category": {"type": "string"},
            "due_date": {"type": "string", "description": "ГГГГ-ММ-ДД"},
        },
        "required": ["students", "title", "category"],
    },
)
def create_tasks_for_group(
    context: ToolContext, students: list[int], title: str, category: str, due_date: str = ""
) -> dict:
    """Задачи создаются сразу: они не доменные поля и откатываются удалением.

    Автором остаётся вызвавший сотрудник — ответственность на человеке.
    """
    from roadmap.models import Task, TaskCategory

    if category not in dict(TaskCategory.choices):
        return {"created": 0, "reason": f"Неизвестная категория {category}"}

    created = 0
    for student_id in students:
        _, is_new = Task.objects.get_or_create(
            student_id=student_id,
            title=title,
            defaults={"category": category, "due_date": due_date or None, "author": context.actor},
        )
        created += int(is_new)
    return {"created": created}
