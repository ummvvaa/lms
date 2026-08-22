"""API справочника вузов, требований и движка соответствия."""

from __future__ import annotations

import json

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.domains import ROLE_STUDENT, can_write
from core.permissions import DomainFieldPermission
from students.models import Student
from universities.catalog import CatalogFilters, facets
from universities.catalog import build as build_catalog
from universities.matching import list_balance, match_student_list, open_programs, what_if
from universities.models import (
    AddedBy,
    AdmissionRequirement,
    AdmissionRound,
    Program,
    StudentUniversity,
    Tier,
    University,
)
from universities.serializers import (
    AdmissionRequirementSerializer,
    AdmissionRoundSerializer,
    ProgramSerializer,
    RequirementImportSerializer,
    StudentUniversitySerializer,
    UniversitySerializer,
    WhatIfSerializer,
)


class UniversityViewSet(viewsets.ModelViewSet):
    queryset = University.objects.all()
    serializer_class = UniversitySerializer
    permission_classes = [DomainFieldPermission]
    domain_model_label = "universities.University"
    search_fields = ("name", "country", "domain")
    filterset_fields = ("country", "is_active")


class ProgramViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Program.objects.select_related("university", "requirement").prefetch_related("rounds").all()
    serializer_class = ProgramSerializer
    search_fields = ("name", "university__name")
    filterset_fields = ("university", "level", "is_active")


class AdmissionRoundViewSet(viewsets.ModelViewSet):
    queryset = AdmissionRound.objects.select_related("program__university").all()
    serializer_class = AdmissionRoundSerializer
    permission_classes = [DomainFieldPermission]
    domain_model_label = "universities.AdmissionRound"
    filterset_fields = ("program", "round_type")


class RequirementFilter(filters.FilterSet):
    country = filters.CharFilter(field_name="program__university__country")
    university = filters.NumberFilter(field_name="program__university")

    class Meta:
        model = AdmissionRequirement
        fields = ("program", "country", "university")


class AdmissionRequirementViewSet(viewsets.ModelViewSet):
    """Справочник требований. Ведёт директор по поступлению."""

    queryset = AdmissionRequirement.objects.select_related("program__university").all()
    serializer_class = AdmissionRequirementSerializer
    permission_classes = [DomainFieldPermission]
    domain_model_label = "universities.AdmissionRequirement"
    filterset_class = RequirementFilter
    search_fields = ("program__name", "program__university__name")


class StudentUniversityViewSet(viewsets.ModelViewSet):
    """Список вузов ученика."""

    queryset = StudentUniversity.objects.select_related("program__university", "admission_round").all()
    serializer_class = StudentUniversitySerializer
    permission_classes = [DomainFieldPermission]
    domain_model_label = "universities.StudentUniversity"
    filterset_fields = ("student", "tier", "application_status")

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == ROLE_STUDENT:
            student = getattr(self.request.user, "student", None)
            return qs.filter(student=student) if student else qs.none()
        return qs


def _student_for(request, student_id: str | None) -> Student | None:
    """Ученик из запроса: сотрудник указывает id, ученик получает себя."""
    if request.user.role == ROLE_STUDENT:
        return getattr(request.user, "student", None)
    if not student_id:
        return None
    return Student.objects.filter(pk=student_id).first()


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def match_my_universities(request):
    """Как ученик выглядит на фоне своего списка вузов."""
    student = _student_for(request, request.query_params.get("student"))
    if student is None:
        return Response({"detail": "Ученик не найден"}, status=status.HTTP_404_NOT_FOUND)
    return Response([m.as_dict() for m in match_student_list(student)])


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def match_open_programs(request):
    """Какие программы открываются при текущем профиле."""
    student = _student_for(request, request.query_params.get("student"))
    if student is None:
        return Response({"detail": "Ученик не найден"}, status=status.HTTP_404_NOT_FOUND)

    results = open_programs(student)
    only_open = request.query_params.get("only_open") == "1"
    if only_open:
        results = [m for m in results if m.is_open]
    return Response([m.as_dict() for m in results])


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def match_list_balance(request):
    """Баланс списка вузов: сколько reach / target / safety и чего добрать."""
    student = _student_for(request, request.query_params.get("student"))
    if student is None:
        return Response({"detail": "Ученик не найден"}, status=status.HTTP_404_NOT_FOUND)
    return Response(list_balance(student))


