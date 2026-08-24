"""Фаза 23: бренд школы, предпочтения интерфейса, профиль.

Свёрнутость сайдбара, тема и язык живут на сервере — они должны
пережить смену устройства, а не остаться в localStorage одного браузера.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.core import mail
from django.test import Client

from accounts import magic_link
from accounts.models import LinkPurpose, Role, User


@pytest.fixture
def logged_in(client, make_user):
    user = make_user(Role.DIRECTOR_EXAM, email="prefs.exam@example.kz")
    client.force_login(user)
    return user


@pytest.mark.django_db
def test_preferences_are_saved_on_the_server(client, logged_in):
    response = client.patch(
        "/api/auth/me/preferences/",
        {"sidebar_collapsed": True, "theme": "dark", "language": "kk"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.data["sidebar_collapsed"] is True
    assert response.data["theme"] == "dark"
    assert response.data["language"] == "kk"

    # «переживает смену устройства»: другой клиент, та же учётная запись
    other = Client()
    other.force_login(User.objects.get(pk=logged_in.pk))
    me = other.get("/api/auth/me/").data
    assert me["sidebar_collapsed"] is True
    assert me["theme"] == "dark"
    assert me["language"] == "kk"


@pytest.mark.django_db
def test_unknown_theme_is_rejected(client, logged_in):
    response = client.patch(
        "/api/auth/me/preferences/",
        {"theme": "neon"},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_partial_patch_keeps_other_preferences(client, logged_in):
    client.patch("/api/auth/me/preferences/", {"theme": "dark"}, content_type="application/json")
    response = client.patch(
        "/api/auth/me/preferences/", {"sidebar_collapsed": True}, content_type="application/json"
    )
    assert response.data["theme"] == "dark"
    assert response.data["sidebar_collapsed"] is True


@pytest.mark.django_db
def test_me_carries_group_and_last_login(client, make_user, student):
    user = make_user(Role.STUDENT, email=student.email)
    student.user = user
    student.save(update_fields=["user"])
    client.force_login(user)

    me = client.get("/api/auth/me/").data
    assert me["group"] == student.group.code
    assert "last_login" in me


@pytest.mark.django_db
def test_invite_letter_carries_school_name_and_logo(make_user):
    """Письмо подписано школой из настроек, а не безымянной «платформой»."""
    user = make_user(Role.STUDENT, email="brand.check@example.kz")
    magic_link.issue(user.email, purpose=LinkPurpose.INVITE)

    assert len(mail.outbox) == 1
    letter = mail.outbox[0]
    assert settings.SCHOOL_NAME in letter.subject
    assert settings.SCHOOL_NAME in letter.body
    html = next(content for content, kind in letter.alternatives if kind == "text/html")
    assert "/brand/logo-email.png" in html


def test_school_name_is_not_hardcoded_outside_settings():
    """Название школы нигде не написано в коде напрямую (фаза 23).

    Бэкенд берёт его из `settings.SCHOOL_NAME`, фронт — из `branding.ts`,
    который читает переменные сборки.
    """
    from pathlib import Path

    root = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
    hits = []
    for base, suffixes in ((root / "backend", (".py",)), (root / "frontend" / "src", (".ts", ".tsx"))):
        for path in base.rglob("*"):
            # `config/settings` — единственное законное место умолчания
            skip = {"migrations", "node_modules", "__pycache__", "tests", "settings"}
            if path.suffix not in suffixes or set(path.parts) & skip or path.name.startswith("test_"):
                continue
            if "Beta High School" in path.read_text(encoding="utf-8"):
                hits.append(str(path))
    assert not hits, hits
