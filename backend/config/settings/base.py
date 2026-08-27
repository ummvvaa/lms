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

# --- Школа -----------------------------------------------------------------
#: Название школы. В коде напрямую не пишется нигде: письма, вход
#: и заголовок вкладки берут его отсюда (фронт — из VITE_SCHOOL_NAME).
SCHOOL_NAME = env("SCHOOL_NAME", "Beta High School")
#: Короткое название — для свёрнутого сайдбара и узких мест.
SCHOOL_SHORT_NAME = env("SCHOOL_SHORT_NAME", "BHS")

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
    "engagement",
    "prep",
    "directories",
    "materials",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.sessions.ResilientSessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # после AuthenticationMiddleware: нужен уже опознанный request.user
    "core.actor.CurrentActorMiddleware",
    "accounts.permissions.MustChangePasswordMiddleware",
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
#: файлы, которые нельзя отдавать прямой ссылкой: `/media/` веб-сервер
#: раздаёт сам, а материалы олимпиадников видит только их группа.
#: Отдаёт их вьюха после проверки прав (`materials.views.download`)
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private")))

#: Пределы загрузки материалов олимпиадников. Школа меняет их без выката.
MATERIAL_MAX_FILE_MB = int(env("MATERIAL_MAX_FILE_MB", "15"))
MATERIAL_MAX_FILES = int(env("MATERIAL_MAX_FILES", "10"))
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
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "600/min",
        # вход: потолок поверх адресной блокировки. Низким его делать нельзя —
        # за одним школьным адресом сидит вся школа
        "login": env("LOGIN_RATE", "60/min"),
        # выдача одноразовых ссылок отправляет письмо: здесь строже
        "password_link": env("PASSWORD_LINK_RATE", "10/min"),
        # операции с моделью стоят денег: один цикл в чужом скрипте
        # не должен съесть месячный бюджет
        "llm": env("LLM_RATE", "20/min"),
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": f"{SCHOOL_NAME} — платформа подготовки к поступлению",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # «категория» есть у активности, вида спорта и задачи — генератор схемы
    # не может выбрать имя сам, и без этих подсказок в схеме появляются
    # `Category356Enum` и прочие имена, по которым ничего не понять
    "ENUM_NAME_OVERRIDES": {
        "ActivityCategoryEnum": "students.models.ActivityCategory.choices",
        "SportCategoryEnum": "directories.models.SportCategory.choices",
        "TaskCategoryEnum": "roadmap.models.TaskCategory.choices",
        "CatalogSourceEnum": "universities.models.CatalogSource.choices",
        "AttemptSourceEnum": "students.models.AttemptSource.choices",
    },
}

#: Общий кэш на все процессы: у LocMemCache он свой на каждый воркер,
#: и ограничение попыток DRF под gunicorn считалось бы по отдельности
#: в каждом из них — то есть почти не считалось бы.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", "redis://localhost:6379/0"),
    }
}

CELERY_BROKER_URL = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE

# --- Вход по почте и паролю ---------------------------------------------

#: Минимальная длина пароля. Проверка по списку распространённых и запрет
#: совпадения с почтой — в `accounts.passwords`.
PASSWORD_MIN_LENGTH = int(env("PASSWORD_MIN_LENGTH", "10"))

#: Сколько живёт ссылка на установку или сброс пароля.
PASSWORD_LINK_TTL_MINUTES = int(env("PASSWORD_LINK_TTL_MINUTES", "60"))

#: Сколько живёт временный пароль, выданный администратором. Просрочен —
#: администратор выпускает новый одной кнопкой. Трое суток: хватает
#: пропустить выходные и мало для того, чтобы письмо разошлось по рукам.
TEMP_PASSWORD_TTL_HOURS = int(env("TEMP_PASSWORD_TTL_HOURS", "72"))

