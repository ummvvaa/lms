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


def test_seeding_commands_are_removed_entirely():
    """`seed_demo` и `seed_prep` удалены из кода целиком (фаза 22).

    Не «запрещены в бою», а отсутствуют: команду, которая есть, однажды
    запустят. `seed_universities` остаётся — это справочник, а не выдуманные
    ученики.
    """
    from django.core.management import get_commands

    commands = get_commands()
    assert "seed_demo" not in commands
    assert "seed_prep" not in commands
    assert "seed_universities" in commands


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
        found = emoji_in(text)
        assert not found, f"{path}: эмодзи {found}"


# --- Эмодзи (фаза 22) -------------------------------------------------------

#: Диапазоны пиктографических символов. Стрелки (→, ←), маркеры списков
#: и геометрические фигуры сюда не входят — это типографика, а не эмодзи.
EMOJI_RANGES = (
    (0x1F000, 0x1FFFF),  # эмодзи, пиктограммы, флаги
    (0x2600, 0x27BF),  # значки и дингбаты: ⚠, ✦, ✎, ☰ и прочие
    (0x2B00, 0x2BFF),  # звёзды и стрелки с эмодзи-начертанием
    (0xFE00, 0xFE0F),  # селекторы эмодзи-начертания
)

#: «✓» (U+2713) — типографский маркер состояния («✓ сохранено»),
#: рисуется текстом в любом шрифте. Единственное исключение.
EMOJI_ALLOWED = {0x2713}


def emoji_in(text: str) -> list[str]:
    return sorted(
        {
            f"U+{ord(ch):04X} {ch}"
            for ch in text
            if ord(ch) not in EMOJI_ALLOWED and any(low <= ord(ch) <= high for low, high in EMOJI_RANGES)
        }
    )


def test_no_emoji_in_frontend_sources():
    """Эмодзи убраны из интерфейса и не возвращаются (фазы 22 и 26).

    С фазы 26 исключений не осталось: иконки навигации и колокольчик
    уведомлений нарисованы контурами (`layout/icons.tsx`), и файл описания
    навигации проверяется наравне с остальными. Не сканируется только
    генерируемый `schema.ts`.
    """
    files = [*source_files(FRONTEND, (".ts", ".tsx", ".css")), FRONTEND.parent / "index.html"]
    # пустой список значит, что каталог фронта не виден — это не «эмодзи нет»
    assert len(files) > 10, f"исходники фронта не найдены в {FRONTEND}"
    nav = FRONTEND / "layout" / "nav.ts"
    assert nav in files, "файл описания навигации не попал в проверку"
    hits = []
    for path in files:
        if path.name in ("schema.ts",):
            continue
        found = emoji_in(path.read_text(encoding="utf-8"))
        if found:
            hits.append(f"{path.name}: {', '.join(found)}")
    assert not hits, hits


def test_no_emoji_in_backend_sources():
    """И в строках, уходящих пользователю с сервера: уведомления, дайджест,
    письма, ошибки, подсказки. Проверяем исходники целиком — так эмодзи
    не спрячется и в новом тексте."""
    hits = []
    for path in source_files(BACKEND, (".py",)):
        found = emoji_in(path.read_text(encoding="utf-8"))
        if found:
            hits.append(f"{path}: {', '.join(found)}")
    assert not hits, hits


def test_emoji_scan_actually_catches_emoji():
    """Сама проверка ловит подложенный символ — иначе она ничего не значит."""
    assert emoji_in("Готово 🎉")
    assert emoji_in("внимание ⚠")
    assert not emoji_in("Было → станет, ✓ сохранено")


# --- Навигация (фаза 26) ----------------------------------------------------


