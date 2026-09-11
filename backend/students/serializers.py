"""Сериализаторы учеников и пяти профилей.

Каждый профиль наследует `DomainModelSerializer`: чужие поля становятся
read-only, внутренние ярлыки не попадают в ответ роли `student`.
"""

from __future__ import annotations

from rest_framework import serializers

from core.domains import Source
from core.labels import acting_for_phrase, field_short, field_title, model_title, value_title
from core.serializers import DomainModelSerializer
from students.models import (
    Activity,
    AdmissionProfile,
    AttemptFormat,
    BehaviorProfile,
    Competition,
    ExamAttempt,
    ExamGoal,
    ExamProfile,
    ParentContact,
    SportProfile,
    Student,
    StudentDocument,
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
            "cost_priority",
            "target_level",
            "has_common_app",
            "has_application_account",
            "status",
            "student_phone",
            "common_app_email",
            "drive_folder_url",
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

    #: название вида спорта рядом со ссылкой: без него в таблице
    #: и в карточке пришлось бы показывать номер записи справочника
    sport_type_name = serializers.CharField(source="sport_type.name", read_only=True, default="")

    class Meta:
        model = SportProfile
        fields = ("sport_type", "sport_type_name", "level", "rank", "leadership_role")


class ExamAttemptSerializer(DomainModelSerializer):
    domain_model_label = "students.ExamAttempt"

    #: откуда результат: у пробника из файла — загрузка с датой и учителем
    mock_import = serializers.IntegerField(source="mock_import_id", read_only=True)
    mock_teacher = serializers.CharField(source="mock_import.teacher", read_only=True, default="")
    is_mock = serializers.SerializerMethodField()
    #: дата не указана в источнике (фаза 65): ставит импорт, снимает
    #: подтверждённая настоящая дата; руками флаг не выставляется
    date_unknown = serializers.BooleanField(read_only=True)

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
            "mock_import",
            "mock_teacher",
            "is_mock",
            "date_unknown",
        )

    def get_is_mock(self, row) -> bool:
        return row.attempt_format == AttemptFormat.MOCK

    def validate(self, attrs):
        """Балл и секции — по шкале экзамена из реестра (D4).

        Ручка попытки идёт мимо `apply_changes`, поэтому границы
        проверяются здесь: ответ 400 с шкалой словами, а не 500.
        """
        from core.domains import SECTION_FIELDS, scale_of

        row = self.instance
        exam_type = attrs.get("exam_type", getattr(row, "exam_type", ""))
        problems = {}
        for name, value in attrs.items():
            if value is None or name not in {"total_score", *SECTION_FIELDS}:
                continue
            scale = scale_of(exam_type, section=name in SECTION_FIELDS)
            if scale is not None and not scale.holds(value):
                problems[name] = f"Шкала {exam_type} — {scale.hint}"
        if problems:
            raise serializers.ValidationError(problems)
        return attrs


class ActivitySerializer(DomainModelSerializer):
    domain_model_label = "students.Activity"

    subject_name = serializers.CharField(source="subject.name", read_only=True, default="")

    class Meta:
        model = Activity
        fields = (
            "id",
            "student",
            "category",
            "subject",
            "subject_name",
            "title",
            "date",
            "description",
            "proof_url",
            "is_confirmed",
        )


class CompetitionSerializer(DomainModelSerializer):
    domain_model_label = "students.Competition"

    sport_type_name = serializers.CharField(source="sport_type.name", read_only=True, default="")
    level_title = serializers.CharField(source="get_level_display", read_only=True, default="")
    student_name = serializers.CharField(source="student.full_name", read_only=True, default="")

    class Meta:
        model = Competition
        fields = (
            "id",
            "student",
            "student_name",
            "name",
            "sport_type",
            "sport_type_name",
            "level",
            "level_title",
            "date",
            "result",
            "has_certificate",
            "proof_url",
        )


