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


# --- Пометки заглушек в именах (фаза 26) ----------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["Салтанат (тест)", "Тестовый Ученик", "Demo User", "Асем (разработка)"])
def test_user_with_a_placeholder_name_is_refused(as_admin, name):
    """«Салтанат (тест)» остаётся в журнале и в письмах навсегда.

    Отказ приходит по-человечески и на поле имени — администратор должен
    понять, что именно система не приняла.
    """
    response = as_admin.post(
        "/api/users/",
        {"email": "someone@school.kz", "full_name": name, "role": Role.DIRECTOR_TALENT},
        format="json",
    )

    assert response.status_code == 400
    assert "full_name" in response.data
    assert not User.objects.filter(email="someone@school.kz").exists()


@pytest.mark.django_db
def test_renaming_an_existing_user_into_a_placeholder_is_refused_too(as_admin):
    """Иначе запрет обходится вторым запросом сразу после создания."""
    created = as_admin.post(
        "/api/users/", {"email": "arman@school.kz", "full_name": "Арман", "role": Role.DIRECTOR_TALENT}, format="json"
    )
    assert created.status_code == 201

    response = as_admin.patch(f"/api/users/{created.data['id']}/", {"full_name": "Арман (тест)"}, format="json")

    assert response.status_code == 400
    assert User.objects.get(email="arman@school.kz").full_name == "Арман"


@pytest.mark.django_db
def test_normal_names_pass(as_admin):
    response = as_admin.post(
        "/api/users/",
        {"email": "saltanat@school.kz", "full_name": "Салтанат Ахметова", "role": Role.DIRECTOR_BEHAVIOR},
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_command_creating_users_refuses_placeholder_names():
    """Запрет живёт в одном месте и действует и в команде создания."""
    from accounts.naming import NameRejected, check_full_name

    with pytest.raises(NameRejected):
        check_full_name("Ученик (тест)")
    assert check_full_name("  Нурлыбек Оспанов ") == "Нурлыбек Оспанов"


@pytest.mark.django_db
def test_dev_users_command_carries_no_placeholder_names():
    """Имена разработческих записей тоже без пометок: их видно в шапке."""
    from accounts.management.commands.create_dev_users import ACCOUNTS
    from accounts.naming import marker_in

    for _email, _role, _var, full_name in ACCOUNTS:
        assert marker_in(full_name) is None, full_name


@pytest.mark.django_db
def test_invite_command_creates_user_and_sends_the_link(db):
    """`invite_user` — тот же путь, что и экран: запись без пароля плюс ссылка."""
    from io import StringIO

    from django.core.management import call_command

    call_command("invite_user", email="kymbat@school.kz", name="Кымбат", role=Role.DIRECTOR_EXAM, stdout=StringIO())

    user = User.objects.get(email="kymbat@school.kz")
    assert user.role == Role.DIRECTOR_EXAM
    assert not user.has_usable_password()
    assert user.must_change_password
    assert MagicLinkToken.objects.filter(email="kymbat@school.kz", purpose=LinkPurpose.INVITE).exists()


# --- Разработческие записи и архив ------------------------------------------

DEV_PASSWORDS = {
    "DEV_STUDENT_PASSWORD": "Ученик!Разработка2026",
    "DEV_BEHAVIOR_PASSWORD": "Поведение!Разработка2026",
    "DEV_ADMISSION_PASSWORD": "Поступление!Разработка2026",
    "DEV_EXAM_PASSWORD": "Экзамены!Разработка2026",
    "DEV_TALENT_PASSWORD": "Таланты!Разработка2026",
    "DEV_SPORT_PASSWORD": "Спорт!Разработка2026",
    "DEV_ADMIN_PASSWORD": "Администратор!Разработка2026",
}


@pytest.fixture
def dev_env(monkeypatch, settings):
    settings.DEBUG = True
    for name, value in DEV_PASSWORDS.items():
        monkeypatch.setenv(name, value)


@pytest.mark.django_db
def test_dev_users_command_leaves_deactivated_accounts_alone(dev_env):
    """Отключённую разработческую запись команда обратно не включает.

    Администратор убрал их в архив — повторный запуск по привычке или из
    документации не должен молча открыть им дверь. Остальные записи
    при этом заводятся как обычно.
    """
    from io import StringIO

    from django.core.management import call_command

    from accounts.services import deactivate

    disabled = User.objects.create_user(
        email="admin@dev.local", password=None, role=Role.ADMIN, full_name="Администратор"
    )
    deactivate(disabled)

    out = StringIO()
    call_command("create_dev_users", stdout=out)

    disabled.refresh_from_db()
    assert not disabled.is_active
    assert not disabled.check_password(DEV_PASSWORDS["DEV_ADMIN_PASSWORD"])
    assert "--reactivate" in out.getvalue()
    # остальные шесть записей заведены и активны
    assert User.objects.filter(email__endswith="@dev.local", is_active=True).count() == 6


@pytest.mark.django_db
def test_dev_users_command_reactivates_only_with_explicit_flag(dev_env):
    """Ключ `--reactivate` возвращает отключённые записи — и только он."""
    from io import StringIO

    from django.core.management import call_command

    from accounts.services import deactivate

    disabled = User.objects.create_user(email="student@dev.local", password=None, role=Role.STUDENT, full_name="Ученик")
    deactivate(disabled)

    call_command("create_dev_users", reactivate=True, stdout=StringIO())

    disabled.refresh_from_db()
    assert disabled.is_active
    assert disabled.check_password(DEV_PASSWORDS["DEV_STUDENT_PASSWORD"])
    assert User.objects.filter(email__endswith="@dev.local", is_active=True).count() == 7
