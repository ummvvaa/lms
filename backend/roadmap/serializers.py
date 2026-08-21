"""Сериализаторы роадмапа и эссе."""

from __future__ import annotations

from rest_framework import serializers

from roadmap.models import Essay, EssayComment, EssayVersion, Task, TaskComment, TaskTemplate


class TaskCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TaskComment
        fields = ("id", "task", "author", "author_name", "text", "created_at")
        read_only_fields = ("author", "author_name", "created_at")

    def get_author_name(self, obj) -> str:
        return (obj.author.full_name or obj.author.email) if obj.author_id else "система"


class TaskSerializer(serializers.ModelSerializer):
    """Задача. Срок из дедлайна вуза приходит вычисляемым полем."""

    due_date_effective = serializers.DateField(source="effective_due_date", read_only=True)
    from_deadline = serializers.SerializerMethodField()
    university_name = serializers.CharField(
        source="admission_round.program.university.name", read_only=True, default=None
    )
    comments = TaskCommentSerializer(many=True, read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "student",
            "title",
            "category",
            "priority",
            "description",
            "status",
            "due_date",
            "due_date_effective",
            "from_deadline",
            "admission_round",
            "university_name",
            "template",
            "created_at",
            "completed_at",
            "comments",
        )
        read_only_fields = ("created_at", "completed_at", "due_date_effective", "from_deadline")

    def get_from_deadline(self, obj) -> bool:
        return obj.admission_round_id is not None


class TaskTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTemplate
        fields = (
            "id",
            "title",
            "category",
            "priority",
            "description",
            "due_month",
            "due_day",
            "graduation_year",
            "grade",
            "is_active",
        )


class EssayVersionSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = EssayVersion
        fields = ("id", "essay", "number", "text", "word_count", "author", "author_name", "created_at")
        read_only_fields = ("number", "word_count", "author", "author_name", "created_at")

    def get_author_name(self, obj) -> str:
        return (obj.author.full_name or obj.author.email) if obj.author_id else "—"


class EssayCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = EssayComment
        fields = ("id", "essay", "version", "author", "author_name", "text", "created_at")
        read_only_fields = ("author", "author_name", "created_at")

    def get_author_name(self, obj) -> str:
        return (obj.author.full_name or obj.author.email) if obj.author_id else "—"


class EssaySerializer(serializers.ModelSerializer):
    versions = EssayVersionSerializer(many=True, read_only=True)
    comments = EssayCommentSerializer(many=True, read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True, default=None)

    class Meta:
        model = Essay
        fields = (
            "id",
            "student",
            "program",
            "program_name",
            "essay_type",
            "title",
            "status",
            "curator",
            "created_at",
            "updated_at",
            "versions",
            "comments",
        )
        read_only_fields = ("created_at", "updated_at")


class GenerateTasksSerializer(serializers.Serializer):
    """Генерация роадмапа: по ученику, группе или всему потоку."""

    student = serializers.IntegerField(required=False)
    group = serializers.CharField(required=False)
    graduation_year = serializers.IntegerField(required=False)
