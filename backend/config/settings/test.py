"""Настройки для pytest: тот же Postgres, но без лишнего шума."""

from .dev import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
# результат синхронной задачи должен попадать в backend, иначе опрос статуса его не найдёт
CELERY_TASK_STORE_EAGER_RESULT = True
LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"handlers": []}}

#: В тестах Redis не нужен: кэш чистится фикстурой между тестами.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

#: Тесты не ходят в интернет и не тратят деньги школы. Ключ, оставленный
#: в окружении контура, до сюда не доходит: иначе прогон уезжал бы
#: к провайдеру — медленно, за деньги и с разным результатом каждый раз.
#: Тесты, которым нужна «подключённая модель», ставят её сами
#: через `override_settings`.
LLM = {**LLM, "API_KEY": ""}  # noqa: F405
