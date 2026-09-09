"""Ручки пробников (фаза 63): список, мастер загрузки, результаты, архив.

Кто загружает: куратор — в свои группы, академический директор — в любую,
администратор — как всегда, за всех. Границу «своя группа» держит тот же
`core.scope`, что и везде: чужая группа отвечает 404, а не 403 — по отказу
не должно быть видно, что в школе есть такая группа и такой пробник.

Файл лежит в закрытом хранилище рядом с документами учеников и отдаётся
только после входа: прямой ссылки на него нет ни на одном экране.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.curators import curated_group_ids
from core.domains import ROLE_ADMIN, ROLE_CURATOR, ROLE_STUDENT
from students import mocks
from students.models import IELTS_SECTIONS, ExamType, MockImport, StudyGroup

#: Кто вправе загружать пробники и решать их судьбу.
UPLOADERS = (ROLE_CURATOR, "director_exam", ROLE_ADMIN)

#: Кто возвращает загрузку из архива. Куратор — нет: он её и убрал,
#: а «убрал и сам вернул» — это не архив, это правка задним числом.
RESTORERS = ("director_exam", ROLE_ADMIN)

#: Ученику раздел закрыт целиком — отказ словами, а не «не найдено»:
#: 404 говорил бы, что такой пробник, может быть, где-то и есть
STUDENT_REFUSAL = "Пробники ведут куратор и академический директор. Свой результат вы видите у себя в кабинете"


def _forbidden(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


def _not_found() -> Response:
    return Response({"detail": "Пробника нет"}, status=status.HTTP_404_NOT_FOUND)


def _bad(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def visible_groups(user) -> list[int]:
    """Группы, чьи пробники человек вправе видеть. Не сотруднику — пусто."""
    role = getattr(user, "role", "")
    if role == ROLE_CURATOR:
        return curated_group_ids(user)
    if role in ("director_exam", ROLE_ADMIN) or (role and role != ROLE_STUDENT):
        return list(StudyGroup.objects.values_list("pk", flat=True))
    return []


def may_upload(user, group_id: int | None = None) -> bool:
    """Может ли человек загрузить пробник в эту группу."""
    role = getattr(user, "role", "")
    if role not in UPLOADERS:
        return False
    if group_id is None:
        return True
    return group_id in visible_groups(user)


def is_staff_here(user) -> bool:
    """Пробники — рабочий раздел школы. Ученику он закрыт целиком."""
    role = getattr(user, "role", "")
    return bool(role) and role != ROLE_STUDENT


def _visible(user, pk: int) -> MockImport | None:
    """Загрузка, которую человеку видно. Чужая группа — как будто её нет."""
    row = MockImport.all_objects.select_related("group", "uploaded_by").filter(pk=pk).first()
    if row is None or row.group_id not in visible_groups(user):
        return None
    return row


def _date(raw: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _decimal(raw) -> Decimal | None:
    text = str(raw if raw is not None else "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _fixes(raw) -> dict[int, mocks.Fix]:
    """Правки человека с шага «Проверка»: кому отнести, какой балл, пропуск."""
    if not raw:
        return {}
    rows = json.loads(raw) if isinstance(raw, str) else raw
    out: dict[int, mocks.Fix] = {}
    for row in rows if isinstance(rows, list) else []:
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        sections = {
            name: value
            for name in IELTS_SECTIONS
            if (value := _decimal((row.get("sections") or {}).get(name))) is not None
        }
        out[index] = mocks.Fix(
            index=index,
            student=int(row["student"]) if str(row.get("student") or "").isdigit() else None,
            total=_decimal(row.get("total")),
            sections=sections,
            skip=bool(row.get("skip")),
        )
    return out


def _wizard_input(request) -> tuple[dict | None, Response | None]:
    """Общая часть шагов «Проверка» и «Применить»: экзамен, группа, дата, файл."""
    if not is_staff_here(request.user):
        return None, _forbidden(STUDENT_REFUSAL)
    if request.user.role not in UPLOADERS:
        return None, _forbidden("Загружают пробники куратор и академический директор")

    exam_type = (request.data.get("exam_type") or "").strip()
    if exam_type not in mocks.MOCK_EXAMS:
        return None, _bad("Пробники загружаются по IELTS и SAT — других экзаменов школа не проводит")

    raw_group = request.data.get("group")
    group = StudyGroup.objects.filter(pk=raw_group).first() if str(raw_group or "").isdigit() else None
    if group is None:
        group = StudyGroup.objects.filter(code=str(raw_group or "").strip()).first()
    if group is None:
        return None, _bad("Не выбрана группа")
    if not may_upload(request.user, group.pk):
        return None, _not_found()

    date = _date(request.data.get("date"))
    if date is None:
        return None, _bad("Не указана дата пробника")

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return None, _bad("Файл не приложен")

    return (
        {
            "exam_type": exam_type,
            "group": group,
            "date": date,
            "teacher": (request.data.get("teacher") or "").strip()[:200],
            "file": uploaded,
        },
        None,
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mock_imports(request):
    """Список загрузок: свои группы у куратора, все — у Кымбат и администратора."""
    if not is_staff_here(request.user):
        return _forbidden(STUDENT_REFUSAL)
    groups = visible_groups(request.user)

    rows = MockImport.all_objects.filter(group_id__in=groups).select_related("group", "uploaded_by")
    archived = request.query_params.get("archived") == "true"
    rows = rows.filter(archived_at__isnull=not archived)

    code = (request.query_params.get("group") or "").strip()
    if code and code != "all":
        rows = rows.filter(group__code=code)

    return Response(
        {
            "results": [mocks.short(row) for row in rows],
            # тот же вид, что у остальных экранов куратора: переключатель групп
            # показывает рядом с кодом число учеников
            "groups": [
                {
                    "id": g.pk,
                    "code": g.code,
                    "grade": g.grade,
                    "students": g.students_count,
                    "since": "",
                }
                for g in StudyGroup.objects.filter(pk__in=groups)
                .annotate(students_count=Count("students", filter=Q(students__is_active=True)))
                .order_by("code")
            ],
            "exams": [{"code": code, "title": ExamType(code).label} for code in mocks.MOCK_EXAMS],
            "may_upload": may_upload(request.user),
            "may_restore": request.user.role in RESTORERS,
            "archived": archived,
        }
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def mock_preview(request):
    """Шаг «Проверка»: разбор файла без единой записи в базу."""
    data, refusal = _wizard_input(request)
    if refusal is not None:
        return refusal

    twin = mocks.duplicate_of(exam_type=data["exam_type"], group=data["group"], date=data["date"])
    if twin is not None:
        return _bad(
            f"Пробник {data['exam_type']} для группы {data['group'].code} на эту дату уже загружен "
            f"({twin.rows_applied} результатов). Проверьте дату или уберите прежнюю загрузку в архив"
        )

    try:
        rows = mocks.parse(
            data["file"],
            exam_type=data["exam_type"],
            group=data["group"],
            date=data["date"],
            fixes=_fixes(request.data.get("fixes")),
        )
    except mocks.FileRejected as error:
        return _bad(str(error))

    return Response(mocks.preview_payload(rows, exam_type=data["exam_type"], group=data["group"]))


@extend_schema(request=None, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def mock_apply(request):
    """Шаг «Применить»: тот же файл с правками человека, одной транзакцией."""
    data, refusal = _wizard_input(request)
    if refusal is not None:
        return refusal

    try:
        record = mocks.apply(
            data["file"],
            exam_type=data["exam_type"],
            group=data["group"],
            date=data["date"],
            teacher=data["teacher"],
            actor=request.user,
            fixes=_fixes(request.data.get("fixes")),
        )
    except mocks.FileRejected as error:
        return _bad(str(error))
    except IntegrityError:
        return _bad("Пробник этого экзамена для этой группы на эту дату уже загружен")

    return Response(
        {
            "import": record.pk,
            "applied": record.rows_applied,
            "skipped": record.rows_skipped,
            "detail": f"Записано результатов: {record.rows_applied}",
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mock_results(request, pk: int):
    """Страница результатов пробника."""
    if not is_staff_here(request.user):
        return _forbidden(STUDENT_REFUSAL)
    record = _visible(request.user, pk)
    if record is None:
        return _not_found()
    payload = mocks.results(record)
    payload["may_upload"] = may_upload(request.user, record.group_id)
    payload["may_restore"] = request.user.role in RESTORERS
    return Response(payload)


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mock_file(request, pk: int):
    """Исходный файл учителя — после входа и только своей группе."""
    if not is_staff_here(request.user):
        return _forbidden(STUDENT_REFUSAL)
    record = _visible(request.user, pk)
    if record is None or not record.file:
        return _not_found()
    response = FileResponse(record.file.open("rb"), as_attachment=True, filename=record.file_name or "mock.xlsx")
    response["Cache-Control"] = "private, no-store"
    return response


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mock_export(request, pk: int):
    """Результаты пробника книгой XLSX — тем же кодом, что остальные выгрузки."""
    if not is_staff_here(request.user):
        return _forbidden(STUDENT_REFUSAL)
    from core.exports import Column, workbook_response

    record = _visible(request.user, pk)
    if record is None:
        return _not_found()
    payload = mocks.results(record)

    columns = [Column("Ученик", lambda r: r["full_name"], width=28)]
    if record.exam_type == ExamType.IELTS:
        columns += [
            Column(name.title(), (lambda n: lambda r: r["sections"].get(n))(name), width=12) for name in IELTS_SECTIONS
        ]
    columns += [
        Column("Балл", lambda r: r["total"], width=10),
        Column("Цель", lambda r: r["target"], width=10),
        Column("Сдавал", lambda r: r["took"], width=10),
    ]
    return workbook_response(
        filename=f"пробник-{record.exam_type}-{record.group.code}-{record.date}.xlsx",
        sheet="Пробник",
        columns=columns,
        rows=payload["results"],
    )


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mock_template(request):
    """Шаблон файла под выбранный экзамен: ФИО группы и пустые колонки."""
    from core.exports import Column, workbook_response

    if not is_staff_here(request.user):
        return _forbidden(STUDENT_REFUSAL)
    exam_type = (request.query_params.get("exam") or ExamType.IELTS).strip()
    if exam_type not in mocks.MOCK_EXAMS:
        return _bad("Шаблон есть для IELTS и SAT")
    if not may_upload(request.user):
        return _forbidden("Пробники загружают куратор и академический директор")

    from students.models import Student

    code = (request.query_params.get("group") or "").strip()
    group = StudyGroup.objects.filter(code=code).first() if code else None
    students = (
        Student.objects.filter(group=group, is_active=True).order_by("last_name", "first_name")
        if group is not None and group.pk in visible_groups(request.user)
        else []
    )

    titles = mocks.template_columns(exam_type)
    rows = mocks.template_rows(exam_type, students)
    columns = [
        Column(title, (lambda i: lambda row: row[i])(index), width=26 if index == 0 else 14)
        for index, title in enumerate(titles)
    ]
    return workbook_response(
        filename=f"шаблон-пробника-{exam_type}.xlsx",
        sheet=exam_type,
        columns=columns,
        rows=rows or [["", *([""] * (len(titles) - 1))]],
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mock_archive(request, pk: int):
    """Убрать загрузку в архив вместе с её результатами."""
    if not is_staff_here(request.user):
        return _forbidden(STUDENT_REFUSAL)
    from core.archive import archive

    record = _visible(request.user, pk)
    if record is None:
        return _not_found()
    if not may_upload(request.user, record.group_id):
        return _forbidden("Убрать пробник может куратор группы или академический директор")
    if record.is_archived:
        return _bad("Этот пробник уже в архиве")

    entry = archive(record, actor=request.user)
    return Response({"archived": entry.pk, "detail": f"Пробник «{record}» в архиве, баллы у учеников скрыты"})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mock_restore(request, pk: int):
    """Вернуть загрузку из архива. Может академический директор или администратор."""
    if not is_staff_here(request.user):
        return _forbidden(STUDENT_REFUSAL)
    from core.archive import restore
    from core.models import ArchiveEntry

    record = _visible(request.user, pk)
    if record is None:
        return _not_found()
    if request.user.role not in RESTORERS:
        return _forbidden("Вернуть пробник из архива может академический директор или администратор")
    if not record.is_archived:
        return _bad("Этот пробник и так не в архиве")

    entry = (
        ArchiveEntry.objects.filter(
            model_label="students.MockImport", object_id=str(record.pk), restored_at__isnull=True
        )
        .order_by("-created_at")
        .first()
    )
    if entry is None:
        return _bad("Записи архива для этого пробника нет — вернуть его нечем")
    outcome = restore(entry, actor=request.user)
    return Response({**outcome, "import": record.pk})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mock_remind(request, pk: int):
    """Задача тем, кто пробник не сдавал."""
    if not is_staff_here(request.user):
        return _forbidden(STUDENT_REFUSAL)
    record = _visible(request.user, pk)
    if record is None:
        return _not_found()
    if not may_upload(request.user, record.group_id):
        return _forbidden("Задачи ставит куратор группы или академический директор")
    made = mocks.remind(record, actor=request.user)
    return Response({"created": len(made), "students": made})