@extend_schema(request=WhatIfSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def match_what_if(request):
    """Что откроется, если поднять IELTS, SAT или GPA."""
    student = _student_for(request, request.data.get("student"))
    if student is None:
        return Response({"detail": "Ученик не найден"}, status=status.HTTP_404_NOT_FOUND)

    serializer = WhatIfSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return Response(
        what_if(
            student,
            ielts_delta=serializer.validated_data["ielts_delta"],
            sat_delta=serializer.validated_data["sat_delta"],
            gpa_delta=serializer.validated_data["gpa_delta"],
        )
    )


@extend_schema(request=RequirementImportSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def import_requirements_view(request):
    """Импорт требований из XLSX/CSV. Только директор по поступлению."""
    from core.domains import domain_of_role
    from students.import_service import read_table
    from universities.import_requirements import TARGET_FIELDS, import_requirements

    domain = domain_of_role(request.user.role)
    if domain is None or domain.code != "admission":
        return Response({"detail": "Требования вузов ведёт директор по поступлению"}, status=status.HTTP_403_FORBIDDEN)

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)

    header, rows = read_table(uploaded)
    raw_mapping = request.data.get("mapping") or "{}"
    mapping = json.loads(raw_mapping) if isinstance(raw_mapping, str) else raw_mapping

    if not mapping:
        return Response({"columns": header, "total_rows": len(rows), "targets": TARGET_FIELDS})

    dry_run = str(request.data.get("dry_run", "")).lower() in {"1", "true", "yes"}
    report = import_requirements(header=header, rows=rows, mapping=mapping, dry_run=dry_run)
    return Response(report.as_dict())


# --- Каталог для ученика --------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def catalog(request):
    """Каталог программ с процентом соответствия под конкретного ученика."""
    student = _student_for(request, request.query_params.get("student"))
    if student is None:
        return Response({"detail": "Ученик не найден"}, status=status.HTTP_404_NOT_FOUND)

    cards = build_catalog(student, CatalogFilters.from_query(request.query_params))
    return Response({"count": len(cards), "results": cards})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def catalog_facets(request):
    """Значения фильтров каталога — только те, что есть в справочнике."""
    return Response(facets())


@extend_schema(request=None, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_to_my_list(request):
    """«Добавить к себе»: ученик кладёт программу в свой список.

    Запись помечается `added_by=student` и ждёт подтверждения директора
    по поступлению — данные от ученика не приравниваются к проверенным.
    """
    from django.conf import settings as django_settings

    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "Список вузов есть только у ученика"}, status=status.HTTP_403_FORBIDDEN)

    program = Program.objects.filter(pk=request.data.get("program"), is_active=True).first()
    if program is None:
        return Response({"detail": "Такой программы нет в справочнике"}, status=status.HTTP_404_NOT_FOUND)

    tier = request.data.get("tier", Tier.TARGET)
    if tier not in Tier.values:
        return Response({"detail": "Неизвестная категория"}, status=status.HTTP_400_BAD_REQUEST)

    limit = django_settings.STUDENT_LIST_LIMIT
    if StudentUniversity.objects.filter(student=student).count() >= limit:
        return Response(
            {"detail": f"В списке уже {limit} программ — это потолок. Уберите лишнее, чтобы добавить новое"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    entry, created = StudentUniversity.objects.get_or_create(
        student=student,
        program=program,
        defaults={"tier": tier, "added_by": AddedBy.STUDENT, "is_confirmed": False},
    )
    if not created:
        return Response({"detail": "Эта программа уже в вашем списке"}, status=status.HTTP_400_BAD_REQUEST)

    return Response(StudentUniversitySerializer(entry).data, status=status.HTTP_201_CREATED)


@extend_schema(responses={204: None})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_from_my_list(request, pk: int):
    """Убрать программу из своего списка.

    Ученик снимает только то, что добавил сам: решение директора
    отменяет тот, кто его принял.
    """
    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "Список вузов есть только у ученика"}, status=status.HTTP_403_FORBIDDEN)

    entry = StudentUniversity.objects.filter(pk=pk, student=student).first()
    if entry is None:
        return Response({"detail": "Записи нет"}, status=status.HTTP_404_NOT_FOUND)
    if entry.added_by != AddedBy.STUDENT:
        return Response(
            {"detail": "Эту программу добавил директор по поступлению — снять её может он"},
            status=status.HTTP_403_FORBIDDEN,
        )

    entry.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_additions(request):
    """Что ученики добавили себе сами и ждёт решения директора."""
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Список подтверждений ведёт директор"}, status=status.HTTP_403_FORBIDDEN)

    rows = (
        StudentUniversity.objects.filter(added_by=AddedBy.STUDENT, is_confirmed=False)
        .select_related("student", "program__university")
        .order_by("-created_at")
    )
    return Response(
        [
            {
                "id": row.id,
                "student": row.student_id,
                "student_name": row.student.full_name,
                "program": row.program_id,
                "university_name": row.program.university.name,
                "program_name": row.program.name,
                "tier": row.tier,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_addition(request, pk: int):
    """Директор подтверждает добавление ученика или снимает его."""
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Решение принимает директор"}, status=status.HTTP_403_FORBIDDEN)
    if not can_write(request.user.role, "universities.StudentUniversity", "tier"):
        return Response({"detail": "Списки вузов ведёт директор по поступлению"}, status=status.HTTP_403_FORBIDDEN)

    entry = StudentUniversity.objects.filter(pk=pk).first()
    if entry is None:
        return Response({"detail": "Записи нет"}, status=status.HTTP_404_NOT_FOUND)

    if request.data.get("decision") == "decline":
        entry.delete()
        return Response({"detail": "Снято"})

    entry.is_confirmed = True
    if request.data.get("tier") in Tier.values:
        entry.tier = request.data["tier"]
    entry.save(update_fields=["is_confirmed", "tier", "updated_at"])
    return Response(StudentUniversitySerializer(entry).data)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def catalog_pick(request):
    """Подбор по словесному запросу. Только программы справочника (инвариант №10)."""
    from universities.picker import pick

    student = _student_for(request, request.data.get("student"))
    if student is None:
        return Response({"detail": "Ученик не найден"}, status=status.HTTP_404_NOT_FOUND)

    text = (request.data.get("text") or "").strip()
    if not text:
        return Response({"detail": "Опишите, чего вы хотите"}, status=status.HTTP_400_BAD_REQUEST)

    return Response(pick(student=student, text=text, actor=request.user).as_dict())
