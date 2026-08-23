"""API учеников и профилей.

Читают все сотрудники, ученик — только себя. Пишет директор и только
в поля своего домена: проверка идёт по реестру `core.domains`.
"""

from __future__ import annotations

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, parser_classes, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.deletion import ArchiveDeleteMixin, refuse
from core.domains import ROLE_ADMIN, ROLE_STUDENT, owns_model
from core.models import AuditLog
from core.permissions import DomainFieldPermission, IsOwnStudentOrStaff
from core.readiness import compute as compute_readiness
from students.batch import apply_batch
from students.linking import link_student
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
from students.serializers import (
    ActivitySerializer,
    AdmissionProfileSerializer,
    AuditEntrySerializer,
    BatchSaveSerializer,
    BehaviorProfileSerializer,
    CompetitionSerializer,
    ExamAttemptSerializer,
    ExamProfileSerializer,
    ImportApplySerializer,
    ImportPreviewRequestSerializer,
    SportProfileSerializer,
    StudentListSerializer,
    StudentSerializer,
    StudentWriteSerializer,
    StudyGroupSerializer,
    TalentProfileSerializer,
)


class StudentFilter(filters.FilterSet):
    """Фильтры списка: группа, класс, год выпуска, статусы доменов."""

    group = filters.CharFilter(field_name="group__code", lookup_expr="iexact")
    grade = filters.NumberFilter(field_name="grade")
    graduation_year = filters.NumberFilter(field_name="graduation_year")
    behavior_status = filters.CharFilter(field_name="behavior__status")
    admission_status = filters.CharFilter(field_name="admission__status")
    portfolio_status = filters.CharFilter(field_name="talent__portfolio_status")
    main_track = filters.CharFilter(field_name="talent__main_track")
    has_common_app = filters.BooleanFilter(field_name="admission__has_common_app")
    ielts_min = filters.NumberFilter(field_name="exam__ielts_current", lookup_expr="gte")
    ielts_max = filters.NumberFilter(field_name="exam__ielts_current", lookup_expr="lt")
    sat_min = filters.NumberFilter(field_name="exam__sat_current", lookup_expr="gte")
    sat_max = filters.NumberFilter(field_name="exam__sat_current", lookup_expr="lt")

    class Meta:
        model = Student
        fields = ("group", "grade", "graduation_year", "is_active")


