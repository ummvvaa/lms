"""Вход, сессия, роли из групп Entra и вторая дверь для выпускников."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from accounts import magic_link
from accounts.entra import EntraClaims
from accounts.models import Identity, IdentityProvider, Role, User
from accounts.services import role_from_groups, upsert_from_entra

GROUP_MAP = {
    "grp-admission": "director_admission",
    "grp-exam": "director_exam",
    "grp-students": "student",
}


@pytest.fixture
def api() -> APIClient:
    return APIClient()


# --- Маппинг групп на роли ---------------------------------------------


@override_settings(ENTRA_GROUP_ROLE_MAP=GROUP_MAP)
def test_role_from_groups():
    assert role_from_groups(["grp-exam"]) == "director_exam"
    assert role_from_groups(["grp-unknown"]) is None


@override_settings(ENTRA_GROUP_ROLE_MAP=GROUP_MAP)
def test_role_priority_is_stable_regardless_of_token_order():
    """Порядок групп в токене не должен влиять на итоговую роль."""
    a = role_from_groups(["grp-exam", "grp-admission"])
    b = role_from_groups(["grp-admission", "grp-exam"])
    assert a == b == "director_admission"


@pytest.mark.django_db
@override_settings(ENTRA_GROUP_ROLE_MAP=GROUP_MAP)
def test_upsert_creates_user_with_role():
    claims = EntraClaims(subject="oid-1", email="asem@school.kz", full_name="Асем", groups=("grp-admission",))
    user, identity = upsert_from_entra(claims)
    assert user.role == Role.DIRECTOR_ADMISSION
    assert user.full_name == "Асем"
    assert identity.provider == IdentityProvider.ENTRA
    assert identity.external_id == "oid-1"
    assert not user.has_usable_password()


@pytest.mark.django_db
@override_settings(ENTRA_GROUP_ROLE_MAP=GROUP_MAP)
def test_upsert_is_idempotent_and_remaps_role():
    """Роль пересчитывается при каждом входе — человека перевели в другую группу."""
    first, _ = upsert_from_entra(EntraClaims("oid-1", "k@school.kz", "Кымбат", ("grp-exam",)))
    second, _ = upsert_from_entra(EntraClaims("oid-1", "k@school.kz", "Кымбат", ("grp-admission",)))
    assert first.pk == second.pk
    assert User.objects.count() == 1
    assert Identity.objects.count() == 1
    assert second.role == Role.DIRECTOR_ADMISSION


@pytest.mark.django_db
@override_settings(ENTRA_GROUP_ROLE_MAP=GROUP_MAP, ENTRA_DEFAULT_ROLE="student")
def test_unmapped_group_falls_back_to_default_role():
    user, _ = upsert_from_entra(EntraClaims("oid-9", "kid@school.kz", "Ученик", ("grp-nope",)))
    assert user.role == Role.STUDENT


@pytest.mark.django_db
@override_settings(ENTRA_GROUP_ROLE_MAP=GROUP_MAP)
def test_entra_identity_attaches_to_existing_user():
    """Выпускник вошёл по личной почте, потом школьный аккаунт — тот же User."""
    user = User.objects.create_user(email="grad@school.kz", password=None, role=Role.STUDENT)
    Identity.objects.create(user=user, provider=IdentityProvider.EMAIL_LINK, email="personal@gmail.com")
    same, identity = upsert_from_entra(EntraClaims("oid-7", "grad@school.kz", "Выпускник", ()))
    assert same.pk == user.pk
    assert user.identities.count() == 2
    assert identity.provider == IdentityProvider.ENTRA


# --- Вход через API и жизнь сессии -------------------------------------


@pytest.mark.django_db
@override_settings(ENTRA_GROUP_ROLE_MAP=GROUP_MAP)
def test_entra_login_issues_own_session(api):
    claims = EntraClaims("oid-2", "kymbat@school.kz", "Кымбат", ("grp-exam",))
    with patch("accounts.views.verify_id_token", return_value=claims):
        response = api.post("/api/auth/entra/", {"id_token": "какой-угодно"}, format="json")
    assert response.status_code == 200
    assert response.data["role"] == "director_exam"
    assert response.data["domain"] == "exam"

    # сессия своя, в httpOnly cookie; токена Microsoft в ответе нет
    cookie = response.cookies["lms_session"]
    assert cookie["httponly"] is True
    assert "id_token" not in str(response.data)

    # сессия переживает «перезагрузку страницы» — новый запрос тем же клиентом
    again = api.get("/api/auth/me/")
    assert again.status_code == 200
    assert again.data["email"] == "kymbat@school.kz"


@pytest.mark.django_db
def test_entra_login_rejects_bad_token(api):
    from accounts.entra import EntraError

    with patch("accounts.views.verify_id_token", side_effect=EntraError("подпись не сошлась")):
        response = api.post("/api/auth/entra/", {"id_token": "мусор"}, format="json")
    assert response.status_code == 401
    assert "подпись" not in str(response.data)  # детали наружу не отдаём


@pytest.mark.django_db
@override_settings(ENTRA_GROUP_ROLE_MAP=GROUP_MAP)
def test_logout_kills_session(api):
    claims = EntraClaims("oid-3", "arman@school.kz", "Арман", ("grp-exam",))
    with patch("accounts.views.verify_id_token", return_value=claims):
        api.post("/api/auth/entra/", {"id_token": "x"}, format="json")
    assert api.get("/api/auth/me/").status_code == 200
    assert api.post("/api/auth/logout/").status_code == 200
    assert api.get("/api/auth/me/").status_code in (401, 403)


@pytest.mark.django_db
def test_me_requires_auth(api):
    assert api.get("/api/auth/me/").status_code in (401, 403)


# --- Вторая дверь: одноразовая ссылка ----------------------------------


@pytest.mark.django_db
def test_magic_link_round_trip(api):
    user = User.objects.create_user(email="alum@school.kz", password=None, role=Role.STUDENT)
    Identity.objects.create(user=user, provider=IdentityProvider.EMAIL_LINK, email="alum.personal@gmail.com")

    token = magic_link.issue("alum.personal@gmail.com")
    assert token

    response = api.post("/api/auth/magic-link/redeem/", {"token": token}, format="json")
    assert response.status_code == 200
    assert response.data["email"] == "alum@school.kz"
    assert api.get("/api/auth/me/").status_code == 200


@pytest.mark.django_db
def test_magic_link_is_single_use(api):
    user = User.objects.create_user(email="alum2@school.kz", password=None)
    Identity.objects.create(user=user, provider=IdentityProvider.EMAIL_LINK, email="alum2@gmail.com")
    token = magic_link.issue("alum2@gmail.com")

    assert api.post("/api/auth/magic-link/redeem/", {"token": token}, format="json").status_code == 200
    api.post("/api/auth/logout/")
    second = api.post("/api/auth/magic-link/redeem/", {"token": token}, format="json")
    assert second.status_code == 401


@pytest.mark.django_db
def test_magic_link_expires(api):
    user = User.objects.create_user(email="alum3@school.kz", password=None)
    Identity.objects.create(user=user, provider=IdentityProvider.EMAIL_LINK, email="alum3@gmail.com")
    with override_settings(MAGIC_LINK_TTL_MINUTES=0):
        token = magic_link.issue("alum3@gmail.com")
    time.sleep(0.01)
    assert api.post("/api/auth/magic-link/redeem/", {"token": token}, format="json").status_code == 401


@pytest.mark.django_db
def test_magic_link_unknown_email_reveals_nothing(api):
    assert magic_link.issue("chuzhoy@example.com") is None
    response = api.post("/api/auth/magic-link/request/", {"email": "chuzhoy@example.com"}, format="json")
    assert response.status_code == 200
    assert "token" not in response.data


@pytest.mark.django_db
def test_link_second_identity_from_cabinet(api):
    user = User.objects.create_user(email="grad4@school.kz", password=None)
    api.force_authenticate(user)
    response = api.post("/api/auth/identities/link/", {"email": "grad4.personal@gmail.com"}, format="json")
    assert response.status_code == 201
    assert user.identities.filter(provider=IdentityProvider.EMAIL_LINK).count() == 1


@pytest.mark.django_db
def test_cannot_steal_someone_elses_email(api):
    owner = User.objects.create_user(email="owner@school.kz", password=None)
    Identity.objects.create(user=owner, provider=IdentityProvider.EMAIL_LINK, email="shared@gmail.com")
    thief = User.objects.create_user(email="thief@school.kz", password=None)

    api.force_authenticate(thief)
    response = api.post("/api/auth/identities/link/", {"email": "shared@gmail.com"}, format="json")
    assert response.status_code == 400
