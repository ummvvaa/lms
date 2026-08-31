"""API справочника вузов, требований и движка соответствия."""

from __future__ import annotations

import json

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.actor import importing
from core.deletion import ArchiveDeleteMixin, HardDeleteMixin, refuse
from core.domains import ROLE_STUDENT, can_write, owns_model
from core.models import ImportBatch
from core.permissions import DomainFieldPermission
from students.models import Student
from universities.catalog import CatalogFilters, facets
from universities.catalog import build as build_catalog
from universities.matching import at_goal, list_balance, match, match_student_list, open_programs, what_if
from universities.models import (
    AddedBy,
    AdmissionRequirement,
    AdmissionRound,
    FavoriteProgram,
    MatchRun,
    Program,
    SavedScholarship,
    Scholarship,
    StudentUniversity,
    Tier,
    University,
)
from universities.seed_catalog import SeedInUse, create_seed, drop_seed, seed_stats
from universities.serializers import (
    AdmissionRequirementSerializer,
    AdmissionRoundSerializer,
    ProgramSerializer,
    RequirementImportSerializer,
    ScholarshipSerializer,
    StudentUniversitySerializer,
    UniversitySerializer,
    WhatIfSerializer,
)
from universities.verification import NotVerifiable, can_verify, confirm_on_manual_edit, set_verified


class ConfirmOnEditMixin:
    """Правка руками снимает плашку «не подтверждено» (фаза 29).

    Раньше запись из заготовки или от модели оставалась неподтверждённой
    даже после того, как директор по поступлению правил её сам, — то есть
    ровно после того, как её проверил человек, которому это поручено.
    """

    def perform_update(self, serializer):
        instance = serializer.save()
        confirm_on_manual_edit(instance, actor=self.request.user)


class UniversityViewSet(ConfirmOnEditMixin, HardDeleteMixin, viewsets.ModelViewSet):
    """Справочник вузов. Ведёт директор по поступлению.

    Удаляется физически: истории у справочной записи нет (инвариант №13).
    Если программы вуза стоят в списках учеников, отказ приходит текстом,
    а не ошибкой сервера.
    """

    queryset = University.objects.all()
    serializer_class = UniversitySerializer
    permission_classes = [DomainFieldPermission]
    domain_model_label = "universities.University"
    search_fields = ("name", "country", "domain")
    filterset_fields = ("country", "is_active")


class ProgramViewSet(ConfirmOnEditMixin, HardDeleteMixin, viewsets.ModelViewSet):
    """Программы вузов. Заводит и убирает директор по поступлению."""

    queryset = Program.objects.select_related("university", "requirement").prefetch_related("rounds").all()
    serializer_class = ProgramSerializer
    permission_classes = [DomainFieldPermission]
    domain_model_label = "universities.Program"
    search_fields = ("name", "university__name")
    filterset_fields = ("university", "level", "is_active")


class AdmissionRoundViewSet(ConfirmOnEditMixin, HardDeleteMixin, viewsets.ModelViewSet):
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


class AdmissionRequirementViewSet(ConfirmOnEditMixin, HardDeleteMixin, viewsets.ModelViewSet):
    """Справочник требований. Ведёт директор по поступлению."""

    queryset = AdmissionRequirement.objects.select_related("program__university").all()
    serializer_class = AdmissionRequirementSerializer
    permission_classes = [DomainFieldPermission]
    domain_model_label = "universities.AdmissionRequirement"
    filterset_class = RequirementFilter
    search_fields = ("program__name", "program__university__name")


class StudentUniversityViewSet(ArchiveDeleteMixin, viewsets.ModelViewSet):
    """Список вузов ученика.

    Запись уходит в архив, а не удаляется: на ней висит история подачи.
    Ученик снимает только то, что добавил сам, — через `/catalog/remove/`.
    """

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

    def perform_create(self, serializer):
        """Ученика ставим отдельно.

        `student` — не доменное поле, а ссылка на владельца строки, и в
        реестре его нет. Сериализатор поэтому держит его только на чтение,
        и без этой строки директор не мог положить программу в список
        ученика вовсе.
        """
        student = Student.objects.filter(pk=self.request.data.get("student")).first()
        if student is None:
            raise ValidationError({"student": "Не указан ученик или его нет в списке"})
        serializer.save(student=student)


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


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def match_at_goal(request):
    """«Если сдашь на цель, откроется вот это» — по целям ученика (фаза 39)."""
    student = _student_for(request, request.query_params.get("student"))
    if student is None:
        return Response({"detail": "Ученик не найден"}, status=status.HTTP_404_NOT_FOUND)
    return Response(at_goal(student))


