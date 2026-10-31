"""Ручки раздела «Кружки» у администратора: список, заведение, правка, архив, записанные.

Право — из реестра (`core.domains.CABINET_WRITERS["clubs.Club"]`): кружки ведёт
администратор. Записанных ментор видит своими ручками (`mentor_views`).
"""

from __future__ import annotations

from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from clubs import payloads, services
from clubs.models import Club, ClubEnrollment
from core.domains import ROLE_MENTOR, can_write_cabinet
from core.exports import Column, workbook_of_sheets

CLUB = "clubs.Club"


def _forbid() -> Response:
    return Response({"detail": _("Кружки ведёт администратор")}, status=status.HTTP_403_FORBIDDEN)


def _not_found() -> Response:
    return Response({"detail": _("Не найдено")}, status=status.HTTP_404_NOT_FOUND)


def _bad(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def _writer(request) -> bool:
    return can_write_cabinet(getattr(request.user, "role", ""), CLUB)


def _int(raw) -> int | None:
    return int(raw) if str(raw if raw is not None else "").isdigit() else None


def _fields(data, *, partial: bool) -> dict:
    """Поля кружка из формы. При правке приходит только изменённое."""
    from accounts.models import User

    out: dict = {}
    for key in ("title", "description", "mentor_name"):
        if key in data or not partial:
            limit = 5000 if key == "description" else 120
            out[key] = str(data.get(key) or "").strip()[:limit]
    if "mentor" in data or not partial:
        mentor_id = _int(data.get("mentor"))
        mentor = User.objects.filter(pk=mentor_id, role=ROLE_MENTOR, is_active=True).first() if mentor_id else None
        if mentor_id and mentor is None:
            raise services.Refused(_("Выберите учётку с ролью «Ментор»"))
        out["mentor"] = mentor
    if "enroll_until" in data or not partial:
        raw = data.get("enroll_until")
        value = parse_datetime(str(raw)) if raw else None
        if raw and value is None:
            raise services.Refused(_("Укажите дату и время"))
        if value is not None and timezone.is_naive(value):
            value = timezone.make_aware(value)
        out["enroll_until"] = value
    if "marks_enabled" in data:
        out["marks_enabled"] = bool(data.get("marks_enabled"))
    if "meetings" in data or not partial:
        out["meetings"] = services.clean_meetings(data.get("meetings"))
    if "parallels" in data or not partial:
        out["parallels"] = services.clean_parallels(data.get("parallels"))
    return out


def _counts() -> dict[int, int]:
    rows = services.active_rows().values("club_id").annotate(n=Count("id"))
    return {row["club_id"]: row["n"] for row in rows}


@extend_schema(request=None, responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def clubs(request):
    """Кружки с числом записанных (GET, `?archived=1` — архив) и новый кружок (POST)."""
    if not _writer(request):
        return _forbid()
    if request.method == "POST":
        try:
            club = services.save_club(None, _fields(request.data, partial=False), actor=request.user)
        except services.Refused as error:
            return _bad(str(error))
        return Response(payloads.club_admin(club), status=status.HTTP_201_CREATED)
    archived = request.query_params.get("archived") == "1"
    query = Club.all_objects.filter(archived_at__isnull=not archived)
    rows = query.select_related("mentor").prefetch_related("meetings", "parallels").order_by("order", "title")
    counts = _counts()
    return Response(
        {
            "rows": [payloads.club_admin(club, counts.get(club.pk, 0)) for club in rows],
            "archived_total": Club.all_objects.filter(archived_at__isnull=False).count(),
        }
    )


def _club(pk) -> Club | None:
    return Club.all_objects.select_related("mentor").prefetch_related("meetings", "parallels").filter(pk=pk).first()


@extend_schema(request=None, responses={200: dict})
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def club(request, pk: int):
    """Кружок: PATCH — правка (и `archived: false` — вернуть из архива), DELETE — в архив."""
    if not _writer(request):
        return _forbid()
    row = _club(pk)
    if row is None:
        return _not_found()
    if request.method == "DELETE":
        if row.archived_at is None:
            row.archived_at = timezone.now()
            row.save(update_fields=["archived_at"])
            services.journal_club(row, "archived", "", row.title, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == "PATCH":
        if request.data.get("archived") is False and row.archived_at is not None:
            row.archived_at = None
            row.save(update_fields=["archived_at"])
            services.journal_club(row, "restored", "", row.title, actor=request.user)
        try:
            row = services.save_club(row, _fields(request.data, partial=True), actor=request.user)
        except services.Refused as error:
            return _bad(str(error))
        row = _club(pk)
    return Response(payloads.club_admin(row, _counts().get(row.pk, 0)))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mentors(request):
    """Учётки с ролью «Ментор» — выбор привязки в форме кружка."""
    from accounts.models import User

    if not _writer(request):
        return _forbid()
    rows = User.objects.filter(role=ROLE_MENTOR, is_active=True).order_by("full_name", "email")
    return Response({"rows": [{"id": u.pk, "title": u.full_name or u.email or u.login} for u in rows]})


def _members(request, row: Club):
    """Записанные в кружок за всё время: действующие сверху, вышедшие — с датой выхода."""
    query = ClubEnrollment.objects.filter(club=row, student__archived_at__isnull=True).select_related(
        "student", "student__group"
    )
    group = _int(request.query_params.get("group"))
    if group:
        query = query.filter(student__group_id=group)
    if request.query_params.get("active") == "1":
        query = query.filter(ended_at__isnull=True)
    return list(
        query.order_by(F("ended_at").asc(nulls_first=True), "student__last_name", "student__first_name", "-enrolled_at")
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def members(request, pk: int):
    """Список записанных: ученик, группа, дата записи, вышел ли. Фильтр `?group=`."""
    if not _writer(request):
        return _forbid()
    row = _club(pk)
    if row is None:
        return _not_found()
    rows = _members(request, row)
    groups = (
        ClubEnrollment.objects.filter(club=row, student__group__isnull=False)
        .values("student__group_id", "student__group__code")
        .annotate(n=Count("id", filter=Q(ended_at__isnull=True)))
        .order_by("student__group__code")
    )
    return Response(
        {
            "club": payloads.club_admin(row),
            "rows": [payloads.enrollment_row(e) for e in rows],
            "groups": [{"id": g["student__group_id"], "code": g["student__group__code"]} for g in groups],
            "active": sum(1 for e in rows if e.ended_at is None),
        }
    )


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def members_export(request, pk: int):
    """Excel записанных: тот же фильтр по группе, что на экране."""
    if not _writer(request):
        return _forbid()
    row = _club(pk)
    if row is None:
        return _not_found()
    columns = [
        Column(_("Ученик"), lambda e: e.student.full_name, 30),
        Column(_("Группа"), lambda e: e.student.group.code if e.student.group_id else "", 10),
        Column(_("Записался"), lambda e: timezone.localtime(e.enrolled_at).date(), 12),
        Column(_("Вышел"), lambda e: timezone.localtime(e.ended_at).date() if e.ended_at else "", 12),
    ]
    return workbook_of_sheets(
        filename=f"{row.title}.xlsx", sheets=[(row.title, columns, _members(request, row))], request=request
    )
