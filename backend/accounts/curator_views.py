"""Назначения кураторов: экран администратора (фаза 60).

Список групп с действующим куратором и историей, список кураторов
с их группами, назначение и смена с датой. Только `admin`: право
на реестр школы — его.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.curators import AssignmentRefused, active_assignments, assign
from accounts.models import CuratorAssignment, Role, User
from accounts.permissions import IsAdmin
from students.models import StudyGroup


class CuratorAssignmentSerializer(serializers.ModelSerializer):
    """Одна строка истории назначений группы."""

    curator_name = serializers.SerializerMethodField()
    group_code = serializers.CharField(source="group.code", read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CuratorAssignment
        fields = (
            "id",
            "group",
            "group_code",
            "curator",
            "curator_name",
            "since",
            "until",
            "is_active",
            "created_by_name",
            "created_at",
        )
        read_only_fields = ("id", "until", "created_at")

    def get_curator_name(self, obj) -> str:
        return obj.curator.full_name or obj.curator.email

    def get_created_by_name(self, obj) -> str:
        who = obj.created_by
        return (who.full_name or who.email) if who is not None else ""


class CuratorAssignmentViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """История назначений и новое назначение.

    Правки и удаления нет: история не переписывается. Смена куратора —
    новое назначение с датой, старое закрывается той же датой само.
    """

    queryset = CuratorAssignment.objects.select_related("curator", "group", "created_by").all()
    serializer_class = CuratorAssignmentSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ("group", "curator")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            row = assign(group=data["group"], curator=data["curator"], since=data["since"], actor=request.user)
        except AssignmentRefused as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(row).data, status=status.HTTP_201_CREATED)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAdmin])
def curators(request):
    """Кураторы с их группами на сегодня — для экрана администратора."""
    rows = []
    active = {}
    for row in active_assignments().select_related("group").order_by("group__code"):
        active.setdefault(row.curator_id, []).append(
            {"id": row.group_id, "code": row.group.code, "grade": row.group.grade, "since": row.since}
        )
    for user in User.objects.filter(role=Role.CURATOR).order_by("full_name", "email"):
        rows.append(
            {
                "id": user.pk,
                "full_name": user.full_name,
                "email": user.email,
                "is_active": user.is_active,
                "groups": active.get(user.pk, []),
            }
        )
    unassigned = StudyGroup.objects.filter(is_active=True).exclude(pk__in=active_assignments().values("group_id"))
    return Response(
        {
            "results": rows,
            "unassigned": [{"id": g.pk, "code": g.code, "grade": g.grade, "hint": g.curator} for g in unassigned],
        }
    )
