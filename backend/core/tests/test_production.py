"""Приёмка фазы 21: система ведёт себя как боевая.

Проверяем то, что легко откатить назад незаметно: разработческие команды
в бою, следы тестовых данных в пользовательских текстах, ослабленные
настройки безопасности.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

#: Корень репозитория. В контейнере он примонтирован в /repo только
#: на чтение: сам бэкенд лежит в /app и файлов контура не видит.
ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend" / "src"


def source_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    skip = {"migrations", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", "tests"}
    return [
        path
        for path in root.rglob("*")
        if path.suffix in suffixes and not set(path.parts) & skip and not path.name.startswith("test_")
    ]


# --- Разработческие команды -----------------------------------------------


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_dev_users_command_refuses_to_run_in_production():
    """`create_dev_users` в бою не работает — и объясняет, что делать."""
    with pytest.raises(CommandError) as error:
        call_command("create_dev_users")
    assert "только при DEBUG=1" in str(error.value)
    assert "администратор" in str(error.value)


@pytest.mark.django_db
@override_settings(DEBUG=False)
@pytest.mark.parametrize("command", ["seed_demo", "seed_prep"])
def test_seeding_commands_refuse_to_run_in_production(command):
    """Демонстрационные данные в боевой базе не появляются (инвариант №8)."""
    with pytest.raises(CommandError) as error:
        call_command(command)
    assert "DEBUG" in str(error.value)


def test_no_command_can_be_forced_past_the_debug_guard():
    """У защиты нет флага «всё равно запустить».

    Такой флаг однажды нажмут в бою — и в базе школы появятся учётные
    записи с паролями из репозитория окружения.
    """
    for path in source_files(BACKEND / "accounts", (".py",)) + source_files(BACKEND / "core", (".py",)):
        text = path.read_text(encoding="utf-8")
        assert "allow-production" not in text, path
        assert "allow_production" not in text, path


@pytest.mark.django_db
def test_seed_universities_stays_available_but_marks_data_unverified():
    """Заготовка справочника остаётся командой, но данные помечены."""
    from universities.models import University

    call_command("seed_universities")
    seeded = University.objects.filter(data_source="seed")
    assert seeded.exists()
    assert not seeded.filter(is_verified=True).exists(), "заготовка не может быть подтверждённой"


# --- Следы разработки ------------------------------------------------------

#: Адреса, которых в коде быть не должно вовсе.
FORBIDDEN_ADDRESSES = ("test.student@lms.local", "test.admin@lms.local", "@lms.local")


def test_no_test_addresses_anywhere():
    """Тестовых адресов из прежних фаз в репозитории не осталось."""
    hits = []
    for root, suffixes in ((BACKEND, (".py",)), (FRONTEND, (".ts", ".tsx"))):
        for path in source_files(root, suffixes):
            if path.name == "schema.ts":
                continue
            text = path.read_text(encoding="utf-8")
            hits += [f"{path.name}: {address}" for address in FORBIDDEN_ADDRESSES if address in text]
    assert not hits, hits


#: Слова, по которым видно заглушку. Ищем только в текстах для человека.
DEV_WORDS = ("демо-режим", "demo mode", "заглушка", "lorem ipsum")

#: Незакрытая работа в комментарии. Ищем именно пометку, а не слово:
#: `todo` — законный код статуса задачи, и ловить его не надо.
UNFINISHED = re.compile(r"(?://|/\*|\{/\*|\*)\s*(TODO|FIXME|ХАК|ВРЕМЕННО)\b", re.IGNORECASE)


def test_no_development_markers_in_user_facing_text():
    """В интерфейсе нет ни «Демо-режима», ни незакрытых пометок, ни рыбы."""
    hits = []
    for path in source_files(FRONTEND, (".ts", ".tsx")):
        if path.name == "schema.ts":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            low = line.lower()
            hits += [f"{path.name}: {line.strip()[:80]}" for word in DEV_WORDS if word in low]
            if UNFINISHED.search(line):
                hits.append(f"{path.name}: {line.strip()[:80]}")
    assert not hits, hits


def test_api_answers_carry_no_development_markers(client, make_user):
    """То же самое — в текстах, которые отдаёт сервер."""
    from accounts.models import Role

    user = make_user(Role.ADMIN, email="prod.check@example.kz")
    client.force_login(user)
    for path in ("/api/meta/domains/", "/api/getting-started/", "/api/commands/", "/api/llm/status/"):
        text = client.get(path).content.decode("utf-8").lower()
        for word in DEV_WORDS:
            assert word not in text, f"{path}: {word}"


# --- Секреты ---------------------------------------------------------------


def test_secrets_are_not_in_the_repository():
    """Боевые переменные лежат только в примерах, и `.gitignore` их держит."""
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for name in ("deploy/.env.prod", "deploy/.env"):
        assert name in ignore, f"{name} не в .gitignore"

    example = (ROOT / "deploy" / ".env.prod.example").read_text(encoding="utf-8")
    for key in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "LLM_API_KEY"):
        line = next((row for row in example.splitlines() if row.startswith(f"{key}=")), "")
        assert line in (f"{key}=", ""), f"в примере окружения задано значение {key}"


def test_settings_read_secrets_only_from_the_environment():
    """Ни ключа модели, ни секрета Django в коде нет."""
    text = (BACKEND / "config" / "settings" / "base.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if "API_KEY" in line or "SECRET_KEY" in line:
            assert "env(" in line, line


# --- Боевые настройки ------------------------------------------------------


def test_production_settings_are_strict():
    """`config.settings.prod` включает всё, что требует `check --deploy`."""
    text = (BACKEND / "config" / "settings" / "prod.py").read_text(encoding="utf-8")
    required = (
        "DEBUG = False",
        "SECURE_SSL_REDIRECT",
        "SECURE_HSTS_SECONDS",
        "SECURE_HSTS_PRELOAD",
        "SESSION_COOKIE_SECURE = True",
        "CSRF_COOKIE_SECURE = True",
        "SECURE_CONTENT_TYPE_NOSNIFF",
        "X_FRAME_OPTIONS",
    )
    for item in required:
        assert item in text, f"в боевых настройках нет {item}"


def test_production_refuses_a_weak_secret_key():
    """Короткий ключ роняет запуск, а не остаётся предупреждением."""
    text = (BACKEND / "config" / "settings" / "prod.py").read_text(encoding="utf-8")
    assert "len(SECRET_KEY) < 50" in text
    assert "ImproperlyConfigured" in text


def test_rate_limits_cover_login_links_and_the_model():
    """Три предела частоты заданы и берутся из окружения."""
    from django.conf import settings

    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    for scope in ("login", "password_link", "llm"):
        assert rates.get(scope), f"нет предела для {scope}"


# --- Контур ----------------------------------------------------------------


def test_certificate_renews_by_itself():
    """Продление сертификата — служба в контуре, а не «через три месяца»."""
    compose = (ROOT / "deploy" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "certbot:" in compose, "нет службы продления сертификата"
    assert "certbot-loop.sh" in compose

    loop = (ROOT / "deploy" / "backup" / "certbot-loop.sh").read_text(encoding="utf-8")
    assert "certbot renew" in loop
    assert "--dry-run" in loop, "механизм продления должен проверяться пробным прогоном"


def test_backup_covers_files_and_verifies_itself():
    """Бэкап снимает и базу, и файлы, и сразу проверяет, что развернётся."""
    script = (ROOT / "deploy" / "backup" / "backup.sh").read_text(encoding="utf-8")
    assert "pg_restore" in script, "бэкап должен проверяться восстановлением"
    assert "tar -czf" in script, "загруженные файлы тоже часть бэкапа"
    assert "tar -tzf" in script, "архив файлов должен проверяться на читаемость"

    restore = (ROOT / "deploy" / "backup" / "restore.sh").read_text(encoding="utf-8")
    assert "tar -xzf" in restore, "восстановление должно возвращать и файлы"


def test_every_service_has_a_healthcheck():
    """У каждой службы боевого контура есть проверка здоровья."""
    compose = (ROOT / "deploy" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    # якоря `x-logging` и `x-backend` идут до `services:` — их не считаем
    body = compose.split("\nservices:", 1)[1].split("\nvolumes:", 1)[0]

    # блок службы — от её заголовка до заголовка следующей
    blocks = dict(re.findall(r"^  ([a-z][\w-]*):\n((?:(?:    |\n).*\n)*)", body, flags=re.M))
    assert blocks, "службы в боевом compose не разобрались"

    # у одноразовой сборки фронта и у служб-циклов проверять нечего:
    # они не обслуживают запросы, а падение видно по перезапускам
    skip = {"frontend-build", "backup", "certbot"}
    # именно свой healthcheck: якорь `x-backend` его не содержит, и «унаследовал»
    # здесь означало бы «проверки нет»
    for service, block in blocks.items():
        if service in skip:
            continue
        assert "healthcheck:" in block, f"у службы {service} нет healthcheck"


def test_private_files_are_not_served_by_the_web_server():
    """Том с закрытыми файлами nginx не монтирует — иначе смысл теряется."""
    compose = (ROOT / "deploy" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    nginx_block = compose.split("\n  nginx:", 1)[1].split("\n  certbot:", 1)[0]
    assert "private_media" not in nginx_block, "закрытые файлы не должны попадать к веб-серверу"
    assert "private_media:/app/private" in compose, "том закрытых файлов должен быть у бэкенда"


def test_deployment_docs_exist_and_cover_the_basics():
    """Инструкции написаны и покрывают то, что придётся делать руками."""
    deploy = (ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
    for topic in ("certbot", "восстанов", "бэкап", "seed_universities"):
        assert topic.lower() in deploy.lower(), f"в DEPLOY.md нет раздела про «{topic}»"

    admin = (ROOT / "docs" / "ADMIN.md").read_text(encoding="utf-8")
    for topic in ("пользовател", "роль", "загруз", "бэкап"):
        assert topic.lower() in admin.lower(), f"в ADMIN.md нет раздела про «{topic}»"
