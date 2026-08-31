"""Сериализаторы центра подготовки."""

from __future__ import annotations

from rest_framework import serializers

from prep.models import Difficulty, MockExam, MockSection, Question, QuestionOption, Section, TheoryLesson
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
            "subtopic",
            "difficulty",
            "question_type",
            "text",
            "explanation",
            "criteria",
            "sample_answer",
            "expected_seconds",
            "source",
            "source_year",
            "passage",
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
    """Пробный экзамен вместе с секциями.

    Секции пишутся вложенно: мок без секций собрать нельзя, а два запроса
    ради одной формы означали бы мок, наполовину заведённый при обрыве.
    """

    sections = MockSectionSerializer(many=True, required=False)

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

    def create(self, validated_data):
        sections = validated_data.pop("sections", [])
        mock = MockExam.objects.create(**validated_data)
        for order, section in enumerate(sections, start=1):
            section.setdefault("order", order)
            MockSection.objects.create(mock=mock, **section)
        return mock

    def update(self, instance, validated_data):
        """Состав секций заменяется целиком: так его и правят — списком."""
        sections = validated_data.pop("sections", None)
        for name, value in validated_data.items():
            setattr(instance, name, value)
        instance.save()
        if sections is not None:
            instance.sections.all().delete()
            for order, section in enumerate(sections, start=1):
                section.setdefault("order", order)
                MockSection.objects.create(mock=instance, **section)
        return instance


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


class TheoryLessonSerializer(serializers.ModelSerializer):
    """Урок теории (фаза 42). Файл отдаётся своим маршрутом с проверкой прав."""

    section_title = serializers.CharField(source="get_section_display", read_only=True, default="")
    level_title = serializers.CharField(source="get_level_display", read_only=True)
    has_file = serializers.SerializerMethodField()

    def get_has_file(self, obj) -> bool:
        return bool(obj.file)

    class Meta:
        model = TheoryLesson
        fields = (
            "id",
            "exam_type",
            "section",
            "section_title",
            "title",
            "level",
            "level_title",
            "reading_minutes",
            "body",
            "has_file",
            "order",
            "is_active",
        )


# --- Квиз (фаза 46) --------------------------------------------------------


class QuizStartSerializer(serializers.Serializer):
    """Начало матча: соло или вызов."""

    kind = serializers.ChoiceField(choices=("solo", "duel"), default="solo")
    exam_type = serializers.CharField(max_length=12)
    section = serializers.CharField(max_length=16, required=False, allow_blank=True)
    size = serializers.IntegerField(min_value=3, max_value=30, required=False)


class QuizJoinSerializer(serializers.Serializer):
    """Принятие вызова по коду."""

    code = serializers.CharField(max_length=8)
