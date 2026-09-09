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

        _warn_about_open_login()


def _warn_about_open_login() -> None:
    """Пустой `LOGIN_TRUSTED_NETWORKS` — «не ограничивать», и об этом говорится
    вслух при старте (фаза 64): молчаливое «пускать всех» на бою — это дыра,
    о которой узнают после первого перебора. В разработке и тестах не шумим.
    """
    import logging

    from django.conf import settings

    if settings.DEBUG or getattr(settings, "TESTING", False):
        return
    if not getattr(settings, "LOGIN_TRUSTED_NETWORKS", None):
        logging.getLogger("accounts.login").warning(
            "LOGIN_TRUSTED_NETWORKS пуст: блокировка по адресу действует на все сети, доверенных нет. "
            "Впишите сеть школы в deploy/.env.prod, иначе после ста неудачных попыток за час "
            "с адреса школы вход закроется для всех"
        )
