"""Настройки для pytest: тот же Postgres, но без лишнего шума.

**Всё, от чего зависят проверки, здесь зафиксировано числами.**
Настройки тестов наследуются от `dev`, а тот читает `deploy/.env` — и
значения рабочего контура доходили до `pytest`. Через эту дыру уже
дважды приходила беда: в фазе 29 тесты уезжали к провайдеру на живом
ключе и тратили деньги владельца, в фазе 30 на машине с заполненным
файлом падали четыре теста, не имеющие отношения к правкам.

Правило простое: если проверка сверяет число, это число задано здесь,
а не приходит из окружения. Тест, зависящий от того, что лежит в `.env`
на конкретной машине, ничего не проверяет — он проверяет машину.
"""

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

# --- Значения, которые сверяют тесты (фаза 31) ---------------------------
# Ниже — умолчания из `base.py`, но записанные, а не прочитанные.
# Менять их здесь можно только вместе с тестами, которые на них смотрят.

#: `accounts.passwords`: короткий пароль отклоняется.
PASSWORD_MIN_LENGTH = 10
#: Блокировка входа: порог по адресу и доверенные сети — тесты задают своё
#: через `override_settings`, а здесь умолчания, чтобы `.env` не протекал.
LOGIN_IP_FAILURES = 100
LOGIN_TRUSTED_NETWORKS = []
SESSION_TOUCH_MINUTES = 15

#: Движок соответствия: веса позиций и нижние планки шкал.
MATCH_WEIGHTS = {"gpa": 30.0, "english": 30.0, "standardized": 25.0, "portfolio": 15.0}
MATCH_FLOORS = {"gpa": 2.0, "ielts": 5.0, "toefl": 45.0, "sat": 800.0, "act": 12.0}

#: Потолок списка вузов у ученика.
STUDENT_LIST_LIMIT = 15

#: Readiness: веса доменов, стартовые планки и цели.
READINESS_WEIGHTS = {"exam": 35.0, "admission": 25.0, "talent": 20.0, "behavior": 10.0, "sport": 10.0}

#: Категории подбора: границы по проценту (фаза 40).
MATCH_TIERS = {"safety": 90.0, "match": 70.0, "reach": 45.0}

#: Напоминания: сроки фиксированы числами (фаза 39).
REMIND_EXAM_DAYS = 14
REMIND_DEADLINE_DAYS = 14
REMIND_TASK_DAYS = 3
REMIND_EXAM_TASK_DAYS = 30

#: Портфолио: веса разделов процента заполнения (фаза 38).
PORTFOLIO_WEIGHTS = {
    "profile": 20.0,
    "academics": 25.0,
    "achievements": 20.0,
    "olympiads": 10.0,
    "sport": 10.0,
    "documents": 15.0,
}
READINESS_BASELINES = {"IELTS_FLOOR": 4.0, "SAT_FLOOR": 800.0}
READINESS_ADMISSION = {
    "TARGET_UNIVERSITIES": 3,
    "POINTS_LIST": 25.0,
    "POINTS_COMMON_APP": 25.0,
    "POINTS_ACCOUNT": 10.0,
    "POINTS_READY": 40.0,
}
READINESS_TALENT_TARGET = 8
READINESS_SPORT = {
    "TARGET_COMPETITIONS": 3,
    "POINTS_COMPETITIONS": 60.0,
    "POINTS_CERTIFICATE": 25.0,
    "POINTS_LEADERSHIP": 15.0,
}

#: Сроки ссылок и временных паролей: на них смотрят проверки входа.
PASSWORD_LINK_TTL_MINUTES = 60
MAGIC_LINK_TTL_MINUTES = 20
TEMP_PASSWORD_TTL_HOURS = 72

#: Название школы: тесты сверяют его в письмах. Пусть будет заведомо
#: не тем, что стоит в контуре, — иначе проверка «имя школы в письме»
#: проходила бы и при пустой настройке.
SCHOOL_NAME = "Школа из настроек тестов"