class ParentContactSerializer(DomainModelSerializer):
    """Контакт родителя. Ведёт домен `behavior` — директор школы."""

    domain_model_label = "students.ParentContact"

    #: имя ученика рядом со строкой: отдельный список контактов без него
    #: превращается в перечень телефонов без хозяев
    student_name = serializers.CharField(source="student.full_name", read_only=True, default="")
    relation_title = serializers.CharField(source="get_relation_display", read_only=True, default="")
    channel_title = serializers.CharField(source="get_preferred_channel_display", read_only=True, default="")

    class Meta:
        model = ParentContact
        fields = (
            "id",
            "student",
            "student_name",
            "full_name",
            "relation",
            "relation_title",
            "phone",
            "email",
            "preferred_channel",
            "channel_title",
            "note",
            "is_primary",
        )

    def validate(self, attrs):
        """Без телефона и почты контакт бесполезен: связаться по нему нечем."""
        phone = attrs.get("phone", getattr(self.instance, "phone", "") or "")
        email = attrs.get("email", getattr(self.instance, "email", "") or "")
        if not str(phone).strip() and not str(email).strip():
            raise serializers.ValidationError(
                {"phone": "Укажите телефон или почту — иначе связаться по этому контакту нечем"}
            )
        return attrs


class StudyGroupSerializer(serializers.ModelSerializer):
    """Учебная группа. Ведёт администратор, домена у неё нет.

    Куратор группы — действующее назначение (`curator_user`), а не текст:
    текстовое поле удалено в фазе 61.
    """

    students_count = serializers.SerializerMethodField()
    curator_user = serializers.SerializerMethodField()

    class Meta:
        model = StudyGroup
        fields = ("id", "code", "grade", "curator_user", "is_active", "students_count")
        # уникальность кода проверяем сами: обычный менеджер не видит
        # архивные группы, и валидатор DRF пропускал бы дубль до 500-й
        extra_kwargs = {"code": {"validators": []}}

    def get_students_count(self, obj) -> int:
        return obj.students.count()

    def get_curator_user(self, obj) -> dict | None:
        from accounts.curators import curator_of

        row = curator_of(obj)
        if row is None:
            return None
        return {
            "id": row.curator_id,
            "full_name": row.curator.full_name or row.curator.email,
            "since": row.since,
        }

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
            "in_olympiad_group",
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
            "in_olympiad_group",
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
    """Строка истории изменений на карточке ученика.

    Технического имени колонки в ответе нет: подпись поля и подписи
    значений считает сервер по реестру доменов (фаза 17).
    """

    id = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    model_label = serializers.CharField(read_only=True)
    model_title = serializers.SerializerMethodField()
    domain_code = serializers.CharField(read_only=True)
    field_title = serializers.SerializerMethodField()
    field_short = serializers.SerializerMethodField()
    old_display = serializers.SerializerMethodField()
    new_display = serializers.SerializerMethodField()
    source = serializers.CharField(read_only=True)
    source_title = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()
    #: роль автора и группа ученика на момент действия (фаза 60): роль
    #: у человека сменится, ученика переведут — а история должна читаться
    #: как тогда. У записей до фазы 60 снимка нет, и подпись пустая
    actor_role_title = serializers.SerializerMethodField()
    student_group = serializers.CharField(read_only=True)
    #: за какой домен действовал автор, если не за свой: администратор
    #: при загрузке файла или вставке текста (фаза 35). Пусто у правок
    #: владельца домена. Подпись — готовой фразой: «за домен «Экзамены»»
    acting_for = serializers.CharField(read_only=True)
    acting_for_title = serializers.SerializerMethodField()

    def get_actor_role_title(self, obj) -> str:
        from core.domains import ROLE_TITLES

        return ROLE_TITLES.get(obj.actor_role, "")

    def get_acting_for_title(self, obj) -> str:
        return acting_for_phrase(obj.acting_for)

    def get_model_title(self, obj) -> str:
        return model_title(obj.model_label)

    def get_field_title(self, obj) -> str:
        return field_title(obj.model_label, obj.field_name)

    def get_field_short(self, obj) -> str:
        return field_short(obj.model_label, obj.field_name)

    def get_old_display(self, obj) -> str:
        return value_title(obj.model_label, obj.field_name, obj.old_value)

    def get_new_display(self, obj) -> str:
        return value_title(obj.model_label, obj.field_name, obj.new_value)

    def get_source_title(self, obj) -> str:
        return dict(Source.CHOICES).get(obj.source, obj.source)

    def get_actor_name(self, obj) -> str:
        if obj.actor_id:
            return obj.actor.full_name or obj.actor.email
        # автора уже нет (одноразовая запись прогона убрана) — подпись-снимок
        return obj.actor_title or "система"