def test_every_menu_item_opens_a_screen_of_its_own():
    """Пункт меню — отдельный экран, а не прокрутка к секции дашборда.

    Раздел, до которого надо доскроллить, человек разделом не считает:
    адрес такого пункта нечем открыть в новой вкладке и некому отправить.
    Проверяем по исходникам: у каждого пункта есть маршрут, и два пункта
    не ведут на один и тот же экран.
    """
    nav = (FRONTEND / "layout" / "nav.ts").read_text(encoding="utf-8")
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")

    assert "anchor" not in nav, "в навигации снова появились якори секций"

    paths = set(re.findall(r"path: '(/[a-z0-9/-]*)'", nav))
    assert len(paths) > 15, "пункты меню не разобрались — проверка ничего не значит"

    routes = dict(re.findall(r'<Route path="(/[a-z0-9/:-]*)" element=\{<(\w+)', app))
    missing = sorted(path for path in paths if path not in routes)
    assert not missing, f"пункт меню без своего маршрута: {missing}"

    screens: dict[str, list[str]] = {}
    for path in sorted(paths):
        screens.setdefault(routes[path], []).append(path)
    shared = {screen: items for screen, items in screens.items() if len(items) > 1}
    assert not shared, f"пункты меню ведут на один экран: {shared}"


# --- Цвета (фаза 26) --------------------------------------------------------

