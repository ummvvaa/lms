"""Тёмная тема и три языка.

Видимый текст мимо `t()` ловят правила ESLint (`npm run lint`); здесь —
то же про ключи без Node: у каждого ключа есть kk и en с теми же
подстановками и формами числа, лишних ключей нет, правила подключены.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from django.core import mail

from accounts import magic_link
from accounts.models import LinkPurpose, Role
from core import translations

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def dictionary(name: str) -> dict[str, str]:
    """Словарь kk.ts или en.ts целиком: ключ → перевод."""
    return translations.Dictionary.read(FRONTEND / "i18n" / f"{name}.ts").entries


def translation_keys() -> dict[str, bool]:
    """Ключи вызовов перевода во фронте → ключ ли это форм числа."""
    keys: dict[str, bool] = {}
    plural = translations.plural_keys(FRONTEND)
    for key in translations.frontend_usages(FRONTEND):
        keys[key] = key in plural
    return keys


def placeholders(text: str) -> set[str]:
    return translations.placeholders(text)


def test_every_translation_key_has_kk_and_en_with_same_placeholders():
    """Ключ вызова перевода есть в kk и en; подстановки и число форм совпадают.

    То же проверяет правило `i18n-keys` в `npm run lint`; здесь — чтобы
    pytest падал и без Node.
    """
    keys = translation_keys()
    assert len(keys) > 1000, "извлечение ключей не сработало — это не «всё переведено»"
    problems = []
    for lang in ("kk", "en"):
        words = dictionary(lang)
        assert len(words) > 1000, f"словарь {lang} не прочитался"
        for key, is_plural in keys.items():
            if key not in words:
                problems.append(f"{lang}: нет «{key}»")
                continue
            if placeholders(words[key]) != placeholders(key):
                problems.append(f"{lang}: подстановки «{words[key]}» ≠ «{key}»")
            forms = words[key].count("|") + 1
            if (forms > 2) if is_plural else (forms != key.count("|") + 1):
                problems.append(f"{lang}: число форм «{words[key]}»")
    assert not problems, f"переводы с ошибками ({len(problems)}): {problems[:20]}"


def test_key_scan_finds_keys_in_every_position():
    """Разбор находит ключ в любой позиции ключа и не путает его с другими строками."""
    source = """
    t(x ?? 'Событие'); tn(f(a.b(c), d).length, '{n} урок|{n} урока|{n} уроков')
    // t('в комментарии')
    const s = `${t('в шаблоне')} ${n}`; t(cond ? 'да' : 'нет'); foo('не ключ'); t(bar('тоже не ключ'))
    """
    keys = {key for _call, key, _line in translations.key_literals(source)}
    assert keys == {"Событие", "{n} урок|{n} урока|{n} уроков", "в шаблоне", "да", "нет"}


def test_dictionaries_hold_no_unused_keys():
    """В словарях только ключи, которые где-то показываются.

    Строки с сервера фронт пока переводит через `t(значение)` — они живут
    в словарях, пока сервер не переводит их сам (этап 3 перевода).
    """
    import re as re_

    used = set(translation_keys())
    server: set[str] = set()
    for path in (ROOT / "backend").rglob("*.py"):
        if "tests" in path.parts:
            continue
        for match in re_.finditer(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'', path.read_text(encoding="utf-8")):
            server.add(match.group(1) or match.group(2))
    unused = sorted(set(dictionary("kk")) - used - server)
    assert not unused, f"неиспользуемые ключи ({len(unused)}): {unused[:20]}"
    assert set(dictionary("kk")) == set(dictionary("en")), "у kk и en разный состав ключей"


def test_frontend_guard_is_wired_into_lint():
    """Правила перевода подключены к `npm run lint` и включены как ошибки."""
    package = json.loads((FRONTEND.parent / "package.json").read_text(encoding="utf-8"))
    assert "--rulesdir eslint-rules" in package["scripts"]["lint"]
    config = (FRONTEND.parent / ".eslintrc.cjs").read_text(encoding="utf-8")
    # базовая линия «сколько мест ещё можно» снята: непереведённого нет нигде
    assert not (FRONTEND.parent / "eslint-rules" / "i18n-baseline.json").exists()
    for rule in ("i18n-text", "i18n-keys", "no-raw-locale", "i18n-module-scope"):
        assert (FRONTEND.parent / "eslint-rules" / f"{rule}.js").is_file(), f"нет правила {rule}"
        assert f"'{rule}': 'error'" in config, f"правило {rule} не включено"


def test_no_hardcoded_locale_in_screens():
    """Дата и число с зашитым языком не проходят: только `lib/format.ts`."""
    pattern = re.compile(r"toLocale\w*String\(\s*'(?:ru|kk|en)")
    found = [
        f"{path.relative_to(FRONTEND)}:{line}"
        for path in FRONTEND.rglob("*.ts*")
        for line, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(text)
    ]
    assert not found, f"язык зашит в формат даты или числа: {found}"


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
def test_letters_follow_the_interface_language(make_user):
    """Письмо уходит на языке интерфейса получателя."""
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
def test_notifications_follow_the_interface_language(make_user, student):
    """Уведомление создаётся на языке интерфейса получателя, а не отправителя."""
    from materials.services import notify

    recipient = make_user(Role.DIRECTOR_TALENT, email="notif.en@example.kz", language="en")
    row = notify(
        recipient,
        kind="material_pending",
        template="Ваш материал «{title}» одобрен и появился в библиотеке",
        title="Разбор",
    )
    assert row.text == "Your material “Разбор” was approved and appeared in the library"


@pytest.mark.django_db
def test_me_offers_three_languages(make_user):
    """Три языка открыты; язык не из списка прямым запросом не включается."""
    from rest_framework.test import APIClient

    api = APIClient()
    api.force_login(make_user(Role.STUDENT, email="lang.me@example.kz"))
    offered = api.get("/api/auth/me/").json()["languages"]
    # каждый язык подписан сам собой
    assert offered == [
        {"value": "ru", "label": "Русский"},
        {"value": "kk", "label": "Қазақша"},
        {"value": "en", "label": "English"},
    ]
    assert api.patch("/api/auth/me/preferences/", {"language": "de"}, format="json").status_code == 400
    assert api.patch("/api/auth/me/preferences/", {"language": "kk"}, format="json").json()["language"] == "kk"


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
