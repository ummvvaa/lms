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

import datetime as dt
import json

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.domains import ROLE_STUDENT
from students import admission_import, credentials
from students.models import AdmissionImport, CredentialKind, Student

#: Ученику мастер закрыт словами, а не «не найдено»: таблица школы —
#: не его дело, и делать вид, что её нет, незачем
IMPORT_REFUSAL = gettext_lazy("Файлы загружают администратор и академический директор — остальные вносят руками")


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
        return Response({"detail": _("Ученика нет")}, status=status.HTTP_404_NOT_FOUND)
    if not credentials.may_view(request.user, student):
        return Response(
            {"detail": _("Пароли ученика видят директора и куратор группы")}, status=status.HTTP_403_FORBIDDEN
        )
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
        return Response({"detail": _("Ученика нет")}, status=status.HTTP_404_NOT_FOUND)
    if not credentials.may_view(request.user, student):
        return Response(
            {"detail": _("Пароли ученика видят директора и куратор группы")}, status=status.HTTP_403_FORBIDDEN
        )
    kind = str(request.data.get("kind") or "")
    if kind not in CredentialKind.values:
        return Response({"detail": _("Неизвестный вид пароля")}, status=status.HTTP_400_BAD_REQUEST)
    try:
        secret = credentials.reveal(student, kind, actor=request.user)
    except Exception as error:  # ключ не тот или запись повреждена
        from core.secrets import KeyMismatch, KeyMissing

        if isinstance(error, KeyMissing | KeyMismatch):
            return Response(
                {"detail": _("Пароль не расшифровать: {error}").format(error=error)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        raise
    if secret is None:
        return Response({"detail": _("Этот пароль не записан")}, status=status.HTTP_404_NOT_FOUND)
    return Response({"kind": kind, "password": secret})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def credential_set(request, pk: int):
    """Записать или убрать пароль. Пустая строка — убрать."""
    student = _student_or_none(request, pk)
    if student is None:
        return Response({"detail": _("Ученика нет")}, status=status.HTTP_404_NOT_FOUND)
    if not credentials.may_edit(request.user, student):
        return Response(
            {"detail": _("Пароль ученика записывают директор по поступлению, куратор группы и сам ученик")},
            status=status.HTTP_403_FORBIDDEN,
        )
    kind = str(request.data.get("kind") or "")
    if kind not in CredentialKind.values:
        return Response({"detail": _("Неизвестный вид пароля")}, status=status.HTTP_400_BAD_REQUEST)
    changed = credentials.set_credential(student, kind, str(request.data.get("password") or ""), actor=request.user)
    return Response({"kind": kind, "changed": changed, "present": credentials.state(student)[kind]})


# --- Правка строк блока «Поступление» ---------------------------------------


def _block_editor_or_refusal(request, pk: int):
    """Ученик и отказ: чужой — 404, без права на блок — 403 словами."""
    from students import admission_block

    student = _student_or_none(request, pk)
    if student is None:
        return None, Response({"detail": _("Ученика нет")}, status=status.HTTP_404_NOT_FOUND)
    if not admission_block.may_edit_whole(request.user, student):
        return None, Response(
            {"detail": _("Попытки и ссылки блока «Поступление» правят директор по поступлению и администратор")},
            status=status.HTTP_403_FORBIDDEN,
        )
    return student, None


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def block_attempt(request, pk: int):
    """Попытка из блока: поправить балл и дату или занять пустой слот."""
    from students import admission_block

    student, refusal = _block_editor_or_refusal(request, pk)
    if refusal is not None:
        return refusal
    raw_date = str(request.data.get("date") or "").strip()
    try:
        date = dt.date.fromisoformat(raw_date) if raw_date else None
    except ValueError:
        return Response({"detail": _("Дата — в виде ГГГГ-ММ-ДД")}, status=status.HTTP_400_BAD_REQUEST)
    try:
        attempt = admission_block.save_attempt(
            student,
            actor=request.user,
            exam=request.data.get("exam"),
            score=request.data.get("score"),
            date=date,
            attempt_id=request.data.get("id") or None,
        )
    except admission_block.BlockRefusal as refusal_text:
        return Response({"detail": str(refusal_text)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"id": attempt.pk})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def block_link(request, pk: int):
    """Ссылка на паспорт, табель или рекомендацию из блока."""
    from students import admission_block

    student, refusal = _block_editor_or_refusal(request, pk)
    if refusal is not None:
        return refusal
    try:
        document = admission_block.save_link(
            student, actor=request.user, code=str(request.data.get("code") or ""), url=request.data.get("url")
        )
    except admission_block.BlockRefusal as refusal_text:
        return Response({"detail": str(refusal_text)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"document": document.pk})


# --- Мастер импорта таблицы -------------------------------------------------


def _may_import(user) -> bool:
    """Мастер импорта открыт администратору и Кымбат.

    С фазы 72 мастер стоял у каждого владельца домена, с 78-й — и у куратора.
    Разбор кабинетов вернул его двоим: остальные вносят руками. Список ролей —
    в реестре импорта (`WIZARD_ROLES`); какие домены человек вправе писать,
    решает `_check_domains`.
    """
    from students import import_registry

    return import_registry.may_open_wizard(user)


def _visible_imports(user):
    """Загрузки мастера, которые человек вправе видеть.

    В отчёте загрузки — имена учеников. Куратор видит только свои загрузки:
    чужая касается чужих групп, а общий список показал бы их целиком.
    """
    rows = AdmissionImport.objects.select_related("uploaded_by")
    if getattr(user, "role", "") == "curator":
        rows = rows.filter(uploaded_by=user)
    return rows


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
        return Response(
            {"detail": _("Домена «{domain}» нет в реестре").format(domain=unknown[0])},
            status=status.HTTP_400_BAD_REQUEST,
        )
    allowed = import_registry.writable_domains(user)
    outside = [DOMAINS[code].title for code in chosen if code not in allowed]
    if outside:
        return Response(
            {"detail": _("Домен «{domain}» вам не принадлежит — выберите свои домены").format(domain=outside[0])},
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


def _assigned(raw) -> dict[str, str]:
    """Назначения человека с шага «Что заполняем»: заголовок файла → ключ колонки реестра.

    Пустой ключ — «не загружать». Незнакомый ключ отбрасывается: назначить
    колонку можно только тому, что есть в реестре соответствий.
    """
    from students import import_registry

    if not raw:
        return {}
    try:
        rows = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    if not isinstance(rows, dict):
        return {}
    return {
        str(title).strip(): str(key or "")
        for title, key in rows.items()
        if str(title).strip() and (not key or str(key) in import_registry.BY_KEY)
    }


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
        return Response({"detail": _("Файл не приложен")}, status=status.HTTP_400_BAD_REQUEST)
    try:
        sheets = admission_import.parse(
            uploaded,
            fixes=_fixes(request.data.get("fixes")),
            group=str(request.data.get("group") or ""),
            actor=request.user,
            assigned=_assigned(request.data.get("assigned")),
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
        return Response({"detail": _("Файл не приложен")}, status=status.HTTP_400_BAD_REQUEST)
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
            assigned=_assigned(request.data.get("assigned")),
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
    from core.imports import filter_by_period

    rows = filter_by_period(_visible_imports(request.user), request.query_params)
    return Response({"rows": [admission_import.record_payload(row) for row in rows]})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admission_report(request, pk: int):
    """Отчёт одной загрузки."""
    if not _may_import(request.user):
        return _refuse_import()
    record = _visible_imports(request.user).filter(pk=pk).first()
    if record is None:
        return Response({"detail": _("Загрузки нет")}, status=status.HTTP_404_NOT_FOUND)
    return Response(admission_import.record_payload(record))


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admission_export(request, pk: int):
    """Отчёт книгой XLSX — тем же кодом, что остальные выгрузки."""
    if not _may_import(request.user):
        return _refuse_import()
    from core.exports import Column, workbook_response

    record = _visible_imports(request.user).filter(pk=pk).first()
    if record is None:
        return Response({"detail": _("Загрузки нет")}, status=status.HTTP_404_NOT_FOUND)
    columns = [
        Column(_("Лист"), lambda r: r["sheet"], width=16),
        Column(_("Строка"), lambda r: r["row"], width=8),
        Column(_("Ученик"), lambda r: r["student"], width=28),
        Column(_("Что"), lambda r: r["kind"], width=12),
        Column(_("Подробности"), lambda r: r["text"], width=70),
    ]
    return workbook_response(
        filename=_("таблица-поступления-{date}.xlsx").format(date=f"{record.created_at:%Y-%m-%d}"),
        sheet=_("Отчёт"),
        columns=columns,
        rows=admission_import.report_rows(record),
        request=request,
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