#: Цвет, записанный числом: #rrggbb, rgb(), hsl(). `color-mix()` сюда
#: не входит — он смешивает уже существующие токены.
COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(")

#: Свойства, значение которых — цвет. Имя цвета словом ищем только здесь:
#: иначе `white-space: nowrap` считался бы белым цветом.
COLOR_PROPERTY = re.compile(
    r"\b(?:color|background|background-color|border(?:-[a-z]+)?-?color|border|fill|stroke"
    r"|box-shadow|outline(?:-color)?|caret-color|accent-color|text-decoration-color)\s*:"
    r"\s*([^;{}\n]+)",
    re.IGNORECASE,
)

#: Имена цветов CSS, которые правдоподобно написать руками.
NAMED_COLORS = {
    "black",
    "white",
    "red",
    "green",
    "blue",
    "gray",
    "grey",
    "silver",
    "navy",
    "teal",
    "orange",
    "yellow",
    "purple",
    "pink",
    "brown",
    "maroon",
    "olive",
    "lime",
    "aqua",
    "fuchsia",
    "darkgray",
    "lightgray",
    "whitesmoke",
}

#: Файл токенов — единственное место, где цвет записан числом.
TOKENS_FILE = "tokens.css"


def colors_in(text: str) -> list[str]:
    """Цвета, заданные не через токен. Пусто — значит всё через переменные."""
    found = {match.group(0) for match in COLOR_LITERAL.finditer(text)}
    for match in COLOR_PROPERTY.finditer(text):
        # имя токена не цвет: `var(--teal)` — это ссылка, а не «teal»
        value = re.sub(r"var\(\s*--[a-z0-9-]+", " ", match.group(1))
        words = re.findall(r"[a-zA-Z]+", value)
        found |= {word.lower() for word in words if word.lower() in NAMED_COLORS}
    return sorted(found)


def test_frontend_components_take_colors_only_from_tokens():
    """Зашитый цвет в компоненте — это место, где тёмная тема не работает.

    Тёмная тема переопределяет токены; всё, что записано числом или именем
    цвета мимо них, остаётся светлым — так и появлялся чёрный текст
    на тёмном фоне. Единственное исключение — сам файл токенов.
    """
    files = [*source_files(FRONTEND, (".ts", ".tsx", ".css")), FRONTEND.parent / "index.html"]
    assert len(files) > 10, f"исходники фронта не найдены в {FRONTEND}"
    hits = []
    for path in files:
        if path.name in ("schema.ts", TOKENS_FILE):
            continue
        found = colors_in(path.read_text(encoding="utf-8"))
        if found:
            hits.append(f"{path.name}: {', '.join(found)}")
    assert not hits, hits


def test_dark_theme_redefines_every_colour_token():
    """У каждого цветового токена есть тёмный двойник.

    Токен, объявленный только в светлом наборе, в тёмной теме остаётся
    светлым — это тот же дефект, только через переменную.
    """
    text = (FRONTEND / "styles" / TOKENS_FILE).read_text(encoding="utf-8")
    light, dark = text.split(":root[data-theme='dark']")
    #: не цвета: скругления, тени, шрифты, шаг сетки
    skip = ("--radius", "--font", "--space", "--shadow", "--domain")
    names = {name for name in re.findall(r"(--[a-z0-9-]+)\s*:", light) if not name.startswith(skip)}
    missing = sorted(name for name in names if f"{name}:" not in dark.replace(" ", ""))
    assert not missing, f"нет тёмного значения: {missing}"


def test_colour_scan_actually_catches_a_hardcoded_colour():
    """Сама проверка ловит подложенный цвет — иначе она ничего не значит."""
    assert colors_in("color: #000")
    assert colors_in("background: rgba(0, 0, 0, 0.5)")
    assert colors_in(".x { color: black }")
    assert not colors_in("white-space: nowrap; color: var(--ink)")
    assert not colors_in("background: color-mix(in srgb, var(--brand) 20%, transparent)")
    assert not colors_in("background: var(--teal-soft);\n  color: var(--teal);")


# --- Файл настроек (фаза 28) ------------------------------------------------

#: Как в настройках читается переменная окружения.
ENV_CALL = re.compile(r"env(?:_bool|_list)?\(\s*\"([A-Z0-9_]+)\"")

#: Строка примера: `ИМЯ=значение`, в том числе закомментированная —
#: закомментированная переменная тоже названа и объяснена, а это и нужно.
ENV_LINE = re.compile(r"^#?\s*([A-Z0-9_]+)=", re.MULTILINE)

ENV_EXAMPLES = ("deploy/.env.example", "deploy/.env.prod.example")


def env_names_in_code() -> set[str]:
    names: set[str] = set()
    for path in (ROOT / "backend" / "config" / "settings").glob("*.py"):
        names |= set(ENV_CALL.findall(path.read_text(encoding="utf-8")))
    return names


def env_names_in(path: Path) -> set[str]:
    return set(ENV_LINE.findall(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("example", ENV_EXAMPLES)
def test_every_setting_is_named_in_the_example(example):
    """Переменная, которую читает код, обязана быть в примере.

    Иначе владелец заполняет файл по документации, выкатывает — и
    получает поведение по умолчанию там, где ждал своего значения.
    Про переменную, которой нет в примере, он просто не узнает.
    """
    names = env_names_in_code()
    assert len(names) > 40, "переменные в настройках не разобрались — проверка ничего не значит"

    listed = env_names_in(ROOT / example)
    missing = sorted(names - listed)
    assert not missing, f"{example}: не названы переменные {missing}"


def test_env_guide_covers_the_required_ones():
    """`docs/ENV.md` объясняет то, без чего система не поднимется.

    Список обязательных — не «все подряд», а те, у которых нет разумного
    умолчания: без них контур либо не стартует, либо работает опасно.
    """
    guide = (ROOT / "docs" / "ENV.md").read_text(encoding="utf-8")
    required = (
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "POSTGRES_PASSWORD",
        "FRONTEND_BASE_URL",
        "CSRF_TRUSTED_ORIGINS",
        "EMAIL_HOST",
        "DEFAULT_FROM_EMAIL",
        "LLM_API_KEY",
        "LLM_MONTHLY_LIMIT",
    )
    for name in required:
        assert name in guide, f"в docs/ENV.md не описана переменная {name}"
    # три группы из задания: без вариантов, для писем, для модели
    for heading in ("Обязательные", "письм", "модел"):
        assert heading.lower() in guide.lower(), f"в docs/ENV.md нет раздела «{heading}»"


def test_env_guide_block_can_be_copied_as_is():
    """Готовый кусок для вставки — с пустыми значениями, а не с чужими.

    Пример с подставленным ключом однажды копируют целиком, вместе
    с ключом, и он уезжает в чужой контур.
    """
    guide = (ROOT / "docs" / "ENV.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```(?:env|dotenv|ini)?\n(.*?)```", guide, re.S)
    assert blocks, "в docs/ENV.md нет блока, который можно скопировать"

    filled = []
    for block in blocks:
        for line in block.splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "LLM_API_KEY", "EMAIL_HOST_PASSWORD"):
                if value.strip():
                    filled.append(line)
    assert not filled, f"в готовом блоке проставлены секреты: {filled}"


# --- Пустые состояния и разделы (фаза 29) -----------------------------------


def test_every_section_explains_itself_in_its_own_words():
    """Три раздела подряд с одинаковой заглушкой читаются как один экран.

    Человек на пустой базе решает, что меню сломано, а не что данных ещё
    нет. Поэтому текст пустого состояния у каждого раздела свой, и это
    проверяется, а не остаётся на добрую волю.
    """
    hints: dict[str, list[str]] = {}
    for path in source_files(FRONTEND, (".tsx",)):
        text = path.read_text(encoding="utf-8")
        for hint in re.findall(r"hint=\{t\(\s*'([^']+)'", text):
            hints.setdefault(hint, []).append(path.name)

    assert len(hints) >= 10, "пустые состояния не разобрались — проверка ничего не значит"
    repeated = {hint: names for hint, names in hints.items() if len(names) > 1}
    assert not repeated, f"один и тот же текст в разных разделах: {repeated}"


def test_getting_started_panel_lives_only_on_dashboards():
    """Панель «Начало работы» — только на дашборде.

    На каждом разделе подряд она занимает пол-экрана и повторяет одно
    и то же: человек перестаёт её читать уже на втором переходе.
    """
    allowed = {"EmptyDashboard.tsx", "GettingStarted.tsx", "Shell.tsx"}
    hits = []
    for path in source_files(FRONTEND, (".tsx",)):
        if path.name in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if "<GettingStarted" not in text:
            continue
        if path.parent.name != "dashboards":
            hits.append(path.name)
    assert not hits, f"панель «Начало работы» вне дашборда: {hits}"


# --- Убранные разделы (фаза 29) ---------------------------------------------


def test_alumni_section_is_gone_everywhere():
    """Каталога выпускников нет ни в коде, ни в маршрутах, ни в меню.

    Убирали целиком: приложение, эндпойнты, экран, пункт меню и запросы.
    Осталось только то, что нужно для входа, — год выпуска у ученика
    и вторая идентичность по личной почте.
    """
    from django.apps import apps
    from django.urls import get_resolver

    assert "alumni" not in {config.label for config in apps.get_app_configs()}

    routes = str(get_resolver().url_patterns)
    for word in ("alumni", "mentorship", "archived-essays"):
        assert word not in routes, f"в маршрутах осталось «{word}»"

    frontend_hits = []
    for path in source_files(FRONTEND, (".ts", ".tsx")):
        # словари переводов — данные, а не код; вход по ссылке для
        # выпускника остался и называется там своим именем
        if path.name == "schema.ts" or path.parent.name == "i18n":
            continue
        text = path.read_text(encoding="utf-8").lower()
        if "alumni" in text or "mentorship" in text:
            frontend_hits.append(path.name)
    assert not frontend_hits, f"во фронте остались следы выпускников: {frontend_hits}"


def test_graduation_year_and_second_identity_survived():
    """Год выпуска и вторая почта остались: они нужны для входа."""
    from accounts.models import Identity, IdentityProvider
    from students.models import Student

    assert Student._meta.get_field("graduation_year") is not None
    assert IdentityProvider.EMAIL_LINK in {value for value, _ in IdentityProvider.choices}
    assert Identity._meta.get_field("email") is not None


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
