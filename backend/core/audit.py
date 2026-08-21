"""Запись изменений доменных полей в журнал (инвариант №9).

Единственная точка, через которую доменные поля меняются программно.
Всё, что пишет в профили — API, импорт, применение предложений, фоновая
сверка — проходит здесь и оставляет след с указанием источника.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models

from core.domains import Source, domain_of_field
from core.models import AuditLog


def model_label(instance_or_model: Any) -> str:
    """`app_label.ModelName` для инстанса или класса модели."""
    meta = instance_or_model._meta
    return f"{meta.app_label}.{meta.object_name}"


def to_text(value: Any) -> str:
    """Значение поля в виде строки для журнала."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, models.Model):
        return str(value.pk)
    return str(value)


def normalize(instance: Any, field_name: str, value: Any) -> Any:
    """Привести значение к тому виду, в котором его хранит колонка.

    Без этого повторный импорт того же файла выглядит как изменение:
    `Decimal("3.8")` и прочитанное из базы `Decimal("3.80")` — одно и то же
    число, но разные строки в журнале.
    """
    try:
        field = instance._meta.get_field(field_name)
    except FieldDoesNotExist:
        return value
    if field.is_relation or value is None:
        return value
    try:
        value = field.to_python(value)
    except (ValidationError, TypeError, ValueError):
        return value
    if isinstance(field, models.DecimalField) and isinstance(value, Decimal) and field.decimal_places is not None:
        value = value.quantize(Decimal(1).scaleb(-field.decimal_places))
    return value


def student_id_of(instance: Any) -> int | None:
    """Ученик, к которому относится объект, если он есть."""
    if hasattr(instance, "student_id"):
        return instance.student_id
    if instance.__class__.__name__ == "Student":
        return instance.pk
    return None


def record_change(
    *,
    instance: Any,
    field_name: str,
    old_value: Any,
    new_value: Any,
    actor=None,
    source: str = Source.MANUAL,
    suggestion=None,
) -> AuditLog | None:
    """Записать одно изменение. Если значение не поменялось — записи нет."""
    old_text, new_text = to_text(old_value), to_text(new_value)
    if old_text == new_text:
        return None
    label = model_label(instance)
    domain = domain_of_field(label, field_name)
    return AuditLog.objects.create(
        actor=actor,
        model_label=label,
        object_id=str(instance.pk),
        student_id=student_id_of(instance),
        field_name=field_name,
        domain_code=domain.code if domain else "",
        old_value=old_text,
        new_value=new_text,
        source=source,
        suggestion=suggestion,
    )


def apply_changes(
    instance: Any,
    changes: dict[str, Any],
    *,
    actor=None,
    source: str = Source.MANUAL,
    suggestion=None,
) -> list[AuditLog]:
    """Применить набор изменений к объекту и записать их в журнал.

    Старые значения снимаются до присваивания. Возвращает созданные записи
    аудита; сохраняются только затронутые поля.
    """
    touched: dict[str, tuple[Any, Any]] = {}
    for field_name, raw_value in changes.items():
        new_value = normalize(instance, field_name, raw_value)
        old_value = getattr(instance, field_name, None)
        if to_text(old_value) == to_text(new_value):
            continue
        touched[field_name] = (old_value, new_value)
        setattr(instance, field_name, new_value)
    if not touched:
        return []
    # сигнал post_save увидит этот флаг и не запишет те же поля второй раз
    instance._audit_handled = tuple(touched)
    if instance.pk is None:
        instance.save()
    else:
        update_fields = set(touched)
        if any(f.name == "updated_at" for f in instance._meta.fields):
            update_fields.add("updated_at")
        instance.save(update_fields=sorted(update_fields))
    entries: list[AuditLog] = []
    for field_name, (old_value, new_value) in touched.items():
        entry = record_change(
            instance=instance,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            actor=actor,
            source=source,
            suggestion=suggestion,
        )
        if entry:
            entries.append(entry)
    return entries
