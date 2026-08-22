"""Метаданные для фронта: реестр доменов и справочники значений.

Фронт строит колонки таблиц отсюда, а не из хардкода (инвариант №2).
"""

from __future__ import annotations

from django.apps import apps
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.domains import DOMAINS, ROLE_STUDENT, ROLE_TITLES, domain_of_role


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
