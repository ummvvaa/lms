"""Фоновые задачи билетов: анонс после публикации и минутный обход раздач."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="sport.announce_drop")
def announce_drop(drop_id: int) -> int:
    """Анонс раздачи всем ученикам её классов — уведомлением, писем нет."""
    from sport import tickets
    from sport.models import TicketDrop

    drop = TicketDrop.objects.filter(pk=drop_id).first()
    return tickets.announce(drop) if drop is not None else 0


@shared_task(name="sport.tickets_tick")
def tickets_tick() -> dict:
    """Раз в минуту: напоминание за пять минут до старта и истёкшие ответы из очереди."""
    from sport import tickets

    return {"reminded": tickets.remind_soon(), "expired": tickets.expire_offers()}
