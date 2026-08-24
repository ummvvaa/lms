"""Сериализаторы предложений."""

from __future__ import annotations

from rest_framework import serializers

from core.labels import field_short, field_title, model_title, value_title
from suggestions.commands import title_of as command_title
from suggestions.models import Suggestion, SuggestionChange


class SuggestionChangeSerializer(serializers.ModelSerializer):
    """Строка предпросмотра. Имя колонки в ответе не показывается человеку:
    рядом всегда идёт подпись из реестра доменов (фаза 17)."""

    student_name = serializers.CharField(source="student.full_name", read_only=True, default=None)
    field_title = serializers.SerializerMethodField()
    field_short = serializers.SerializerMethodField()
    model_title = serializers.SerializerMethodField()
    old_display = serializers.SerializerMethodField()
    new_display = serializers.SerializerMethodField()

    def get_field_title(self, obj) -> str:
        return field_title(obj.model_label, obj.field_name)

    def get_field_short(self, obj) -> str:
        return field_short(obj.model_label, obj.field_name)

    def get_model_title(self, obj) -> str:
        return model_title(obj.model_label)

    def get_old_display(self, obj) -> str:
        return value_title(obj.model_label, obj.field_name, obj.old_value)

    def get_new_display(self, obj) -> str:
        return value_title(obj.model_label, obj.field_name, obj.new_value)

    class Meta:
        model = SuggestionChange
        fields = (
            "id",
            "student",
            "student_name",
            "model_label",
            "model_title",
            "field_title",
            "field_short",
            "old_value",
            "new_value",
            "old_display",
            "new_display",
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
    command_title = serializers.SerializerMethodField()
    status_title = serializers.CharField(source="get_status_display", read_only=True)
    source_title = serializers.CharField(source="get_source_type_display", read_only=True)

    def get_command_title(self, obj) -> str:
        return command_title(obj.command) or obj.get_source_type_display()

    class Meta:
        model = Suggestion
        fields = (
            "id",
            "author",
            "author_name",
            "role",
            "domain_code",
            "command",
            "command_title",
            "status_title",
            "source_title",
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
