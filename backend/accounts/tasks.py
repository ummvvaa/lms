"""Фоновая отправка ожидающих приглашений."""

from celery import shared_task


@shared_task(name="accounts.drain_invite_queue")
def drain_invite_queue() -> dict:
    """Очередь и защита от параллельных запусков хранятся в базе."""
    from accounts.mailing import drain_queue

    return drain_queue()
