"""Вход по почте и паролю, блокировка перебора, ссылки и смена пароля."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import magic_link, passwords
from accounts.models import Identity, IdentityProvider, LinkPurpose, LoginAttempt, Role, User
from accounts.services import create_user

GOOD_PASSWORD = "Кымбат!Осень2026"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def director(db):
    user = User.objects.create_user(email="kymbat@school.kz", password=None, role=Role.DIRECTOR_EXAM)
    passwords.set_password(user, GOOD_PASSWORD)
    return user


def login(api, email, password):
    return api.post("/api/auth/login/", {"email": email, "password": password}, format="json")


# --- вход ----------------------------------------------------------------


@pytest.mark.django_db
def test_login_issues_own_session(api, director):
    response = login(api, director.email, GOOD_PASSWORD)

    assert response.status_code == 200
    assert response.data["role"] == Role.DIRECTOR_EXAM
    assert response.data["domain"] == "exam"
    assert api.get("/api/auth/me/").data["email"] == director.email


@pytest.mark.django_db
def test_wrong_password_and_unknown_email_answer_the_same(api, director):
    """Форма входа не должна работать как проверка «есть ли такой человек»."""
    wrong = login(api, director.email, "совсем-не-тот-пароль")
    unknown = login(api, "nobody@school.kz", "совсем-не-тот-пароль")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.data["detail"] == unknown.data["detail"]


@pytest.mark.django_db
def test_deactivated_user_cannot_log_in_but_keeps_audit(api, director):
    from core.models import AuditLog

    AuditLog.objects.create(
        actor=director,
        model_label="students.ExamProfile",
        object_id="1",
        field_name="ielts_current",
        old_value="6.0",
        new_value="6.5",
        source="manual",
    )
    director.is_active = False
    director.save(update_fields=["is_active"])

    assert login(api, director.email, GOOD_PASSWORD).status_code in (401, 403)
    # запись в журнале осталась: поэтому отключаем, а не удаляем
    assert AuditLog.objects.filter(actor=director).count() == 1


@pytest.mark.django_db
def test_logout_kills_session(api, director):
    login(api, director.email, GOOD_PASSWORD)
    assert api.post("/api/auth/logout/").status_code == 200
    assert api.get("/api/auth/me/").status_code in (401, 403)


# --- блокировка перебора --------------------------------------------------


@pytest.mark.django_db
def test_six_wrong_passwords_lock_the_account(api, director):
    for _ in range(5):
        assert login(api, director.email, "мимо").status_code == 401

    sixth = login(api, director.email, "мимо")
    assert sixth.status_code == 429
    assert "попыток" in sixth.data["detail"]

    # даже верный пароль теперь не проходит: блокировка не про пароль
    assert login(api, director.email, GOOD_PASSWORD).status_code == 429


@pytest.mark.django_db
def test_lock_delay_grows(api, director):
    for _ in range(5):
        login(api, director.email, "мимо")

    first = passwords.check_lock(email=director.email, ip=None)
    assert first is not None
    # ещё одна неудача — задержка удваивается
    passwords.record_attempt(email=director.email, ip=None, successful=False, reason="bad_credentials")
    second = passwords.check_lock(email=director.email, ip=None)
    assert second is not None and second.seconds > first.seconds


@pytest.mark.django_db
def test_successful_login_breaks_the_series(api, director):
    """Забытый пароль не должен копиться до блокировки через неделю."""
    for _ in range(4):
        login(api, director.email, "мимо")
    assert login(api, director.email, GOOD_PASSWORD).status_code == 200

    for _ in range(4):
        login(api, director.email, "мимо")
    assert passwords.check_lock(email=director.email, ip=None) is None


@pytest.mark.django_db
def test_attempts_are_written_to_the_journal(api, director):
    login(api, director.email, "мимо")
    login(api, director.email, GOOD_PASSWORD)

    assert LoginAttempt.objects.filter(email=director.email, successful=False).count() == 1
    assert LoginAttempt.objects.filter(email=director.email, successful=True).count() == 1


@pytest.mark.django_db
def test_old_failures_do_not_lock(api, director):
    """Серия считается за окно: неудачи месячной давности блокировкой не грозят."""
    for _ in range(6):
        attempt = LoginAttempt.objects.create(email=director.email, successful=False, reason="bad_credentials")
        LoginAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(days=30))

    assert passwords.check_lock(email=director.email, ip=None) is None


# --- требования к паролю --------------------------------------------------


@pytest.mark.django_db
def test_short_password_is_rejected():
    with pytest.raises(passwords.PasswordRejected, match="короче"):
        passwords.validate_password("коротко1")


@pytest.mark.django_db
def test_common_password_is_rejected():
    with pytest.raises(passwords.PasswordRejected, match="распространён"):
        passwords.validate_password("password123")


@pytest.mark.django_db
def test_password_equal_to_email_is_rejected():
    with pytest.raises(passwords.PasswordRejected, match="почтой"):
        passwords.validate_password("kymbat@school.kz", email="kymbat@school.kz")
    with pytest.raises(passwords.PasswordRejected, match="почтой"):
        passwords.validate_password("kymbat.exam", email="kymbat.exam@school.kz")


@pytest.mark.django_db
def test_good_password_passes():
    passwords.validate_password(GOOD_PASSWORD, email="kymbat@school.kz")


# --- обязательная смена при первом входе ----------------------------------


@pytest.mark.django_db
def test_first_login_requires_password_change(api, db):
    user = create_user(email="new@school.kz", role=Role.DIRECTOR_SPORT)
    user.set_password("ВыданныйШколой!26")
    user.save(update_fields=["password"])

    response = login(api, user.email, "ВыданныйШколой!26")
    assert response.status_code == 200
    assert response.data["must_change_password"] is True

    # до смены пароля система закрыта — проверка на сервере, не в интерфейсе
    blocked = api.get("/api/students/")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "password_change_required"

    changed = api.post(
        "/api/auth/password/change/",
        {"current_password": "ВыданныйШколой!26", "new_password": GOOD_PASSWORD},
        format="json",
    )
    assert changed.status_code == 200
    assert changed.data["must_change_password"] is False
    assert api.get("/api/students/").status_code == 200


@pytest.mark.django_db
def test_password_change_rejects_weak_password(api, director):
    login(api, director.email, GOOD_PASSWORD)

    response = api.post(
        "/api/auth/password/change/",
        {"current_password": GOOD_PASSWORD, "new_password": "12345678901"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_password_change_needs_current_password(api, director):
    login(api, director.email, GOOD_PASSWORD)

    response = api.post(
        "/api/auth/password/change/",
        {"current_password": "не тот", "new_password": "СовсемДругой!2026"},
        format="json",
    )
    assert response.status_code == 400
    director.refresh_from_db()
    assert director.check_password(GOOD_PASSWORD)


# --- ссылки: приглашение и сброс ------------------------------------------


@pytest.mark.django_db
def test_reset_link_sets_new_password_and_logs_in(api, director):
    token = magic_link.issue(director.email, purpose=LinkPurpose.RESET)
    assert token

    response = api.post("/api/auth/password/set/", {"token": token, "new_password": "НовыйПароль!2026"}, format="json")
    assert response.status_code == 200
    assert api.get("/api/auth/me/").data["email"] == director.email

    director.refresh_from_db()
    assert director.check_password("НовыйПароль!2026")
    assert director.must_change_password is False


@pytest.mark.django_db
def test_link_is_single_use(api, director):
    token = magic_link.issue(director.email, purpose=LinkPurpose.RESET)
    api.post("/api/auth/password/set/", {"token": token, "new_password": "НовыйПароль!2026"}, format="json")

    again = APIClient().post(
        "/api/auth/password/set/", {"token": token, "new_password": "ЕщёОдин!2026Пароль"}, format="json"
    )
    assert again.status_code == 400


@pytest.mark.django_db
def test_reset_link_cannot_be_used_as_login_link(api, director):
    """Назначение ссылки сверяется: сбросом пароля просто войти нельзя."""
    token = magic_link.issue(director.email, purpose=LinkPurpose.RESET)

    assert api.post("/api/auth/magic-link/redeem/", {"token": token}, format="json").status_code == 400


@pytest.mark.django_db
@override_settings(PASSWORD_LINK_TTL_MINUTES=60)
def test_reset_link_lives_an_hour(director):
    from accounts.models import MagicLinkToken

    magic_link.issue(director.email, purpose=LinkPurpose.RESET)
    record = MagicLinkToken.objects.get(email=director.email)

    life = record.expires_at - record.created_at
    assert timedelta(minutes=59) <= life <= timedelta(minutes=61)


@pytest.mark.django_db
def test_reset_answers_the_same_for_unknown_email(api):
    known = api.post("/api/auth/password/reset/", {"email": "nobody@school.kz"}, format="json")
    assert known.status_code == 200
    assert "Если такая почта" in known.data["detail"]


# --- идентичности ---------------------------------------------------------


@pytest.mark.django_db
def test_created_user_gets_password_identity(db):
    user = create_user(email="asel@school.kz", role=Role.STUDENT)

    identity = Identity.objects.get(email="asel@school.kz")
    assert identity.provider == IdentityProvider.PASSWORD
    assert identity.user == user


@pytest.mark.django_db
def test_link_personal_email_as_second_identity(api, director):
    login(api, director.email, GOOD_PASSWORD)

    response = api.post("/api/auth/identities/link/", {"email": "personal.mail@gmail.com"}, format="json")

    assert response.status_code == 201
    assert director.identities.filter(provider=IdentityProvider.EMAIL_LINK).exists()