class StudentViewSet(
    ArchiveDeleteMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Ученики: список, карточка, заведение и удаление в архив.

    Доменные поля правятся через профили — здесь только реестровая часть,
    которую ведёт администратор: кто это, класс, группа, год выпуска.
    Ученика целиком заводит и сносит только администратор (инвариант №13).
    """

    queryset = (
        Student.objects.select_related("group", "behavior", "admission", "exam", "talent", "sport")
        .all()
        .order_by("last_name", "first_name", "id")
    )
    permission_classes = [IsOwnStudentOrStaff]
    filterset_class = StudentFilter
    search_fields = ("last_name", "first_name", "email")
    ordering_fields = ("last_name", "grade", "graduation_year")

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return StudentWriteSerializer
        return StudentListSerializer if self.action == "list" else StudentSerializer

    def create(self, request, *args, **kwargs):
        """Завести карточку ученика. Пять профилей создаются сразу пустыми."""
        if request.user.role != ROLE_ADMIN:
            return Response({"detail": "Учеников заводит администратор"}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if request.user.role != ROLE_ADMIN:
            return Response(
                {"detail": "Реестровую карточку ведёт администратор, доменные поля правятся у себя"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        student = serializer.save()
        # без пустых профилей карточка открывается наполовину, а таблица
        # рисует пустые ячейки и сохраняет с пустым `expected`
        for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
            model.objects.get_or_create(student=student)
        # учётная запись с той же почтой — это тот же человек: связываем
        # сразу, иначе ученик войдёт в пустой кабинет и не поймёт, почему
        link_student(student)

    def perform_update(self, serializer):
        link_student(serializer.save())

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == ROLE_STUDENT:
            # ученик видит только себя (инвариант №7 и разграничение доступа)
            student = getattr(user, "student", None)
            return qs.filter(pk=student.pk) if student else qs.none()
        return qs

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        """Кабинет ученика: своя карточка без внутренних ярлыков."""
        student = getattr(request.user, "student", None)
        if student is None:
            raise NotFound("У этого пользователя нет карточки ученика")
        data = self.get_serializer(student).data
        data["readiness"] = compute_readiness(student).as_dict()
        return Response(data)

    @action(detail=True, methods=["get"])
    def readiness(self, request, pk=None):
        """Готовность одного ученика — вычисляется, не хранится."""
        return Response(compute_readiness(self.get_object()).as_dict())

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Вкладка истории изменений на карточке ученика."""
        student = self.get_object()
        if request.user.role == ROLE_STUDENT:
            return Response({"detail": "История доступна сотрудникам"}, status=status.HTTP_403_FORBIDDEN)
        entries = AuditLog.objects.filter(student_id=student.pk).select_related("actor")[:200]
        return Response(AuditEntrySerializer(entries, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        """Карточка ученика: пять доменов плюс готовность."""
        student = self.get_object()
        data = self.get_serializer(student).data
        data["readiness"] = compute_readiness(student).as_dict()
        return Response(data)


class BaseProfileViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Профиль одного домена. Ключ — id ученика, а не id профиля."""

    permission_classes = [DomainFieldPermission, IsOwnStudentOrStaff]
    lookup_field = "student_id"
    lookup_url_kwarg = "student_id"
    domain_model_label = ""

    def get_queryset(self):
        qs = self.queryset.select_related("student")
        user = self.request.user
        if user.role == ROLE_STUDENT:
            student = getattr(user, "student", None)
            return qs.filter(student=student) if student else qs.none()
        return qs


class BehaviorProfileViewSet(BaseProfileViewSet):
    queryset = BehaviorProfile.objects.all()
    serializer_class = BehaviorProfileSerializer
    domain_model_label = "students.BehaviorProfile"


class AdmissionProfileViewSet(BaseProfileViewSet):
    queryset = AdmissionProfile.objects.all()
    serializer_class = AdmissionProfileSerializer
    domain_model_label = "students.AdmissionProfile"


class ExamProfileViewSet(BaseProfileViewSet):
    queryset = ExamProfile.objects.all()
    serializer_class = ExamProfileSerializer
    domain_model_label = "students.ExamProfile"


class TalentProfileViewSet(BaseProfileViewSet):
    queryset = TalentProfile.objects.all()
    serializer_class = TalentProfileSerializer
    domain_model_label = "students.TalentProfile"


class SportProfileViewSet(BaseProfileViewSet):
    queryset = SportProfile.objects.all()
    serializer_class = SportProfileSerializer
    domain_model_label = "students.SportProfile"


@extend_schema(request=BatchSaveSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def batch_save(request):
    """Массовое сохранение из табличного режима.

    Валидирует домен по реестру, применяет одной транзакцией, пишет аудит.
    Строки чужого домена возвращаются в `rejected`, а не роняют весь запрос.
    """
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Ученик не редактирует данные"}, status=status.HTTP_403_FORBIDDEN)

    serializer = BatchSaveSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = apply_batch(
        changes=serializer.validated_data["changes"],
        role=request.user.role,
        actor=request.user,
    )
    return Response(result.as_dict())


@extend_schema(request=ImportPreviewRequestSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def import_preview(request):
    """Предпросмотр импорта: сопоставление колонок и отчёт о конфликтах."""
    import json

    from students.import_service import build_preview, read_table

    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Импорт доступен сотрудникам"}, status=status.HTTP_403_FORBIDDEN)

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)

    header, rows = read_table(uploaded)
    raw_mapping = request.data.get("mapping") or "{}"
    mapping = json.loads(raw_mapping) if isinstance(raw_mapping, str) else raw_mapping

    if not mapping:
        # первый шаг: показываем колонки файла, чтобы директор их сопоставил
        return Response({"columns": header, "total_rows": len(rows), "rows": [], "matched": 0, "unmatched": []})

    preview = build_preview(header=header, rows=rows, mapping=mapping, role=request.user.role)
    return Response(preview.as_dict())


@extend_schema(request=ImportApplySerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_apply(request):
    """Применение предпросмотренного импорта."""
    from students.import_service import apply_preview

    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Импорт доступен сотрудникам"}, status=status.HTTP_403_FORBIDDEN)

    serializer = ImportApplySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = apply_preview(
        preview_rows=serializer.validated_data["rows"],
        role=request.user.role,
        actor=request.user,
        file_name=serializer.validated_data.get("file_name", ""),
    )
    return Response(result)


class StudentScopedViewSet(ArchiveDeleteMixin, viewsets.ModelViewSet):
    """Дочерняя таблица ученика: строки заводит и убирает владелец домена.

    Ученик такие записи только читает и только свои. Право на удаление
    берётся из реестра доменов — проверяет его `ArchiveDeleteMixin`.
    """

    permission_classes = [DomainFieldPermission, IsOwnStudentOrStaff]
    domain_model_label = ""

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == ROLE_STUDENT:
            student = getattr(user, "student", None)
            return qs.filter(student=student) if student else qs.none()
        return qs

    def create(self, request, *args, **kwargs):
        # заводить строки в чужой таблице нельзя: без этой проверки чужой
        # директор создавал бы пустую запись — все поля у него read_only
        if not owns_model(request.user.role, self.domain_model_label):
            return refuse(request.user.role, self.domain_model_label)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Ученика ставим отдельно.

        В реестре доменов поля `student` нет и быть не должно — это не
        доменное поле, а ссылка на владельца строки. Сериализатор его
        поэтому держит только на чтение, и без этой строки запись
        сохранялась бы без ученика.
        """
        student = Student.objects.filter(pk=self.request.data.get("student")).first()
        if student is None:
            raise ValidationError({"student": "Не указан ученик или его нет в списке"})
        serializer.save(student=student)


class ExamAttemptViewSet(StudentScopedViewSet):
    """История попыток экзаменов — из неё строится график динамики.

    Инвариант №5: попытки лежат строками, а не полем профиля. Платформенные
    моки видно по источнику `platform` — на графике они отмечены отдельно.
    """

    queryset = ExamAttempt.objects.select_related("student").all().order_by("date")
    serializer_class = ExamAttemptSerializer
    domain_model_label = "students.ExamAttempt"
    filterset_fields = ("student", "exam_type", "attempt_format", "source")
    ordering_fields = ("date",)


class ActivityViewSet(StudentScopedViewSet):
    """Активности портфолио. Ведёт директор талантов (инвариант №5)."""

    queryset = Activity.objects.select_related("student").all()
    serializer_class = ActivitySerializer
    domain_model_label = "students.Activity"
    filterset_fields = ("student", "category", "is_confirmed")
    search_fields = ("title", "description")


class CompetitionViewSet(StudentScopedViewSet):
    """Соревнования. Ведёт директор спорта (инвариант №5)."""

    queryset = Competition.objects.select_related("student").all()
    serializer_class = CompetitionSerializer
    domain_model_label = "students.Competition"
    filterset_fields = ("student", "has_certificate")
    search_fields = ("name", "result")


class StudyGroupViewSet(ArchiveDeleteMixin, viewsets.ModelViewSet):
    """Учебные группы. Реестр школы — ведёт администратор."""

    queryset = StudyGroup.objects.all()
    serializer_class = StudyGroupSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("grade", "is_active")
    search_fields = ("code", "curator")

    def _staff_only(self, request):
        return request.user.role != ROLE_ADMIN

    def create(self, request, *args, **kwargs):
        if self._staff_only(request):
            return Response({"detail": "Группы заводит администратор"}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if self._staff_only(request):
            return Response({"detail": "Группы ведёт администратор"}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)
