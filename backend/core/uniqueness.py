"""Условные ограничения уникальности — словами, а не 500 (D24, D35).

У моделей есть частичные `UniqueConstraint`: «одна живая цель на экзамен»,
«одна задача на ученика по раунду». DRF 3.17 такие ограничения либо
пропускает (поле условия `archived_at` не входит в сериализатор), либо
превращает в валидатор, который делает необязательные поля обязательными.
Итог был один: запрос доходил до базы, база отвечала `IntegrityError`,
человек видел 500.

Здесь одно место, где столкновение ищется до записи и называется по-русски.
Его зовут сериализаторы перед сохранением и `apply_changes` перед `save()`:
так покрыты и ручки API, и применение предложений, и импорт.
"""

from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import Q, UniqueConstraint

#: Текст столкновения по имени ограничения. Подстановки — из полей записи.
MESSAGES: dict[str, str] = {
    "unique_active_exam_goal": "Цель по {exam} уже есть — измените её, а не заводите вторую",
    "unique_task_per_exam_goal": "Задача по этой цели у ученика уже есть",
    "uniq_task_per_student_round": "Задача по этому раунду у ученика уже есть",
    "uniq_task_per_student_template": "Задача по этому шаблону у ученика уже есть",
    "uniq_task_per_scholarship": "Задача по этой стипендии у ученика уже есть",
    "unique_active_plan_per_program": "План по этой программе у ученика уже есть",
    "unique_active_mock_import": "Пробник этого экзамена для этой группы на эту дату уже загружен",
}


def _value_of(instance: Any, field_name: str) -> Any:
    """Значение поля для сравнения: у ссылки — идентификатор."""
    field = instance._meta.get_field(field_name)
    if field.is_relation:
        return getattr(instance, field.attname, None)
    return getattr(instance, field_name, None)


def _holds(condition: Q | None, instance: Any) -> bool:
    """Выполнено ли условие ограничения у самой записи.

    Условия у нас простые — «поле пусто» и «поле не пусто» через `isnull`,
    иногда равенство. Незнакомую форму считаем выполненной: тогда решает
    запрос к базе с тем же условием, и лишнего отказа не будет.
    """
    if condition is None:
        return True
    results = []
    for child in condition.children:
        if isinstance(child, Q):
            results.append(_holds(child, instance))
            continue
        lookup, expected = child
        name, _, op = lookup.partition("__")
        try:
            value = _value_of(instance, name)
        except Exception:
            results.append(True)
            continue
        if op == "isnull":
            results.append((value is None) == bool(expected))
        elif op == "":
            results.append(value == expected)
        else:
            results.append(True)
    if not results:
        return True
    combined = any(results) if condition.connector == Q.OR else all(results)
    return not combined if condition.negated else combined


def _describe(instance: Any, constraint: UniqueConstraint) -> str:
    """Человеческий текст столкновения."""
    from core.audit import model_label
    from core.labels import field_title

    template = MESSAGES.get(constraint.name)
    if template:
        params: dict[str, str] = {}
        for name in constraint.fields:
            related = getattr(instance, name, None)
            params[name] = str(related) if related is not None else ""
        try:
            return template.format(**params)
        except (KeyError, IndexError):
            return template
    label = model_label(instance)
    titles = ", ".join(f"«{field_title(label, name)}»" for name in constraint.fields)
    return f"Такая запись уже есть: {titles} совпадают"


def conflict_of(instance: Any) -> str | None:
    """Найти живую запись, с которой столкнётся эта. Пусто — столкновения нет."""
    manager = getattr(type(instance), "all_objects", type(instance)._default_manager)
    for constraint in instance._meta.constraints:
        if not isinstance(constraint, UniqueConstraint) or not constraint.fields:
            continue
        values = {name: _value_of(instance, name) for name in constraint.fields}
        if any(value is None for value in values.values()):
            continue
        if not _holds(constraint.condition, instance):
            continue
        rows = manager.filter(**values)
        if constraint.condition is not None:
            rows = rows.filter(constraint.condition)
        if instance.pk is not None:
            rows = rows.exclude(pk=instance.pk)
        if rows.exists():
            return _describe(instance, constraint)
    return None


def touches(instance: Any, field_names: Any) -> bool:
    """Задевает ли набор полей хоть одно ограничение уникальности."""
    names = set(field_names)
    for constraint in instance._meta.constraints:
        if isinstance(constraint, UniqueConstraint) and names & set(constraint.fields):
            return True
        if isinstance(constraint, UniqueConstraint) and constraint.condition is not None:
            # смена условия (например, возврат из архива) тоже может столкнуть
            if names & _condition_fields(constraint.condition):
                return True
    return False


def _condition_fields(condition: Q) -> set[str]:
    out: set[str] = set()
    for child in condition.children:
        if isinstance(child, Q):
            out |= _condition_fields(child)
        else:
            out.add(child[0].partition("__")[0])
    return out


def build(model: type[models.Model], instance: Any | None, data: dict[str, Any]) -> Any:
    """Черновик записи для проверки: существующая с правками или новая."""
    draft = instance if instance is not None else model()
    if instance is not None:
        # проверяем копию, чтобы не задеть объект сериализатора
        draft = model(**{f.attname: getattr(instance, f.attname) for f in model._meta.concrete_fields})
    for name, value in data.items():
        try:
            field = model._meta.get_field(name)
        except Exception:
            continue
        if field.is_relation and not isinstance(value, models.Model):
            setattr(draft, field.attname, value)
        else:
            setattr(draft, name, value)
    return draft
