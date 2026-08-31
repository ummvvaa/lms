"""Сериализаторы онбординга и геймификации."""

from __future__ import annotations

from rest_framework import serializers

from engagement.models import CareerDirection, CareerQuestion, CareerRun


class OnboardingAnswerSerializer(serializers.Serializer):
    """Один шаг квиза."""

    question = serializers.CharField(max_length=32)
    value = serializers.CharField(allow_blank=True, required=False, max_length=250)


class OnboardingReviewSerializer(serializers.Serializer):
    """Решение директора по ответу ученика."""

    decision = serializers.ChoiceField(choices=(("confirm", "Подтвердить"), ("decline", "Отклонить")))
    value = serializers.CharField(allow_blank=True, required=False, max_length=250)


# --- Профтест (фаза 45) ----------------------------------------------------


class CareerQuestionSerializer(serializers.ModelSerializer):
    """Вопрос анкеты. Варианты приходят разобранными списком."""

    options_list = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = CareerQuestion
        fields = ("id", "code", "text", "hint", "kind", "options", "options_list", "order", "is_active")


class CareerDirectionSerializer(serializers.ModelSerializer):
    """Одно направление разбора вместе с программами справочника."""

    programs = serializers.SerializerMethodField()
    agreed = serializers.SerializerMethodField()

    class Meta:
        model = CareerDirection
        fields = ("id", "order", "title", "reasoning", "subjects", "exams", "programs", "agreed", "suggestion")

    def get_programs(self, obj) -> list[dict]:
        return [
            {
                "id": program.pk,
                "name": program.name,
                "university": program.university.name,
                "level_title": program.get_level_display(),
            }
            for program in obj.programs.select_related("university").all()
        ]

    def get_agreed(self, obj) -> bool:
        return obj.agreed_at is not None


class CareerRunSerializer(serializers.ModelSerializer):
    """Проход профтеста: ответы и разбор строками."""

    directions = CareerDirectionSerializer(many=True, read_only=True)
    answers = serializers.SerializerMethodField()

    class Meta:
        model = CareerRun
        fields = ("id", "status", "summary", "error", "created_at", "directions", "answers")

    def get_answers(self, obj) -> list[dict]:
        return [
            {"question": row.question.text, "value": row.value} for row in obj.answers.select_related("question").all()
        ]


class CareerAnswerRowSerializer(serializers.Serializer):
    """Один ответ анкеты: код вопроса и текст."""

    question = serializers.CharField(max_length=40)
    value = serializers.CharField(allow_blank=True, required=False, max_length=1000)


class CareerRunRequestSerializer(serializers.Serializer):
    """Заполненная анкета целиком."""

    answers = CareerAnswerRowSerializer(many=True)
