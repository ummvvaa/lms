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