@extend_schema(request=RequirementImportSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def import_requirements_view(request):
    """Импорт требований из XLSX/CSV. Файл грузит администратор за домен «Поступление».

    Требования ведёт директор по поступлению, он же снимает плашки и правит
    руками. Но файл с ними, как и любой файл, с фазы 35 грузит администратор:
    каждая правка в журнале помечается доменом, за который он действовал.
    """
    from core.domains import DOMAINS, can_upload_files
    from students.import_service import read_table
    from universities.import_requirements import TARGET_FIELDS, import_requirements

    if not can_upload_files(request.user.role):
        return Response(
            {"detail": "Файлы загружает администратор. Требования заводятся руками в справочнике"},
            status=status.HTTP_403_FORBIDDEN,
        )
    domain = DOMAINS["admission"]

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)

    header, rows = read_table(uploaded)
    raw_mapping = request.data.get("mapping") or "{}"
    mapping = json.loads(raw_mapping) if isinstance(raw_mapping, str) else raw_mapping

    if not mapping:
        return Response({"columns": header, "total_rows": len(rows), "targets": TARGET_FIELDS})

    dry_run = str(request.data.get("dry_run", "")).lower() in {"1", "true", "yes"}
    if dry_run:
        return Response(import_requirements(header=header, rows=rows, mapping=mapping, dry_run=True).as_dict())

    # загрузка попадает в историю и целиком отменяется оттуда же:
    # правки внутри блока помечаются этой записью через контекст
    batch = ImportBatch.objects.create(
        actor=request.user,
        file_name=getattr(uploaded, "name", "") or "",
        kind=ImportBatch.Kind.REQUIREMENTS,
        domain_code=domain.code,
        rows_total=len(rows),
    )
    with importing(batch):
        report = import_requirements(header=header, rows=rows, mapping=mapping, dry_run=False)

    payload = report.as_dict()
    batch.rows_created = payload.get("created", 0)
    batch.rows_updated = payload.get("updated", 0)
    batch.rows_failed = len(payload.get("errors", []))
    if batch.rows_created:
        batch.note = "Отмена вернёт прежние пороги, но заведённые программы и требования не удалит"
    batch.save(update_fields=["rows_created", "rows_updated", "rows_failed", "note"])
    payload["batch"] = batch.pk
    return Response(payload)


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


# --- Стартовый справочник и подтверждение данных ---------------------------


