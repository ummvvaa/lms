"""Сериализаторы предложений."""

from __future__ import annotations

from rest_framework import serializers

from core.labels import field_short, field_title, model_title, value_title
from suggestions.commands import title_of as command_title
from suggestions.models import AssistantMessage, AssistantThread, Suggestion, SuggestionChange


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
            "new_object_key",
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
    #: домен, за который вставляет администратор; директору не нужен (фаза 35)
    domain = serializers.CharField(required=False, allow_blank=True, max_length=32)


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
    """«Загрузить файл» — администратор, за выбранный домен."""

    file = serializers.FileField()
    domain = serializers.CharField(required=False, allow_blank=True, max_length=32)


class OperationSerializer(serializers.Serializer):
    """Запуск операции уровня управления."""

    code = serializers.CharField()
    text = serializers.CharField(required=False, allow_blank=True, default="")
    students = serializers.ListField(child=serializers.IntegerField(), required=False)
    student = serializers.IntegerField(required=False)
    days = serializers.IntegerField(required=False, min_value=1, max_value=90)


class ParseUniversitySerializer(serializers.Serializer):
    text = serializers.CharField()


class VerifyRequirementsSerializer(serializers.Serializer):
    program = serializers.IntegerField()


class ParseActivitySerializer(serializers.Serializer):
    text = serializers.CharField()
    student = serializers.IntegerField()


class ParseImageSerializer(serializers.Serializer):
    """Фото грамоты или скриншот с баллами."""

    file = serializers.ImageField()
    student = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=("certificate", "scores"))


class AssistantThreadSerializer(serializers.ModelSerializer):
    """Строка истории диалогов."""

    class Meta:
        model = AssistantThread
        fields = ("id", "title", "created_at", "updated_at")
        read_only_fields = fields


class AssistantMessageSerializer(serializers.ModelSerializer):
    """Сообщение диалога; строки-списки отдаются массивом."""

    lines = serializers.SerializerMethodField()

    class Meta:
        model = AssistantMessage
        fields = ("id", "author", "text", "lines", "command", "suggestion", "offline", "affected", "created_at")
        read_only_fields = fields

    def get_lines(self, obj) -> list[str]:
        return [row for row in obj.lines.split("\n") if row] if obj.lines else []


class AssistantAskSerializer(serializers.Serializer):
    """Запрос помощнику: быстрая кнопка или свободный текст."""

    thread = serializers.IntegerField(required=False, allow_null=True)
    command = serializers.CharField(required=False, allow_blank=True, max_length=64)
    text = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    #: контекст экрана: какие ученики сейчас отфильтрованы
    students = serializers.ListField(child=serializers.IntegerField(), required=False, max_length=500)
    screen = serializers.CharField(required=False, allow_blank=True, max_length=200)

    def validate(self, attrs):
        if not (attrs.get("command") or "").strip() and not (attrs.get("text") or "").strip():
            raise serializers.ValidationError("Нужна кнопка или текст вопроса")
        return attrs
