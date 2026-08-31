"""Сериализаторы роадмапа и эссе."""

from __future__ import annotations

from rest_framework import serializers

from core.serializers import PartialUniqueMixin
from roadmap.models import (
    ApplicationPlan,
    Essay,
    EssayCheckQuestion,
    EssayComment,
    EssayDocType,
    EssayExample,
    EssayGuide,
    EssayVersion,
    Task,
    TaskComment,
    TaskTemplate,
)
from students.models import Student
from universities.models import AdmissionRound


class TaskCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TaskComment
        fields = ("id", "task", "author", "author_name", "text", "created_at")
        read_only_fields = ("author", "author_name", "created_at")

    def get_author_name(self, obj) -> str:
        return (obj.author.full_name or obj.author.email) if obj.author_id else "система"


class TaskSerializer(PartialUniqueMixin, serializers.ModelSerializer):
    """Задача. Срок из дедлайна вуза приходит вычисляемым полем."""

    due_date_effective = serializers.DateField(source="effective_due_date", read_only=True)
    from_deadline = serializers.SerializerMethodField()
    # оба поля необязательны: задача бывает и без раунда, и без шаблона.
    # DRF делал их обязательными из-за частичных UniqueConstraint с `student`,
    # и завести обычную задачу через API было нельзя вовсе
    admission_round = serializers.PrimaryKeyRelatedField(
        queryset=AdmissionRound.objects.all(), required=False, allow_null=True
    )
    template = serializers.PrimaryKeyRelatedField(queryset=TaskTemplate.objects.all(), required=False, allow_null=True)
    university_name = serializers.CharField(
        source="admission_round.program.university.name", read_only=True, default=None
    )
    # задача плана по вузу (фаза 41): пометка, к какому вузу относится
    plan_university = serializers.CharField(source="plan.program.university.name", read_only=True, default=None)
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
            "plan",
            "plan_university",
            "template",
            "created_at",
            "completed_at",
            "comments",
        )
        read_only_fields = (
            "created_at",
            "completed_at",
            "due_date_effective",
            "from_deadline",
            "plan",
            "plan_university",
        )

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
    doc_type_name = serializers.CharField(source="doc_type.name", read_only=True, default=None)
    effective_word_limit = serializers.SerializerMethodField()
    # ученик заводит эссе себе, не передавая student; сотрудник указывает его
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all(), required=False)

    def get_effective_word_limit(self, obj) -> int:
        """Свой лимит слов, иначе из типа документа, иначе стандартный (фаза 43)."""
        if obj.word_limit:
            return obj.word_limit
        if obj.doc_type_id:
            return obj.doc_type.default_word_limit
        return 650

    class Meta:
        model = Essay
        fields = (
            "id",
            "student",
            "program",
            "program_name",
            "essay_type",
            "doc_type",
            "doc_type_name",
            "word_limit",
            "effective_word_limit",
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


class ApplicationPlanSerializer(serializers.ModelSerializer):
    """План поступления по программе (фаза 41). Дедлайн — из раунда, не копия."""

    university_name = serializers.CharField(source="program.university.name", read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True)
    level_title = serializers.CharField(source="program.get_level_display", read_only=True)
    round_type = serializers.CharField(source="admission_round.round_type", read_only=True, default=None)
    deadline = serializers.DateField(read_only=True)
    counters = serializers.SerializerMethodField()
    days_left = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationPlan
        fields = (
            "id",
            "student",
            "program",
            "admission_round",
            "university_name",
            "program_name",
            "level_title",
            "round_type",
            "deadline",
            "generation_status",
            "generation_offline",
            "counters",
            "days_left",
            "progress",
            "created_at",
        )
        read_only_fields = fields

    def _counts(self, obj) -> dict:
        cache = getattr(obj, "_counts_cache", None)
        if cache is None:
            tasks = obj.tasks.all()
            total = len(tasks)
            done = sum(1 for t in tasks if t.status == "done")
            in_progress = sum(1 for t in tasks if t.status == "in_progress")
            cache = {"total": total, "done": done, "in_progress": in_progress, "remaining": total - done}
            obj._counts_cache = cache
        return cache

    def get_counters(self, obj) -> dict:
        return self._counts(obj)

    def get_progress(self, obj) -> int:
        counts = self._counts(obj)
        return round(counts["done"] / counts["total"] * 100) if counts["total"] else 0

    def get_days_left(self, obj):
        if obj.deadline is None:
            return None
        from django.utils import timezone

        return (obj.deadline - timezone.localdate()).days


# --- Конструктор эссе (фаза 43) --------------------------------------------


class EssayGuideSerializer(serializers.ModelSerializer):
    class Meta:
        model = EssayGuide
        fields = ("id", "doc_type", "what_is", "prompts", "mistakes", "tips")


class EssayCheckQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EssayCheckQuestion
        fields = (
            "id",
            "doc_type",
            "text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "correct",
            "explanation",
            "order",
        )


class EssayDocTypeSerializer(serializers.ModelSerializer):
    guide = EssayGuideSerializer(read_only=True)
    check_questions = EssayCheckQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = EssayDocType
        fields = (
            "id",
            "code",
            "name",
            "description",
            "default_word_limit",
            "order",
            "is_active",
            "guide",
            "check_questions",
        )


class EssayExampleSerializer(serializers.ModelSerializer):
    doc_type_name = serializers.CharField(source="doc_type.name", read_only=True, default="")

    class Meta:
        model = EssayExample
        fields = ("id", "doc_type", "doc_type_name", "title", "source_url", "body", "note", "is_active", "created_at")
        read_only_fields = ("created_at",)