class ImportPreviewRequestSerializer(serializers.Serializer):
    """Загрузка файла и сопоставление колонок."""

    file = serializers.FileField()
    mapping = serializers.JSONField(required=False)
    #: домен, за который администратор грузит файл (фаза 35)
    domain = serializers.CharField(required=False, allow_blank=True, max_length=32)


class EnrollmentApplySerializer(serializers.Serializer):
    """Строки заведения учеников: их отдаёт экран после предпросмотра."""

    rows = serializers.ListField(child=serializers.DictField(), allow_empty=False, max_length=500)


class AttemptBulkSerializer(serializers.Serializer):
    """Строки массового ввода результатов: их отдаёт таблица на экране."""

    rows = serializers.ListField(child=serializers.DictField(), allow_empty=False, max_length=500)


class ImportApplySerializer(serializers.Serializer):
    rows = serializers.ListField(child=serializers.JSONField())
    #: домен, за который идёт загрузка: проверяется во вьюхе по реестру
    domain = serializers.CharField(required=False, allow_blank=True, max_length=32)
    #: имя файла нужно истории загрузок: «отменить импорт» без него
    #: превращается в выбор из одинаковых безымянных строк
    file_name = serializers.CharField(required=False, allow_blank=True, max_length=250)


class StudentDocumentSerializer(serializers.ModelSerializer):
    """Документ портфолио: метаданные без прямой ссылки на файл.

    Ссылки на файл в ответе нет намеренно — он отдаётся только через
    `/api/documents/<id>/file/` с проверкой прав (фаза 38).
    """

    doc_type_title = serializers.CharField(source="get_doc_type_display", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    #: проверка (фаза 62): статус и причину ученик видит, имени проверившего
    #: в ответе нет — ни здесь, ни в чек-листе портфолио
    status_title = serializers.CharField(source="get_status_display", read_only=True)
    state = serializers.CharField(read_only=True)
    needs_expiry = serializers.SerializerMethodField()
    #: документ-ссылка (фаза 65): адрес виден тем же, кому виден документ;
    #: заводит его импорт таблицы Асем, руками ссылка не заводится
    is_link = serializers.BooleanField(read_only=True)
    external_url = serializers.URLField(read_only=True)

    class Meta:
        model = StudentDocument
        fields = (
            "id",
            "student",
            "student_name",
            "doc_type",
            "doc_type_title",
            "title",
            "content_type",
            "size",
            "issued_date",
            "expires_at",
            "needs_expiry",
            "note",
            "status",
            "status_title",
            "state",
            "reject_reason",
            "created_at",
            "is_link",
            "external_url",
        )
        read_only_fields = (
            "id",
            "student",
            "student_name",
            "content_type",
            "size",
            "status",
            "status_title",
            "state",
            "reject_reason",
            "created_at",
            "is_link",
            "external_url",
        )

    def get_needs_expiry(self, obj) -> bool:
        from students.models import EXPIRING_TYPES

        return obj.doc_type in EXPIRING_TYPES

    def validate(self, attrs):
        """Срок действия — только у паспорта и сертификатов, и только вперёд."""
        from django.utils import timezone

        from students.models import EXPIRING_TYPES

        doc_type = attrs.get("doc_type")
        expires = attrs.get("expires_at")
        if doc_type and doc_type not in EXPIRING_TYPES and expires:
            raise serializers.ValidationError({"expires_at": "У этого типа документа срока действия нет"})
        if expires and expires < timezone.localdate():
            raise serializers.ValidationError({"expires_at": "Срок действия уже прошёл — такой документ не примут"})
        return attrs


class ExamGoalSerializer(DomainModelSerializer):
    """Цель по экзамену: ставит ученик предложением, ведёт домен `exam`."""

    domain_model_label = "students.ExamGoal"

    exam_name = serializers.CharField(source="exam.name", read_only=True, default="")
    student_name = serializers.CharField(source="student.full_name", read_only=True, default="")

    class Meta:
        model = ExamGoal
        fields = (
            "id",
            "student",
            "student_name",
            "exam",
            "exam_name",
            "target_score",
            "exam_date",
            "registration_date",
            "note",
        )
