"""Сериализаторы предложений."""

from __future__ import annotations

from rest_framework import serializers

from suggestions.models import Suggestion, SuggestionChange


class SuggestionChangeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True, default=None)

    class Meta:
        model = SuggestionChange
        fields = (
            "id",
            "student",
            "student_name",
            "model_label",
            "field_name",
            "old_value",
            "new_value",
            "confidence",
            "source_ref",
            "source_quote",
            "is_accepted",
            "is_applied",
            "conflict",
        )
        read_only_fields = ("is_applied", "conflict")


class SuggestionSerializer(serializers.ModelSerializer):
    changes = SuggestionChangeSerializer(many=True, read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = Suggestion
        fields = (
            "id",
            "author",
            "author_name",
            "role",
            "domain_code",
            "command",
            "source_type",
            "source_ref",
            "status",
            "created_at",
            "resolved_at",
            "changes",
        )
        read_only_fields = fields

    def get_author_name(self, obj) -> str:
        return (obj.author.full_name or obj.author.email) if obj.author_id else "система"


class PasteSerializer(serializers.Serializer):
    """«Вставить как есть»."""

    text = serializers.CharField()
    command = serializers.CharField(required=False, default="paste_as_is")


class ApplySerializer(serializers.Serializer):
    """Частичное принятие: галочки в предпросмотре."""

    changes = serializers.ListField(child=serializers.IntegerField(), required=False)


class AcceptAboveSerializer(serializers.Serializer):
    """«Принять все выше порога» — отдельное явное действие."""

    threshold = serializers.FloatField(min_value=0, max_value=1)


class ResolveAmbiguitySerializer(serializers.Serializer):
    """«Нашлось двое, выберите»."""

    query = serializers.CharField()
    student = serializers.IntegerField()
    model = serializers.CharField()
    field = serializers.CharField()
    value = serializers.JSONField()
    source_quote = serializers.CharField(required=False, allow_blank=True)


class ExplainSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    program = serializers.IntegerField()


class EssayQuestionsSerializer(serializers.Serializer):
    essay = serializers.IntegerField()
    prompt = serializers.CharField()


class UploadSerializer(serializers.Serializer):
    """«Загрузить файл»."""

    file = serializers.FileField()
