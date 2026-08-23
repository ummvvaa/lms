"""Метаданные для фронта: реестр доменов и справочники значений.

Фронт строит колонки таблиц отсюда, а не из хардкода (инвариант №2).
"""

from __future__ import annotations

from django.apps import apps
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.archive import blockers, manager_of, resolve_model, restore
from core.archive import preview as archive_preview
from core.domains import (
    DOMAINS,
    ROLE_ADMIN,
    ROLE_STUDENT,
    ROLE_TITLES,
    can_delete,
    deleters_of,
    domain_of_role,
)
from core.imports import revert_batch
from core.models import ArchiveEntry, ImportBatch
from core.onboarding import build as build_checklist


def _field_payload(model_label: str, spec) -> dict:
    """Описание поля для фронта: тип, подпись, варианты значений."""
    model = apps.get_model(model_label)
    try:
        field = model._meta.get_field(spec.name)
    except Exception:
        return {"name": spec.name, "title": spec.title, "type": "string", "internal_label": spec.internal_label}

    kind = field.get_internal_type()
    payload = {
        "name": spec.name,
        "title": spec.title,
        "type": {
            "BooleanField": "boolean",
            "IntegerField": "integer",
            "PositiveSmallIntegerField": "integer",
            "SmallIntegerField": "integer",
            "BigIntegerField": "integer",
            "DecimalField": "number",
            "DateField": "date",
            "DateTimeField": "datetime",
            "ForeignKey": "reference",
        }.get(kind, "string"),
        "internal_label": spec.internal_label,
    }
    choices = getattr(field, "choices", None)
    if choices:
        payload["choices"] = [{"value": v, "title": t} for v, t in choices]
    return payload


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def domain_meta(request):
    """Реестр доменов в виде, пригодном для генерации колонок.

    Ученику ярлыки не отдаются вовсе (инвариант №7).
    """
    role = request.user.role
    own = domain_of_role(role)
    hide_labels = role == ROLE_STUDENT

    domains = []
    for domain in DOMAINS.values():
        models_payload = []
        for model in domain.models:
            fields = [_field_payload(model.label, f) for f in model.fields if not (hide_labels and f.internal_label)]
            models_payload.append({"label": model.label, "fields": fields})
        domains.append(
            {
                "code": domain.code,
                "title": domain.title,
                "emoji": domain.emoji,
                "owner_name": domain.owner_name,
                "role": domain.role,
                "is_mine": own is not None and own.code == domain.code,
                "models": models_payload,
            }
        )

    return Response(
        {
            "role": role,
            "role_title": ROLE_TITLES.get(role, role),
            "my_domain": own.code if own else None,
            "domains": domains,
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request, code: str):
    """Дашборд одного домена. Директор видит любой, ученик — никакой."""
    from core.dashboards import DASHBOARDS, school_overview

    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Дашборды доступны только сотрудникам"}, status=403)

    if code == "overview":
        # роль `admin` техническая; школу целиком видит тот, кому это
        # разрешено флагом — так у Салтанат остаётся одна роль
        if not request.user.can_see_whole_school:
            return Response({"detail": "Сводный вид доступен директору школы"}, status=403)
        return Response(school_overview())

    builder = DASHBOARDS.get(code)
    if builder is None:
        return Response({"detail": "Неизвестный дашборд"}, status=404)
    return Response(builder())


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def readiness_config(request):
    """Веса Readiness Score — чтобы фронт подписывал графики теми же числами."""
    from django.conf import settings

    return Response({"weights": settings.READINESS_WEIGHTS})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def digest(request):
    """Дайджест на сегодня — открывается при входе директора."""
    from core.digest import build

    days = int(request.query_params.get("days", 1))
    return Response(build(user=request.user, days=max(1, min(days, 30))))


# --- Фаза 14: удаление, архив и история загрузок --------------------------


def _archive_target(request):
    """Объект из запроса плюс проверка права на удаление.

    Возвращает `(instance, error_response)`. Право берётся из реестра
    доменов: директор удаляет только в своём домене (инвариант №1).
    """
    label = (request.query_params.get("model") or request.data.get("model") or "").strip()
    object_id = request.query_params.get("id") or request.data.get("id")

    model = resolve_model(label)
    if model is None:
        return None, Response({"detail": "Неизвестный вид записи"}, status=status.HTTP_400_BAD_REQUEST)
    if not can_delete(request.user.role, label):
        allowed = ", ".join(ROLE_TITLES.get(role, role) for role in deleters_of(label)) or "никто"
        return None, Response(
            {"detail": f"Удалять такие записи может: {allowed}"},
            status=status.HTTP_403_FORBIDDEN,
        )

    instance = manager_of(model).filter(pk=object_id).first()
    if instance is None:
        return None, Response({"detail": "Записи нет — возможно, её уже удалили"}, status=status.HTTP_404_NOT_FOUND)
    return instance, None


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def delete_preview(request):
    """Текст диалога подтверждения: что уйдёт и что за этим последует."""
    instance, error = _archive_target(request)
    if error is not None:
        return error

    payload = archive_preview(instance)
    if not payload["soft"]:
        reasons = blockers(instance)
        if reasons:
            payload["blocked"] = True
            payload["consequences"] = [
                "Удалить нельзя: на запись ссылаются " + "; ".join(reasons),
                "Сначала уберите эти ссылки — иначе история подачи развалится",
            ]
    return Response(payload)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def archive_list(request):
    """Экран архива: что удалено, кем, когда, что можно вернуть."""
    if request.user.role != ROLE_ADMIN:
        return Response({"detail": "Архив ведёт администратор"}, status=status.HTTP_403_FORBIDDEN)

    rows = ArchiveEntry.objects.select_related("actor", "restored_by")
    if request.query_params.get("restored") == "false":
        rows = rows.filter(restored_at__isnull=True)
    return Response(
        [
            {
                "id": row.id,
                "model": row.model_label,
                "object_id": row.object_id,
                "title": row.title,
                "kind": row.kind_title,
                "summary": row.summary,
                "related_count": row.related_count,
                "actor_name": row.actor.full_name or row.actor.email if row.actor else "",
                "created_at": row.created_at,
                "restored_at": row.restored_at,
                "restored_by_name": row.restored_by.full_name or row.restored_by.email if row.restored_by else "",
            }
            for row in rows[:200]
        ]
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def archive_restore(request, pk: int):
    """Вернуть удалённое из архива вместе со всеми связями."""
    if request.user.role != ROLE_ADMIN:
        return Response({"detail": "Восстанавливает администратор"}, status=status.HTTP_403_FORBIDDEN)

    entry = ArchiveEntry.objects.filter(pk=pk).first()
    if entry is None:
        return Response({"detail": "Записи архива нет"}, status=status.HTTP_404_NOT_FOUND)
    return Response(restore(entry, actor=request.user))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def import_batches(request):
    """История загрузок с фильтром по автору и дате."""
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "История загрузок — для сотрудников"}, status=status.HTTP_403_FORBIDDEN)

    rows = ImportBatch.objects.select_related("actor", "reverted_by")
    author = request.query_params.get("actor")
    if author:
        rows = rows.filter(actor_id=author)
    since = request.query_params.get("since")
    if since:
        rows = rows.filter(created_at__date__gte=since)
    until = request.query_params.get("until")
    if until:
        rows = rows.filter(created_at__date__lte=until)

    return Response(
        [
            {
                "id": row.id,
                "file_name": row.file_name,
                "kind": row.kind,
                "kind_title": row.get_kind_display(),
                "domain_code": row.domain_code,
                "rows_total": row.rows_total,
                "rows_created": row.rows_created,
                "rows_updated": row.rows_updated,
                "rows_failed": row.rows_failed,
                "status": row.status,
                "status_title": row.get_status_display(),
                "actor": row.actor_id,
                "actor_name": row.actor.full_name or row.actor.email if row.actor else "",
                "created_at": row.created_at,
                "reverted_at": row.reverted_at,
                "changes": row.audit_entries.count(),
                "note": row.note,
            }
            for row in rows[:200]
        ]
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_batch_revert(request, pk: int):
    """Отменить загрузку целиком: вернуть прежние значения."""
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Загрузки отменяют сотрудники"}, status=status.HTTP_403_FORBIDDEN)

    batch = ImportBatch.objects.filter(pk=pk).first()
    if batch is None:
        return Response({"detail": "Такой загрузки нет"}, status=status.HTTP_404_NOT_FOUND)
    if batch.status != ImportBatch.Status.APPLIED:
        return Response(
            {"detail": "Эту загрузку уже отменяли — второй раз откатывать нечего"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    # свою загрузку отменяет тот же домен, что её делал: чужую отменять нельзя
    if batch.domain_code and domain_of_role(request.user.role) is None:
        return Response({"detail": "У вашей роли нет домена"}, status=status.HTTP_403_FORBIDDEN)
    if batch.domain_code and domain_of_role(request.user.role).code != batch.domain_code:
        return Response(
            {"detail": "Эту загрузку делал другой директор — отменить её может он"},
            status=status.HTTP_403_FORBIDDEN,
        )

    return Response(revert_batch(batch, actor=request.user))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def getting_started(request):
    """Панель «Начало работы»: что уже сделано и куда идти дальше."""
    return Response(build_checklist(request.user).as_dict())
