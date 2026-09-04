"""Боевые настройки. Всё чувствительное приходит из окружения."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env, env_bool, env_list

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

# Проверяем самое важное сразу, а не когда что-нибудь сломается: короткий
# ключ и пустой список хостов — это не «предупреждение при проверке»,
# а неработающая безопасность в бою.
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY короче 50 символов. Сгенерируйте новый: "
        'python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS пуст: укажите домен школы через запятую")
# админка на стандартном адресе — первое, что перебирают сканеры; в бою
# у неё своё слово, и наружу через Caddy открыт только этот путь
if ADMIN_PATH == "admin/":  # noqa: F405
    raise ImproperlyConfigured(
        "DJANGO_ADMIN_PATH пуст или равен «admin»: в бою админка живёт на своём адресе. "
        "Задайте одно слово без слэшей, например DJANGO_ADMIN_PATH=office-7f3a"
    )

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
#: весь трафик уходит на https. Отключать можно только там, где TLS
#: терминируется выше по цепочке и редирект делает он
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
#: пробы здоровья ходят изнутри контейнера по http и без TLS: редирект
#: на https для них — это 301 вместо 200, и Docker считал бэкенд
#: нездоровым, а Caddy не стартовал (найдено локальным подъёмом, фаза 56)
SECURE_REDIRECT_EXEMPT = [r"^healthz$", r"^readyz$"]
#: те же пробы приходят с Host: 127.0.0.1 — без этого Django отвечал бы
#: им 400 на любом сервере, где ALLOWED_HOSTS — только домен школы
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "127.0.0.1"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = 31536000 if env_bool("ENABLE_HSTS", True) else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
#: в бою умолчаний нет: список задаётся переменной окружения и только ей
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

#: Перед приложением стоит один nginx: без этого DRF считает адресом клиента
#: адрес прокси, и ограничение по адресу становится общим на всю школу.
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": 1}  # noqa: F405
