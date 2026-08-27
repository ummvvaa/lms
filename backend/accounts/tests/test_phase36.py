"""Фаза 36: три дефекта «до запуска» — D1, D2, D3 (серверная часть).

D1: после смены пароля сессия не теряется — ключ не вращается, параллельный
ответ не переписывает ни cookie, ни отпечаток пароля; продление сессии
не пишет данные. D2: порог по адресу из настроек, доверенные сети,
список блокировок и снятие администратором, отказ объясняет, когда и к кому.
D3 на сервере не требует правок: 401/403 остаются как есть.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import HASH_SESSION_KEY
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from accounts import passwords
from accounts.models import LoginAttempt, Role, User

PASSWORD = "Фаза36!Пароль2026"
NEW_PASSWORD = "Фаза36!Новый2026"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def director(db):
    user = User.objects.create_user(email="p36.exam@school.kz", password=None, role=Role.DIRECTOR_EXAM)
    passwords.set_password(user, PASSWORD)
    return user


@pytest.fixture
def admin(db):
    user = User.objects.create_user(email="p36.admin@school.kz", password=None, role=Role.ADMIN)
    passwords.set_password(user, PASSWORD)
    return user


def login(api, email, password, ip="203.0.113.7"):
    return api.post("/api/auth/login/", {"email": email, "password": password}, format="json", REMOTE_ADDR=ip)


def session_cookie(response):
    return response.cookies.get("lms_session")


# --- D1: смена пароля не роняет сессию -------------------------------------


@pytest.mark.django_db
def test_password_change_keeps_the_session_key(api, director):
    """Ключ сессии после смены пароля тот же: перетереть cookie мёртвым ключом нечем."""
    entered = login(api, director.email, PASSWORD)
    key_before = session_cookie(entered).value

    changed = api.post(
        "/api/auth/password/change/",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert changed.status_code == 200, changed.data
    cookie = session_cookie(changed)
    # cookie либо не переставлялась, либо переставлена с тем же ключом
    assert cookie is None or cookie.value == key_before
    assert api.session.session_key == key_before

    # сессия жива и работает дальше без повторного входа
    assert api.get("/api/auth/me/").status_code == 200
    # отпечаток нового пароля лёг в ту же сессию
    director.refresh_from_db()
    assert Session.objects.get(session_key=key_before).get_decoded()[HASH_SESSION_KEY] == (
        director.get_session_auth_hash()
    )


@pytest.mark.django_db
def test_other_sessions_of_the_same_person_still_drop_after_the_change(director):
    """Ротацию ключа убрали, а смысл её оставили: чужое устройство выходит."""
    phone, laptop = APIClient(), APIClient()
    login(phone, director.email, PASSWORD)
    login(laptop, director.email, PASSWORD)

    laptop.post(
        "/api/auth/password/change/",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )

    assert laptop.get("/api/auth/me/").status_code == 200
    assert phone.get("/api/auth/me/").status_code in (401, 403)


@pytest.mark.django_db
def test_a_read_only_request_does_not_rewrite_the_session(api, director):
    """Тот самый «параллельный запрос»: прочитал и ответил, но данные сессии не тронул.

    Раньше `SESSION_SAVE_EVERY_REQUEST` пересохранял сессию на каждый ответ —
    и ответ, ушедший со старым отпечатком, возвращал его поверх нового.
    """
    login(api, director.email, PASSWORD)
    key = api.session.session_key
    before = Session.objects.get(session_key=key)

    response = api.get("/api/auth/me/")
    assert response.status_code == 200

    after = Session.objects.get(session_key=key)
    assert after.session_data == before.session_data
    # cookie, если и переставлена продлением, несёт тот же ключ
    cookie = session_cookie(response)
    assert cookie is None or cookie.value == key


@pytest.mark.django_db
def test_session_is_prolonged_by_expiry_only_and_at_most_once_per_interval(api, director):
    """Продление — сдвиг срока в базе, без записи данных, раз в интервал."""
    from datetime import timedelta

    from django.utils import timezone

    cache.clear()
    login(api, director.email, PASSWORD)
    key = api.session.session_key
    # срок укорочен до часа — живая, но «старая» сессия
    Session.objects.filter(session_key=key).update(expire_date=timezone.now() + timedelta(hours=1))
    stale = Session.objects.get(session_key=key)

    # отметку продления сбрасываем: вход мог её занять
    cache.clear()
    first = api.get("/api/auth/me/")
    assert first.status_code == 200
    prolonged = Session.objects.get(session_key=key)
    assert prolonged.expire_date > stale.expire_date
    assert prolonged.session_data == stale.session_data
    assert session_cookie(first).value == key

    # второй запрос в том же интервале базу не трогает
    Session.objects.filter(session_key=key).update(expire_date=stale.expire_date)
    second = api.get("/api/auth/me/")
    assert second.status_code == 200
    assert Session.objects.get(session_key=key).expire_date == stale.expire_date
    assert session_cookie(second) is None


# --- D2: блокировка по адресу --------------------------------------------


@pytest.mark.django_db
@override_settings(LOGIN_IP_FAILURES=3)
def test_address_threshold_comes_from_settings(api, director):
    """Разные учётные записи с одного адреса: порог считается по адресу и берётся из настроек."""
    for index in range(3):
        assert login(api, f"nobody{index}@school.kz", "мимо").status_code == 401
    refused = login(api, director.email, PASSWORD)
    assert refused.status_code == 429
    assert refused.data["scope"] == "address"
    assert refused.data["unlock_in"] > 0


@pytest.mark.django_db
@override_settings(LOGIN_IP_FAILURES=3, LOGIN_TRUSTED_NETWORKS=["203.0.113.0/24"])
def test_trusted_network_is_never_locked_by_address_but_accounts_still_are(api, director):
    """Школьный адрес: по адресу не запирается, по записи — как все."""
    for index in range(10):
        assert login(api, f"nobody{index}@school.kz", "мимо").status_code == 401
    # верный пароль проходит: адрес доверенный
    assert login(api, director.email, PASSWORD).status_code == 200

    other = APIClient()
    for _ in range(5):
        login(other, director.email, "мимо")
    sixth = login(other, director.email, PASSWORD)
    assert sixth.status_code == 429
    assert sixth.data["scope"] == "account"


@pytest.mark.django_db
def test_refusal_says_when_and_to_whom(api, director):
    for _ in range(5):
        login(api, director.email, "мимо")
    refused = login(api, director.email, PASSWORD)
    assert refused.status_code == 429
    text = refused.data["detail"]
    assert "Вход откроется через" in text
    assert "администратору школы" in text
    assert "попыток" in text


@pytest.mark.django_db
def test_admin_sees_locks_and_lifts_them(api, director, admin):
    """Список блокировок, снятие кнопкой, журнал остаётся."""
    for _ in range(5):
        login(api, director.email, "мимо")
    assert login(api, director.email, PASSWORD).status_code == 429

    staff = APIClient()
    staff.force_authenticate(admin)
    listed = staff.get("/api/auth/locks/")
    assert listed.status_code == 200
    assert listed.data["account_threshold"] == 5
    assert listed.data["address_threshold"] == 100
    accounts = [lock for lock in listed.data["locks"] if lock["scope"] == "account"]
    # одна запись — одна строка, а не по строке на каждую неудачу
    assert [lock["value"] for lock in accounts] == [director.email]
    assert accounts[0]["failures"] >= 5
    assert accounts[0]["unlock_at"]

    lifted = staff.post("/api/auth/locks/unlock/", {"scope": "account", "value": director.email}, format="json")
    assert lifted.status_code == 200
    assert lifted.data["cleared"] >= 5
    # журнал на месте, попытки помечены снятыми
    assert LoginAttempt.objects.filter(email=director.email, successful=False).count() >= 5
    assert LoginAttempt.objects.filter(email=director.email, cleared_at__isnull=False).count() >= 5

    assert login(api, director.email, PASSWORD).status_code == 200
    assert [lock for lock in staff.get("/api/auth/locks/").data["locks"] if lock["value"] == director.email] == []


@pytest.mark.django_db
def test_only_admin_manages_locks(api, director):
    api.force_authenticate(director)
    assert api.get("/api/auth/locks/").status_code == 403
    assert (
        api.post("/api/auth/locks/unlock/", {"scope": "account", "value": "x@y.kz"}, format="json").status_code == 403
    )


@pytest.mark.django_db
def test_unlock_needs_a_scope_and_a_value(admin):
    staff = APIClient()
    staff.force_authenticate(admin)
    assert staff.post("/api/auth/locks/unlock/", {"scope": "nope", "value": "x"}, format="json").status_code == 400


def test_trusted_networks_parse_addresses_and_subnets_and_skip_garbage():
    with override_settings(LOGIN_TRUSTED_NETWORKS=["10.0.0.5", "192.168.1.0/24", "не адрес"]):
        assert passwords.is_trusted("10.0.0.5")
        assert passwords.is_trusted("192.168.1.77")
        assert not passwords.is_trusted("192.168.2.1")
        assert not passwords.is_trusted(None)
