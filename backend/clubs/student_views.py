"""Ручки ученика: свои кружки, запись сразу, выход с историей, строка «Сегодня кружок».

Ученик видит кружки своей параллели и те, где он уже состоит. Внутренних
ярлыков и заметок ментора в ответе нет (инвариант №7): только карточка
кружка, своя запись и задание ментора.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from clubs import payloads, services
from clubs.models import Club, ClubEnrollment
from core.domains import ROLE_STUDENT
from core.parallels import parallel_of
from students.models import Student


def _me(request):
    if getattr(request.user, "role", "") != ROLE_STUDENT:
        return None
    return Student.objects.filter(user=request.user, is_active=True).select_related("group").first()


def _forbid(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


def _mine(student) -> dict[int, ClubEnrollment]:
    return {row.club_id: row for row in ClubEnrollment.objects.filter(student=student, ended_at__isnull=True)}


def _clubs_of(student):
    """Кружки параллели ученика и те, где он состоит, — даже если параллель потом сняли."""
    grade = parallel_of(student)
    query = Q(parallels__parallel=grade) | Q(enrollments__student=student, enrollments__ended_at__isnull=True)
    return Club.objects.filter(query).distinct().prefetch_related("meetings", "parallels").order_by("order", "title")


def payload(student) -> dict:
    mine = _mine(student)
    clubs = []
    for club in _clubs_of(student):
        row = mine.get(club.pk)
        card = payloads.club_card(club)
        card.update(
            {
                "enrolled": row is not None,
                "enrolled_at": payloads.when(row.enrolled_at) if row else None,
                "can_enroll": row is None and services.is_open(club) and services.allows(club, parallel_of(student)),
                # пересечение со своей секцией — заранее, тихой строкой у кнопки
                "overlaps": services.sport_overlaps(student, club) if row is None else [],
                "homework": (
                    [payloads.homework_row(h) for h in services.visible_homework(club).select_related("club")]
                    if row is not None
                    else []
                ),
            }
        )
        clubs.append(card)
    today = [
        {"id": club.pk, "title": club.title, "time": services.time_words(meeting)}
        for club, meeting in services.today_for(student)
    ]
    return {"clubs": clubs, "today": today}


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_clubs(request):
    """Кружки ученика: карточки, своя запись, задание ментора и встречи сегодня."""
    me = _me(request)
    if me is None:
        return _forbid(_("Раздел — у ученика"))
    return Response(payload(me))


def _club_for(me, pk) -> Club | None:
    """Кружок, который ученик видит: своей параллели или свой."""
    return _clubs_of(me).filter(pk=pk).first()


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_enroll(request, pk: int):
    """«Записаться» — сразу, без заявки. `warnings` — пересечения со спортивной секцией."""
    me = _me(request)
    if me is None:
        return _forbid(_("Записывается ученик"))
    club = _club_for(me, pk)
    if club is None:
        return Response({"detail": _("Не найдено")}, status=status.HTTP_404_NOT_FOUND)
    try:
        _row, warnings = services.enroll(student=me, club=club, actor=request.user)
    except services.Refused as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({**payload(me), "warnings": warnings})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_leave(request, pk: int):
    """«Выйти из кружка» — и при закрытой записи; записаться снова можно в любой момент открытого окна."""
    me = _me(request)
    if me is None:
        return _forbid(_("Выходит из кружка ученик"))
    club = _club_for(me, pk)
    if club is None:
        return Response({"detail": _("Не найдено")}, status=status.HTTP_404_NOT_FOUND)
    try:
        services.leave(student=me, club=club, actor=request.user)
    except services.Refused as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(payload(me))