# --- Одноразовые ссылки и почта ------------------------------------------
#: Ссылка на вход для выпускника — короче, чем на пароль: ею просто входят.
MAGIC_LINK_TTL_MINUTES = int(env("MAGIC_LINK_TTL_MINUTES", "20"))
#: Отдавать токен в ответе API — только для локальной отладки без почтового сервера.
MAGIC_LINK_RETURN_TOKEN = env_bool("MAGIC_LINK_RETURN_TOKEN", False)
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", "http://localhost:8080")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@school.kz")
#: Отправка идёт через SMTP сервиса рассылок. Хост не задан — Django пишет
#: письма в журнал, а администратор видит предупреждение (`core.mail`):
#: молчаливая потеря приглашения выглядит как «письмо, наверное, в спаме».
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else "django.core.mail.backends.console.EmailBackend",
)
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
#: 465 — это SSL, 587 — STARTTLS. Вместе Django их не разрешает и падает
#: при первой же отправке, поэтому SSL здесь выключает TLS сам.
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
if EMAIL_USE_SSL:
    EMAIL_USE_TLS = False
#: Без таймаута зависший почтовый сервер держит воркер до упора.
EMAIL_TIMEOUT = int(env("EMAIL_TIMEOUT", "20"))

# --- Сессия: своя, в httpOnly cookie -------------------------------------
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "lms_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(env("SESSION_COOKIE_AGE", str(60 * 60 * 12)))
# Сессию не пересохраняем на каждый запрос (фаза 36, D1): при этом каждый
# ответ переписывал cookie и данные сессии, и запрос, ушедший параллельно
# со сменой пароля, затирал новый отпечаток пароля старым. Продление
# при активности делает `core.sessions` — обновлением срока в базе,
# не трогая данные, и не чаще раза в `SESSION_TOUCH_MINUTES`.
SESSION_SAVE_EVERY_REQUEST = False
SESSION_TOUCH_MINUTES = 15

# --- Блокировка входа (фаза 36) --------------------------------------------
# Порог неудач за час с одного адреса. Порог по учётной записи (5) в коде
# и не смягчается. Умолчание — на 250 человек за одним школьным адресом.
LOGIN_IP_FAILURES = int(env("LOGIN_IP_FAILURES", "100"))
# Адреса и подсети, для которых блокировка по адресу не действует:
# «10.0.0.5, 192.168.1.0/24». По учётной записи они блокируются как все.
LOGIN_TRUSTED_NETWORKS = env_list("LOGIN_TRUSTED_NETWORKS", "")
CSRF_COOKIE_HTTPONLY = False  # фронт читает токен и кладёт в заголовок

#: Origin, с которых принимаются небезопасные методы.
#:
#: Читается здесь, а не только в prod: фронт живёт на отдельном порту
#: (Vite на 5173, nginx на 8080), Django видит Origin одного адреса и Host
#: другого и отбивает каждый POST после входа. Без этого списка интерфейс
#: в контуре разработки работает только на чтение.
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080",
)

# --- Геймификация --------------------------------------------------------
# Инвариант №12: XP даётся за действия, а не за результаты. Ни одного пункта
# про баллы экзаменов, GPA или статусы здесь нет и появиться не может.

XP_AWARDS = {
    "task_done": int(env("XP_TASK_DONE", "10")),
    "exercise_solved": int(env("XP_EXERCISE_SOLVED", "5")),
    "mock_taken": int(env("XP_MOCK_TAKEN", "25")),
    "profile_section": int(env("XP_PROFILE_SECTION", "15")),
    "essay_submitted": int(env("XP_ESSAY_SUBMITTED", "20")),
    "onboarding_done": int(env("XP_ONBOARDING_DONE", "30")),
}

#: Сколько XP на уровень. Уровни отмечают движение, а не выстраивают гонку.
XP_LEVEL_STEP = int(env("XP_LEVEL_STEP", "100"))

