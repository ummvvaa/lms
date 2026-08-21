"""Настройки для pytest: тот же Postgres, но без лишнего шума."""

from .dev import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
# результат синхронной задачи должен попадать в backend, иначе опрос статуса его не найдёт
CELERY_TASK_STORE_EAGER_RESULT = True
LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"handlers": []}}
