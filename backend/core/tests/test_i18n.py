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
def test_letters_arrive_in_the_recipient_language(make_user):
    """Письмо уходит на языке получателя — из его профиля."""
    en_user = make_user(Role.STUDENT, email="letter.en@example.kz", language="en")
    magic_link.issue(en_user.email, purpose=LinkPurpose.INVITE)
    assert "platform access" in mail.outbox[-1].subject
    assert "is valid for" in mail.outbox[-1].body

    kk_user = make_user(Role.STUDENT, email="letter.kk@example.kz", language="kk")
    magic_link.issue(kk_user.email, purpose=LinkPurpose.RESET)
    assert "құпиясөзді қалпына келтіру" in mail.outbox[-1].subject

    ru_user = make_user(Role.STUDENT, email="letter.ru@example.kz")
    magic_link.issue(ru_user.email, purpose=LinkPurpose.LOGIN)
    assert "вход в платформу" in mail.outbox[-1].subject


@pytest.mark.django_db
def test_notifications_arrive_in_the_recipient_language(make_user, student):
    """Уведомление создаётся на языке получателя."""
    from materials.services import notify

    recipient = make_user(Role.DIRECTOR_TALENT, email="notif.en@example.kz", language="en")
    row = notify(
        recipient,
        kind="material_pending",
        template="Ваш материал «{title}» одобрен и появился в библиотеке",
        title="Разбор",
    )
    assert row.text == "Your material “Разбор” was approved and appeared in the library"


def test_dark_theme_tokens_exist_and_orange_is_muted():
    """Тёмный набор токенов есть, и в нём нет светлого #ff6a13."""
    tokens = (FRONTEND / "styles" / "tokens.css").read_text(encoding="utf-8")
    assert "[data-theme='dark']" in tokens
    dark = tokens.split("[data-theme='dark']", 1)[1]
    assert "ff6a13" not in dark.lower(), "оранжевый для тёмной темы должен быть приглушён"
    for token in ("--milk", "--surface", "--ok", "--warn", "--risk", "--on-ink"):
        assert f"{token}:" in dark, f"в тёмной теме не задан {token}"


def test_kazakh_draft_is_marked_unverified():
    """Казахский перевод помечен как не вычитанный носителем (docs/I18N.md)."""
    doc = (ROOT / "docs" / "I18N.md").read_text(encoding="utf-8")
    assert "не вычитан" in doc
    kk_ts = (FRONTEND / "i18n" / "kk.ts").read_text(encoding="utf-8")
    assert "не вычитан" in kk_ts
