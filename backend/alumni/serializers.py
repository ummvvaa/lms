"""Сериализаторы выпускников и менторства."""

from __future__ import annotations

from rest_framework import serializers

from alumni.models import (
    Alumnus,
    AlumnusApplication,
    ArchivedEssay,
    MentorshipMeeting,
    MentorshipRequest,
)


class AlumnusApplicationSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source="program.university.name", read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True)

    class Meta:
        model = AlumnusApplication
        fields = ("id", "program", "university_name", "program_name", "outcome", "scholarship", "note")


class AlumnusSerializer(serializers.ModelSerializer):
    """Карточка выпускника.

    Контактная почта не отдаётся никому, кроме сотрудников: связь идёт
    через школу, а не напрямую.
    """

    full_name = serializers.CharField(read_only=True)
    university_name = serializers.CharField(source="university.name", read_only=True, default=None)
    program_name = serializers.CharField(source="program.name", read_only=True, default=None)
    applications = AlumnusApplicationSerializer(many=True, read_only=True)

    class Meta:
        model = Alumnus
        fields = (
            "id",
            "student",
            "full_name",
            "graduation_year",
            "university",
            "university_name",
            "program",
            "program_name",
            "country",
            "current_occupation",
            "admission_gpa",
            "admission_ielts",
            "admission_sat",
            "admission_activities",
            "mentorship_consent",
            "applications",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        role = getattr(getattr(request, "user", None), "role", "")
        if role == "student":
            # ученик видит каталог, но не служебные заметки и не контакты
            self.fields.pop("student", None)


class MentorshipMeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = MentorshipMeeting
        fields = ("id", "request", "date", "duration_minutes", "summary")


class MentorshipRequestSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    alumnus_name = serializers.CharField(source="alumnus.full_name", read_only=True)
    meetings = MentorshipMeetingSerializer(many=True, read_only=True)

    class Meta:
        model = MentorshipRequest
        fields = (
            "id",
            "student",
            "student_name",
            "alumnus",
            "alumnus_name",
            "topic",
            "message",
            "status",
            "is_visible_to_alumnus",
            "review_note",
            "created_at",
            "meetings",
        )
        read_only_fields = ("status", "is_visible_to_alumnus", "review_note", "created_at")


class CreateMentorshipSerializer(serializers.Serializer):
    alumnus = serializers.IntegerField()
    topic = serializers.CharField(max_length=250)
    message = serializers.CharField(required=False, allow_blank=True)


class ReviewMentorshipSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)


class ArchivedEssaySerializer(serializers.ModelSerializer):
    author_label = serializers.CharField(read_only=True)
    university_name = serializers.CharField(source="program.university.name", read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True)

    class Meta:
        model = ArchivedEssay
        fields = (
            "id",
            "author_label",
            "university_name",
            "program_name",
            "essay_type",
            "title",
            "text",
            "created_at",
        )
        read_only_fields = fields