# --- Соответствие требованиям --------------------------------------------
# Процент соответствия — это НЕ шанс поступления (инвариант №11). Он считается
# механически от порогов в `AdmissionRequirement`: по каждому критерию берётся
# степень достижения, критерии взвешиваются, группы альтернатив (IELTS или
# TOEFL, SAT или ACT) считаются как одна позиция.
#
# Веса — по позициям, а не по отдельным экзаменам: иначе ученик с IELTS,
# но без TOEFL терял бы половину «английского» веса ни за что.

MATCH_WEIGHTS = {
    "gpa": float(env("MATCH_W_GPA", "30")),
    "english": float(env("MATCH_W_ENGLISH", "30")),
    "standardized": float(env("MATCH_W_STANDARDIZED", "25")),
    "portfolio": float(env("MATCH_W_PORTFOLIO", "15")),
}

# Нижняя планка шкалы: с неё считается прогресс к порогу. Без неё IELTS 6.0
# при пороге 6.5 давал бы 92% — число, которое льстит и ничего не значит.
#
# Планки взяты не с нуля, а с реального начала пути: у SAT шкала физически
# начинается с 800, а IELTS 5.0 — тот уровень, с которого ученики школы
# обычно стартуют. Ниже планки процент упирается в ноль, и это честно.
MATCH_FLOORS = {
    "gpa": float(env("MATCH_FLOOR_GPA", "2.0")),
    "ielts": float(env("MATCH_FLOOR_IELTS", "5.0")),
    "toefl": float(env("MATCH_FLOOR_TOEFL", "45")),
    "sat": float(env("MATCH_FLOOR_SAT", "800")),
    "act": float(env("MATCH_FLOOR_ACT", "12")),
}

#: Разумный потолок списка вузов у одного ученика. Больше — не список,
#: а свалка: заявку в каждый из них всё равно не подать.
STUDENT_LIST_LIMIT = int(env("STUDENT_LIST_LIMIT", "15"))

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
    # провайдер за интерфейсом: смена поставщика — переменная окружения,
    # а не переписывание кода операций (`suggestions/providers.py`)
    "PROVIDER": env("LLM_PROVIDER", "anthropic"),
    "API_KEY": env("LLM_API_KEY", ""),
    "BASE_URL": env("LLM_BASE_URL", "https://api.anthropic.com"),
    "MODEL": env("LLM_MODEL", "claude-sonnet-5"),
    "TIMEOUT": int(env("LLM_TIMEOUT", "60")),
    # сеть моргает, провайдер отвечает 429 и 529 — один такой ответ
    # не повод показывать директору ошибку
    "RETRIES": int(env("LLM_RETRIES", "2")),
    "RETRY_DELAY": float(env("LLM_RETRY_DELAY", "1.0")),
    # признак того, что нехранение запросов оговорено с провайдером
    # на уровне учётной записи. Заголовка, который включал бы это
    # из запроса, у Anthropic нет — придуманный он отвергает целиком
    "NO_RETENTION": env_bool("LLM_NO_RETENTION", True),
    # поиск в интернете — только по белому списку доменов
    # (`suggestions/websearch.py`): сайты вузов из справочника и Common App
    "SEARCH": env_bool("LLM_SEARCH", True),
    "SEARCH_MAX_USES": int(env("LLM_SEARCH_MAX_USES", "5")),
}

#: Прейскурант в долларах за миллион токенов. Провайдер цену в ответе
#: не присылает, а цены живут своей жизнью — держим их в настройках,
#: чтобы школа меняла их без выката.
LLM_PRICES = {
    "default": {"input": env("LLM_PRICE_INPUT", "3"), "output": env("LLM_PRICE_OUTPUT", "15")},
}

#: Цена поиска в интернете — за тысячу запросов, токенами он не считается.
LLM_PRICE_SEARCH_PER_1000 = env("LLM_PRICE_SEARCH", "10")

#: Месячный лимит расходов на модель, доллары. Ноль — лимита нет.
#: При исчерпании операции отключаются с понятным текстом, а не молча.
LLM_MONTHLY_LIMIT = env("LLM_MONTHLY_LIMIT", "0")

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
