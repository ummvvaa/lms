"""Сериализаторы справочника вузов и требований."""

from __future__ import annotations

from rest_framework import serializers

from core.serializers import DomainModelSerializer
from universities.models import (
    AdmissionRequirement,
    AdmissionRound,
    Program,
    Scholarship,
    StudentUniversity,
    University,
)


class VerificationMixin(serializers.Serializer):
    """Признак «данные подтверждены» и текст плашки (инвариант №14).

    Поля только на чтение: снимает признак директор по поступлению
    отдельным действием, а не попутной правкой карточки.
    """

    verification_note = serializers.CharField(read_only=True)

    VERIFICATION_FIELDS = ("data_source", "is_verified", "verified_at", "verification_note")


class UniversitySerializer(VerificationMixin, DomainModelSerializer):
    domain_model_label = "universities.University"

    class Meta:
        model = University
        fields = (
            "id",
            "name",
            "country",
            "website",
            "domain",
            "world_rank",
            "is_active",
            *VerificationMixin.VERIFICATION_FIELDS,
        )


class AdmissionRoundSerializer(VerificationMixin, DomainModelSerializer):
    domain_model_label = "universities.AdmissionRound"
    university_name = serializers.CharField(source="program.university.name", read_only=True)

    class Meta:
        model = AdmissionRound
        fields = (
            "id",
            "program",
            "university_name",
            "round_type",
            "deadline",
            "source_url",
            "checked_at",
            *VerificationMixin.VERIFICATION_FIELDS,
        )


class AdmissionRequirementSerializer(VerificationMixin, DomainModelSerializer):
    domain_model_label = "universities.AdmissionRequirement"
    university_name = serializers.CharField(source="program.university.name", read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True)

    class Meta:
        model = AdmissionRequirement
        fields = (
            "id",
            "program",
            "university_name",
            "program_name",
            "min_gpa",
            "min_ielts",
            "min_toefl",
            "min_sat",
            "min_act",
            "required_subjects",
            "portfolio_required",
            "portfolio_note",
            "notes",
            "source_url",
            "checked_at",
            *VerificationMixin.VERIFICATION_FIELDS,
        )


class ProgramSerializer(VerificationMixin, serializers.ModelSerializer):
    university_name = serializers.CharField(source="university.name", read_only=True)
    country = serializers.CharField(source="university.country", read_only=True)
    requirement = AdmissionRequirementSerializer(read_only=True)
    rounds = AdmissionRoundSerializer(many=True, read_only=True)

    class Meta:
        model = Program
        fields = (
            "id",
            "university",
            "university_name",
            "country",
            "name",
            "level",
            "is_active",
            "requirement",
            "rounds",
            *VerificationMixin.VERIFICATION_FIELDS,
        )


class StudentUniversitySerializer(DomainModelSerializer):
    domain_model_label = "universities.StudentUniversity"
    program_name = serializers.CharField(source="program.name", read_only=True)
    university_name = serializers.CharField(source="program.university.name", read_only=True)
    country = serializers.CharField(source="program.university.country", read_only=True)
    deadline = serializers.DateField(read_only=True)

    class Meta:
        model = StudentUniversity
        fields = (
            "id",
            "student",
            "program",
            "program_name",
            "university_name",
            "country",
            "admission_round",
            "deadline",
            "tier",
            "application_status",
            "note",
            # кто положил программу в список и подтверждена ли она:
            # ученик и директор — не одно и то же
            "added_by",
            "is_confirmed",
        )
        read_only_fields = ("added_by", "is_confirmed")


class RequirementImportSerializer(serializers.Serializer):
    """Загрузка файла требований с сопоставлением колонок."""

    file = serializers.FileField()
    mapping = serializers.JSONField(required=False)
    dry_run = serializers.BooleanField(required=False, default=False)


class WhatIfSerializer(serializers.Serializer):
    """Что откроется, если поднять баллы."""

    ielts_delta = serializers.FloatField(required=False, default=0.0)
    sat_delta = serializers.IntegerField(required=False, default=0)
    gpa_delta = serializers.FloatField(required=False, default=0.0)


class ScholarshipSerializer(VerificationMixin, DomainModelSerializer):
    """Стипендия справочника (фаза 44).

    Ученику отдаётся тем же сериализатором: плашка «не подтверждено»
    приходит вместе с записью, а не подставляется экраном (инвариант №14).
    """

    domain_model_label = "universities.Scholarship"
    # ключ строки — название плюс организатор, а организатор бывает не указан:
    # без умолчания DRF делает его обязательным ради проверки уникальности
    organizer = serializers.CharField(required=False, allow_blank=True, default="")
    university_name = serializers.CharField(source="university.name", read_only=True, default="")
    level_title = serializers.CharField(source="get_level_display", read_only=True)
    funding_title = serializers.CharField(source="get_funding_type_display", read_only=True)
    basis_titles = serializers.ListField(child=serializers.CharField(), read_only=True)
    amount_title = serializers.SerializerMethodField()
    deadline_state = serializers.SerializerMethodField()
    days_left = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()

    class Meta:
        model = Scholarship
        fields = (
            "id",
            "name",
            "organizer",
            "country",
            "level",
            "level_title",
            "funding_type",
            "funding_title",
            "amount_min",
            "amount_max",
            "currency",
            "amount_title",
            "for_international",
            "for_merit",
            "for_need",
            "basis_titles",
            "deadline",
            "deadline_state",
            "days_left",
            "url",
            "requirements",
            "description",
            "university",
            "university_name",
            "is_active",
            "is_saved",
            *VerificationMixin.VERIFICATION_FIELDS,
        )

    def get_amount_title(self, obj) -> str:
        from universities.scholarships import amount_title

        return amount_title(obj)

    def get_deadline_state(self, obj) -> str:
        from universities.scholarships import deadline_state

        return deadline_state(obj.deadline)

    def get_days_left(self, obj) -> int | None:
        from django.utils import timezone

        return None if obj.deadline is None else (obj.deadline - timezone.localdate()).days

    def get_is_saved(self, obj) -> bool:
        """Сохранена ли она этим учеником — сердечко рисуется по ответу."""
        saved = self.context.get("saved_ids")
        return obj.pk in saved if saved is not None else False
