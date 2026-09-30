"""Фаза 24: тёмная тема и три языка.

Главная проверка: строка, не вынесенная в переводы, роняет тест.
Извлечение повторяет то, которым собирались словари: все кириллические
строковые литералы фронта должны присутствовать и в kk, и в en.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from django.core import mail

from accounts import magic_link
from accounts.models import LinkPurpose, Role

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'")


def cyrillic_literals(source: str) -> set[str]:
    """Кириллические строковые литералы файла — как при сборке словарей."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"(?m)(?<![:'\"])//(?!.*').*$", "", source)
    found = set()
    for match in LITERAL.finditer(source):
        text = match.group(1)
        if CYRILLIC.search(text):
            found.add(text.replace("\\'", "'").replace("\\\\", "\\"))
    return found


def dictionary_keys(name: str) -> set[str]:
    """Ключи словаря kk.ts или en.ts — в кавычках любого вида."""
    text = (FRONTEND / "i18n" / f"{name}.ts").read_text(encoding="utf-8")
    keys = set()
    for line in text.splitlines():
        match = re.match(r"""^\s{2}('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"):""", line)
        if match:
            raw = match.group(1)
            if raw.startswith('"'):
                keys.add(json.loads(raw))
            else:
                keys.add(raw[1:-1].replace("\\'", "'").replace("\\\\", "\\"))
            continue
        # prettier снимает кавычки с ключей-идентификаторов («Август»)
        bare = re.match(r"^\s{2}([\w$А-Яа-яЁё-]+):\s", line)
        if bare:
            keys.add(bare.group(1))
    return keys


def frontend_strings() -> set[str]:
    strings: set[str] = set()
    for path in FRONTEND.rglob("*.ts*"):
        if "i18n" in path.parts or path.name == "schema.ts":
            continue
        strings |= cyrillic_literals(path.read_text(encoding="utf-8"))
    return strings


def test_every_frontend_string_is_in_both_dictionaries():
    """Строка без перевода не проходит: словари обязаны покрывать всё.

    Шаблонные литералы (`${…}`) сюда не входят — это отдельный долг,
    записан в docs/I18N.md.
    """
    strings = frontend_strings()
    assert len(strings) > 300, "извлечение строк не сработало — это не «всё переведено»"
    kk = dictionary_keys("kk")
    en = dictionary_keys("en")
    missing = sorted((strings - kk) | (strings - en))
    assert not missing, f"строки без перевода ({len(missing)}): {missing[:20]}"


def test_the_scan_actually_catches_a_new_string():
    """Сам детектор ловит подложенную строку — иначе проверка пуста."""
    found = cyrillic_literals("const x = 'Новая непереведённая строка'")
    assert found == {"Новая непереведённая строка"}
    assert cyrillic_literals("const y = 'plain english'") == set()


def test_server_dictionaries_cover_each_other():
    """У kk и en одинаковый состав ключей серверных шаблонов."""
    from core.i18n import SERVER_TEXTS

    assert set(SERVER_TEXTS["kk"]) == set(SERVER_TEXTS["en"])


def test_notification_templates_are_translated():
    """Каждый шаблон уведомления из кода есть в обоих серверных словарях."""
    from core.i18n import SERVER_TEXTS

    source = (ROOT / "backend" / "materials" / "services.py").read_text(encoding="utf-8")
    templates = re.findall(r'template="([^"]+)"', source)
    assert templates, "шаблоны уведомлений не нашлись — проверка ослепла"
    for template in templates:
        assert template in SERVER_TEXTS["kk"], f"нет казахского перевода: {template}"
        assert template in SERVER_TEXTS["en"], f"нет английского перевода: {template}"


@pytest.mark.django_db
def test_hidden_language_letters_and_notices_are_russian(make_user, student):
    """Язык не предлагается в выборе — письма и уведомления по-русски, как интерфейс.

    В профиле мог остаться `kk` или `en` (решение владельца, 30.09.2026):
    интерфейс у такого человека русский, и письмо на казахском при русском
    экране было бы вторым источником правды о языке.
    """
    from materials.services import notify

    kk_user = make_user(Role.STUDENT, email="letter.kk@example.kz", language="kk")
    magic_link.issue(kk_user.email, purpose=LinkPurpose.RESET)
    assert "сброс пароля" in mail.outbox[-1].subject

    en_user = make_user(Role.DIRECTOR_TALENT, email="notif.en@example.kz", language="en")
    row = notify(
        en_user,
        kind="material_pending",
        template="Ваш материал «{title}» одобрен и появился в библиотеке",
        title="Разбор",
    )
    assert row.text == "Ваш материал «Разбор» одобрен и появился в библиотеке"


@pytest.mark.django_db
def test_letters_follow_the_interface_language_once_offered(make_user, monkeypatch):
    """Язык включили в выбор — письмо уходит на языке интерфейса человека."""
    from core import i18n

    monkeypatch.setattr(i18n, "INTERFACE_LANGUAGES", ("ru", "kk", "en"))
    en_user = make_user(Role.STUDENT, email="letter.en@example.kz", language="en")
    magic_link.issue(en_user.email, purpose=LinkPurpose.INVITE)
    assert "platform access" in mail.outbox[-1].subject
    # срок — датой, а не длительностью (фаза 69)
    assert "is valid until" in mail.outbox[-1].body

    kk_user = make_user(Role.STUDENT, email="letter.kk@example.kz", language="kk")
    magic_link.issue(kk_user.email, purpose=LinkPurpose.RESET)
    assert "құпиясөзді қалпына келтіру" in mail.outbox[-1].subject

    ru_user = make_user(Role.STUDENT, email="letter.ru@example.kz")
    magic_link.issue(ru_user.email, purpose=LinkPurpose.LOGIN)
    assert "вход в платформу" in mail.outbox[-1].subject


@pytest.mark.django_db
def test_notifications_follow_the_interface_language_once_offered(make_user, student, monkeypatch):
    """Уведомление создаётся на языке интерфейса получателя, когда язык предлагается."""
    from core import i18n
    from materials.services import notify

    monkeypatch.setattr(i18n, "INTERFACE_LANGUAGES", ("ru", "en"))
    recipient = make_user(Role.DIRECTOR_TALENT, email="notif.en@example.kz", language="en")
    row = notify(
        recipient,
        kind="material_pending",
        template="Ваш материал «{title}» одобрен и появился в библиотеке",
        title="Разбор",
    )
    assert row.text == "Your material “Разбор” was approved and appeared in the library"


@pytest.mark.django_db
def test_me_offers_only_the_interface_languages(make_user):
    """Список языков выбора — с сервера; скрытый язык прямым запросом не включается."""
    from rest_framework.test import APIClient

    api = APIClient()
    api.force_login(make_user(Role.STUDENT, email="lang.me@example.kz"))
    assert api.get("/api/auth/me/").json()["languages"] == [{"value": "ru", "label": "Русский"}]
    assert api.patch("/api/auth/me/preferences/", {"language": "kk"}, format="json").status_code == 400
    assert api.patch("/api/auth/me/preferences/", {"language": "ru"}, format="json").status_code == 200


def test_dark_theme_tokens_exist_and_orange_is_muted():
    """Тёмный набор токенов есть, и в нём нет светлого #ff6a13."""
    tokens = (FRONTEND / "styles" / "tokens.css").read_text(encoding="utf-8")
    assert "[data-theme='dark']" in tokens
    dark = tokens.split("[data-theme='dark']", 1)[1]
    assert "ff6a13" not in dark.lower(), "оранжевый для тёмной темы должен быть приглушён"
    for token in ("--canvas", "--surface", "--good", "--warn", "--bad", "--on-accent"):
        assert f"{token}:" in dark, f"в тёмной теме не задан {token}"


def test_kazakh_draft_is_marked_unverified():
    """Казахский перевод помечен как не вычитанный носителем прямо в словаре."""
    kk_ts = (FRONTEND / "i18n" / "kk.ts").read_text(encoding="utf-8")
    assert "не вычитан" in kk_ts
