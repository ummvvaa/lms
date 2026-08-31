"""Сигналы Celery: конец задачи закрывает плашку операции (фаза 47).

Задачи о плашке не знают: они как были, так и остались обычными
`shared_task`. Механизм привязывается к ним снаружи — по идентификатору
задачи, который вьюха записала в `BackgroundJob` при запуске.

Так добавление новой фоновой операции не требует помнить про уведомления
и проценты: достаточно завести запись рядом с `.delay(...)`.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def ready() -> None:
    from celery.signals import task_failure, task_success

    task_success.connect(_on_success, dispatch_uid="core.jobs.success")
    task_failure.connect(_on_failure, dispatch_uid="core.jobs.failure")


def _on_success(sender=None, result=None, **kwargs) -> None:
    from core import jobs

    task_id = getattr(getattr(sender, "request", None), "id", None)
    if not task_id:
        return
    try:
        jobs.complete(task_id, link=_link_of(result))
    except Exception:  # плашка не должна ронять саму операцию
        log.exception("не удалось закрыть фоновую операцию %s", task_id)


def _on_failure(task_id=None, exception=None, **kwargs) -> None:
    from core import jobs

    if not task_id:
        return
    try:
        jobs.fail(task_id, str(exception) if exception else "")
    except Exception:
        log.exception("не удалось пометить фоновую операцию %s сорвавшейся", task_id)


def _link_of(result) -> str:
    """Если задача вернула номер предложения — вести к нему."""
    if isinstance(result, dict) and result.get("suggestion"):
        return f"/suggestions/{result['suggestion']}"
    return ""
