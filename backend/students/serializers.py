"""Сериализаторы учеников и пяти профилей.

Каждый профиль наследует `DomainModelSerializer`: чужие поля становятся
read-only, внутренние ярлыки не попадают в ответ роли `student`.
"""

from __future__ import annotations

from rest_framework import serializers

from core.serializers import DomainModelSerializer
from students.models import (
    Activity,
    AdmissionProfile,
    BehaviorProfile,
    Competition,
    ExamAttempt,
    ExamProfile,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)


class StudyGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyGroup
        fields = ("id", "code", "grade", "curator", "is_active")


class BehaviorProfileSerializer(DomainModelSerializer):
    domain_model_label = "students.BehaviorProfile"

    class Meta:
        model = BehaviorProfile
        fields = ("attendance_percent", "remarks_count", "homework_percent", "status", "comment")


class AdmissionProfileSerializer(DomainModelSerializer):
    domain_model_label = "students.AdmissionProfile"

    class Meta:
        model = AdmissionProfile
        fields = (
            "target_country",
            "target_major",
            "has_common_app",
            "has_application_account",
            "status",
            "comment",
        )


class ExamProfileSerializer(DomainModelSerializer):
    domain_model_label = "students.ExamProfile"

    class Meta:
        model = ExamProfile
        fields = (
            "ielts_current",
            "ielts_target",
            "sat_current",
            "sat_target",
            "hours_per_week",
            "teacher",
            "gpa",
            "next_mock_date",
        )


class TalentProfileSerializer(DomainModelSerializer):
    domain_model_label = "students.TalentProfile"

    class Meta:
        model = TalentProfile
        fields = ("main_track", "portfolio_status", "comment")


class SportProfileSerializer(DomainModelSerializer):
    domain_model_label = "students.SportProfile"

    class Meta:
        model = SportProfile
        fields = ("sport_kind", "level", "rank", "leadership_role")


class ExamAttemptSerializer(DomainModelSerializer):
    domain_model_label = "students.ExamAttempt"

    class Meta:
        model = ExamAttempt
        fields = (
            "id",
            "student",
            "exam_type",
            "attempt_format",
            "date",
            "total_score",
            "listening",
            "reading",
            "writing",
            "speaking",
            "math",
            "verbal",
        )


class ActivitySerializer(DomainModelSerializer):
    domain_model_label = "students.Activity"

    class Meta:
        model = Activity
        fields = ("id", "student", "category", "title", "date", "description", "proof_url", "is_confirmed")


class CompetitionSerializer(DomainModelSerializer):
    domain_model_label = "students.Competition"

    class Meta:
        model = Competition
        fields = ("id", "student", "name", "date", "result", "has_certificate")


class StudentSerializer(serializers.ModelSerializer):
    """Ученик со всеми пятью доменами на одной карточке.

    Инвариант №7 соблюдается вложенными сериализаторами: для роли
    `student` поля-ярлыки просто отсутствуют в ответе.
    """

    full_name = serializers.CharField(read_only=True)
    group_code = serializers.CharField(source="group.code", read_only=True, default=None)
    behavior = BehaviorProfileSerializer(read_only=True)
    admission = AdmissionProfileSerializer(read_only=True)
    exam = ExamProfileSerializer(read_only=True)
    talent = TalentProfileSerializer(read_only=True)
    sport = SportProfileSerializer(read_only=True)

    class Meta:
        model = Student
        fields = (
            "id",
            "last_name",
            "first_name",
            "middle_name",
            "full_name",
            "email",
            "grade",
            "group",
            "group_code",
            "graduation_year",
            "is_active",
            "behavior",
            "admission",
            "exam",
            "talent",
            "sport",
        )
        read_only_fields = fields


class StudentListSerializer(serializers.ModelSerializer):
    """Короткая строка для списков и таблиц."""

    full_name = serializers.CharField(read_only=True)
    group_code = serializers.CharField(source="group.code", read_only=True, default=None)

    class Meta:
        model = Student
        fields = ("id", "full_name", "email", "grade", "group", "group_code", "graduation_year")
        read_only_fields = fields
