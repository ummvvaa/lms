"""Базовые сериализаторы, знающие про домены и про инвариант №7.

Скрытие внутренних ярлыков от ученика делается здесь, на бэкенде.
Прятать их на фронте нельзя: ответ API не должен их содержать вовсе.
"""

from __future__ import annotations

from django.db import models
from rest_framework import serializers

from core.audit import apply_changes, model_label
from core.domains import ROLE_STUDENT, Source, can_write, internal_label_fields


def unique_conflict(serializer, attrs: dict) -> str | None:
    """Столкновение по частичной уникальности — до сохранения (D24, D35).

    Ученик у дочерних таблиц приходит не полем сериализатора, а отдельно
    при сохранении (`perform_create`), поэтому берём его из сырых данных:
    без него «одна цель на экзамен» не с чем было бы сравнивать.
    """
    from core.uniqueness import build, conflict_of

    model = serializer.Meta.model
    data = dict(attrs)
    initial = getattr(serializer, "initial_data", None) or {}
    if serializer.instance is None and "student" not in data and hasattr(model, "student"):
        raw = initial.get("student") if hasattr(initial, "get") else None
        if str(raw or "").isdigit():
            data["student"] = int(raw)
    draft = build(model, serializer.instance, data)
    return conflict_of(draft)


class PartialUniqueMixin:
    """Частичные `UniqueConstraint`: без обязательности полей, но с проверкой.

    Ограничение с `condition` действует только когда условие выполнено —
    например «одна задача на ученика по одному раунду» работает лишь
    у задач с раундом. DRF превращает такое ограничение в проверку,
    которая требует все его поля в каждом запросе, и завести обычную
    задачу без раунда становилось нельзя вовсе. Поэтому валидаторы DRF
    по условным ограничениям снимаются, а столкновение ищет `validate`
    сам — иначе вместо отказа словами прилетал бы `IntegrityError` (D35).
    """

    def get_unique_together_validators(self):
        conditional = {
            tuple(constraint.fields)
            for constraint in self.Meta.model._meta.constraints
            if isinstance(constraint, models.UniqueConstraint) and constraint.condition is not None
        }
        return [
            validator
            for validator in super().get_unique_together_validators()
            if tuple(validator.fields) not in conditional
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        reason = unique_conflict(self, attrs)
        if reason:
            raise serializers.ValidationError(reason)
        return attrs


class DomainModelSerializer(serializers.ModelSerializer):
    """Сериализатор доменной модели.

    * для роли `student` выбрасывает поля-ярлыки из ответа;
    * поля чужого домена помечает `read_only`;
    * сохранение идёт через `core.audit.apply_changes`, поэтому каждое
      изменение попадает в журнал (инвариант №9).
    """

    #: `app_label.ModelName` — по нему сверяется реестр
    domain_model_label: str = ""

    def get_fields(self):
        """Состав полей считается лениво — на этот момент есть контекст запроса.

        Во вложенном сериализаторе `__init__` отрабатывает при объявлении
        родителя, когда `self.context` ещё пуст: фильтрация по роли там
        просто не сработает. DRF зовёт `get_fields()` при первом обращении
        к `.fields`, когда объект уже привязан к родителю и контекст доступен.
        """
        fields = super().get_fields()
        role = self._role()
        label = self.domain_model_label or model_label(self.Meta.model)

        if role == ROLE_STUDENT:
            for name in internal_label_fields(label):
                fields.pop(name, None)

        for name, field in fields.items():
            if not field.read_only and not can_write(role, label, name):
                field.read_only = True
        return fields

    def _role(self) -> str:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return getattr(user, "role", "") or ""

    def validate(self, attrs):
        """До записи — словами: частичная уникальность (D24) и шкала (D4, D17).

        DRF условие `archived_at` не видит и пропускает запрос к базе,
        а границы шкалы при создании через `objects.create` не проверял
        никто: цель IELTS 1200 проходила насквозь.
        """
        from core.audit import ValueRejected, check_bounds
        from core.uniqueness import build

        attrs = super().validate(attrs)
        reason = unique_conflict(self, attrs)
        if reason:
            raise serializers.ValidationError(reason)
        draft = build(self.Meta.model, self.instance, attrs)
        problems = {}
        for name, value in attrs.items():
            if value in (None, ""):
                continue
            try:
                check_bounds(draft, name, value)
            except ValueRejected as error:
                problems[name] = str(error)
        if problems:
            raise serializers.ValidationError(problems)
        return attrs

    def update(self, instance, validated_data):
        request = self.context.get("request")
        entries = apply_changes(
            instance,
            validated_data,
            actor=getattr(request, "user", None),
            source=Source.MANUAL,
        )
        self.context["audit_entries"] = entries
        return instance


class ReadOnlyDomainSerializer(DomainModelSerializer):
    """Чужой домен: видно, но не редактируется."""

    def update(self, instance, validated_data):  # pragma: no cover — запись запрещена
        raise serializers.ValidationError("Этот домен ведёт другой директор")
