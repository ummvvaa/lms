"""Аналитика использования: безопасный пакет, сводка и две страницы Excel."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count, Max
from django.db.models.functions import TruncDate
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from accounts.models import User
from accounts.probe import probe_users
from core import usage
from core.domains import ROLE_TITLES, USAGE_READERS, USAGE_WRITERS
from core.exports import Column, workbook_of_sheets
from core.models import UsageEvent
from core.pagination import StandardPagination
from core.usage_registry import (
    ACTIONS,
    ACTIONS_BY_KEY,
    BATCH_LIMIT,
    CLIENT_ACTIONS,
    FLUSH_INTERVAL_MS,
    SCREENS,
    SCREENS_BY_KEY,
    client_screens,
)

ALMATY = ZoneInfo("Asia/Almaty")
GROUPINGS = ("action", "user", "role", "day")


class UsageThrottle(UserRateThrottle):
    scope = "usage"


class StrictSerializer(serializers.Serializer):
    """Неизвестные поля запрещены: нельзя незаметно принять actor или payload."""

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise ValidationError({"non_field_errors": [_("В пакете действий есть неизвестные поля")]})
        return super().to_internal_value(data)


class ClientEventSerializer(StrictSerializer):
    id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=CLIENT_ACTIONS)
    screen = serializers.CharField(max_length=64, trim_whitespace=False)

    def validate_screen(self, value):
        if value not in self.context["screens"]:
            raise ValidationError(_("Этот экран недоступен для записи действий"))
        return value


class ClientBatchSerializer(StrictSerializer):
    events = ClientEventSerializer(many=True, max_length=BATCH_LIMIT, allow_empty=True)


def _may_read(request) -> None:
    if request.user.role not in USAGE_READERS:
        raise PermissionDenied(_("Использование доступно администратору и директору школы"))


def _action_title(key: str) -> str:
    action = ACTIONS_BY_KEY.get(key)
    return action.title if action else _("Неизвестное действие")


def _screen_title(key: str) -> str:
    screen = SCREENS_BY_KEY.get(key)
    return screen.title if screen else _("Неизвестный экран")


def _actor_title(actor_id: int | None, full_name: str | None = None) -> str:
    if actor_id is None:
        return _("Удалённый пользователь")
    return full_name or _("Пользователь №{number}").format(number=actor_id)


def _filters(request) -> dict:
    """Один разбор фильтров для сводки, журнала и выгрузки, даты включительны."""
    params = request.query_params
    today = timezone.localdate(timezone=ALMATY)
    field = serializers.DateField()
    start = field.run_validation(params.get("from", (today - timedelta(days=29)).isoformat()))
    end = field.run_validation(params.get("to", today.isoformat()))
    if start > end or end == date.max:
        raise ValidationError({"detail": _("Проверьте начало и конец периода")})
    by = params.get("by", "action")
    if by not in GROUPINGS:
        raise ValidationError({"detail": _("Выберите разрез сводки")})
    result = {"from": start, "to": end, "by": by}
    for name, allowed in (("action", ACTIONS_BY_KEY), ("screen", SCREENS_BY_KEY), ("role", ROLE_TITLES)):
        value = params.get(name, "")
        if value:
            if value not in allowed:
                raise ValidationError({"detail": _("Неизвестное значение фильтра")})
            result[name] = value
    actor = params.get("user", "")
    if actor:
        if actor == "deleted":
            result["user"] = None
        else:
            result["user"] = serializers.IntegerField(min_value=1).run_validation(actor)
    return result


def _events(filters):
    start = datetime.combine(filters["from"], time.min, tzinfo=ALMATY)
    end = datetime.combine(filters["to"] + timedelta(days=1), time.min, tzinfo=ALMATY)
    events = UsageEvent.objects.filter(occurred_at__gte=start, occurred_at__lt=end)
    for name in ("action", "screen", "role"):
        if name in filters:
            events = events.filter(**{name: filters[name]})
    if "user" in filters:
        events = events.filter(actor_id=filters["user"])
    return events


def _cards(events) -> dict:
    totals = events.aggregate(actions=Count("pk"), active_users=Count("actor_id", distinct=True))
    top = events.values("action").annotate(count=Count("pk")).order_by("-count", "action").first()
    return {
        **totals,
        "most_frequent": (
            {"key": top["action"], "title": _action_title(top["action"]), "count": top["count"]} if top else None
        ),
        # Это состояние реальных учётных записей за всё время, а не нули
        # событий выбранного периода; аналитика не восстанавливает прошлые входы.
        "never_logged_in": User.objects.filter(is_active=True, is_fictional=False, last_login__isnull=True)
        .exclude(pk__in=probe_users())
        .count(),
    }


def _grouped(events, by: str):
    if by == "user":
        grouped = events.values("actor_id", "actor__full_name")
        ordering = ("-count", "actor_id")
    elif by == "day":
        grouped = events.annotate(day=TruncDate("occurred_at", tzinfo=ALMATY)).values("day")
        ordering = ("day",)
    else:
        grouped = events.values(by)
        ordering = ("-count", by)
    return grouped.annotate(
        count=Count("pk"), users=Count("actor_id", distinct=True), last_at=Max("occurred_at")
    ).order_by(*ordering)


def _group_row(row, by: str) -> dict:
    if by == "user":
        key = str(row["actor_id"]) if row["actor_id"] is not None else "deleted"
        title = _actor_title(row["actor_id"], row["actor__full_name"])
    elif by == "day":
        key = row["day"].isoformat()
        title = formats.date_format(row["day"], "DATE_FORMAT")
    else:
        key = row[by]
        title = _action_title(key) if by == "action" else ROLE_TITLES.get(key, _("Неизвестная роль"))
    return {"key": key, "title": title, "count": row["count"], "users": row["users"], "last_at": row["last_at"]}


def _event_row(event: UsageEvent) -> dict:
    return {
        "id": event.pk,
        "actor_id": event.actor_id,
        "actor": _actor_title(event.actor_id, event.actor.full_name if event.actor_id else None),
        "role": event.role,
        "role_title": ROLE_TITLES.get(event.role, _("Неизвестная роль")),
        "action": event.action,
        "action_title": _action_title(event.action),
        "screen": event.screen,
        "screen_title": _screen_title(event.screen),
        "occurred_at": event.occurred_at,
        "source": event.source,
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def registry(request):
    return Response(
        {
            "can_read": request.user.role in USAGE_READERS,
            "batch_limit": BATCH_LIMIT,
            "flush_interval_ms": FLUSH_INTERVAL_MS,
            "client_actions": CLIENT_ACTIONS,
            "client_screens": client_screens(request.user),
            "actions": [
                {"key": item.key, "title": item.title, "source": item.source, "screen": item.screen} for item in ACTIONS
            ],
            "screens": [{"key": item.key, "title": item.title, "aliases": [item.key]} for item in SCREENS],
            "roles": [{"key": key, "title": str(title)} for key, title in ROLE_TITLES.items()],
        }
    )


@extend_schema(request=ClientBatchSerializer, responses={200: dict, 202: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([UsageThrottle])
def summary(request):
    if request.method == "POST":
        if request.user.role not in USAGE_WRITERS:
            raise PermissionDenied(_("Запись действий недоступна для этой роли"))
        data = ClientBatchSerializer(data=request.data, context={"screens": client_screens(request.user)})
        data.is_valid(raise_exception=True)
        events = data.validated_data["events"]
        usage.track_client(request, events)
        # Не раскрываем, был ли UUID записан раньше, в том числе у другого автора.
        return Response({"accepted": len(events)}, status=202)
    _may_read(request)
    filters = _filters(request)
    events = _events(filters)
    pagination = StandardPagination()
    rows = pagination.paginate_queryset(_grouped(events, filters["by"]), request)
    response = pagination.get_paginated_response([_group_row(row, filters["by"]) for row in rows])
    response.data.update(
        period={"from": filters["from"].isoformat(), "to": filters["to"].isoformat()},
        by=filters["by"],
        cards=_cards(events),
    )
    response["Cache-Control"] = "private, no-store"
    return response


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def events_list(request):
    _may_read(request)
    events = _events(_filters(request)).select_related("actor")
    pagination = StandardPagination()
    page = pagination.paginate_queryset(events, request)
    response = pagination.get_paginated_response([_event_row(event) for event in page])
    response["Cache-Control"] = "private, no-store"
    return response


def _excel_text(value: str) -> str:
    """ФИО — данные человека, а не формула Excel."""
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _local_time(value):
    return timezone.localtime(value, ALMATY)


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export(request):
    _may_read(request)
    filters = _filters(request)
    events = _events(filters)
    grouped = [_group_row(row, filters["by"]) for row in _grouped(events, filters["by"])]
    summary_columns = [
        Column(_("Разрез"), lambda row: _excel_text(row["title"]), width=44),
        Column(_("Действий"), lambda row: row["count"]),
        Column(_("Пользователей"), lambda row: row["users"]),
        Column(_("Последнее действие"), lambda row: _local_time(row["last_at"]), width=24),
    ]
    raw = [_event_row(event) for event in events.select_related("actor").iterator(chunk_size=1000)]
    event_columns = [
        Column(_("Пользователь"), lambda row: _excel_text(row["actor"]), width=36),
        Column(_("Роль"), lambda row: row["role_title"], width=38),
        Column(_("Действие"), lambda row: row["action_title"], width=44),
        Column(_("Экран"), lambda row: row["screen_title"], width=30),
        Column(_("Время по Алматы"), lambda row: _local_time(row["occurred_at"]), width=24),
    ]
    with timezone.override(ALMATY):
        return workbook_of_sheets(
            filename=f"usage-{filters['from'].isoformat()}-{filters['to'].isoformat()}.xlsx",
            sheets=[(_("Сводка"), summary_columns, grouped), (_("События"), event_columns, raw)],
            request=request,
        )
