"""Боевые настройки. Всё чувствительное приходит из окружения."""

from .base import *  # noqa: F403
from .base import env, env_bool, env_list

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = 31536000 if env_bool("ENABLE_HSTS", True) else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
X_FRAME_OPTIONS = "DENY"
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")


# --- Наблюдаемость ---------------------------------------------------------

SENTRY_DSN = env("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        environment=env("SENTRY_ENVIRONMENT", "production"),
        # персональные данные учеников в трассировки не отправляем
        send_default_pii=False,
    )

# Логи пишем в stdout: ротацию делает docker с драйвером json-file,
# настройки размера и количества файлов заданы в боевом compose.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {process:d} {message}", "style": "{"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "llm": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
