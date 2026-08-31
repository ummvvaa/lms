"""Конфигурация приложения core."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Ядро"

    def ready(self) -> None:
        # сигналы аудита подключаются при старте приложения
        from core import signals

        signals.ready()

        # фоновые операции: конец задачи Celery закрывает плашку и шлёт
        # уведомление — один механизм на все долгие дела (фаза 47)
        from core import job_signals

        job_signals.ready()
