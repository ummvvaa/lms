"""Вход и выдача доступа учитываются один раз после принятой операции."""

from unittest.mock import Mock

import pytest
from rest_framework.test import APIClient

from accounts import magic_link
from accounts.models import LinkPurpose

pytestmark = pytest.mark.django_db


@pytest.fixture
def tracked(monkeypatch):
    tracker = Mock()
    monkeypatch.setattr("core.usage.track", tracker)
    return tracker


@pytest.mark.parametrize("mode", ["password", "magic", "reset"])
def test_login_methods_emit_once_for_the_authenticated_user(make_user, tracked, mode):
    user = make_user("teacher")
    api = APIClient()
    if mode == "password":
        response = api.post("/api/auth/login/", {"email": user.email, "password": "pass12345"}, format="json")
    else:
        purpose = LinkPurpose.LOGIN if mode == "magic" else LinkPurpose.RESET
        token, _ = magic_link.issue_for(user, purpose=purpose, send=False)
        path = "/api/auth/magic-link/redeem/" if mode == "magic" else "/api/auth/password/set/"
        payload = {"token": token}
        if mode == "reset":
            payload["new_password"] = "ДругаяФраза!2026"
        response = api.post(path, payload, format="json")
    assert response.status_code == 200, response.data
    tracked.assert_called_once()
    request, key = tracked.call_args.args
    assert request.user.pk == user.pk and key == "auth.login"
    assert tracked.call_args.kwargs == {}


def test_failed_login_and_anonymous_link_request_do_not_claim_another_users_action(make_user, tracked, mailoutbox):
    user = make_user("teacher")
    api = APIClient()
    assert api.post("/api/auth/login/", {"email": user.email, "password": "wrong"}, format="json").status_code == 401
    assert api.post("/api/auth/magic-link/request/", {"email": user.email}, format="json").status_code == 200
    tracked.assert_not_called()


def test_access_link_emits_only_after_issue_and_preserves_permissions(make_user, tracked, mailoutbox):
    admin = make_user("admin")
    user = make_user("student")
    api = APIClient()
    api.force_authenticate(user)
    assert api.post(f"/api/users/{user.pk}/invite-link/").status_code == 403
    api.force_authenticate(admin)
    assert api.post("/api/users/999999/invite-link/").status_code == 404
    tracked.assert_not_called()
    response = api.post(f"/api/users/{user.pk}/invite-link/")
    assert response.status_code == 200 and response.data["link"]
    tracked.assert_called_once()
    request, key = tracked.call_args.args
    assert request.user.pk == admin.pk and key == "access.link.issue"


def test_student_password_link_has_its_own_action_and_does_not_claim_a_login(make_user, student, tracked, mailoutbox):
    student.user = make_user("student")
    student.save(update_fields=["user"])
    api = APIClient()
    admin = make_user("admin")
    api.force_authenticate(admin)
    response = api.post(f"/api/students/{student.pk}/password-link/")
    assert response.status_code == 200 and response.data["link"]
    tracked.assert_called_once()
    request, key = tracked.call_args.args
    assert request.user.pk == admin.pk and key == "access.student_link.issue"


@pytest.mark.parametrize("endpoint", ["bulk", "invite"])
def test_bulk_invites_emit_once_for_sent_and_queued_but_not_for_all_skipped(
    make_user, set_rules, mailoutbox, tracked, endpoint
):
    set_rules(mail_daily_limit=1)
    admin = make_user("admin")
    people = [make_user("student", f"usage-{number}@example.kz") for number in range(2)]
    api = APIClient()
    api.force_authenticate(admin)
    if endpoint == "bulk":
        path, payload = "/api/users/bulk/", {"action": "invite", "users": [row.pk for row in people]}
    else:
        path, payload = "/api/users/invite/", {"emails": [row.email for row in people]}
    response = api.post(path, payload, format="json")
    assert response.status_code == 200, response.data
    assert (response.data["sent"], response.data["queued"]) == (1, 1)
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == "access.invite.bulk"
    repeated = api.post(path, payload, format="json")
    assert repeated.status_code == 200 and repeated.data["sent"] + repeated.data["queued"] == 0
    assert tracked.call_count == 1


def test_credentials_csv_emits_only_the_download_key(make_user, tracked):
    api = APIClient()
    api.force_authenticate(make_user("admin"))
    response = api.post(
        "/api/users/credentials/",
        {"rows": [{"full_name": "Получатель", "login": "recipient", "email": "", "password": "secret-value"}]},
        format="json",
    )
    assert response.status_code == 200, response.content
    tracked.assert_called_once()
    assert tracked.call_args.args[1:] == ("export.download",)
    assert tracked.call_args.kwargs == {}
