"""Снимок принятого действия и фоновая запись без данных затронутых учеников."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from core.usage_registry import ACTIONS_BY_KEY, EXPORT_SCREENS

logger = logging.getLogger(__name__)
RETENTION_DAYS = 365
PUBLISH_TIMEOUT = 0.25
EVENT_NAMESPACE = uuid.UUID("ef8e5d82-c46c-49ac-8a31-a482ea554c64")


def _real_actor(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_active or user.is_fictional or user.is_probe:
        return None
    return user


def _snapshot(user, *, event_id, action: str, screen: str, source: str, occurred_at) -> dict:
    # UUID клиента имеет пространство пользователя. Уникальный внутренний UUID
    # остаётся тем же и после удаления пользователя (FK становится NULL), поэтому
    # повтор доставки не создаёт копию; одинаковые UUID разных людей независимы.
    return {
        "event_id": str(uuid.uuid5(EVENT_NAMESPACE, f"{user.pk}:{event_id}")),
        "actor_id": user.pk,
        "role": str(user.role),
        "action": action,
        "screen": screen,
        "source": source,
        "occurred_at": occurred_at.isoformat(),
    }


def _enqueue(events: list[dict]) -> None:
    if not events:
        return

    def publish():
        from core.tasks import record_usage_events

        try:
            # Отдельный producer не ждёт свободного места в общем пуле.
            # retry=False относится к публикации; первоначальное подключение
            # и Redis-сокет ограничиваем отдельно, только для аналитики.
            app = record_usage_events.app
            with app.connection_for_write(
                connect_timeout=PUBLISH_TIMEOUT,
                transport_options={
                    "socket_connect_timeout": PUBLISH_TIMEOUT,
                    "socket_timeout": PUBLISH_TIMEOUT,
                    "retry_on_timeout": False,
                    "max_retries": 0,
                    "connect_retries_timeout": PUBLISH_TIMEOUT,
                },
            ) as connection:
                with app.amqp.Producer(connection) as producer:
                    record_usage_events.apply_async(args=[events], producer=producer, retry=False, ignore_result=True)
        except Exception:
            # Ошибка телеметрии не отменяет принятое действие. Ни тело пакета,
            # ни текст ошибки подключения (в нём бывают реквизиты) не журналируем.
            logger.warning("Не удалось передать события использования в очередь")

    transaction.on_commit(publish, robust=True)


def track(request, action_key: str) -> None:
    """Один вызов после принятой операции; bulk считается целиком, не по строкам."""
    user = _real_actor(request)
    if user is None:
        return
    action = ACTIONS_BY_KEY.get(action_key)
    if action is None or action.source != "server":
        logger.warning("Серверное действие отсутствует в реестре использования")
        return
    screen = action.screen
    if action_key == "export.download":
        from core.exports import wants_preview

        if wants_preview(request):
            return
        screen = EXPORT_SCREENS.get(getattr(getattr(request, "resolver_match", None), "url_name", None))
    if screen is None:
        return
    _enqueue(
        [
            _snapshot(
                user,
                event_id=uuid.uuid4(),
                action=action_key,
                screen=screen,
                source="server",
                occurred_at=timezone.now(),
            )
        ]
    )


def track_client(request, events: list[dict]) -> None:
    """Проверенный API пакет: время и роль берутся с сервера, а не из браузера."""
    user = _real_actor(request)
    if user is None:
        return
    now = timezone.now()
    _enqueue(
        [
            _snapshot(
                user,
                event_id=event["id"],
                action=event["action"],
                screen=event["screen"],
                source="client",
                occurred_at=now,
            )
            for event in events
        ]
    )


@transaction.atomic
def store_events(events: list[dict]) -> int:
    """Повторная доставка безопасна; удаление автора не переписывает снимок роли."""
    from accounts.models import User
    from core.models import UsageEvent

    # Держим существующих авторов до вставки: удаление между SELECT и INSERT
    # иначе нарушило бы FK. no_key не блокирует чужие вставки ссылок на User.
    actor_ids = {event["actor_id"] for event in events}
    existing = set(
        User.objects.select_for_update(no_key=True).filter(pk__in=actor_ids).order_by("pk").values_list("pk", flat=True)
    )
    rows = [
        UsageEvent(
            event_id=event["event_id"],
            actor_id=event["actor_id"] if event["actor_id"] in existing else None,
            role=event["role"],
            action=event["action"],
            screen=event["screen"],
            source=event["source"],
            occurred_at=datetime.fromisoformat(event["occurred_at"]),
        )
        for event in events
    ]
    UsageEvent.objects.bulk_create(rows, ignore_conflicts=True, batch_size=100)
    return len(rows)


def purge_old_events() -> int:
    """Раз в неделю удаляем только события строго старше 365 суток."""
    from core.models import UsageEvent

    count, _ = UsageEvent.objects.filter(occurred_at__lt=timezone.now() - timedelta(days=RETENTION_DAYS)).delete()
    return count
