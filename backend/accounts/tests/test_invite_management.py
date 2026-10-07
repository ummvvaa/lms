"""Рассылка с экрана: правдивые итоги, единая очередь и закрытый журнал."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import magic_link
from accounts.models import InviteMail, LinkPurpose, MagicLinkToken, Role, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, "mail-admin@example.kz", full_name="Администратор")


@pytest.fixture
def client(admin):
    client = APIClient()
    client.force_authenticate(admin)
    return client


def test_bulk_response_reports_sent_queue_and_no_address(client, admin, make_user, set_rules, mailoutbox):
    set_rules(mail_daily_limit=1)
    first = make_user(Role.STUDENT, "first-mail@example.kz")
    second = make_user(Role.STUDENT, "second-mail@example.kz")
    without_address = User.objects.create_user(login="no.mail", role=Role.STUDENT)
    response = client.post(
        "/api/users/bulk/",
        {"action": "invite", "users": [first.pk, second.pk, without_address.pk]},
        format="json",
    )
    assert response.status_code == 200
    result = response.json()
    assert (result["sent"], result["done"], result["queued"], result["failed"]) == (1, 1, 1, 0)
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["user"] == without_address.pk
    assert "почт" in result["skipped"][0]["reason"]
    assert "Отправлено 1" in result["detail"]
    assert len(mailoutbox) == 1
    queued = InviteMail.objects.get(status=InviteMail.Status.QUEUED)
    assert queued.actor_id == admin.pk
    assert not MagicLinkToken.objects.filter(user_id=queued.user_id).exists()
    queue = client.get("/api/users/mail-queue/")
    assert queue.json()["pending"] == 1
    assert queue.json()["next_send_at"]
    assert "no-store" in queue["Cache-Control"]


def test_both_mass_invite_endpoints_share_repeat_protection(client, make_user, mailoutbox):
    person = make_user(Role.STUDENT, "repeat-mail@example.kz")
    first = client.post("/api/users/invite/", {"emails": [person.email, person.email.upper()]}, format="json")
    assert first.json()["created"] == 0
    assert first.json()["invited"] == first.json()["sent"] == 1
    second = client.post("/api/users/bulk/", {"action": "invite", "users": [person.pk]}, format="json")
    assert second.json()["sent"] == 0
    assert "уходило" in second.json()["skipped"][0]["reason"]
    forced = client.post("/api/users/bulk/", {"action": "invite", "users": [person.pk], "force": True}, format="json")
    assert forced.json()["sent"] == 1
    assert len(mailoutbox) == 2


def test_cancel_queue_preserves_history_and_does_not_issue_link(client, make_user, set_rules):
    set_rules(mail_daily_limit=1)
    people = [make_user(Role.STUDENT, f"cancel-mail-{number}@example.kz") for number in range(2)]
    client.post("/api/users/bulk/", {"action": "invite", "users": [p.pk for p in people]}, format="json")
    queued = InviteMail.objects.get(status=InviteMail.Status.QUEUED)
    result = client.post("/api/users/mail-queue/cancel/", {}, format="json")
    assert result.status_code == 200
    assert result.json()["cancelled"] == 1
    assert client.post("/api/users/mail-queue/cancel/", {}, format="json").json()["cancelled"] == 0
    queued.refresh_from_db()
    assert queued.status == InviteMail.Status.CANCELLED
    assert not MagicLinkToken.objects.filter(user_id=queued.user_id).exists()
    assert client.get("/api/users/mail-queue/").json()["pending"] == 0
    history = client.get(f"/api/users/{queued.user_id}/mail-history/").json()["rows"]
    assert history[0]["status"] == InviteMail.Status.CANCELLED


def test_list_and_history_show_only_real_sending_date(client, admin, make_user, mailoutbox):
    person = make_user(Role.STUDENT, "history-mail@example.kz")
    person.set_unusable_password()
    person.save(update_fields=["password"])
    token, _ = magic_link.issue_for(person, purpose=LinkPurpose.INVITE, actor=admin)
    sent = InviteMail.objects.get(user=person, status=InviteMail.Status.SENT)
    response = client.get(f"/api/users/{person.pk}/mail-history/")
    history = response.json()["rows"]
    assert history[0]["actor"] == admin.pk
    assert history[0]["actor_name"] == admin.full_name
    assert history[0]["sent_at"]
    assert token not in response.content.decode()
    assert "token_hash" not in response.content.decode()
    assert "no-store" in response["Cache-Control"]
    assert len(mailoutbox) == 1

    # Более свежая ручная ссылка не превращается в новое письмо.
    with patch("accounts.magic_link.timezone.now", return_value=timezone.now() + timedelta(hours=1)):
        magic_link.issue_for(person, purpose=LinkPurpose.INVITE, send=False, actor=admin)
    row = client.get(f"/api/users/?search={person.email}").json()["results"][0]
    assert row["password_state"] == "invite_issued"
    assert datetime.fromisoformat(row["last_mail_sent_at"].replace("Z", "+00:00")) == sent.sent_at


def test_smtp_error_is_not_reported_as_sent(client, make_user):
    person = make_user(Role.STUDENT, "failed-mail@example.kz")
    with patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("SMTP unavailable")):
        response = client.post("/api/users/bulk/", {"action": "invite", "users": [person.pk]}, format="json")
    result = response.json()
    assert (result["sent"], result["failed"], result["done"]) == (0, 1, 0)
    assert "ошибок отправки 1" in result["detail"]
    history = client.get(f"/api/users/{person.pk}/mail-history/").json()["rows"]
    assert history[0]["status"] == "failed"
    assert "SMTP unavailable" in history[0]["error"]
    assert history[0]["sent_at"] is None


@pytest.mark.parametrize("role", [role for role in Role.values if role != Role.ADMIN])
def test_mail_administration_is_closed_to_every_other_role(role, make_user):
    client = APIClient()
    user = make_user(role, f"{role}-mail-rights@example.kz")
    client.force_authenticate(user)
    for path in ("/api/users/mail-queue/", f"/api/users/{user.pk}/mail-history/"):
        assert client.get(path).status_code in (403, 404)
    assert client.post("/api/users/mail-queue/cancel/", {}, format="json").status_code in (403, 404)


def test_missing_user_has_no_mail_history(client):
    assert client.get("/api/users/999999/mail-history/").status_code == 404
