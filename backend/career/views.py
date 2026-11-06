"""Ручки профтеста: тесты и разборы — учителю профориентации, прохождение — ученику.

Кто что может — `career/rights.py`. Шлюзы ролей (куратор, учитель) пускают
маршруты по имени, границу «своя группа» держат `visible_group_ids`
и `sees_student`: чужая группа — 404, не 403.
"""

from __future__ import annotations

import uuid

from django.db.models import Count, Exists, OuterRef, Q
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics.payloads import student_brief
from career import analysis as analyses
from career import exports, files, payloads, rights, scoring, services, word
from career.models import (
    AnalysisStatus,
    AttemptStatus,
    CareerAnalysis,
    CareerAttempt,
    CareerAttemptAnswer,
    CareerItemChoice,
    CareerTest,
    CareerTestOption,
    ExportStatus,
    ItemKind,
)
from career.tasks import JOB_KIND
from core import jobs, usage
from core.domains import ROLE_ADMIN, ROLE_STUDENT
from core.exports import _disposition
from core.i18n import language_of
from students.models import Student, StudyGroup

MAX_UPLOAD = 5 * 1024 * 1024
#: Ученику показываются только его баллы; разборы ему не отдаются (решение владельца,
#: 09.10.2026: «скроем, удалять не надо»). Механика показа и версия на «ты» остаются
#: в коде и базе — включается этим флагом.
STUDENT_SEES_ANALYSIS = False
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _forbid(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


def _not_found() -> Response:
    return Response({"detail": _("Не найдено")}, status=status.HTTP_404_NOT_FOUND)


def _bad(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


MANAGE_REFUSAL = gettext_lazy("Тесты профориентации ведёт учитель профориентации и администратор")
READ_REFUSAL = gettext_lazy(
    "Результаты профтеста читают учитель профориентации, директор по поступлению и администратор"
)


def _manager(request) -> Response | None:
    if not rights.manages(request.user):
        return _forbid(str(MANAGE_REFUSAL))
    return None


def _reader(request) -> Response | None:
    if getattr(request.user, "role", "") == ROLE_STUDENT or not rights.reads(request.user):
        return _forbid(str(READ_REFUSAL))
    return None


def _own_student(request) -> Student | None:
    if getattr(request.user, "role", "") != ROLE_STUDENT:
        return None
    return getattr(request.user, "student", None)


def _test_or_none(user, pk: int) -> CareerTest | None:
    """Живой тест — любому, кто ведёт профтест: тест общий для школы.

    Кто загрузил и кому назначен, не важно (решение владельца, 06.11.2026);
    граница по группам — только у учеников, назначений и результатов.
    """
    if not rights.manages(user):
        return None
    return CareerTest.objects.filter(pk=pk, archived_at__isnull=True).first()


def _scope_group_ids(user) -> set[int] | None:
    """Группы, по которым человеку считаются назначения и попытки; администратору — все (None)."""
    if getattr(user, "role", "") == ROLE_ADMIN:
        return None
    return set(rights.visible_group_ids(user))


def _scoped_groups(test: CareerTest, scope: set[int] | None) -> list[dict]:
    rows = services.assigned_groups(test)
    if scope is None:
        return rows
    return [row for row in rows if row["group"].pk in scope]


def _can_remove(user, test: CareerTest) -> bool:
    """Удалить или убрать в архив — автор и администратор: тест общий, чужой не трогаем."""
    return getattr(user, "role", "") == ROLE_ADMIN or test.created_by_id == user.pk


def _int(raw) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _group_for(request, raw) -> StudyGroup | None:
    gid = _int(raw)
    if gid is None or not rights.sees_group(request.user, gid):
        return None
    return StudyGroup.objects.filter(pk=gid).first()


# --- Тесты: список, загрузка, включение, назначение ---------------------------------


def _counts(tests: list[CareerTest], scope: set[int] | None) -> dict[int, dict]:
    """Сколько назначено, сдано и идёт — по каждому тесту одним проходом.

    Учителю — по его группам, администратору — по всем (`scope is None`).
    """
    out = {test.pk: {"assigned": 0, "done": 0, "in_progress": 0} for test in tests}
    ids = list(out)
    attempts = CareerAttempt.objects.filter(test_id__in=ids, archived_at__isnull=True)
    if scope is not None:
        attempts = attempts.filter(student__group_id__in=scope)
    for row in attempts.values("test_id", "status").annotate(n=Count("id")):
        key = "done" if row["status"] == AttemptStatus.DONE else "in_progress"
        out[row["test_id"]][key] = row["n"]
    for test in tests:
        seen: set[int] = set()
        for entry in _scoped_groups(test, scope):
            seen.update(services.assigned_student_ids(test, entry["group"]))
        out[test.pk]["assigned"] = len(seen)
    return out


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def tests(request):
    """Список тестов — тем, кто ведёт; загрузка файла — там же."""
    if request.method == "POST":
        return _upload(request, apply=True)
    refused = _reader(request)
    if refused:
        return refused
    user = request.user
    # тест общий для школы: все живые тесты — каждому, кто ведёт (решение владельца, 06.11.2026)
    rows = list(
        services.live_tests()
        .select_related("created_by")
        .annotate(
            n_items=Count("items", distinct=True),
            n_scales=Count("scales", distinct=True),
        )
        # попытки — подзапросом: третий Count по join умножал строки items × scales × attempts,
        # и на проде с сотнями попыток список тестов не успевал ответить
        .annotate(has_attempts=Exists(CareerAttempt.objects.filter(test_id=OuterRef("pk"))))
    )
    counts = _counts(rows, _scope_group_ids(user))
    return Response(
        {
            "manage": rights.manages(user),
            "tests": [
                payloads.test_row(
                    t,
                    items=t.n_items,
                    scales=t.n_scales,
                    used=t.has_attempts,
                    can_remove=_can_remove(user, t),
                    **counts[t.pk],
                )
                for t in rows
            ],
        }
    )


def _upload(request, *, apply: bool) -> Response:
    refused = _manager(request)
    if refused:
        return refused
    upload = request.FILES.get("file")
    if upload is None:
        return _bad(_("Приложите файл xlsx"))
    if upload.size > MAX_UPLOAD:
        return _bad(_("Файл больше 5 МБ"))
    data = upload.read()
    parsed = files.parse(data)
    if not apply:
        return Response(parsed.report())
    if not parsed.ok:
        return Response(
            {**parsed.report(), "detail": _("В файле есть ошибки — исправьте и загрузите снова")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    test = services.create_test(parsed, data=data, file_name=upload.name or "test.xlsx", actor=request.user)
    usage.track(request, "career.test.upload")
    return Response(payloads.test_detail(test, []), status=status.HTTP_201_CREATED)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def test_preview(request):
    """Проверка файла без записи: что нашлось и что не так."""
    return _upload(request, apply=False)


@extend_schema(responses={200: bytes})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def test_template(request):
    refused = _manager(request)
    if refused:
        return refused
    response = HttpResponse(files.template(), content_type=XLSX)
    response["Content-Disposition"] = 'attachment; filename="career-test-template.xlsx"'
    return response


@extend_schema(responses={200: dict})
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def test_detail(request, pk: int):
    refused = _reader(request)
    if refused:
        return refused
    test = _test_or_none(request.user, pk)
    if test is None:
        return _not_found()
    scope = _scope_group_ids(request.user)
    if request.method == "GET":
        return Response(payloads.test_detail(test, _scoped_groups(test, scope)))
    refused = _manager(request)
    if refused:
        return refused
    if request.method == "DELETE":
        if not _can_remove(request.user, test):
            return _forbid(_("Удалить тест может тот, кто его загрузил, и администратор"))
        if test.attempts.exists():
            test.archived_at = timezone.now()
            test.is_active = False
            test.save(update_fields=["archived_at", "is_active"])
            return Response({"archived": True})
        test.file.delete(save=False)
        # вопросы держат шкалы PROTECT: без попыток тест уходит целиком, вопросами вперёд
        test.items.all().delete()
        test.delete()
        return Response({"archived": False})
    body = request.data if isinstance(request.data, dict) else {}
    fields: list[str] = []
    if "is_active" in body:
        test.is_active = bool(body["is_active"])
        fields.append("is_active")
    if "analysis_min_score" in body:
        number = _int(body["analysis_min_score"])
        if number is None or not -100 <= number <= 100:
            return _bad(_("Порог для разбора — целое число"))
        test.analysis_min_score = number
        fields.append("analysis_min_score")
    if "title" in body:
        title = str(body["title"] or "").strip()
        if not title:
            return _bad(_("Название не может быть пустым"))
        test.title = title[:200]
        fields.append("title")
    if fields:
        test.save(update_fields=fields)
    return Response(payloads.test_detail(test, _scoped_groups(test, scope)))


@extend_schema(responses={200: bytes})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def test_file(request, pk: int):
    refused = _reader(request)
    if refused:
        return refused
    test = _test_or_none(request.user, pk)
    if test is None or not test.file:
        return _not_found()
    response = FileResponse(test.file.open("rb"), content_type=XLSX)
    response["Content-Disposition"] = f'attachment; filename="career-test-{test.pk}.xlsx"'
    response["Cache-Control"] = "private, no-store"
    return response


@extend_schema(request=dict, responses={200: dict})
@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def test_assignments(request, pk: int):
    """Кому открыт тест: `{"groups": [{"group": 1, "students": null | [ids]}]}`."""
    refused = _manager(request)
    if refused:
        return refused
    test = _test_or_none(request.user, pk)
    if test is None:
        return _not_found()
    allowed = set(rights.visible_group_ids(request.user)) if request.user.role != ROLE_ADMIN else None
    if allowed is not None:
        allowed &= set(rights.taught_group_ids(request.user))
    body = request.data if isinstance(request.data, dict) else {}
    rows = body.get("groups")
    if not isinstance(rows, list):
        return _bad(_("Нужен список групп"))
    plan: list[dict] = []
    for row in rows:
        gid = _int((row or {}).get("group"))
        if gid is None or (allowed is not None and gid not in allowed):
            return _bad(_("Группа не из ваших составов"))
        group = StudyGroup.objects.filter(pk=gid, is_active=True).first()
        if group is None:
            return _bad(_("Группа не найдена"))
        picked = row.get("students")
        if picked is None:
            plan.append({"group": group, "students": None})
            continue
        if not isinstance(picked, list):
            return _bad(_("Список учеников — числа"))
        ids = [i for i in (_int(x) for x in picked) if i is not None]
        students = list(Student.objects.filter(pk__in=ids, group=group, is_active=True))
        if not students:
            continue
        plan.append({"group": group, "students": students})
    # назначения чужих групп (другого учителя, администратора) учитель не видит и не стирает
    services.assign(test, plan, actor=request.user, within=allowed)
    return Response(payloads.test_detail(test, _scoped_groups(test, _scope_group_ids(request.user))))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def groups(request):
    """Группы человека с учениками: назначать (свои составы) и смотреть (своя граница)."""
    refused = _reader(request)
    if refused:
        return refused
    user = request.user
    visible = rights.visible_group_ids(user)
    assignable = set(visible) if user.role == ROLE_ADMIN else set(rights.taught_group_ids(user))
    rows = StudyGroup.objects.filter(pk__in=visible).order_by("parallel", "code")
    students = Student.objects.filter(group_id__in=visible, is_active=True).order_by("last_name", "first_name", "id")
    by_group: dict[int, list[dict]] = {}
    for student in students:
        by_group.setdefault(student.group_id, []).append(student_brief(student))
    return Response(
        {
            "manage": rights.manages(user),
            "groups": [
                {
                    "id": g.pk,
                    "code": g.code,
                    "parallel": g.parallel,
                    "assignable": g.pk in assignable,
                    "students": by_group.get(g.pk, []),
                }
                for g in rows
            ],
        }
    )


# --- Результаты и попытки --------------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def results(request):
    """Ученики группы × тесты, назначенные группе: кто сдал, кто идёт, кто не начинал."""
    refused = _reader(request)
    if refused:
        return refused
    group = _group_for(request, request.query_params.get("group"))
    if group is None:
        return Response({"group": None, "tests": [], "students": []})
    tests_q = services.live_tests().filter(Q(assignments__group=group) | Q(attempts__student__group=group)).distinct()
    tests_rows = list(tests_q.order_by("created_at", "id"))
    students = list(Student.objects.filter(group=group, is_active=True).order_by("last_name", "first_name", "id"))
    attempts = CareerAttempt.objects.filter(
        test__in=tests_rows, student__in=students, archived_at__isnull=True
    ).annotate(answered=Count("answers"))
    cells: dict[tuple[int, int], dict] = {}
    for attempt in attempts:
        cells[(attempt.student_id, attempt.test_id)] = {
            "status": attempt.status,
            "attempt": attempt.pk,
            "finished_at": attempt.finished_at,
            "answered": attempt.answered,
        }
    assigned = {test.pk: set(services.assigned_student_ids(test, group)) for test in tests_rows}
    return Response(
        {
            "group": {"id": group.pk, "code": group.code, "parallel": group.parallel},
            "tests": [
                {**payloads.test_brief(t), "items": t.items.count(), "assigned": len(assigned[t.pk])}
                for t in tests_rows
            ],
            "students": [
                {
                    **student_brief(s),
                    "cells": {
                        str(t.pk): cells.get(
                            (s.pk, t.pk), {"status": "assigned" if s.pk in assigned[t.pk] else "none", "attempt": None}
                        )
                        for t in tests_rows
                    },
                }
                for s in students
            ],
        }
    )


def _attempt_for_staff(request, pk: int) -> CareerAttempt | None:
    attempt = CareerAttempt.objects.select_related("test", "student", "student__group").filter(pk=pk).first()
    if attempt is None or not rights.sees_student(request.user, attempt.student):
        return None
    return attempt


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attempt_detail(request, pk: int):
    refused = _reader(request)
    if refused:
        return refused
    attempt = _attempt_for_staff(request, pk)
    if attempt is None:
        return _not_found()
    return Response(payloads.attempt_dict(attempt, with_student=True))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def attempt_retake(request, pk: int):
    """Разрешить пройти заново: попытка уходит в историю, разборы по ней остаются."""
    refused = _manager(request)
    if refused:
        return refused
    attempt = _attempt_for_staff(request, pk)
    if attempt is None:
        return _not_found()
    if attempt.archived_at is not None:
        return _bad(_("Эта попытка уже в истории"))
    services.allow_retake(attempt, actor=request.user)
    return Response(payloads.attempt_dict(attempt, with_student=True))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_results(request, pk: int):
    """Блок «Профтест» в карточке ученика: сданные тесты с баллами и разборы."""
    refused = _reader(request)
    if refused:
        return refused
    student = Student.objects.select_related("group").filter(pk=pk).first()
    if student is None or not rights.sees_student(request.user, student):
        return _not_found()
    attempts = (
        CareerAttempt.objects.filter(student=student, archived_at__isnull=True, test__archived_at__isnull=True)
        .select_related("test")
        .order_by("-finished_at", "-started_at")
    )
    rows = CareerAnalysis.objects.filter(student=student).select_related("created_by", "edited_by")
    return Response(
        {
            "student": student_brief(student),
            "attempts": [payloads.attempt_dict(a) for a in attempts],
            "analyses": [payloads.analysis_dict(a) for a in rows],
        }
    )


# --- Разборы ---------------------------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def analyses_view(request):
    if request.method == "POST":
        return _start_analyses(request)
    refused = _reader(request)
    if refused:
        return refused
    group = _group_for(request, request.query_params.get("group"))
    if group is None:
        return Response({"group": None, "tests": [], "analyses": []})
    students = Student.objects.filter(group=group, is_active=True)
    done = (
        CareerAttempt.objects.filter(
            student__in=students, status=AttemptStatus.DONE, archived_at__isnull=True, test__archived_at__isnull=True
        )
        .values("test_id", "test__title")
        .annotate(n=Count("id"))
        .order_by("test__created_at")
    )
    rows = CareerAnalysis.objects.filter(student__in=students).select_related(
        "student", "student__group", "created_by", "edited_by"
    )
    run = jobs.latest_for(kind=JOB_KIND, target=group)
    versions = _version_runs(list(rows), request.user)
    return Response(
        {
            "manage": rights.manages(request.user),
            "student_sees": STUDENT_SEES_ANALYSIS,
            "group": {"id": group.pk, "code": group.code, "parallel": group.parallel},
            "tests": [{"id": r["test_id"], "title": r["test__title"], "done": r["n"]} for r in done],
            "analyses": [{**payloads.analysis_dict(a), "version_run": versions.get(a.pk)} for a in rows],
            # последний запуск по группе: «идёт с 11:42», отмена, причина сбоя
            "run": jobs.payload(run, request.user) if run else None,
        }
    )


def _version_runs(rows: list[CareerAnalysis], viewer) -> dict[int, dict]:
    """Последний запуск версии для ученика у каждого разбора — одним запросом."""
    from career.tasks import VERSION_KIND
    from core.models import BackgroundJob

    if not rows:
        return {}
    out: dict[int, dict] = {}
    found = BackgroundJob.objects.filter(
        kind=VERSION_KIND, target_model="career.CareerAnalysis", target_id__in=[row.pk for row in rows]
    ).order_by("created_at")
    for job in found:
        out[job.target_id] = jobs.payload(job, viewer)
    return out


def _start_analyses(request) -> Response:
    """Запуск: `{"group": 1, "tests": [ids], "students": null | [ids], "force": false}`."""
    refused = _manager(request)
    if refused:
        return refused
    body = request.data if isinstance(request.data, dict) else {}
    group = _group_for(request, body.get("group"))
    if group is None:
        return _bad(_("Группа не найдена"))
    test_ids = [i for i in (_int(x) for x in (body.get("tests") or [])) if i is not None]
    tests_rows = list(services.live_tests().filter(pk__in=test_ids))
    if not tests_rows:
        return _bad(_("Выберите хотя бы один тест"))
    students = Student.objects.filter(group=group, is_active=True).order_by("last_name", "first_name", "id")
    picked = body.get("students")
    if isinstance(picked, list):
        ids = [i for i in (_int(x) for x in picked) if i is not None]
        students = students.filter(pk__in=ids)
    # разбор этой группы уже идёт — второй не заводим, кнопка ведёт к идущему
    running = jobs.active_for(kind=JOB_KIND, target=group)
    if running is not None:
        return Response(
            {
                "created": 0,
                "reused": 0,
                "skipped": [],
                "job": running.pk,
                "already": True,
                "run": jobs.payload(running, request.user),
            },
            status=status.HTTP_200_OK,
        )
    plan = analyses.plan(list(students), tests_rows, force=bool(body.get("force")))
    language = language_of(request.user)
    created: list[CareerAnalysis] = [
        analyses.open_analysis(student, attempts, actor=request.user, language=language)
        for student, attempts in plan.create
    ]
    job_id = None
    if created:
        from career.tasks import analyze

        task_id = uuid.uuid4().hex
        job = jobs.start(
            user=request.user,
            kind=JOB_KIND,
            title=_("Разбор профтеста: {n}").format(n=len(created)),
            task_id=task_id,
            link="/career-tests?tab=analyses",
            # повтор — запуском заново с экрана: строки отменённого запуска закрыты
            target=group,
        )
        CareerAnalysis.objects.filter(pk__in=[row.pk for row in created]).update(job=job)
        job_id = job.pk
        analyze.apply_async(kwargs={"analysis_ids": [row.pk for row in created]}, task_id=task_id)
        usage.track(request, "career.analysis.start")
    return Response(
        {
            "created": len(created),
            "reused": len(plan.reuse),
            "skipped": [{"student": student_brief(s), "reason": reason} for s, reason in plan.skipped],
            "job": job_id,
        },
        status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK,
    )


def _analysis_for(request, pk: int) -> CareerAnalysis | None:
    row = (
        CareerAnalysis.objects.select_related("student", "student__group", "created_by", "edited_by")
        .filter(pk=pk)
        .first()
    )
    if row is None or not rights.sees_student(request.user, row.student):
        return None
    return row


@extend_schema(responses={200: dict})
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def analysis_detail(request, pk: int):
    refused = _reader(request)
    if refused:
        return refused
    row = _analysis_for(request, pk)
    if row is None:
        return _not_found()
    if request.method == "GET":
        return Response({**payloads.analysis_dict(row), "version_run": _version_runs([row], request.user).get(row.pk)})
    refused = _manager(request)
    if refused:
        return refused
    body = request.data if isinstance(request.data, dict) else {}
    edited = False
    wants_version = False
    if "visible_to_student" in body:
        if row.status != AnalysisStatus.DONE and bool(body["visible_to_student"]):
            return _bad(_("Показать ученику можно только готовый разбор"))
        # первый показ — версия для ученика пишется моделью; без неё показывать нечего (Г1).
        # Переписывание идёт минутами — в фоне; разбор покажется ученику, когда версия готова
        if bool(body["visible_to_student"]) and not row.summary_student and "summary_student" not in body:
            wants_version = True
        else:
            row.visible_to_student = bool(body["visible_to_student"])
            row.save(update_fields=["visible_to_student"])
    if "summary" in body:
        row.summary = str(body["summary"] or "").strip()
        edited = True
    if "summary_student" in body:
        row.summary_student = str(body["summary_student"] or "").strip()
        edited = True
    for item in body.get("directions") or []:
        did = _int((item or {}).get("id"))
        direction = row.directions.filter(pk=did).first() if did else None
        if direction is None:
            continue
        for field_name, limit in (
            ("title", 150),
            ("title_abroad", 150),
            ("reasoning", 0),
            ("reasoning_student", 0),
            ("professions", 0),
            ("exams", 0),
            ("subjects", 0),
            ("next_steps", 0),
        ):
            if field_name in item:
                value = str(item[field_name] or "").strip()
                if field_name == "title" and not value:
                    return _bad(_("Название направления не может быть пустым"))
                setattr(direction, field_name, value[:limit] if limit else value)
                edited = True
        direction.save()
        # профессии и программы с объяснением: правится название профессии и текст
        for entry in item.get("items") or []:
            iid = _int((entry or {}).get("id"))
            line = direction.items.filter(pk=iid).first() if iid else None
            if line is None:
                continue
            if "title" in entry and line.kind == ItemKind.PROFESSION:
                title = str(entry["title"] or "").strip()
                if not title:
                    return _bad(_("Название профессии не может быть пустым"))
                line.title = title[:200]
            if "text" in entry:
                line.text = str(entry["text"] or "").strip()
            line.save(update_fields=["title", "text"])
            edited = True
    if edited:
        row.edited_at = timezone.now()
        row.edited_by = request.user
        row.save(update_fields=["summary", "summary_student", "edited_at", "edited_by"])
    if wants_version:
        # после правок: модель переписывает уже исправленный текст учителя
        from career.tasks import VERSION_KIND, student_version

        job, _created = jobs.launch(
            user=request.user,
            kind=VERSION_KIND,
            title=_("Версия разбора для ученика: {name}").format(name=student_brief(row.student)["short"]),
            task=student_version,
            kwargs={"analysis_id": row.pk, "actor_id": request.user.pk},
            target=row,
            link="/career-tests?tab=analyses",
        )
        job.refresh_from_db()
        row.refresh_from_db()
        return Response(
            {**payloads.analysis_dict(row), "version_run": jobs.payload(job, request.user)},
            status=status.HTTP_202_ACCEPTED,
        )
    return Response(payloads.analysis_dict(row))


# --- Выгрузка в Word --------------------------------------------------------------------


@extend_schema(responses={200: bytes})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_word(request, pk: int):
    """Word одного ученика сразу — когда модель не нужна; иначе 409 «нужно подготовить»."""
    refused = _manager(request)
    if refused:
        return refused
    student = Student.objects.select_related("group").filter(pk=pk).first()
    if student is None or not rights.sees_student(request.user, student):
        return _not_found()
    language = exports.language_or_none(request.query_params.get("language")) or language_of(request.user)
    try:
        prepared = exports.immediate(student, language=language, actor=request.user)
    except exports.NeedsPreparation as error:
        return Response({"detail": str(error), "prepare": True}, status=status.HTTP_409_CONFLICT)
    except exports.Refused as error:
        return _bad(str(error))
    usage.track(request, "career.export.word")
    response = HttpResponse(prepared.payload, content_type=word.DOCX_TYPE)
    response["Content-Disposition"] = _disposition(prepared.name, word.DOCX_TYPE)
    return response


def _export_for(request, pk: int):
    """Выгрузка — тому, кто запускал, и администратору; остальным её нет."""
    from career.models import CareerExport

    row = CareerExport.objects.select_related("group", "job").filter(pk=pk).first()
    if row is None or not exports.can_download(row, request.user):
        return None
    return row


@extend_schema(request=dict, responses={200: dict, 202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def exports_view(request):
    """Скачать Word: `{"language": "kk", "group": 1}` или `{"language": "kk", "students": [ids]}`.

    Один ученик, модель не нужна — `{"ready": true, "url": …}`, файл отдаётся сразу.
    Иначе — подготовка в фоне: `{"ready": false, "export": {…}}`; такая же уже
    идёт — ведём к ней (`already`).
    """
    from career.models import CareerExport

    refused = _manager(request)
    if refused:
        return refused
    body = request.data if isinstance(request.data, dict) else {}
    language = exports.language_or_none(body.get("language")) or language_of(request.user)
    whole_group = body.get("group") not in (None, "")
    if whole_group:
        group = _group_for(request, body.get("group"))
        if group is None:
            return _not_found()
        students = list(
            Student.objects.filter(group=group, is_active=True)
            .select_related("group")
            .order_by("last_name", "first_name", "id")
        )
    else:
        ids = [i for i in (_int(x) for x in (body.get("students") or [])) if i is not None]
        if not ids:
            return _bad(_("Отметьте хотя бы одного ученика"))
        students = list(
            Student.objects.filter(pk__in=ids).select_related("group").order_by("last_name", "first_name", "id")
        )
        if len(students) != len(set(ids)) or not all(rights.sees_student(request.user, s) for s in students):
            return _not_found()
        group = students[0].group
    if not students:
        return _bad(_("В группе нет учеников"))
    if not whole_group and len(students) == 1 and not exports.needs_model(students[0], language):
        return Response(
            {"ready": True, "url": f"/career/students/{students[0].pk}/word/?language={language}"},
            status=status.HTTP_200_OK,
        )
    ids = [student.pk for student in students]
    running = exports.running_for(request.user, group=group if whole_group else None, students=ids, language=language)
    if running is not None:
        return Response({"ready": False, "already": True, "export": exports.export_dict(running, request.user)})
    export = CareerExport.objects.create(
        owner=request.user, group=group, whole_group=whole_group, language=language, total=len(students)
    )
    from career.tasks import export_files

    job, _created = jobs.launch(
        user=request.user,
        kind=exports.JOB_KIND,
        title=exports.job_title(group, students, whole_group=whole_group),
        task=export_files,
        kwargs={"export_id": export.pk, "students": ids, "language": language, "actor_id": request.user.pk},
        target=group if whole_group else None,
        link=exports.link_of(export),
        same_args=True,
    )
    CareerExport.objects.filter(pk=export.pk, job__isnull=True).update(job=job)
    export.refresh_from_db()
    usage.track(request, "career.export.start")
    return Response(
        {"ready": False, "export": exports.export_dict(export, request.user)}, status=status.HTTP_202_ACCEPTED
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_detail(request, pk: int):
    """Ход и итог подготовки — тому, кто запускал, и администратору."""
    refused = _manager(request)
    if refused:
        return refused
    row = _export_for(request, pk)
    if row is None:
        return _not_found()
    if row.status == ExportStatus.DONE and exports.is_expired(row):
        exports.expire(row)
    return Response(exports.export_dict(row, request.user))


@extend_schema(responses={200: bytes})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_file(request, pk: int):
    """Готовый файл: тому, кто запускал, и администратору, пока не вышел срок хранения."""
    refused = _manager(request)
    if refused:
        return refused
    row = _export_for(request, pk)
    if row is None:
        return _not_found()
    if row.status == ExportStatus.DONE and exports.is_expired(row):
        exports.expire(row)
    if row.status != ExportStatus.DONE or not row.file:
        return Response(
            {"detail": _("Файла нет: срок хранения истёк или файл ещё не готов")}, status=status.HTTP_404_NOT_FOUND
        )
    kind = exports.ZIP_TYPE if row.file_name.endswith(".zip") else word.DOCX_TYPE
    response = FileResponse(row.file.open("rb"), content_type=kind)
    response["Content-Disposition"] = _disposition(row.file_name, kind)
    usage.track(request, "career.export.file")
    return response


# --- Ученик ----------------------------------------------------------------------------

STUDENT_ONLY = gettext_lazy("Профтест проходит ученик")


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my(request):
    """Тесты, открытые ученику, его попытки и разборы, которые ему показали."""
    student = _own_student(request)
    if student is None:
        return _forbid(str(STUDENT_ONLY))
    tests_rows = list(services.tests_for(student).annotate(n_items=Count("items", distinct=True)))
    attempts = {
        a.test_id: a
        for a in CareerAttempt.objects.filter(student=student, archived_at__isnull=True, test__in=tests_rows).annotate(
            answered=Count("answers")
        )
    }
    out = []
    for test in tests_rows:
        attempt = attempts.get(test.pk)
        out.append(
            {
                **payloads.test_brief(test),
                "instruction": test.instruction,
                "items": test.n_items,
                "status": attempt.status if attempt else "none",
                "attempt": attempt.pk if attempt else None,
                "answered": attempt.answered if attempt else 0,
                "finished_at": attempt.finished_at if attempt else None,
            }
        )
    shown = (
        CareerAnalysis.objects.filter(student=student, visible_to_student=True, status=AnalysisStatus.DONE)
        if STUDENT_SEES_ANALYSIS
        else CareerAnalysis.objects.none()
    )
    return Response({"tests": out, "analyses": [payloads.analysis_dict(a, for_student=True) for a in shown]})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_start(request, pk: int):
    student = _own_student(request)
    if student is None:
        return _forbid(str(STUDENT_ONLY))
    test = services.tests_for(student).filter(pk=pk).first()
    if test is None:
        return _not_found()
    attempt = services.start_attempt(test, student)
    return Response(_my_attempt_payload(attempt), status=status.HTTP_200_OK)


def _my_attempt(request, pk: int) -> tuple[Student | None, CareerAttempt | None]:
    student = _own_student(request)
    if student is None:
        return None, None
    attempt = CareerAttempt.objects.select_related("test").filter(pk=pk, student=student).first()
    return student, attempt


def _my_attempt_payload(attempt: CareerAttempt) -> dict:
    test = attempt.test
    out = payloads.attempt_dict(attempt)
    out["instruction"] = test.instruction
    if attempt.is_done:
        return out
    out["options"] = [payloads.option_dict(o) for o in test.options.all()]
    # ключ (шкала и знак) ученику не отдаётся — он отвечает, а не считает
    out["items"] = [
        {
            "id": item.pk,
            "number": item.number,
            "text": item.text,
            "choices": [{"id": c.pk, "label": c.label} for c in item.choices.all()],
        }
        for item in test.items.prefetch_related("choices")
    ]
    out["answers"] = {str(a.item_id): {"option": a.option_id, "choice": a.choice_id} for a in attempt.answers.all()}
    return out


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_attempt(request, pk: int):
    student, attempt = _my_attempt(request, pk)
    if student is None:
        return _forbid(str(STUDENT_ONLY))
    if attempt is None:
        return _not_found()
    return Response(_my_attempt_payload(attempt))


@extend_schema(request=dict, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_answers(request, pk: int):
    """Черновик на сервере: `{"answers": [{"item": id, "option": id} | {"item": id, "choice": id}]}`."""
    student, attempt = _my_attempt(request, pk)
    if student is None:
        return _forbid(str(STUDENT_ONLY))
    if attempt is None:
        return _not_found()
    if attempt.is_done or attempt.archived_at is not None:
        return _bad(_("Тест уже сдан"))
    if not attempt.test.is_active:
        return _bad(_("Тест выключен учителем"))
    body = request.data if isinstance(request.data, dict) else {}
    rows = body.get("answers")
    if not isinstance(rows, list):
        return _bad(_("Нужен список ответов"))
    items = {item.pk: item for item in attempt.test.items.all()}
    options = {o.pk: o for o in attempt.test.options.all()}
    choices = {c.pk: c for c in CareerItemChoice.objects.filter(item__test=attempt.test)}
    for row in rows:
        item_id = _int((row or {}).get("item"))
        item = items.get(item_id)
        if item is None:
            return _bad(_("Вопроса {number} в тесте нет").format(number=item_id))
        option_id, choice_id = _int(row.get("option")), _int(row.get("choice"))
        option: CareerTestOption | None = options.get(option_id) if option_id else None
        choice: CareerItemChoice | None = choices.get(choice_id) if choice_id else None
        if choice is not None and choice.item_id != item.pk:
            return _bad(_("Вариант не из этого вопроса"))
        if option is None and choice is None:
            CareerAttemptAnswer.objects.filter(attempt=attempt, item=item).delete()
            continue
        if item.choices.exists() and choice is None:
            return _bad(_("У вопроса {number} свои варианты — выберите один из них").format(number=item.number))
        CareerAttemptAnswer.objects.update_or_create(
            attempt=attempt, item=item, defaults={"option": option if choice is None else None, "choice": choice}
        )
    return Response({"answered": attempt.answers.count(), "total": len(items)})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_finish(request, pk: int):
    student, attempt = _my_attempt(request, pk)
    if student is None:
        return _forbid(str(STUDENT_ONLY))
    if attempt is None:
        return _not_found()
    if attempt.is_done:
        return Response(_my_attempt_payload(attempt))
    if not attempt.test.is_active:
        return _bad(_("Тест выключен учителем"))
    left = scoring.unanswered(attempt)
    if left:
        return _bad(_("Остались вопросы без ответа: {n}").format(n=left))
    scoring.finish(attempt)
    usage.track(request, "career.attempt.finish")
    return Response(_my_attempt_payload(attempt))
