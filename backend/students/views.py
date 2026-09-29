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
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.deletion import ArchiveDeleteMixin, refuse
from core.domains import ROLE_ADMIN, ROLE_CURATOR, ROLE_STUDENT, domain_of_role, owns_model
from core.models import AuditLog
from core.parallels import (
    ADMISSION_ONLY,
    JUNIOR_ACTIVITY_CATEGORY,
    JUNIOR_DOCUMENT_TYPE,
    admission_students,
    document_open,
    domain_parallels,
    has_admission,
    in_parallel,
)
from core.permissions import DomainFieldPermission, IsOwnStudentOrStaff
from core.readiness import compute as compute_readiness
from core.scope import scope_to_user, sees_student
from students.batch import apply_batch
from students.linking import link_student
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
from students.serializers import (
    ActivitySerializer,
    AdmissionProfileSerializer,
    AttemptBulkSerializer,
    AuditEntrySerializer,
    BatchSaveSerializer,
    BehaviorProfileSerializer,
    CompetitionSerializer,
    EnrollmentApplySerializer,
    ExamAttemptSerializer,
    ExamGoalSerializer,
    ExamProfileSerializer,
    ImportApplySerializer,
    ImportPreviewRequestSerializer,
    ParentContactSerializer,
    SportProfileSerializer,
    StudentDocumentSerializer,
    StudentListSerializer,
    StudentSerializer,
    StudentWriteSerializer,
    StudyGroupSerializer,
    TalentProfileSerializer,
)


class StudentFilter(filters.FilterSet):
    """Фильтры списка: группа, параллель группы, год выпуска, статусы доменов.

    Параллель — фильтр списков сотрудников (`core.parallels`); у ученика
    её не выбирают и не вводят.
    """

    group = filters.CharFilter(field_name="group__code", lookup_expr="iexact")
    parallel = filters.NumberFilter(method="filter_parallel")
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
        fields = ("group", "graduation_year", "is_active")

    def filter_parallel(self, queryset, name, value):
        return in_parallel(queryset, value)


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
    которую ведёт администратор: кто это, группа, год выпуска.
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
    ordering_fields = ("last_name", "graduation_year")

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
        # ученик видит только себя (инвариант №7), куратор — свои группы
        # (фаза 60); чужой ученик отсюда не выходит вовсе — дальше 404
        rows = scope_to_user(super().get_queryset(), self.request.user, path="")
        own = domain_of_role(self.request.user.role)
        if self.action == "list" and own is not None and domain_parallels(own.code) == ADMISSION_ONLY:
            # таблица домена, который ведётся только у 11 (экзамены Кымбат):
            # 8–10 в ней нет; карточку ученика она открывает — там учёба
            rows = admission_students(rows)
        return rows

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        """Кабинет ученика: своя карточка без внутренних ярлыков."""
        student = getattr(request.user, "student", None)
        if student is None:
            raise NotFound("У этого пользователя нет карточки ученика")
        data = self.get_serializer(student).data
        if not has_admission(student):
            # у 8–10 нет поступления: ни профилей поступления и экзаменов,
            # ни процента готовности — в ответе их нет и пустыми
            for key in ("admission", "exam", "admission_block"):
                data.pop(key, None)
            data["readiness"] = None
            return Response(data)
        data["readiness"] = compute_readiness(student).as_dict()
        return Response(data)

    @action(detail=True, methods=["get"])
    def readiness(self, request, pk=None):
        """Готовность одного ученика — вычисляется, не хранится. У 8–10 её нет."""
        student = self.get_object()
        if not has_admission(student):
            raise NotFound("Готовность к подаче считается только у 11 параллели")
        return Response(compute_readiness(student).as_dict())

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
        if not has_admission(student):
            # у 8–10 нет поступления: ни профилей поступления и экзаменов,
            # ни процента готовности — в ответе их нет и пустыми
            for key in ("admission", "exam", "admission_block"):
                data.pop(key, None)
            data["readiness"] = None
            return Response(data)
        data["readiness"] = compute_readiness(student).as_dict()
        return Response(data)


class BaseProfileViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Профиль одного домена. Ключ — id ученика, а не id профиля."""

    permission_classes = [DomainFieldPermission, IsOwnStudentOrStaff]
    lookup_field = "student_id"
    lookup_url_kwarg = "student_id"
    domain_model_label = ""

    def get_queryset(self):
        return scope_to_user(self.queryset.select_related("student"), self.request.user)


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


#: Отказ директору на любую загрузку файла. Текст объясняет, куда идти,
#: а не только «нельзя»: первое, что сделает человек без кнопки, —
#: напишет, что она пропала.
FILES_ARE_ADMINS = "Файлы загружает администратор. Данные вносятся руками в таблице " "или вставкой текста в помощнике"


def _deny_file_upload(request):
    """403 всем, кроме тех, кому реестр разрешает грузить файлы (фаза 35)."""
    from core.domains import can_upload_files

    if not can_upload_files(request.user.role):
        return Response({"detail": FILES_ARE_ADMINS}, status=status.HTTP_403_FORBIDDEN)
    return None


def _chosen_domain(request):
    """Домен, за который администратор грузит файл. Без него загрузки нет.

    Возвращает `(код домена, None)` либо `(None, ответ 400)`.
    """
    from core.domains import DOMAINS

    code = str(request.data.get("domain") or "").strip()
    if code in DOMAINS:
        return code, None
    titles = ", ".join(f"«{d.title}»" for d in DOMAINS.values())
    return None, Response(
        {"detail": f"Сначала выберите домен, чьи данные в файле: {titles}"},
        status=status.HTTP_400_BAD_REQUEST,
    )


@extend_schema(request=ImportPreviewRequestSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def import_preview(request):
    """Предпросмотр импорта: сопоставление колонок и отчёт о конфликтах.

    Только администратор, и только за выбранный домен: чужие для этого
    домена колонки отсекает `build_preview`, а не интерфейс.
    """
    import json

    from students.import_service import build_preview, read_table

    denied = _deny_file_upload(request)
    if denied:
        return denied
    domain_code, problem = _chosen_domain(request)
    if problem:
        return problem

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)

    header, rows = read_table(uploaded)
    raw_mapping = request.data.get("mapping") or "{}"
    mapping = json.loads(raw_mapping) if isinstance(raw_mapping, str) else raw_mapping

    if not mapping:
        # первый шаг: читаем файл и объясняем словами, что будет загружено.
        # Сопоставление — предложение: человек переназначает любую колонку
        from students.import_reading import read

        reading = read(header=header, rows=rows, domain_code=domain_code, actor=request.user)
        return Response(
            {
                "columns": header,
                "total_rows": len(rows),
                "rows": [],
                "matched": reading.matched,
                "unmatched": [],
                "reading": reading.as_dict(),
            }
        )

    preview = build_preview(header=header, rows=rows, mapping=mapping, domain_code=domain_code)
    payload = preview.as_dict()
    # объяснение пересобираем и на втором шаге: сопоставление могло
    # измениться руками, и текст обязан говорить о нём, а не о прежнем
    from students.import_reading import read

    payload["reading"] = read(
        header=header, rows=rows, domain_code=domain_code, actor=request.user, mapping=mapping
    ).as_dict()
    return Response(payload)


@extend_schema(request=ImportPreviewRequestSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def enrollment_preview(request):
    """Предпросмотр заведения учеников списком: что создастся, что нет."""
    from students.enrollment import build_preview
    from students.import_service import read_table

    if request.user.role != ROLE_ADMIN:
        return Response({"detail": "Учётные записи заводит администратор"}, status=status.HTTP_403_FORBIDDEN)

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)

    header, rows = read_table(uploaded)
    return Response(build_preview(header=header, rows=rows).as_dict())


@extend_schema(request=EnrollmentApplySerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def enrollment_apply(request):
    """Завести учеников из проверенных строк — карточка, запись, пароль."""
    from students.enrollment import enroll

    if request.user.role != ROLE_ADMIN:
        return Response({"detail": "Учётные записи заводит администратор"}, status=status.HTTP_403_FORBIDDEN)

    payload = EnrollmentApplySerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    return Response(enroll(rows=payload.validated_data["rows"], actor=request.user))


@extend_schema(request=ImportPreviewRequestSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def contacts_preview(request):
    """Предпросмотр загрузки контактов родителей: что заведётся, что нет.

    Контакты ведёт директор школы, но файл с ними грузит администратор —
    за домен «Профиль и дисциплина» (фаза 35).
    """
    from students.contacts_import import build_preview
    from students.import_service import read_table

    denied = _deny_file_upload(request)
    if denied:
        return denied

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)

    header, rows = read_table(uploaded)
    return Response(build_preview(header=header, rows=rows).as_dict())


@extend_schema(request=EnrollmentApplySerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def contacts_apply(request):
    """Завести контакты из проверенных строк предпросмотра."""
    from students.contacts_import import apply_rows

    denied = _deny_file_upload(request)
    if denied:
        return denied

    payload = EnrollmentApplySerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    return Response(
        apply_rows(
            rows=payload.validated_data["rows"],
            actor=request.user,
            file_name=str(request.data.get("file_name", ""))[:250],
        )
    )


@extend_schema(request=ImportPreviewRequestSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def competitions_preview(request):
    """Предпросмотр загрузки соревнований: что заведётся, что уже есть.

    Выступления ведёт директор спорта, файл грузит администратор за домен
    «Спорт» (фаза 35).
    """
    from students.competitions_import import build_preview
    from students.import_service import read_table

    denied = _deny_file_upload(request)
    if denied:
        return denied

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)

    header, rows = read_table(uploaded)
    return Response(build_preview(header=header, rows=rows).as_dict())


@extend_schema(request=EnrollmentApplySerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def competitions_apply(request):
    """Завести выступления из проверенных строк предпросмотра."""
    from students.competitions_import import apply_rows

    denied = _deny_file_upload(request)
    if denied:
        return denied

    payload = EnrollmentApplySerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    return Response(
        apply_rows(
            rows=payload.validated_data["rows"],
            actor=request.user,
            file_name=str(request.data.get("file_name", ""))[:250],
        )
    )


@extend_schema(request=ImportApplySerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_apply(request):
    """Применение предпросмотренного импорта — администратором, за выбранный домен."""
    from students.import_service import apply_preview

    denied = _deny_file_upload(request)
    if denied:
        return denied
    domain_code, problem = _chosen_domain(request)
    if problem:
        return problem

    serializer = ImportApplySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = apply_preview(
        preview_rows=serializer.validated_data["rows"],
        domain_code=domain_code,
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
        return scope_to_user(super().get_queryset(), self.request.user)

    def _may_create(self, role: str) -> bool:
        """Владелец домена — или куратор там, где он вносит за ученика."""
        from core.domains import curator_may_touch

        if owns_model(role, self.domain_model_label):
            return True
        return role == ROLE_CURATOR and curator_may_touch(self.domain_model_label)

    def create(self, request, *args, **kwargs):
        # заводить строки в чужой таблице нельзя: без этой проверки чужой
        # директор создавал бы пустую запись — все поля у него read_only
        if not self._may_create(request.user.role):
            return refuse(request.user.role, self.domain_model_label)
        return super().create(request, *args, **kwargs)

    def extra_on_create(self) -> dict:
        """Что вьюха ставит строке сама — не из запроса."""
        return {}

    def perform_create(self, serializer):
        """Ученика ставим отдельно.

        В реестре доменов поля `student` нет и быть не должно — это не
        доменное поле, а ссылка на владельца строки. Сериализатор его
        поэтому держит только на чтение, и без этой строки запись
        сохранялась бы без ученика. Чужой куратору ученик — 404, как везде.
        """
        from rest_framework.exceptions import NotFound

        student = Student.objects.filter(pk=self.request.data.get("student")).first()
        if student is None:
            raise ValidationError({"student": "Не указан ученик или его нет в списке"})
        if not sees_student(self.request.user, student.pk):
            raise NotFound("Ученик не найден")
        row = serializer.save(student=student, **self.extra_on_create())
        self.after_curator_create(row)

    def after_curator_create(self, row) -> None:
        """Крючок для записей, которыми куратор перекрывает предложение ученика."""


@extend_schema(request=AttemptBulkSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def attempts_bulk(request):
    """Массовый ввод результатов после общешкольного мока.

    После пробного результаты вносят десятками, и по одному это неделя
    работы. Строка с непригодным значением не отменяет остальные — её
    называют по номеру, как в импорте (фаза 15).
    """
    from students.attempts_bulk import save_rows

    if not owns_model(request.user.role, "students.ExamAttempt"):
        return refuse(request.user.role, "students.ExamAttempt")

    payload = AttemptBulkSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    return Response(save_rows(rows=payload.validated_data["rows"], actor=request.user))


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

    MOCKS_BY_FILE = "Пробник из файла не правится руками: неверный файл убирают в архив и загружают заново"

    def extra_on_create(self) -> dict:
        # куратор вносит официальную попытку с сертификата или пробник руками
        # (файлом пробники грузят Кымбат и администратор); формат сдачи —
        # не его поле в реестре, поэтому берётся из запроса здесь
        if self.request.user.role == ROLE_CURATOR:
            wanted = str(self.request.data.get("attempt_format") or AttemptFormat.OFFICIAL)
            if wanted not in (AttemptFormat.OFFICIAL, AttemptFormat.MOCK):
                raise ValidationError({"attempt_format": "Формат сдачи — официальный или пробник"})
            return {"attempt_format": wanted}
        return {}

    def after_curator_create(self, row) -> None:
        if self.request.user.role == ROLE_CURATOR:
            from suggestions.superseding import by_new_row

            by_new_row(row, actor=self.request.user)

    def _mock_closed_to_curator(self, request):
        # пробник, пришедший файлом, куратор не правит; внесённый руками — его строка
        if request.user.role != ROLE_CURATOR:
            return None
        if self.get_object().mock_import_id:
            return Response({"detail": self.MOCKS_BY_FILE}, status=status.HTTP_403_FORBIDDEN)
        return None

    NOT_A_TABLE_ROW = "Директор по поступлению правит попытки своей таблицы — остальные ведёт домен экзаменов"

    def _foreign_to_the_admission_block(self, request):
        """Асем правит попытки как строки блока «Поступление» — и только их.

        Реестр даёт ей балл и дату попытки (`ADMISSION_BLOCK_EXTRA`), но
        граница «строка таблицы поступления» — про запись, а не про поле,
        поэтому держится здесь.
        """
        from core.domains import DOMAINS
        from students.models import AttemptSource

        if request.user.role != DOMAINS["admission"].role:
            return None
        if self.get_object().source != AttemptSource.ADMISSION_IMPORT:
            return Response({"detail": self.NOT_A_TABLE_ROW}, status=status.HTTP_403_FORBIDDEN)
        return None

    def update(self, request, *args, **kwargs):
        return (
            self._mock_closed_to_curator(request)
            or self._foreign_to_the_admission_block(request)
            or super().update(request, *args, **kwargs)
        )

    def destroy(self, request, *args, **kwargs):
        return self._mock_closed_to_curator(request) or super().destroy(request, *args, **kwargs)


class ActivityViewSet(StudentScopedViewSet):
    """Активности портфолио. Ведёт директор талантов (инвариант №5)."""

    queryset = Activity.objects.select_related("student").all()
    serializer_class = ActivitySerializer
    domain_model_label = "students.Activity"
    filterset_fields = ("student", "category", "is_confirmed")
    search_fields = ("title", "description")

    def get_queryset(self):
        rows = super().get_queryset()
        student = getattr(self.request.user, "student", None) if self.request.user.role == ROLE_STUDENT else None
        if student is not None and not has_admission(student):
            # у 8–10 из достижений — только олимпиады: прочее ушло
            # вместе с «Портфолио» (`core/parallels.py`)
            return rows.filter(category=JUNIOR_ACTIVITY_CATEGORY)
        return rows


class CompetitionViewSet(StudentScopedViewSet):
    """Соревнования. Ведёт директор спорта (инвариант №5)."""

    queryset = Competition.objects.select_related("student").all()
    serializer_class = CompetitionSerializer
    domain_model_label = "students.Competition"
    filterset_fields = ("student", "has_certificate", "show_in_card")
    search_fields = ("name", "result")

    #: кто видит соревнования целиком: владелец домена, куратор (вкладка
    #: «Портфолио» своих групп), администратор и сам ученик у себя. Остальным
    #: директорам карточка показывает только отмеченные «в карточку»
    SEES_EVERYTHING = ("director_sport", ROLE_CURATOR, ROLE_ADMIN, ROLE_STUDENT)

    def get_queryset(self):
        rows = super().get_queryset()
        if self.request.user.role in self.SEES_EVERYTHING:
            return rows
        return rows.filter(show_in_card=True)


class ParentContactViewSet(StudentScopedViewSet):
    """Контакты родителей. Домен — `behavior`, владелец — директор школы.

    Заводит и убирает контакт не только она (фаза 70): куратор ведёт их
    по своим группам, администратор — везде. Право дали ещё в 66-й, но
    кнопки не было, и куратор мог только поправить телефон у записи,
    которую кто-то завёл до него.

    Ученику свои контакты видны: это его семья, а не внутренняя оценка.
    """

    queryset = ParentContact.objects.select_related("student").all()
    serializer_class = ParentContactSerializer
    domain_model_label = "students.ParentContact"
    filterset_fields = ("student", "relation", "is_primary")
    search_fields = ("full_name", "phone", "email", "student__last_name", "student__first_name")
    ordering_fields = ("full_name", "is_primary")

    def create(self, request, *args, **kwargs):
        """Контакт заводит тот, кто по нему звонит (фаза 70).

        Владелец домена — по всей школе, куратор — ученику своей группы,
        администратор — везде. Чужого ученика не видно вовсе: выборка
        одна на систему, и подсказывать о его существовании незачем.
        """
        from core.domains import ROLE_ADMIN, ROLE_CURATOR, owns_model
        from core.scope import sees_student

        role = request.user.role
        if role not in (ROLE_ADMIN, ROLE_CURATOR) and not owns_model(role, self.domain_model_label):
            return refuse(role, self.domain_model_label)
        student_id = request.data.get("student")
        if not sees_student(request.user, int(student_id) if str(student_id).isdigit() else None):
            return Response({"detail": "Ученика нет в ваших группах"}, status=status.HTTP_404_NOT_FOUND)
        return viewsets.ModelViewSet.create(self, request, *args, **kwargs)


class StudyGroupViewSet(ArchiveDeleteMixin, viewsets.ModelViewSet):
    """Учебные группы. Реестр школы — ведёт администратор."""

    queryset = StudyGroup.objects.all()
    serializer_class = StudyGroupSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("is_active", "parallel")
    search_fields = ("code",)

    #: поля «куратор» у группы больше нет (фаза 61): куратор — назначение
    #: с датой. Старый запрос с этим полем получает внятный отказ, а не
    #: молчаливое «сохранено» с потерянным значением
    CURATOR_FIELD_FROZEN = "Куратора назначают на экране «Пользователи»: у группы нет поля с именем куратора"

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == ROLE_CURATOR:
            from accounts.curators import curated_group_ids

            # куратор видит список только своих групп (фаза 60)
            return qs.filter(pk__in=curated_group_ids(self.request.user))
        return qs

    def _staff_only(self, request):
        return request.user.role != ROLE_ADMIN

    def _curator_field_touched(self, request):
        if "curator" in (request.data or {}):
            return Response({"detail": self.CURATOR_FIELD_FROZEN}, status=status.HTTP_400_BAD_REQUEST)
        return None

    def create(self, request, *args, **kwargs):
        if self._staff_only(request):
            return Response({"detail": "Группы заводит администратор"}, status=status.HTTP_403_FORBIDDEN)
        return self._curator_field_touched(request) or super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if self._staff_only(request):
            return Response({"detail": "Группы ведёт администратор"}, status=status.HTTP_403_FORBIDDEN)
        return self._curator_field_touched(request) or super().update(request, *args, **kwargs)


# --- Портфолио и документы (фаза 38) --------------------------------------


def _portfolio_student(request):
    """Карточка ученика за запросом; None — это не ученик."""
    if request.user.role != ROLE_STUDENT:
        return None
    return getattr(request.user, "student", None)


class StudentDocumentViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Документы портфолио: загружает и убирает ученик, сотрудники читают.

    Куратор загружает документ за ученика своей группы — он ложится сразу
    подтверждённым — и правит срок действия. Удалять документ куратор
    не может: перезагрузка оставляет прежний файл в истории.

    Это документы человека, а не табличные данные — правило «файлы грузит
    администратор» (фаза 35) на них не распространяется, как и на материалы
    олимпиадников. Прямой ссылки на файл нет: он отдаётся своим маршрутом
    после проверки прав.
    """

    queryset = StudentDocument.objects.select_related("student").all()
    serializer_class = StudentDocumentSerializer
    permission_classes = [IsAuthenticated]
    # JSONParser в списке нужен, чтобы запрос без файла получал честный
    # отказ по роли (403), а не 415 из-за типа содержимого
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ("doc_type", "student")

    def get_queryset(self):
        # ученик — свои, куратор — учеников своих групп, сотрудники — все
        rows = scope_to_user(super().get_queryset(), self.request.user)
        student = _portfolio_student(self.request)
        if student is not None and not has_admission(student):
            # у 8–10 документов поступления нет — только сканы-подтверждения
            rows = rows.filter(doc_type=JUNIOR_DOCUMENT_TYPE)
        return rows

    def create(self, request, *args, **kwargs):
        from materials.files import FileRejected, inspect

        student = _portfolio_student(request)
        if student is not None and not document_open(student, str(request.data.get("doc_type") or "")):
            return Response(
                {"detail": "Документы поступления ведутся только у 11 параллели", "code": "parallel_closed"},
                status=status.HTTP_403_FORBIDDEN,
            )
        by_curator = False
        if student is None and request.user.role == ROLE_CURATOR:
            # куратор — за ученика своей группы; чужой ученик — 404, как везде
            student = Student.objects.filter(pk=request.data.get("student")).first()
            if student is None or not sees_student(request.user, student.pk):
                return Response({"detail": "Ученик не найден"}, status=status.HTTP_404_NOT_FOUND)
            by_curator = True
        if student is None:
            return Response(
                {"detail": "Документы портфолио загружает сам ученик или куратор его группы"},
                status=status.HTTP_403_FORBIDDEN,
            )
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            info = inspect(uploaded)
        except FileRejected as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded.seek(0)
        row = serializer.save(
            student=student,
            file=uploaded,
            content_type=info.content_type,
            size=info.size,
            uploaded_by=request.user,
        )
        # проверка (фаза 62): документ чек-листа встаёт в очередь домена
        # «Документы»; если это перезагрузка после отклонения — куратор группы
        # узнаёт. Файл «прочее» при достижении проверяется вместе с самим
        # достижением (строка Армана) и отдельной очереди не получает
        from students import documents
        from students.portfolio import REQUIRED_DOCUMENTS
        from suggestions.followups import document_reuploaded

        if by_curator:
            # значение сразу настоящее: очереди нет, в матрице и чек-листе зелёный
            documents.entered_by_curator(row, actor=request.user)
        elif row.doc_type in REQUIRED_DOCUMENTS:
            documents.submit(row, author=request.user)
            document_reuploaded(row)
        return Response(self.get_serializer(row).data, status=status.HTTP_201_CREATED)

    #: что в документе правится после загрузки — остальное меняется перезагрузкой
    EDITABLE = ("title", "issued_date", "expires_at", "note")

    def partial_update(self, request, *args, **kwargs):
        """Срок действия и подписи документа: владелец домена и куратор группы.

        Право — из реестра (`can_write`), граница «своя группа» — из выборки:
        чужой документ отсюда не находится вовсе. Ученик правит перезагрузкой.
        """
        from core.audit import apply_changes
        from core.domains import Source, can_write

        row = self.get_object()
        role = request.user.role
        wanted = {name: request.data[name] for name in self.EDITABLE if name in request.data}
        if role == ROLE_STUDENT or not all(can_write(role, "students.StudentDocument", name) for name in wanted):
            return refuse(role, "students.StudentDocument")
        serializer = self.get_serializer(row, data=wanted, partial=True)
        serializer.is_valid(raise_exception=True)
        apply_changes(row, serializer.validated_data, actor=request.user, source=Source.MANUAL)
        return Response(self.get_serializer(row).data)

    def _own_row(self, request):
        """Удаление — только у хозяина документа."""
        row = self.get_object()
        student = _portfolio_student(request)
        if student is None or row.student_id != student.pk:
            return None
        return row

    def destroy(self, request, *args, **kwargs):
        from core.archive import archive

        row = self._own_row(request)
        if row is None:
            return Response({"detail": "Свой документ убирает сам ученик"}, status=status.HTTP_403_FORBIDDEN)
        entry = archive(row, actor=request.user)
        return Response({"archived": entry.pk, "detail": f"Документ «{entry.title}» в архиве"})


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def document_file(request, pk: int):
    """Файл документа — после проверки прав, вне корня веб-сервера.

    Ученик видит свои, сотрудники — документы любого ученика. Чужому
    ученику — 404, а не 403: по 403 видно, что документ существует.
    """
    from django.http import FileResponse

    from students.models import StudentDocument

    row = StudentDocument.objects.select_related("student").filter(pk=pk).first()
    if row is None or not sees_student(request.user, row.student_id):
        raise NotFound("Документа нет")
    own = _portfolio_student(request)
    if own is not None and not document_open(own, row.doc_type):
        raise NotFound("Документа нет")
    # документ-ссылка (фаза 65): после той же проверки прав — переход на адрес;
    # сам адрес в ответах API виден только тем, кому виден документ
    if row.is_link:
        from django.http import HttpResponseRedirect

        response = HttpResponseRedirect(row.external_url)
        response["Cache-Control"] = "private, no-store"
        return response
    if not row.file:
        raise NotFound("У документа нет файла")

    extension = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}.get(row.content_type, "")
    response = FileResponse(row.file.open("rb"), content_type=row.content_type or "application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="document-{row.pk}{extension}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def portfolio_state(request):
    """Портфолио ученика: процент заполнения, следующие шаги, чек-лист."""
    from students import portfolio

    student = _portfolio_student(request)
    if student is None:
        return Response({"detail": "Портфолио — экран ученика"}, status=status.HTTP_403_FORBIDDEN)
    return Response(portfolio.state(student))


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def portfolio_cv(request):
    """Экспорт CV: файл собирается по запросу и на сервере не хранится."""
    from django.http import HttpResponse

    from students import portfolio

    student = _portfolio_student(request)
    if student is None:
        return Response({"detail": "CV собирается из портфолио ученика"}, status=status.HTTP_403_FORBIDDEN)
    response = HttpResponse(portfolio.cv_html(student), content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cv.html"'
    response["Cache-Control"] = "private, no-store"
    return response


# --- Цели по экзаменам и календарь (фаза 39) --------------------------------


class ExamGoalViewSet(StudentScopedViewSet):
    """Цели по экзаменам. Ставит ученик предложением, ведёт домен `exam`."""

    queryset = ExamGoal.objects.select_related("student", "exam").all()
    serializer_class = ExamGoalSerializer
    domain_model_label = "students.ExamGoal"
    filterset_fields = ("student", "exam")

    def after_curator_create(self, row) -> None:
        if self.request.user.role == ROLE_CURATOR:
            from suggestions.superseding import by_new_row

            by_new_row(row, actor=self.request.user)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def calendar_state(request):
    """Календарь ученика: события с датами и ближайшее с отсчётом."""
    from students import calendar_feed

    student = _portfolio_student(request)
    if student is None:
        # у сотрудника карточки ученика нет, но календарь ему нужен свой:
        # события его учеников с числом сдающих и подающих (фаза 49)
        return Response(calendar_feed.staff_state())
    return Response(calendar_feed.state(student))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exam_goals_attention(request):
    """Списки академическому директору: у кого нет целей, у кого экзамен близко.

    «Не зарегистрировался» — дата регистрации пуста, а экзамен ближе,
    чем срок появления автозадачи о регистрации.
    """
    import datetime as dt

    from django.conf import settings
    from django.utils import timezone

    from core.domains import DOMAINS

    if request.user.role not in (DOMAINS["exam"].role, ROLE_ADMIN):
        return Response({"detail": "Списки целей ведёт академический директор"}, status=status.HTTP_403_FORBIDDEN)

    today = timezone.localdate()
    week = today + dt.timedelta(days=7)
    horizon = today + dt.timedelta(days=settings.REMIND_EXAM_TASK_DAYS)

    with_goals = set(ExamGoal.objects.values_list("student_id", flat=True))
    without = [
        {"id": row.pk, "name": row.full_name}
        # экзамены ведутся только у 11 (`core/parallels.py`)
        for row in admission_students(Student.objects.exclude(pk__in=with_goals)).order_by("last_name", "first_name")[
            :100
        ]
    ]
    this_week = [
        {
            "id": goal.student_id,
            "name": goal.student.full_name,
            "exam": goal.exam.name,
            "date": goal.exam_date.isoformat(),
        }
        for goal in ExamGoal.objects.filter(exam_date__gte=today, exam_date__lte=week).select_related("student", "exam")
    ]
    not_registered = [
        {
            "id": goal.student_id,
            "name": goal.student.full_name,
            "exam": goal.exam.name,
            "date": goal.exam_date.isoformat(),
        }
        for goal in ExamGoal.objects.filter(
            registration_date__isnull=True, exam_date__gte=today, exam_date__lte=horizon
        ).select_related("student", "exam")
    ]
    return Response({"no_goals": without, "exam_this_week": this_week, "not_registered": not_registered})


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def year_transfer(request):
    """Перевод на следующий год: GET — предпросмотр, POST — перевод с подтверждением числом.

    Только администратор. 8→9, 9→10, 10→11, 11 — выпуск в архив; один раз
    за учебный год (`students.year_transfer`).
    """
    from students import year_transfer as transfer

    if request.user.role != ROLE_ADMIN:
        return Response({"detail": "Перевод на следующий год делает администратор"}, status=status.HTTP_403_FORBIDDEN)
    if request.method == "GET":
        return Response(transfer.preview())
    try:
        outcome = transfer.run(actor=request.user, confirm=str(request.data.get("confirm") or ""))
    except transfer.TransferRefused as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(outcome)
