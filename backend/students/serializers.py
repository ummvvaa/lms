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
            "source",
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


class StudyGroupSerializer(serializers.ModelSerializer):
    """Учебная группа. Ведёт администратор, домена у неё нет."""

    students_count = serializers.SerializerMethodField()

    class Meta:
        model = StudyGroup
        fields = ("id", "code", "grade", "curator", "is_active", "students_count")
        # уникальность кода проверяем сами: обычный менеджер не видит
        # архивные группы, и валидатор DRF пропускал бы дубль до 500-й
        extra_kwargs = {"code": {"validators": []}}

    def get_students_count(self, obj) -> int:
        return obj.students.count()

    def validate_code(self, value: str) -> str:
        value = value.strip()
        query = StudyGroup.all_objects.filter(code__iexact=value)
        if self.instance is not None:
            query = query.exclude(pk=self.instance.pk)
        existing = query.first()
        if existing is None:
            return value
        raise serializers.ValidationError(
            f"Группа «{existing.code}» лежит в архиве — верните её оттуда"
            if existing.is_archived
            else f"Группа «{existing.code}» уже заведена"
        )


class StudentWriteSerializer(serializers.ModelSerializer):
    """Заведение и правка реестровой карточки ученика.

    Доменных полей здесь нет: их ведут директора у себя. Это только
    то, что заводит администратор — кто это, в каком классе и группе.
    """

    class Meta:
        model = Student
        fields = ("id", "last_name", "first_name", "middle_name", "email", "grade", "group", "graduation_year")

    def validate_email(self, value: str) -> str:
        # архивного ученика обычный менеджер не видит, а уникальность
        # почты в базе никуда не делась — иначе получаем 500 на сохранении
        value = value.strip().lower()
        query = Student.all_objects.filter(email__iexact=value)
        if self.instance is not None:
            query = query.exclude(pk=self.instance.pk)
        existing = query.first()
        if existing is not None:
            where = "в архиве" if existing.is_archived else "в списке"
            raise serializers.ValidationError(
                f"Ученик с такой почтой уже есть {where}: {existing.full_name}. "
                "Возьмите другую почту или верните запись из архива."
            )
        return value


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
    """Строка для списков и табличного режима.

    Профили пяти доменов идут вместе со строкой: без них табличный режим
    рисовал все ячейки пустыми, а сохранение уходило с `expected: ""`
    и молча превращалось в конфликт (`docs/DEFECTS.md`, B5).

    Ярлыки чужих доменов режет `DomainModelSerializer`, ученику они
    не отдаются вовсе (инвариант №7).
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
            "full_name",
            "email",
            "grade",
            "group",
            "group_code",
            "graduation_year",
            "behavior",
            "admission",
            "exam",
            "talent",
            "sport",
        )
        read_only_fields = fields


class ReadinessSerializer(serializers.Serializer):
    """Readiness Score — вычисляемое поле, в базе не хранится."""

    score = serializers.IntegerField(read_only=True)
    parts = serializers.ListField(read_only=True)
    weakest = serializers.CharField(read_only=True, allow_null=True)
    weakest_title = serializers.CharField(read_only=True, allow_null=True)


class BatchChangeSerializer(serializers.Serializer):
    """Одна ячейка из табличного режима."""

    student = serializers.IntegerField()
    model = serializers.CharField()
    field = serializers.CharField()
    value = serializers.JSONField(allow_null=True)
    expected = serializers.JSONField(required=False, allow_null=True)


class BatchSaveSerializer(serializers.Serializer):
    """Пакет изменений: копится в черновике на фронте, уходит одним запросом."""

    changes = BatchChangeSerializer(many=True)


class AuditEntrySerializer(serializers.Serializer):
    """Строка истории изменений на карточке ученика."""

    id = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    model_label = serializers.CharField(read_only=True)
    field_name = serializers.CharField(read_only=True)
    domain_code = serializers.CharField(read_only=True)
    old_value = serializers.CharField(read_only=True)
    new_value = serializers.CharField(read_only=True)
    source = serializers.CharField(read_only=True)
    actor_name = serializers.SerializerMethodField()

    def get_actor_name(self, obj) -> str:
        return obj.actor.full_name or obj.actor.email if obj.actor_id else "система"


class ImportPreviewRequestSerializer(serializers.Serializer):
    """Загрузка файла и сопоставление колонок."""

    file = serializers.FileField()
    mapping = serializers.JSONField(required=False)


class ImportApplySerializer(serializers.Serializer):
    rows = serializers.ListField(child=serializers.JSONField())
    #: имя файла нужно истории загрузок: «отменить импорт» без него
    #: превращается в выбор из одинаковых безымянных строк
    file_name = serializers.CharField(required=False, allow_blank=True, max_length=250)