@extend_schema(request=None, responses={200: dict})
@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def seed_catalog_view(request):
    """Стартовый справочник: сколько его в базе, завести, удалить.

    Заведённое школой не трогается ни при заведении, ни при удалении —
    удаляются ровно записи с источником `seed`.
    """
    if not can_verify(request.user.role):
        return Response(
            {"detail": "Стартовым справочником распоряжается директор по поступлению"},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        return Response(seed_stats())

    if request.method == "POST":
        created = create_seed()
        return Response({**seed_stats(), "created": created, "detail": "Стартовый справочник заведён"})

    force = str(request.query_params.get("force", "")).lower() in ("1", "true", "yes")
    try:
        removed = drop_seed(force=force)
    except SeedInUse as error:
        return Response(
            {"detail": str(error), "held_by_students": error.held, "need_force": True},
            status=status.HTTP_409_CONFLICT,
        )
    return Response({**seed_stats(), "removed": removed, "detail": "Стартовый справочник удалён"})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_record(request):
    """Снять с записи справочника плашку «данные не подтверждены».

    Право есть только у директора по поступлению (инвариант №14).
    """
    if not can_verify(request.user.role):
        return Response(
            {"detail": "Подтверждать данные справочника может только директор по поступлению"},
            status=status.HTTP_403_FORBIDDEN,
        )

    kind = request.data.get("kind") or "university"
    record_id = request.data.get("id")
    verified = request.data.get("verified", True)
    if record_id in (None, ""):
        return Response({"detail": "Не указано, какую запись подтверждаем"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        payload = set_verified(kind, int(record_id), verified=bool(verified), actor=request.user)
    except NotVerifiable as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    except LookupError as error:
        return Response({"detail": str(error)}, status=status.HTTP_404_NOT_FOUND)
    except (TypeError, ValueError):
        return Response({"detail": "Номер записи должен быть числом"}, status=status.HTTP_400_BAD_REQUEST)
    return Response(payload)


# --- Подбор вузов: прогоны, избранное (фаза 40) -----------------------------


def _run_payload(run, *, with_results: bool = False) -> dict:
    """Прогон в ответ API: статус, воронка, стратегия и — по запросу — строки."""
    from universities.selection import methodology, stage_titles

    payload = {
        "id": run.pk,
        "status": run.status,
        "status_title": run.get_status_display(),
        "stage": run.stage,
        "stages": stage_titles(),
        "progress": run.progress,
        "major": run.major,
        "level": run.level,
        "level_title": run.get_level_display() if run.level else "",
        "countries": [c for c in run.countries.split(",") if c],
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "error": run.error,
        "profile": {
            "gpa": str(run.snapshot_gpa) if run.snapshot_gpa is not None else None,
            "ielts": str(run.snapshot_ielts) if run.snapshot_ielts is not None else None,
            "sat": run.snapshot_sat,
            "grade": run.snapshot_grade,
            "graduation_year": run.snapshot_graduation_year,
        },
        "funnel": {
            "catalog": run.funnel_catalog,
            "filtered": run.funnel_filtered,
            "analyzed": run.funnel_analyzed,
            "final": run.funnel_final,
        },
        "strategy": {
            "position": run.strategy_position,
            "improve": run.strategy_improve,
            "next_step": run.strategy_next,
            "offline": run.strategy_offline,
        },
    }
    if with_results:
        student = run.student
        favorites = set(FavoriteProgram.objects.filter(student=student).values_list("program_id", flat=True))
        listed = set(StudentUniversity.objects.filter(student=student).values_list("program_id", flat=True))
        rows = run.results.select_related("program__university").all()
        payload["results"] = [
            {
                "id": row.pk,
                "program": row.program_id,
                "program_name": row.program.name,
                "university": row.program.university_id,
                "university_name": row.program.university.name,
                "country": row.program.university.country,
                "world_rank": row.program.university.world_rank,
                "is_verified": row.program.is_verified,
                "percent_now": row.percent_now,
                "percent_goal": row.percent_goal,
                "tier": row.tier,
                "tier_title": row.get_tier_display() if row.tier else "",
                "section": row.section,
                "is_favorite": row.program_id in favorites,
                "in_my_list": row.program_id in listed,
            }
            for row in rows
        ]
        payload["methodology"] = methodology()
        tiers = {}
        for row in rows:
            if row.section == "top" and row.tier:
                tiers[row.tier] = tiers.get(row.tier, 0) + 1
        payload["tiers"] = tiers
    return payload


@extend_schema(request=None, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def selection_start(request):
    """Запустить подбор. Считается в фоне, экран можно свернуть."""
    from universities.selection import start_run

    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "Подбор запускает ученик"}, status=status.HTTP_403_FORBIDDEN)
    if MatchRun.objects.filter(student=student, status="running").exists():
        return Response({"detail": "Подбор уже считается — дождитесь результата"}, status=status.HTTP_409_CONFLICT)

    major = str(request.data.get("major") or "")[:150]
    level = str(request.data.get("level") or "")
    countries = [str(c)[:100] for c in (request.data.get("countries") or [])][:20]
    run = start_run(student, major=major, level=level, countries=countries)
    return Response(_run_payload(run), status=status.HTTP_201_CREATED)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def selection_runs(request):
    """История подборов ученика: дата, специальность, охват."""
    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "История подборов — экран ученика"}, status=status.HTTP_403_FORBIDDEN)
    rows = MatchRun.objects.filter(student=student)[:30]
    return Response({"results": [_run_payload(run) for run in rows]})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def selection_active(request):
    """Текущий считающийся прогон — для плашки поверх любого экрана."""
    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"run": None})
    run = MatchRun.objects.filter(student=student, status="running").first()
    return Response({"run": _run_payload(run) if run else None})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def selection_run_detail(request, pk: int):
    """Результат прогона — снимок с датой; свой и только свой."""
    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "Результат подбора — экран ученика"}, status=status.HTTP_403_FORBIDDEN)
    run = MatchRun.objects.filter(pk=pk, student=student).first()
    if run is None:
        return Response({"detail": "Такого подбора нет"}, status=status.HTTP_404_NOT_FOUND)
    return Response(_run_payload(run, with_results=run.status == "done"))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def selection_explain(request, pk: int, program_id: int):
    """«Почему такой процент» — живой разбор по позициям.

    Снимок в карточке — на дату прогона; разбор считается по текущему
    профилю, и если числа разошлись, об этом сказано прямо.
    """
    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "Разбор — экран ученика"}, status=status.HTTP_403_FORBIDDEN)
    run = MatchRun.objects.filter(pk=pk, student=student).first()
    row = run.results.filter(program_id=program_id).select_related("program__university").first() if run else None
    if row is None:
        return Response({"detail": "Этой программы нет в подборе"}, status=status.HTTP_404_NOT_FOUND)

    live = match(student, row.program)
    payload = live.as_dict()
    payload["snapshot_percent"] = row.percent_now
    payload["percent_goal"] = row.percent_goal
    payload["profile_changed"] = live.percent != row.percent_now
    if payload["profile_changed"]:
        payload["profile_changed_note"] = (
            f"С даты подбора профиль изменился: сейчас соответствие {live.percent}%. "
            "Перезапустите подбор, чтобы обновить снимок"
        )
    return Response(payload)


