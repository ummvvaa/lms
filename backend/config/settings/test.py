"""Настройки для pytest: тот же Postgres, но без лишнего шума."""

from .dev import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"handlers": []}}
