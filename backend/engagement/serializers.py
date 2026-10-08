"""Сериализаторы онбординга и геймификации."""

from __future__ import annotations

from django.utils.translation import gettext_lazy
from rest_framework import serializers

from engagement.models import Badge, CallRule, HomeCue


class OnboardingAnswerSerializer(serializers.Serializer):
    """Один шаг квиза."""

    question = serializers.CharField(max_length=32)
    value = serializers.CharField(allow_blank=True, required=False, max_length=250)


class OnboardingReviewSerializer(serializers.Serializer):
    """Решение директора по ответу ученика."""

    decision = serializers.ChoiceField(
        choices=(("confirm", gettext_lazy("Подтвердить")), ("decline", gettext_lazy("Отклонить")))
    )
    value = serializers.CharField(allow_blank=True, required=False, max_length=250)


class BadgeSerializer(serializers.ModelSerializer):
    """Бейдж справочника. Условие — мера плюс порог, а не текст в коде."""

    metric_title = serializers.CharField(source="get_metric_display", read_only=True)

    class Meta:
        model = Badge
        fields = (
            "id",
            "code",
            "name",
            "description",
            "metric",
            "metric_title",
            "threshold",
            "icon",
            "order",
            "is_active",
        )


# --- Справочники фазы 49 ---------------------------------------------------


class HomeCueSerializer(serializers.ModelSerializer):
    """Сюжет карусели: условие из закрытого набора, слова и цвет — школы."""

    condition_title = serializers.CharField(source="get_condition_display", read_only=True)

    class Meta:
        model = HomeCue
        fields = (
            "id",
            "code",
            "condition",
            "condition_title",
            "title",
            "description",
            "action_label",
            "action_path",
            "tone",
            "order",
            "is_active",
        )


class CallRuleSerializer(serializers.ModelSerializer):
    """Правило обзвона: условие, порог, фраза причины и срочность."""

    condition_title = serializers.CharField(source="get_condition_display", read_only=True)
    urgency_title = serializers.CharField(source="get_urgency_display", read_only=True)

    class Meta:
        model = CallRule
        fields = (
            "id",
            "code",
            "condition",
            "condition_title",
            "reason",
            "urgency",
            "urgency_title",
            "threshold",
            "order",
            "is_active",
        )
