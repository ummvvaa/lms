"""Фоновые задачи сдачи ДЗ."""

from __future__ import annotations

import datetime as dt

from celery import shared_task
from django.utils import timezone

#: загрузка, не дошедшая до конца за сутки, брошена
STALE_HOURS = 24


@shared_task(name="homework.drop_stale_uploads")
def drop_stale_uploads() -> int:
    """Убрать брошенные загрузки: строку и начатый объект в хранилище (части тоже)."""
    from homework.models import FileState, HomeworkFile

    edge = timezone.now() - dt.timedelta(hours=STALE_HOURS)
    dropped = 0
    for row in HomeworkFile.objects.filter(state=FileState.UPLOADING, created_at__lt=edge):
        try:
            row.drop_stored()
        except Exception:  # объекта может не быть — строку всё равно убираем
            pass
        row.delete()
        dropped += 1
    return dropped
