"""Настройки для локальной разработки."""

from .base import *  # noqa: F403
from .base import env_bool

DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

#: ключ паролей учеников — фиксированный для контура разработки и тестов (фаза 65)
CREDENTIALS_KEY = CREDENTIALS_KEY or "H_NSLockqCkfmX4srlV8APcg38BKjiwF0qU534WsZYk="  # noqa: F405
