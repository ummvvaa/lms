"""Сериализаторы раздела материалов.

Технических кодов в ответах нет: рядом с каждым статусом и типом
источника идёт подпись, собранная сервером (фаза 17).
"""

from __future__ import annotations

from rest_framework import serializers

from core.serializers import PartialUniqueMixin
from materials.models import (
    CollectionItem,
    MaterialCollection,
    MaterialComment,
    MaterialFile,
    MaterialReport,
    MaterialRequest,
    SourceKind,
    StudyMaterial,
)


class MaterialFileSerializer(serializers.ModelSerializer):
    """Файл материала. Ссылка ведёт на вьюху с проверкой прав, а не в /media/."""

    url = serializers.SerializerMethodField()
    size_human = serializers.SerializerMethodField()

    def get_url(self, obj) -> str:
        return f"/api/materials/files/{obj.pk}/"

    def get_size_human(self, obj) -> str:
        mb = obj.size / (1024 * 1024)
        return f"{mb:.1f} МБ".replace(".0 ", " ") if mb >= 0.1 else f"{max(1, obj.size // 1024)} КБ"

    class Meta:
        model = MaterialFile
        fields = ("id", "original_name", "content_type", "size", "size_human", "url", "created_at")


class MaterialSerializer(serializers.ModelSerializer):
    """Карточка материала."""

    author_name = serializers.CharField(source="author.full_name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    source_kind_title = serializers.CharField(source="get_source_kind_display", read_only=True)
    status_title = serializers.CharField(source="get_status_display", read_only=True)
    files = MaterialFileSerializer(many=True, read_only=True)
    marked_helpful = serializers.SerializerMethodField()
    can_moderate = serializers.SerializerMethodField()

    def get_marked_helpful(self, obj) -> bool:
        student = getattr(self.context.get("request").user, "student", None) if self.context.get("request") else None
        if student is None:
            return False
        return obj.helpful_marks.filter(student=student).exists()

    def get_can_moderate(self, obj) -> bool:
        from materials.access import keeps_the_group

        request = self.context.get("request")
        return bool(request and keeps_the_group(request.user))

    class Meta:
        model = StudyMaterial
        fields = (
            "id",
            "author",
            "author_name",
            "subject",
            "subject_name",
            "topic",
            "title",
            "description",
            "source_kind",
            "source_kind_title",
            "rights_confirmed",
            "status",
            "status_title",
            "reject_reason",
            "request",
            "helpful_count",
            "marked_helpful",
            "can_moderate",
            "files",
            "created_at",
            "reviewed_at",
        )
        read_only_fields = (
            "author",
            "status",
            "reject_reason",
            "helpful_count",
            "created_at",
            "reviewed_at",
        )

    def validate_rights_confirmed(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                "Без подтверждения права на публикацию материал не заводится. "
                "Если материал чужой и права нет — не выкладывайте его"
            )
        return value

    def validate_source_kind(self, value: str) -> str:
        if value not in SourceKind.values:
            raise serializers.ValidationError("Выберите, что это за материал: ваше решение, ваш разбор или чужое")
        return value


class MaterialCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    def get_author_name(self, obj) -> str:
        return obj.author.full_name or obj.author.email

    def get_is_mine(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and obj.author_id == request.user.pk)

    class Meta:
        model = MaterialComment
        fields = ("id", "material", "author", "author_name", "is_mine", "text", "created_at")
        read_only_fields = ("author", "created_at")


class MaterialReportSerializer(PartialUniqueMixin, serializers.ModelSerializer):
    reporter_name = serializers.SerializerMethodField()
    status_title = serializers.CharField(source="get_status_display", read_only=True)

    def get_reporter_name(self, obj) -> str:
        return obj.reporter.full_name or obj.reporter.email

    class Meta:
        model = MaterialReport
        fields = (
            "id",
            "material",
            "comment",
            "reporter",
            "reporter_name",
            "reason",
            "status",
            "status_title",
            "resolution",
            "created_at",
            "resolved_at",
        )
        read_only_fields = ("reporter", "status", "resolution", "created_at", "resolved_at")

    def validate(self, attrs):
        if not attrs.get("material") and not attrs.get("comment"):
            raise serializers.ValidationError("Укажите, на что жалуетесь: на материал или на комментарий")
        return attrs


class MaterialRequestSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    status_title = serializers.CharField(source="get_status_display", read_only=True)
    answers = serializers.SerializerMethodField()

    def get_answers(self, obj) -> int:
        return obj.materials.filter(status="approved").count()

    class Meta:
        model = MaterialRequest
        fields = (
            "id",
            "author",
            "author_name",
            "subject",
            "subject_name",
            "topic",
            "text",
            "status",
            "status_title",
            "answers",
            "created_at",
            "closed_at",
        )
        read_only_fields = ("author", "status", "created_at", "closed_at")


class CollectionItemSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="material.title", read_only=True)
    author_name = serializers.CharField(source="material.author.full_name", read_only=True)
    subject_name = serializers.CharField(source="material.subject.name", read_only=True)

    class Meta:
        model = CollectionItem
        fields = ("id", "material", "title", "author_name", "subject_name", "position")


class MaterialCollectionSerializer(serializers.ModelSerializer):
    items = CollectionItemSerializer(many=True, read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True, default="")

    class Meta:
        model = MaterialCollection
        fields = ("id", "name", "description", "subject", "subject_name", "items", "created_at")
        read_only_fields = ("created_at",)


class ReviewSerializer(serializers.Serializer):
    """Решение по материалу: одобрить или отклонить с причиной."""

    decision = serializers.ChoiceField(choices=("approve", "reject"))
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        if attrs["decision"] == "reject" and not (attrs.get("reason") or "").strip():
            raise serializers.ValidationError(
                {"reason": "Отклонение без причины автор не поймёт — напишите, что не так"}
            )
        return attrs


class GroupPickSerializer(serializers.Serializer):
    """Отбор в олимпиадную группу: отметить или снять."""

    student = serializers.IntegerField()
    member = serializers.BooleanField()


class CollectionPickSerializer(serializers.Serializer):
    material = serializers.IntegerField()
    position = serializers.IntegerField(required=False, default=100)
