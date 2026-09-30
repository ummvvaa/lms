"""Сервер на трёх языках: ни одной строки мимо перевода, каталоги полные.

Страж (`core/i18n_guard.py`) обходит код приложений: кириллическая строка —
либо строка перевода, либо объяснённое исключение. Каталоги `locale/kk` и
`locale/en` покрывают каждую строку перевода из кода, подстановки и формы
числа совпадают, скомпилированный `.mo` не отстаёт от `.po`. Язык ответа —
язык профиля вошедшего, без входа — `Accept-Language`.
"""

from __future__ import annotations

import gettext as pygettext

import pytest
from django.utils import translation
from rest_framework.test import APIClient

from accounts.models import Role
from core import i18n_guard, translations


def test_no_server_string_bypasses_translation():
    violations = i18n_guard.check_paths()
    assert not violations, f"строки мимо перевода ({len(violations)}):\n" + "\n".join(map(str, violations[:30]))


def test_the_guard_catches_what_it_should():
    source = """
from django.utils.translation import gettext as _, gettext_lazy

LABEL = gettext_lazy("Подпись")
EAGER = _("Застынет")


def view(name):
    ok = _("Ученик {name}").format(name=name)
    pieces = _(f"Ученик {name}")
    raw = "Строка мимо перевода"
    skipped = "не показывается"  # i18n-skip: сравнение с данными
    return ok, pieces, raw, skipped
"""
    reasons = {(v.line, v.reason) for v in i18n_guard.check_source(source)}
    assert (5, "gettext на уровне модуля — нужен gettext_lazy") in reasons
    assert (10, "перевод из кусков") in reasons
    assert (11, "строка мимо перевода") in reasons
    assert len(reasons) == 3


def test_catalogs_cover_every_server_string():
    wanted = {msgid for msgid, _plural in i18n_guard.translatable_strings()}
    assert len(wanted) > 500, "строки перевода не нашлись — страж ослеп"
    problems = []
    for lang in translations.LANGS:
        catalog = {entry.msgid: entry for entry in translations.read_po(lang) if not entry.obsolete}
        for msgid in sorted(wanted):
            entry = catalog.get(msgid)
            if entry is None:
                problems.append(f"{lang}: нет в каталоге «{msgid}» — makemessages")
                continue
            if "fuzzy" in entry.flags:
                problems.append(f"{lang}: неточный перевод «{msgid}»")
                continue
            problem = translations.check_translation(msgid, entry.msgstr, is_plural="|" in msgid)
            if problem:
                problems.append(f"{lang}: {problem} — «{msgid}» → «{entry.msgstr}»")
    assert not problems, f"каталоги неполные ({len(problems)}):\n" + "\n".join(problems[:30])


def test_compiled_catalog_matches_the_source():
    """`.mo` скомпилирован из текущего `.po` — иначе сервер показывает старые переводы."""
    for lang in translations.LANGS:
        path = translations.po_path(lang)
        with path.with_suffix(".mo").open("rb") as handle:
            compiled = pygettext.GNUTranslations(handle)
        stale = [
            entry.msgid
            for entry in translations.read_po(lang)
            if entry.msgstr
            and not entry.obsolete
            and "fuzzy" not in entry.flags
            and (compiled.pgettext(entry.msgctxt, entry.msgid) if entry.msgctxt else compiled.gettext(entry.msgid))
            != entry.msgstr
        ]
        assert not stale, f"{lang}: .mo отстаёт от .po — i18n_import или translations.compile_server(): {stale[:5]}"


def test_plural_forms_follow_the_language():
    from core.phrasing import tn

    with translation.override("ru"):
        assert tn(1, "{n} урок|{n} урока|{n} уроков") == "1 урок"
        assert tn(3, "{n} урок|{n} урока|{n} уроков") == "3 урока"
        assert tn(11, "{n} урок|{n} урока|{n} уроков") == "11 уроков"
    with translation.override("kk"):
        assert tn(5, "{n} урок|{n} урока|{n} уроков") == "5 сабақ"
    with translation.override("en"):
        assert tn(1, "{n} урок|{n} урока|{n} уроков") == "1 lesson"
        assert tn(5, "{n} урок|{n} урока|{n} уроков") == "5 lessons"


@pytest.mark.django_db
def test_answer_language_is_the_profile_language(make_user):
    api = APIClient()
    api.force_login(make_user(Role.STUDENT, email="lang.answer@example.kz", language="kk"))
    response = api.patch("/api/auth/me/preferences/", {"theme": "purple"}, format="json")
    assert response.status_code == 400
    assert response["Content-Language"] == "kk"
    # встроенное сообщение DRF о неверном варианте — по-казахски
    message = str(response.json()["theme"][0])
    with translation.override("kk"):
        from rest_framework.fields import ChoiceField

        expected = str(ChoiceField.default_error_messages["invalid_choice"]).format(input="purple")
    assert message == expected
    assert "не является" not in message


@pytest.mark.django_db
def test_anonymous_answer_language_comes_from_the_browser():
    api = APIClient()
    response = api.post("/api/auth/login/", {"login": "", "password": "x"}, format="json", HTTP_ACCEPT_LANGUAGE="en")
    assert response["Content-Language"] == "en"
    response = api.post("/api/auth/login/", {"login": "", "password": "x"}, format="json", HTTP_ACCEPT_LANGUAGE="de")
    assert response["Content-Language"] == "ru"
