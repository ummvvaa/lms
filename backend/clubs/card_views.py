"""Блок «Кружки» в карточке ученика у куратора: в каких кружках, с какой даты, вышел ли.

Читают куратор своих групп и администратор (`core.domains.CABINET_READERS`,
граница — `core.scope`): чужой ученик — 404. Заметок ментора здесь нет и не
будет (`clubs.rights.NOTE_READERS`); посещение кружка — только когда
администратор включил в нём отметку.
"""

from __future__ import annotations

from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from clubs import payloads, services
from clubs.models import ClubEnrollment
from core.domains import can_read_cabinet
from core.scope import visible_students

ENROLLMENT = "clubs.ClubEnrollment"


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_clubs(request, pk: int):
    """Кружки ученика за всё время: действующие сверху, вышедшие — с датой выхода."""
    if not can_read_cabinet(getattr(request.user, "role", ""), ENROLLMENT):
        return Response({"detail": _("Кружки ученика видят куратор и администратор")}, status=status.HTTP_403_FORBIDDEN)
    student = visible_students(request.user).filter(pk=pk).first()
    if student is None:
        return Response({"detail": _("Не найдено")}, status=status.HTTP_404_NOT_FOUND)
    rows = (
        ClubEnrollment.objects.filter(student=student, club__archived_at__isnull=True)
        .select_related("club")
        .prefetch_related("club__meetings")
    )
    out = []
    for row in sorted(rows, key=lambda r: (r.ended_at is not None, -(r.enrolled_at.timestamp()))):
        item = {
            "id": row.pk,
            "club": row.club.title,
            "schedule": services.schedule_words(row.club.meetings.all()),
            "enrolled_at": payloads.when(row.enrolled_at),
            "ended_at": payloads.when(row.ended_at),
            "left": row.ended_at is not None,
        }
        # посещение — только при включённой отметке: выключена — его нет нигде
        if row.club.marks_enabled and row.ended_at is None:
            item["percent"] = services.month_percent(row)
        out.append(item)
    return Response({"rows": out})