@extend_schema(request=None, responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def favorites_view(request):
    """Избранное: «присмотрел», в отличие от списка «подаюсь»."""
    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "Избранное — экран ученика"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "POST":
        program = Program.objects.filter(pk=request.data.get("program")).first()
        if program is None:
            return Response({"detail": "Такой программы нет"}, status=status.HTTP_404_NOT_FOUND)
        row, made = FavoriteProgram.objects.get_or_create(student=student, program=program)
        return Response({"id": row.pk, "created": made}, status=status.HTTP_201_CREATED if made else status.HTTP_200_OK)

    listed = set(StudentUniversity.objects.filter(student=student).values_list("program_id", flat=True))
    rows = FavoriteProgram.objects.filter(student=student).select_related("program__university")
    return Response(
        {
            "count": rows.count(),
            "results": [
                {
                    "id": row.pk,
                    "program": row.program_id,
                    "program_name": row.program.name,
                    "university_name": row.program.university.name,
                    "country": row.program.university.country,
                    "level_title": row.program.get_level_display(),
                    "in_my_list": row.program_id in listed,
                    "created_at": row.created_at,
                }
                for row in rows
            ],
        }
    )


@extend_schema(responses={200: dict})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def favorite_remove(request, program_id: int):
    """Снять сердечко — по программе. Истории у отметки нет, удаление физическое."""
    student = getattr(request.user, "student", None)
    row = FavoriteProgram.objects.filter(program_id=program_id, student=student).first() if student else None
    if row is None:
        return Response({"detail": "Такой отметки нет"}, status=status.HTTP_404_NOT_FOUND)
    row.delete()
    return Response({"detail": "Убрано из избранного"})


# --- Стипендии (фаза 44) ---------------------------------------------------


class ScholarshipViewSet(ConfirmOnEditMixin, HardDeleteMixin, viewsets.ModelViewSet):
    """Справочник стипендий. Ведёт директор по поступлению, читают все.

    Удаление физическое: истории у справочной записи нет (инвариант №13).
    Сохранение стипендии учеником — не запись справочника, а отметка;
    она живёт отдельным действием и справочнику не мешает.
    """

    queryset = Scholarship.objects.select_related("university").all()
    serializer_class = ScholarshipSerializer
    permission_classes = [DomainFieldPermission]
    domain_model_label = "universities.Scholarship"
    search_fields = ("name", "organizer", "country")

    def get_queryset(self):
        from universities.scholarships import ScholarshipFilters, apply_filters, base_queryset

        student = getattr(self.request.user, "student", None)
        qs = base_queryset(for_student=self.request.user.role == ROLE_STUDENT and student is not None)
        return apply_filters(qs, ScholarshipFilters.from_request(self.request.query_params))

    def get_serializer_context(self):
        from universities.scholarships import saved_ids

        context = super().get_serializer_context()
        context["saved_ids"] = saved_ids(getattr(self.request.user, "student", None))
        return context

    def create(self, request, *args, **kwargs):
        # заводить записи в чужом справочнике нельзя: у чужого директора
        # все поля read_only, и без этой проверки он завёл бы пустую строку
        if not owns_model(request.user.role, self.domain_model_label):
            return refuse(request.user.role, self.domain_model_label)
        return super().create(request, *args, **kwargs)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def scholarship_overview(request):
    """Три числа сверху каталога и состав фильтров.

    Сумма финансирования считается по каждой валюте отдельно: складывать
    доллары с евро по выдуманному курсу нельзя.
    """
    from universities.scholarships import ScholarshipFilters, apply_filters, base_queryset, facets, stats

    student = getattr(request.user, "student", None)
    everything = base_queryset(for_student=request.user.role == ROLE_STUDENT and student is not None)
    filtered = apply_filters(everything, ScholarshipFilters.from_request(request.query_params))
    return Response({**stats(filtered), "facets": facets(everything)})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def saved_scholarships(request):
    """Сохранённые стипендии ученика — тот же механизм, что избранное вузов."""
    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "Сохранённые стипендии — экран ученика"}, status=status.HTTP_403_FORBIDDEN)
    rows = SavedScholarship.objects.filter(student=student).select_related("scholarship__university")
    serializer = ScholarshipSerializer(
        [row.scholarship for row in rows],
        many=True,
        context={"request": request, "saved_ids": {row.scholarship_id for row in rows}},
    )
    return Response({"count": len(serializer.data), "results": serializer.data})


