"""Сериализаторы центра подготовки."""

from __future__ import annotations

from rest_framework import serializers

from prep.models import Difficulty, MockExam, MockSection, Question, QuestionOption, Section
from students.models import ExamType


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ("id", "letter", "text", "is_correct")


class QuestionSerializer(serializers.ModelSerializer):
    """Задание с вариантами. Верный ответ виден только сотрудникам."""

    options = QuestionOptionSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = (
            "id",
            "exam_type",
            "section",
            "topic",
            "difficulty",
            "text",
            "explanation",
            "source",
            "is_active",
            "options",
        )

    def create(self, validated_data):
        options = validated_data.pop("options", [])
        question = Question.objects.create(**validated_data)
        for option in options:
            QuestionOption.objects.create(question=question, **option)
        return question

    def update(self, instance, validated_data):
        options = validated_data.pop("options", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if options is not None:
            instance.options.all().delete()
            for option in options:
                QuestionOption.objects.create(question=instance, **option)
        return instance


class MockSectionSerializer(serializers.ModelSerializer):
    section_title = serializers.CharField(source="get_section_display", read_only=True)

    class Meta:
        model = MockSection
        fields = ("id", "section", "section_title", "question_count", "order")


class MockExamSerializer(serializers.ModelSerializer):
    sections = MockSectionSerializer(many=True, read_only=True)

    class Meta:
        model = MockExam
        fields = (
            "id",
            "title",
            "exam_type",
            "time_limit_minutes",
            "description",
            "is_active",
            "sections",
        )


class StartPracticeSerializer(serializers.Serializer):
    """Параметры тренировки."""

    exam_type = serializers.ChoiceField(choices=ExamType.choices)
    section = serializers.ChoiceField(choices=Section.choices, required=False, allow_blank=True)
    difficulty = serializers.ChoiceField(choices=Difficulty.choices, required=False, allow_blank=True)
    topic = serializers.CharField(required=False, allow_blank=True, max_length=120)
    size = serializers.IntegerField(required=False, min_value=1, max_value=50)


class AnswerSerializer(serializers.Serializer):
    """Ответ на одно задание. Верность считает сервер."""

    answer_id = serializers.IntegerField()
    option = serializers.IntegerField(required=False, allow_null=True)
    seconds = serializers.IntegerField(required=False, min_value=0, max_value=36_000)


class FinishSerializer(serializers.Serializer):
    seconds = serializers.IntegerField(required=False, min_value=0, max_value=36_000)


class ReviewMockSerializer(serializers.Serializer):
    """Решение директора: учитывать платформенный мок или нет."""

    count_it = serializers.BooleanField()


class QuestionImportSerializer(serializers.Serializer):
    """Импорт банка заданий из файла."""

    file = serializers.FileField()
