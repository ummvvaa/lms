"""Общие настройки Django. Секреты — только из переменных окружения."""

import os
from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str:
    """Переменная окружения; без значения и без умолчания — ошибка запуска."""
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Не задана обязательная переменная окружения {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in env(name, default).split(",") if x.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "core",
    "accounts",
    "students",
    "universities",
    "suggestions",
    "roadmap",
    "alumni",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "lms"),
        "USER": env("POSTGRES_USER", "lms"),
        "PASSWORD": env("POSTGRES_PASSWORD", "lms"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = env("TZ", "Asia/Almaty")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "600/min"},
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Платформа подготовки к поступлению",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

CELERY_BROKER_URL = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE

# --- Вход через Microsoft Entra ID ---------------------------------------

ENTRA_TENANT_ID = env("ENTRA_TENANT_ID", "")
ENTRA_CLIENT_ID = env("ENTRA_CLIENT_ID", "")
ENTRA = {
    "TENANT_ID": ENTRA_TENANT_ID,
    "CLIENT_ID": ENTRA_CLIENT_ID,
    "ISSUER": env("ENTRA_ISSUER", f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/v2.0"),
    "JWKS_URL": env("ENTRA_JWKS_URL", f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys"),
    "LEEWAY_SECONDS": int(env("ENTRA_LEEWAY_SECONDS", "60")),
}


#: Маппинг групп Entra на роли. Задаётся настройкой, а не кодом:
#: `ENTRA_GROUP_ROLE_MAP=<guid>:director_exam,<guid>:director_admission`.
#: Порядок в строке задаёт приоритет, если человек в нескольких группах.
def _parse_group_map(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        group_id, role = pair.split(":", 1)
        out[group_id.strip()] = role.strip()
    return out


ENTRA_GROUP_ROLE_MAP = _parse_group_map(env("ENTRA_GROUP_ROLE_MAP", ""))
ENTRA_DEFAULT_ROLE = env("ENTRA_DEFAULT_ROLE", "student")

# --- Вторая дверь для выпускников ----------------------------------------

MAGIC_LINK_TTL_MINUTES = int(env("MAGIC_LINK_TTL_MINUTES", "20"))
MAGIC_LINK_RETURN_TOKEN = env_bool("MAGIC_LINK_RETURN_TOKEN", False)
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", "http://localhost:8080")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@school.kz")
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)

# --- Сессия: своя, в httpOnly cookie -------------------------------------

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "lms_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(env("SESSION_COOKIE_AGE", str(60 * 60 * 12)))
SESSION_SAVE_EVERY_REQUEST = True
CSRF_COOKIE_HTTPONLY = False  # фронт читает токен и кладёт в заголовок

# --- Readiness Score -----------------------------------------------------
# Веса конфигурируемы: школа подкручивает их без выката кода.
# Сумма должна давать 100; вес отсутствующего домена расходится по остальным.

READINESS_WEIGHTS = {
    "exam": float(env("READINESS_W_EXAM", "35")),
    "admission": float(env("READINESS_W_ADMISSION", "25")),
    "talent": float(env("READINESS_W_TALENT", "20")),
    "behavior": float(env("READINESS_W_BEHAVIOR", "10")),
    "sport": float(env("READINESS_W_SPORT", "10")),
}

#: Стартовые планки: прогресс считается от них к личной цели ученика.
READINESS_BASELINES = {
    "IELTS_FLOOR": float(env("READINESS_IELTS_FLOOR", "4.0")),
    "SAT_FLOOR": float(env("READINESS_SAT_FLOOR", "800")),
}

READINESS_ADMISSION = {
    "TARGET_UNIVERSITIES": int(env("READINESS_TARGET_UNIVERSITIES", "3")),
    "POINTS_LIST": 25.0,
    "POINTS_COMMON_APP": 25.0,
    "POINTS_ACCOUNT": 10.0,
    "POINTS_READY": 40.0,
}

READINESS_TALENT_TARGET = int(env("READINESS_TALENT_TARGET", "8"))

READINESS_SPORT = {
    "TARGET_COMPETITIONS": int(env("READINESS_SPORT_COMPETITIONS", "3")),
    "POINTS_COMPETITIONS": 60.0,
    "POINTS_CERTIFICATE": 25.0,
    "POINTS_LEADERSHIP": 15.0,
}

# --- Модель (LLM) --------------------------------------------------------
# Ключа нет — система работает в офлайн-режиме: разбор идёт правилами.

LLM = {
    "API_KEY": env("LLM_API_KEY", ""),
    "BASE_URL": env("LLM_BASE_URL", "https://api.anthropic.com"),
    "MODEL": env("LLM_MODEL", "claude-sonnet-5"),
    "TIMEOUT": int(env("LLM_TIMEOUT", "60")),
    # просим провайдера не хранить запросы
    "NO_RETENTION": env_bool("LLM_NO_RETENTION", True),
}

#: Порог уверенности, выше которого строку предложения можно принять пачкой.
SUGGESTION_CONFIDENCE_THRESHOLD = float(env("SUGGESTION_CONFIDENCE_THRESHOLD", "0.9"))

# --- Фоновая сверка дедлайнов -------------------------------------------
# Ходим только по белому списку: сайты вузов из справочника и Common App.

SYNC_TIMEOUT = int(env("SYNC_TIMEOUT", "20"))
SYNC_USER_AGENT = env("SYNC_USER_AGENT", "SchoolAdmissionsBot/1.0 (+https://school.kz)")
SYNC_EXTRA_HOSTS = env_list("SYNC_EXTRA_HOSTS", "")

CELERY_BEAT_SCHEDULE = {
    "sync-deadlines": {
        "task": "universities.sync_deadlines",
        # раз в сутки ночью: чаще незачем, дедлайны меняются редко
        "schedule": crontab(hour=3, minute=0),
    },
    "promote-graduates": {
        "task": "universities.promote_graduates",
        "schedule": crontab(hour=4, minute=0),
    },
    "readiness-snapshot": {
        "task": "core.snapshot_readiness",
        # понедельник: недельный срез для графиков динамики
        "schedule": crontab(hour=2, minute=0, day_of_week=1),
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {asctime} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
