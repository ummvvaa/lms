"""Ручки блока «Поступление»: пароли и мастер импорта таблицы (фаза 65).

Пароли ученика от почты и Common App — единственные данные, которые
открывают чужие аккаунты. Поэтому здесь их ровно два маршрута: список
«есть / нет» и показ одного пароля, который пишется в журнал. В любых
других ответах системы пароля нет ни открытым текстом, ни шифртекстом,
и это стережёт отдельный тест.

Мастер импорта повторяет мастер пробников: файл → проверка без единой
записи → применение одной транзакцией → отчёт, который сохраняется
и выгружается книгой.
"""

from __future__ import annotations

import json

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.domains import ROLE_ADMIN, ROLE_STUDENT
from students import admission_import, credentials
from students.models import AdmissionImport, CredentialKind, Student

#: Ученику мастер закрыт словами, а не «не найдено»: таблица школы —
#: не его дело, и делать вид, что её нет, незачем
IMPORT_REFUSAL = "Файлы загружают администратор и директора — каждый в свой домен"


def _student_or_none(request, pk: int) -> Student | None:
    """Ученик, которого этот человек вправе видеть; иначе — None (404)."""
    from core.scope import sees_student

    student = Student.objects.filter(pk=pk).first()
    if student is None or not sees_student(request.user, student.pk):
        return None
    return student


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def credentials_state(request, pk: int):
    """Есть ли у ученика пароли — и ничего больше.

    Ответ этой ручки ходит в карточку: в нём «есть / нет», маска и то,
    вправе ли смотрящий нажать «Показать». Самих паролей здесь нет.
    """
    student = _student_or_none(request, pk)
    if student is None:
        return Response({"detail": "Ученика нет"}, status=status.HTTP_404_NOT_FOUND)
    if not credentials.may_view(request.user, student):
        return Response({"detail": "Пароли ученика видят директора и куратор группы"}, status=status.HTTP_403_FORBIDDEN)
    present = credentials.state(student)
    return Response(
        {
            "student": student.pk,
            "mask": credentials.MASK,
            "may_edit": credentials.may_edit(request.user, student),
            "rows": [
                {"kind": kind, "title": CredentialKind(kind).label, "present": present[kind]}
                for kind in CredentialKind.values
            ],
        }
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def credential_reveal(request, pk: int):
    """Показать один пароль — отдельным запросом и с записью в журнал.

    Показ — событие: в истории ученика видно, кто и когда открывал его
    пароль. Поэтому ручка POST, а не GET: её нельзя случайно вызвать
    ссылкой, предзагрузкой или обновлением страницы.
    """
    student = _student_or_none(request, pk)
    if student is None:
        return Response({"detail": "Ученика нет"}, status=status.HTTP_404_NOT_FOUND)
    if not credentials.may_view(request.user, student):
        return Response({"detail": "Пароли ученика видят директора и куратор группы"}, status=status.HTTP_403_FORBIDDEN)
    kind = str(request.data.get("kind") or "")
    if kind not in CredentialKind.values:
        return Response({"detail": "Неизвестный вид пароля"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        secret = credentials.reveal(student, kind, actor=request.user)
    except Exception as error:  # ключ не тот или запись повреждена
        from core.secrets import KeyMismatch, KeyMissing

        if isinstance(error, KeyMissing | KeyMismatch):
            return Response({"detail": f"Пароль не расшифровать: {error}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        raise
    if secret is None:
        return Response({"detail": "Этот пароль не записан"}, status=status.HTTP_404_NOT_FOUND)
    return Response({"kind": kind, "password": secret})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def credential_set(request, pk: int):
    """Записать или убрать пароль. Пустая строка — убрать."""
    student = _student_or_none(request, pk)
    if student is None:
        return Response({"detail": "Ученика нет"}, status=status.HTTP_404_NOT_FOUND)
    if not credentials.may_edit(request.user, student):
        return Response(
            {"detail": "Пароль ученика записывают директор по поступлению, куратор группы и сам ученик"},
            status=status.HTTP_403_FORBIDDEN,
        )
    kind = str(request.data.get("kind") or "")
    if kind not in CredentialKind.values:
        return Response({"detail": "Неизвестный вид пароля"}, status=status.HTTP_400_BAD_REQUEST)
    changed = credentials.set_credential(student, kind, str(request.data.get("password") or ""), actor=request.user)
    return Response({"kind": kind, "changed": changed, "present": credentials.state(student)[kind]})


# --- Мастер импорта таблицы -------------------------------------------------


def _may_import(user) -> bool:
    """Мастер импорта открыт администратору и владельцам доменов (фаза 72).

    До фазы 77 здесь стоял список «Асем и администратор» из фазы 65, а экран
    «Импорт» с 72-й показывал мастер каждому владельцу домена — и у четырёх
    директоров всё отвечало 403 (поймано первым полным прогоном после 72-й).
    Какие домены владелец вправе писать, решает `_check_domains`; куратор
    и ученик доменов не пишут — им отказ.
    """
    from students import import_registry

    role = getattr(user, "role", "")
    return role == ROLE_ADMIN or bool(import_registry.writable_domains(user))


def _refuse_import():
    return Response({"detail": IMPORT_REFUSAL}, status=status.HTTP_403_FORBIDDEN)


def _domains(raw) -> list[str] | None:
    """Выбранные домены с экрана: коды через запятую или списком. Пусто — все найденные."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = raw.split(",")
        raw = parsed
    if not isinstance(raw, list):
        return None
    return [str(code).strip() for code in raw if str(code).strip()]


def _check_domains(user, chosen: list[str] | None) -> Response | None:
    """Владелец домена пишет свои домены и то, что реестр отдал его таблице.

    Администратор — любые; куратор сюда не доходит вовсе. Незнакомый код
    домена — отказ словами, а не молчаливый пропуск.
    """
    from core.domains import DOMAINS
    from students import import_registry

    if chosen is None:
        return None
    unknown = [code for code in chosen if code not in DOMAINS]
    if unknown:
        return Response({"detail": f"Домена «{unknown[0]}» нет в реестре"}, status=status.HTTP_400_BAD_REQUEST)
    allowed = import_registry.writable_domains(user)
    outside = [DOMAINS[code].title for code in chosen if code not in allowed]
    if outside:
        return Response(
            {"detail": f"Домен «{outside[0]}» вам не принадлежит — выберите свои домены"},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _fixes(raw) -> dict[str, admission_import.Fix]:
    """Правки человека с шага «Проверка»: кому отнести строку и что пропустить."""
    if not raw:
        return {}
    rows = json.loads(raw) if isinstance(raw, str) else raw
    out: dict[str, admission_import.Fix] = {}
    for row in rows if isinstance(rows, list) else []:
        key = str(row.get("key") or "")
        if not key:
            continue
        out[key] = admission_import.Fix(
            student=int(row["student"]) if str(row.get("student") or "").isdigit() else None,
            skip=bool(row.get("skip")),
        )
    return out


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admission_preview(request):
    """Шаг «Проверка»: разбор книги без единой записи в базу."""
    if not _may_import(request.user):
        return _refuse_import()
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        sheets = admission_import.parse(
            uploaded, fixes=_fixes(request.data.get("fixes")), group=str(request.data.get("group") or "")
        )
    except admission_import.FileRejected as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    from students import import_registry

    payload = admission_import.preview_payload(sheets)
    # что из найденного этот человек вправе заполнять — экран покажет остальное серым
    allowed = import_registry.writable_domains(request.user)
    payload["writable_domains"] = [code for code in payload["domains"] if code in allowed]
    return Response(payload)


@extend_schema(request=None, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admission_apply(request):
    """Шаг «Применить»: та же книга с правками, одной транзакцией."""
    if not _may_import(request.user):
        return _refuse_import()
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)
    chosen = _domains(request.data.get("domains"))
    refused = _check_domains(request.user, chosen)
    if refused is not None:
        return refused
    try:
        record = admission_import.apply(
            uploaded,
            actor=request.user,
            fixes=_fixes(request.data.get("fixes")),
            domains=chosen,
            group=str(request.data.get("group") or ""),
        )
    except admission_import.FileRejected as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(admission_import.record_payload(record), status=status.HTTP_201_CREATED)


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admission_template(request):
    """Шаблон файла из реестра: заголовки колонок, лист — группа (фаза 72)."""
    from django.http import HttpResponse

    if not _may_import(request.user):
        return _refuse_import()
    response = HttpResponse(
        admission_import.template_workbook(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="shablon-importa.xlsx"'
    return response


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admission_imports(request):
    """История загрузок таблицы: она одноразовая, но след остаётся."""
    if not _may_import(request.user):
        return _refuse_import()
    rows = AdmissionImport.objects.select_related("uploaded_by")[:20]
    return Response({"rows": [admission_import.record_payload(row) for row in rows]})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admission_report(request, pk: int):
    """Отчёт одной загрузки."""
    if not _may_import(request.user):
        return _refuse_import()
    record = AdmissionImport.objects.select_related("uploaded_by").filter(pk=pk).first()
    if record is None:
        return Response({"detail": "Загрузки нет"}, status=status.HTTP_404_NOT_FOUND)
    return Response(admission_import.record_payload(record))


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admission_export(request, pk: int):
    """Отчёт книгой XLSX — тем же кодом, что остальные выгрузки."""
    if not _may_import(request.user):
        return _refuse_import()
    from core.exports import Column, workbook_response

    record = AdmissionImport.objects.filter(pk=pk).first()
    if record is None:
        return Response({"detail": "Загрузки нет"}, status=status.HTTP_404_NOT_FOUND)
    columns = [
        Column("Лист", lambda r: r["sheet"], width=16),
        Column("Строка", lambda r: r["row"], width=8),
        Column("Ученик", lambda r: r["student"], width=28),
        Column("Что", lambda r: r["kind"], width=12),
        Column("Подробности", lambda r: r["text"], width=70),
    ]
    return workbook_response(
        filename=f"таблица-поступления-{record.created_at:%Y-%m-%d}.xlsx",
        sheet="Отчёт",
        columns=columns,
        rows=admission_import.report_rows(record),
    )


def student_refusal() -> Response:
    """Ученику мастер закрыт — вынесено, чтобы текст был один."""
    return Response({"detail": IMPORT_REFUSAL}, status=status.HTTP_403_FORBIDDEN)


__all__ = [
    "ROLE_STUDENT",
    "admission_apply",
    "admission_export",
    "admission_imports",
    "admission_preview",
    "admission_report",
    "credential_reveal",
    "credential_set",
    "credentials_state",
    "student_refusal",
]
