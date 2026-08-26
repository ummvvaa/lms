"""Одноразовые записи прогона: заводятся только при DEBUG, исчезают насовсем, журнал остаётся."""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from accounts import probe
from accounts.models import LoginAttempt, Role, User
from accounts.passwords import set_password
from accounts.services import deactivate
from core.models import AuditLog

PASSWORD = "Прогон!Проверка2026"


@pytest.fixture
def probe_env(monkeypatch, settings):
    settings.DEBUG = True
    monkeypatch.setenv(probe.PASSWORD_VAR, PASSWORD)


def test_create_refuses_outside_debug(db, monkeypatch, settings):
    """В бою одноразовые записи не заводятся, флага «всё равно» нет."""
    settings.DEBUG = False
    monkeypatch.setenv(probe.PASSWORD_VAR, PASSWORD)
    with pytest.raises(CommandError) as error:
        call_command("create_probe_users", stdout=StringIO())
    assert "только при DEBUG=1" in str(error.value)
    assert not probe.probe_users().exists()


def test_create_needs_the_password_variable(db, settings, monkeypatch):
    settings.DEBUG = True
    monkeypatch.delenv(probe.PASSWORD_VAR, raising=False)
    with pytest.raises(CommandError) as error:
        call_command("create_probe_users", stdout=StringIO())
    assert probe.PASSWORD_VAR in str(error.value)


def test_create_makes_seven_accounts_marked_by_domain(db, probe_env):
    """Семь ролей, все входят одним паролем, система отличает их сама."""
    call_command("create_probe_users", stdout=StringIO())

    users = {user.email: user for user in probe.probe_users()}
    assert len(users) == 7
    assert {user.role for user in users.values()} == {value for value, _ in Role.choices}
    admin = users["admin@probe.local"]
    assert admin.is_staff and admin.is_superuser
    assert users["behavior@probe.local"].sees_whole_school
    for user in users.values():
        assert user.is_probe
        assert user.is_active
        assert not user.must_change_password
        assert user.check_password(PASSWORD)


def test_create_is_idempotent_and_purges_leftovers_first(db, probe_env):
    """Упавший прогон оставил записи и сессии — новый начинается с чистого."""
    call_command("create_probe_users", stdout=StringIO())
    api = APIClient()
    api.post("/api/auth/login/", {"email": "exam@probe.local", "password": PASSWORD}, format="json")
    assert Session.objects.count() == 1

    call_command("create_probe_users", stdout=StringIO())
    assert probe.probe_users().count() == 7
    assert Session.objects.count() == 0


def test_purge_removes_accounts_and_sessions_but_keeps_the_journal(db, probe_env, student):
    """После уборки записей нет, а строка журнала осталась и подписана."""
    call_command("create_probe_users", stdout=StringIO())
    exam = User.objects.get(email="exam@probe.local")
    api = APIClient()
    api.post("/api/auth/login/", {"email": exam.email, "password": PASSWORD}, format="json")
    entry = AuditLog.objects.create(
        actor=exam,
        model_label="students.ExamProfile",
        object_id="1",
        student_id=student.pk,
        field_name="ielts_current",
        old_value="",
        new_value="6.5",
    )
    # запись, заведённая самим прогоном под тем же доменом, уходит вместе с ним
    User.objects.create_user(email="invited.xyz@probe.local", password=None, role=Role.STUDENT)

    out = StringIO()
    call_command("purge_probe_users", stdout=out)

    assert not probe.probe_users().exists()
    assert not User.objects.filter(email="invited.xyz@probe.local").exists()
    assert Session.objects.count() == 0
    assert not LoginAttempt.objects.filter(email__endswith="@probe.local").exists()
    entry.refresh_from_db()
    assert entry.actor_id is None
    assert "Кымбат Прогон" in entry.actor_title
    assert "8" in out.getvalue()


def test_purge_works_outside_debug_and_touches_nothing_else(db, monkeypatch, settings):
    """Уборка возможна всегда; чужие записи, включая отключённые dev.local, не трогает."""
    settings.DEBUG = True
    monkeypatch.setenv(probe.PASSWORD_VAR, PASSWORD)
    call_command("create_probe_users", stdout=StringIO())
    dev = User.objects.create_user(email="admin@dev.local", password=None, role=Role.ADMIN)
    deactivate(dev)
    owner = User.objects.create_user(email="owner@school.kz", password=None, role=Role.ADMIN)

    settings.DEBUG = False
    call_command("purge_probe_users", stdout=StringIO())

    assert not probe.probe_users().exists()
    dev.refresh_from_db()
    assert not dev.is_active
    assert User.objects.filter(pk=owner.pk).exists()


def test_probe_login_is_refused_outside_debug(db, settings):
    """Забытая запись прогона в бою не входит — ни паролем, ни как-либо ещё."""
    user = User.objects.create_user(email="admin@probe.local", password=None, role=Role.ADMIN)
    set_password(user, PASSWORD)
    api = APIClient()

    settings.DEBUG = False
    denied = api.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    assert denied.status_code == 403
    assert "разработки" in denied.json()["detail"]

    settings.DEBUG = True
    allowed = api.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    assert allowed.status_code == 200


def test_user_list_marks_probe_accounts(db, probe_env):
    """Администратор видит, что перед ним запись прогона, а не человек."""
    call_command("create_probe_users", stdout=StringIO())
    api = APIClient()
    api.post("/api/auth/login/", {"email": "admin@probe.local", "password": PASSWORD}, format="json")
    rows = api.get("/api/users/").json()
    flags = {row["email"]: row["is_probe"] for row in rows}
    assert flags["admin@probe.local"] is True
    me = api.get("/api/auth/me/").json()
    assert me["is_probe"] is True


def test_dev_accounts_and_probe_accounts_do_not_overlap():
    """Одноразовые записи не пересекаются с разработческими ни по одной почте."""
    from accounts.management.commands.create_dev_users import ACCOUNTS as DEV

    dev_emails = {email for email, *_ in DEV}
    probe_emails = {email for email, *_ in probe.ACCOUNTS}
    assert not dev_emails & probe_emails
    assert all(probe.is_probe_email(email) for email in probe_emails)
    assert not any(probe.is_probe_email(email) for email in dev_emails)