@extend_schema(responses={200: dict})
@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def save_scholarship(request, pk: int):
    """Сохранить стипендию или снять отметку. Истории у отметки нет."""
    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "Сохранять стипендии может ученик"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "DELETE":
        row = SavedScholarship.objects.filter(student=student, scholarship_id=pk).first()
        if row is None:
            return Response({"detail": "Такой отметки нет"}, status=status.HTTP_404_NOT_FOUND)
        row.delete()
        return Response({"detail": "Убрано из сохранённых"})

    scholarship = Scholarship.objects.filter(pk=pk, is_active=True).first()
    if scholarship is None:
        return Response({"detail": "Такой стипендии нет"}, status=status.HTTP_404_NOT_FOUND)
    row, made = SavedScholarship.objects.get_or_create(student=student, scholarship=scholarship)
    return Response(
        {"id": row.pk, "created": made, "detail": "Сохранено. Дедлайн появится в календаре"},
        status=status.HTTP_201_CREATED if made else status.HTTP_200_OK,
    )


@extend_schema(responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pick_scholarships(request):
    """Подбор стипендий под профиль: отбирают правила, формулирует модель.

    Инвариант №10: в ответе могут появиться только стипендии справочника —
    модель получает их номера и ссылается на них, а не называет своими
    словами. Справочник пуст — так и говорится.
    """
    from universities.scholarships import pick_for

    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "Подбор стипендий — экран ученика"}, status=status.HTTP_403_FORBIDDEN)
    return Response(pick_for(student, actor=request.user, role=request.user.role))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def scholarship_attention(request):
    """Кто сохранил стипендии, у кого дедлайн на неделе, кто не сохранил."""
    from core.domains import DOMAINS, ROLE_ADMIN
    from universities.scholarships import attention

    if request.user.role not in (DOMAINS["admission"].role, ROLE_ADMIN):
        return Response(
            {"detail": "Сводка по стипендиям — у директора по поступлению"}, status=status.HTTP_403_FORBIDDEN
        )
    return Response(attention())


@extend_schema(request=RequirementImportSerializer, responses={200: dict})
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def import_scholarships_view(request):
    """Загрузка стипендий из XLSX/CSV. Файл грузит администратор за домен «Поступление»."""
    from core.domains import DOMAINS, can_upload_files
    from students.import_service import read_table
    from universities.import_scholarships import TARGET_FIELDS, import_scholarships

    if not can_upload_files(request.user.role):
        return Response(
            {"detail": "Файлы загружает администратор. Стипендии заводятся руками в справочнике"},
            status=status.HTTP_403_FORBIDDEN,
        )
    domain = DOMAINS["admission"]

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)

    header, rows = read_table(uploaded)
    raw_mapping = request.data.get("mapping") or "{}"
    mapping = json.loads(raw_mapping) if isinstance(raw_mapping, str) else raw_mapping
    if not mapping:
        return Response({"columns": header, "total_rows": len(rows), "targets": TARGET_FIELDS})

    dry_run = str(request.data.get("dry_run", "")).lower() in {"1", "true", "yes"}
    if dry_run:
        return Response(import_scholarships(header=header, rows=rows, mapping=mapping, dry_run=True).as_dict())

    batch = ImportBatch.objects.create(
        actor=request.user,
        file_name=getattr(uploaded, "name", "") or "",
        kind=ImportBatch.Kind.SCHOLARSHIPS,
        domain_code=domain.code,
        rows_total=len(rows),
    )
    with importing(batch):
        report = import_scholarships(header=header, rows=rows, mapping=mapping, dry_run=False)

    payload = report.as_dict()
    batch.rows_created = payload.get("created", 0)
    batch.rows_updated = payload.get("updated", 0)
    batch.rows_failed = len(payload.get("errors", []))
    if batch.rows_created:
        batch.note = "Отмена вернёт прежние значения, но заведённые стипендии не удалит"
    batch.save(update_fields=["rows_created", "rows_updated", "rows_failed", "note"])
    payload["batch"] = batch.pk
    return Response(payload)
