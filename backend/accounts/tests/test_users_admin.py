"""Управление учётными записями: только `admin`, только отключение, только приглашения."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import LinkPurpose, MagicLinkToken, Role, User
from accounts.passwords import set_password

PASSWORD = "Администратор!2026"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def admin(db):
    user = User.objects.create_user(email="admin@school.kz", password=None, role=Role.ADMIN)
    set_password(user, PASSWORD)
    return user


@pytest.fixture
def as_admin(api, admin):
    api.post("/api/auth/login/", {"email": admin.email, "password": PASSWORD}, format="json")
    return api


@pytest.mark.django_db
def test_only_admin_manages_users(api, db):
    director = User.objects.create_user(email="exam@school.kz", password=None, role=Role.DIRECTOR_EXAM)
    set_password(director, "Кымбат!Осень2026")
    api.post("/api/auth/login/", {"email": director.email, "password": "Кымбат!Осень2026"}, format="json")

    assert api.get("/api/users/").status_code == 403
    assert api.post("/api/users/", {"email": "x@school.kz"}, format="json").status_code == 403


@pytest.mark.django_db
def test_admin_creates_user_and_invitation_goes_out(as_admin):
    response = as_admin.post(
        "/api/users/",
        {"email": "asel@school.kz", "full_name": "Асель", "role": Role.DIRECTOR_TALENT},
        format="json",
    )

    assert response.status_code == 201
    user = User.objects.get(email="asel@school.kz")
    assert user.role == Role.DIRECTOR_TALENT
    # пароля нет: человек задаст его себе сам, администратор его не знает
    assert not user.has_usable_password()
    assert MagicLinkToken.objects.filter(email="asel@school.kz", purpose=LinkPurpose.INVITE).exists()


@pytest.mark.django_db
def test_invited_person_sets_password_and_gets_own_screens(as_admin, db):
    from accounts import magic_link

    as_admin.post("/api/users/", {"email": "nurlybek@school.kz", "role": Role.DIRECTOR_SPORT}, format="json")
    token = magic_link.issue("nurlybek@school.kz", purpose=LinkPurpose.INVITE)

    fresh = APIClient()
    response = fresh.post(
        "/api/auth/password/set/", {"token": token, "new_password": "Нурлыбек!Спорт26"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["role"] == Role.DIRECTOR_SPORT
    assert response.data["domain"] == "sport"
    assert response.data["must_change_password"] is False
    # и сразу может работать: экраны своей роли открыты
    assert fresh.get("/api/dashboards/sport/").status_code == 200


@pytest.mark.django_db
def test_duplicate_email_is_refused(as_admin):
    as_admin.post("/api/users/", {"email": "dubl@school.kz"}, format="json")
    again = as_admin.post("/api/users/", {"email": "dubl@school.kz"}, format="json")

    assert again.status_code == 400


@pytest.mark.django_db
def test_deactivation_keeps_the_record(as_admin, db):
    from core.models import AuditLog

    as_admin.post("/api/users/", {"email": "byebye@school.kz"}, format="json")
    user = User.objects.get(email="byebye@school.kz")
    AuditLog.objects.create(
        actor=user,
        model_label="students.SportProfile",
        object_id="1",
        field_name="rank",
        old_value="",
        new_value="КМС",
        source="manual",
    )

    response = as_admin.patch(f"/api/users/{user.pk}/", {"is_active": False}, format="json")

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.is_active is False
    # запись никуда не делась — ради этого отключаем, а не удаляем
    assert AuditLog.objects.filter(actor=user).count() == 1
    assert User.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_admin_cannot_switch_itself_off(as_admin, admin):
    response = as_admin.patch(f"/api/users/{admin.pk}/", {"is_active": False}, format="json")

    assert response.status_code == 400
    admin.refresh_from_db()
    assert admin.is_active is True


@pytest.mark.django_db
def test_bulk_invite_creates_and_invites(as_admin):
    response = as_admin.post(
        "/api/users/invite/",
        {"emails": ["a@school.kz", "b@school.kz", "c@school.kz"], "role": Role.STUDENT},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["created"] == 3
    assert response.data["invited"] == 3
    assert MagicLinkToken.objects.filter(purpose=LinkPurpose.INVITE).count() == 3


@pytest.mark.django_db
def test_bulk_invite_skips_deactivated(as_admin, db):
    User.objects.create_user(email="off@school.kz", password=None, role=Role.STUDENT, is_active=False)

    response = as_admin.post("/api/users/invite/", {"emails": ["off@school.kz"]}, format="json")

    assert response.data["invited"] == 0
    assert response.data["skipped"][0]["email"] == "off@school.kz"


@pytest.mark.django_db
def test_search_finds_by_name_and_email(as_admin):
    as_admin.post("/api/users/", {"email": "saltanat@school.kz", "full_name": "Салтанат"}, format="json")

    by_name = as_admin.get("/api/users/?search=Салтанат")
    by_email = as_admin.get("/api/users/?search=saltanat")

    assert len(by_name.data) == 1
    assert len(by_email.data) == 1
