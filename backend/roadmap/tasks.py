"""Фоновые задачи роадмапа: дневной прогон напоминаний (фаза 39)."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="roadmap.daily_reminders")
def daily_reminders() -> dict:
    """Автозадачи о регистрации и напоминания о событиях — раз в день."""
    from roadmap.reminders import run_daily

    return run_daily()
