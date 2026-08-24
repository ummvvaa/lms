"""Фаза 27: отправка писем.

Без работающей отправки нельзя пригласить 250 учеников: администратору
пришлось бы придумывать и передавать пароль каждому лично. Проверяем не
доставку (её проверяет пробное письмо в бою), а то, что ломается тихо:
незаданные настройки, письмо не на языке получателя, отсутствие
предупреждения у администратора.
"""

from __future__ import annotations

import pytest
from django.core import mail as django_mail
from django.test import override_settings

from accounts.models import LinkPurpose, Role, User
from core import mail

SMTP = "django.core.mail.backends.smtp.EmailBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"
MEMORY = "django.core.mail.backends.locmem.EmailBackend"


# --- Состояние настройки ---------------------------------------------------


@override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
def test_without_settings_mail_is_not_considered_configured():
    assert mail.is_configured() is False
    assert "не настроена" in mail.warning()
    assert "приглашения" in mail.warning()


@override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST="")
def test_smtp_without_a_host_is_not_configured_either():
    """Бэкенд SMTP без сервера никуда не отправит, но выглядит настроенным."""
    assert mail.is_configured() is False


@override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST="smtp.sendgrid.net", EMAIL_PORT=587)
def test_configured_mail_reports_where_letters_go():
    assert mail.is_configured() is True
    assert mail.warning() == ""
    assert "smtp.sendgrid.net" in mail.status()["detail"]


@override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST="smtp.office365.com")
def test_microsoft_basic_auth_is_called_out():
    """Microsoft отключает эту аутентификацию — предупреждаем заранее.

    Настройка работает сегодня и перестанет работать в неизвестный день,
    без предупреждения с их стороны. Это худший вид поломки.
    """
    note = mail.warning()
    assert "Microsoft" in note
    assert "перестанут уходить" in note


# --- Предупреждение администратору ----------------------------------------


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
def test_admin_sees_the_warning_in_the_api(client, make_user):
    admin = make_user(Role.ADMIN, email="admin.mail@example.kz")
    client.force_login(admin)

    body = client.get("/api/mail/status/").json()
    assert body["configured"] is False
    assert "не настроена" in body["warning"]


@pytest.mark.django_db
def test_only_admin_asks_about_mail(client, make_user):
    director = make_user(Role.DIRECTOR_EXAM, email="kymbat.mail@example.kz")
    client.force_login(director)
    assert client.get("/api/mail/status/").status_code == 403


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=MEMORY, EMAIL_HOST="smtp.sendgrid.net")
def test_admin_can_send_a_test_letter_without_creating_anyone(client, make_user):
    """Проверка почты ничего не заводит: приглашение — заводит, а это нет."""
    admin = make_user(Role.ADMIN, email="admin.test-mail@example.kz")
    client.force_login(admin)
    before = User.objects.count()

    body = client.post("/api/mail/test/", {"email": "someone@school.kz"}, content_type="application/json").json()

    assert body["ok"] is True
    assert User.objects.count() == before
    assert len(django_mail.outbox) == 1
    assert django_mail.outbox[0].to == ["someone@school.kz"]


# --- Сами письма -----------------------------------------------------------


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=MEMORY, EMAIL_HOST="smtp.sendgrid.net", SCHOOL_NAME="Тестовая школа")
def test_invitation_carries_the_school_name_and_the_logo(db):
    """Шаблон один на все письма: логотип, название школы, ссылка."""
    from accounts import magic_link

    user = User.objects.create_user(email="new.person@school.kz", password=None, role=Role.STUDENT)
    magic_link.issue(user.email, purpose=LinkPurpose.INVITE)

    assert len(django_mail.outbox) == 1
    letter = django_mail.outbox[0]
    assert "Тестовая школа" in letter.subject
    html = letter.alternatives[0][0]
    assert "logo-email.png" in html
    assert "set-password?token=" in html


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=MEMORY, EMAIL_HOST="smtp.sendgrid.net")
def test_letter_goes_in_the_language_of_the_recipient(db):
    """Язык берётся из профиля получателя, а не из настроек сервера."""
    from accounts import magic_link

    user = User.objects.create_user(email="english.person@school.kz", password=None, role=Role.STUDENT)
    user.language = "en"
    user.save(update_fields=["language"])

    magic_link.issue(user.email, purpose=LinkPurpose.RESET)
    letter = django_mail.outbox[0]
    assert "password" in letter.body.lower()


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
def test_unconfigured_mail_does_not_break_the_invitation(db, caplog):
    """Письмо уходит в журнал, а не в исключение: приглашение не падает."""
    from accounts import magic_link
    from accounts.models import MagicLinkToken

    user = User.objects.create_user(email="quiet@school.kz", password=None, role=Role.STUDENT)
    token = magic_link.issue(user.email, purpose=LinkPurpose.INVITE)

    assert token
    assert MagicLinkToken.objects.filter(email=user.email).exists()


# --- Команда проверки ------------------------------------------------------


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=MEMORY, EMAIL_HOST="smtp.sendgrid.net")
def test_check_mail_command_sends_a_test_letter():
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("check_mail", to="admin@school.kz", stdout=out)

    assert "smtp.sendgrid.net" in out.getvalue()
    assert len(django_mail.outbox) == 1


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
def test_test_letter_does_not_claim_success_when_nothing_is_configured(client, make_user):
    """Консольный бэкенд «отправляет» что угодно — врать об этом нельзя."""
    admin = make_user(Role.ADMIN, email="admin.honest-mail@example.kz")
    client.force_login(admin)

    body = client.post("/api/mail/test/", {"email": "someone@school.kz"}, content_type="application/json").json()

    assert body["ok"] is False
    assert "только в журнал" in body["detail"]


@override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
def test_check_mail_command_says_plainly_that_nothing_will_go_out():
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("check_mail", stdout=out)
    assert "не настроена" in out.getvalue()
