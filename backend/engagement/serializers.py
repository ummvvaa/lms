"""Сериализаторы онбординга и геймификации."""

from __future__ import annotations

from rest_framework import serializers


class OnboardingAnswerSerializer(serializers.Serializer):
    """Один шаг квиза."""

    question = serializers.CharField(max_length=32)
    value = serializers.CharField(allow_blank=True, required=False, max_length=250)


class OnboardingReviewSerializer(serializers.Serializer):
    """Решение директора по ответу ученика."""

    decision = serializers.ChoiceField(choices=(("confirm", "Подтвердить"), ("decline", "Отклонить")))
    value = serializers.CharField(allow_blank=True, required=False, max_length=250)
