"""Базовые сериализаторы, знающие про домены и про инвариант №7.

Скрытие внутренних ярлыков от ученика делается здесь, на бэкенде.
Прятать их на фронте нельзя: ответ API не должен их содержать вовсе.
"""

from __future__ import annotations

from django.db import models
from rest_framework import serializers

from core.audit import apply_changes, model_label
from core.domains import ROLE_STUDENT, Source, can_write, internal_label_fields


class PartialUniqueMixin:
    """Частичные `UniqueConstraint` не должны делать поля обязательными.

    Ограничение с `condition` действует только когда условие выполнено —
    например «одна задача на ученика по одному раунду» работает лишь
    у задач с раундом. DRF же превращает такое ограничение в проверку,
    которая требует все его поля в каждом запросе, и завести обычную
    задачу без раунда становилось нельзя вовсе.
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
