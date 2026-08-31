"""API справочников: список, заведение, правка, скрытие, замена, удаление.

Право берётся из реестра доменов: предметы олимпиад ведёт директор
талантов, виды спорта — директор спорта. Читают справочник все —
без этого в карточке ученика нечем подписать ссылку.
"""

from __future__ import annotations

from django.db import models
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.audit import model_label
from core.deletion import refuse
from core.domains import ROLE_STUDENT, can_delete, owns_model
from directories.models import ExamKind, OlympiadSubject, SportType
from directories.serializers import (
    ExamKindSerializer,
    OlympiadSubjectSerializer,
    ReplaceSerializer,
    SportTypeSerializer,
)
from directories.services import deletion_verdict, duplicate_groups, replace, usage_total


class DirectoryViewSet(viewsets.ModelViewSet):
    """Один справочник. Ведёт его домен-владелец, читают все сотрудники."""

    permission_classes = [IsAuthenticated]
    filterset_fields = ("is_active",)
    search_fields = ("name", "description")
    #: `app_label.ModelName` — по нему сверяется реестр доменов
    directory_label: str = ""

    def get_queryset(self):
        queryset = self.queryset
        # ученику нужен только список выбора, скрытые записи ему не нужны
        if self.request.user.role == ROLE_STUDENT or self.request.query_params.get("active") == "true":
            queryset = queryset.filter(is_active=True)
        return queryset

    def _deny_if_not_owner(self) -> None:
        if not owns_model(self.request.user.role, self.directory_label):
            raise PermissionDenied(self.owner_message)

    @property
    def owner_message(self) -> str:
        model = self.queryset.model
        return f"Справочник «{model._meta.verbose_name_plural}» ведёт другой директор"

    def perform_create(self, serializer):
        self._deny_if_not_owner()
        serializer.save()

    def perform_update(self, serializer):
        self._deny_if_not_owner()
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """Удаление физическое: истории у справочника нет (инвариант №13).

        Запись, на которую ссылаются, не удаляется — вместо отказа
        предлагаются два выхода: скрыть или заменить.
        """
        instance = self.get_object()
        label = model_label(instance)
        if not can_delete(request.user.role, label):
            return refuse(request.user.role, label)

        verdict = deletion_verdict(instance)
        if not verdict["can_delete"]:
            return Response({"detail": verdict["message"], **verdict}, status=status.HTTP_409_CONFLICT)

        name = instance.name
        instance.delete()
        return Response({"detail": f"Удалено: {name}"})

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"], url_path="usage")
    def usage_view(self, request, pk=None):
        """Что будет, если удалить: где запись используется и какие есть выходы."""
        return Response(deletion_verdict(self.get_object()))

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def hide(self, request, pk=None):
        """Убрать запись из списка выбора, ссылки оставить как есть."""
        self._deny_if_not_owner()
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        return Response(
            {
                "detail": f"«{instance.name}» больше не появится в списке выбора. "
                f"В уже заведённых записях она осталась",
                "id": instance.pk,
                "is_active": False,
            }
        )

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def show(self, request, pk=None):
        """Вернуть запись в список выбора."""
        self._deny_if_not_owner()
        instance = self.get_object()
        instance.is_active = True
        instance.save(update_fields=["is_active"])
        return Response({"detail": f"«{instance.name}» снова в списке выбора", "id": instance.pk, "is_active": True})

    @extend_schema(request=ReplaceSerializer, responses={200: dict})
    @action(detail=True, methods=["post"], url_path="replace")
    def replace_view(self, request, pk=None):
        """Перенести все ссылки на другую запись и удалить эту."""
        self._deny_if_not_owner()
        payload = ReplaceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        instance = self.get_object()
        target = self.queryset.filter(pk=payload.validated_data["target"]).first()
        if target is None:
            return Response({"detail": "Записи, на которую заменяем, нет"}, status=status.HTTP_404_NOT_FOUND)
        try:
            return Response(replace(instance, target))
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def duplicates(self, request):
        """«Возможно, это одно и то же» — группы похожих написаний.

        Склеивать автоматически нельзя: решение принимает директор,
        а разъединить потом будет нечем.
        """
        groups = duplicate_groups(self.queryset.model)
        return Response(
            {
                "groups": groups,
                "detail": (
                    "Похожих написаний не нашлось"
                    if not groups
                    else "Проверьте: возможно, это одно и то же. Объединение переносит все ссылки"
                ),
            }
        )


class OlympiadSubjectViewSet(DirectoryViewSet):
    """Предметы олимпиад — домен `talent` (Арман)."""

    queryset = OlympiadSubject.objects.all()
    serializer_class = OlympiadSubjectSerializer
    directory_label = "directories.OlympiadSubject"
    filterset_fields = ("is_active", "area")


class SportTypeViewSet(DirectoryViewSet):
    """Виды спорта — домен `sport` (Нурлыбек)."""

    queryset = SportType.objects.all()
    serializer_class = SportTypeSerializer
    directory_label = "directories.SportType"
    filterset_fields = ("is_active", "category")


def counts(model: type[models.Model]) -> dict:
    """Сколько записей в справочнике и сколько из них используется."""
    rows = list(model.objects.all())
    return {
        "total": len(rows),
        "active": sum(1 for row in rows if row.is_active),
        "used": sum(1 for row in rows if usage_total(row)),
    }


class ExamKindViewSet(DirectoryViewSet):
    """Экзамены — домен `exam` (Кымбат). Фаза 39."""

    queryset = ExamKind.objects.all()
    serializer_class = ExamKindSerializer
    directory_label = "directories.ExamKind"
    filterset_fields = ("is_active",)
