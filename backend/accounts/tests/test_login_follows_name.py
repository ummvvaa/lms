"""Логин следует за ФИО (решение владельца, 16.10.2026).

У учётки без почты логин «имя.фамилия» пересчитывается при каждой смене
имени или фамилии тем же правилом, что при заведении, и сохраняется вместе
с ФИО; прежний логин больше не находится при входе, пароль не меняется.
Учётки со входом по почте и записи прогона не трогаются.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.logins import find_user, fits
from accounts.models import Role, User
from accounts.passwords import set_password
from core.models import AuditLog
from students.models import Student, StudyGroup

PASSWORD = "Админ!Осень2026"


@pytest.fixture
def admin(db):
    user = User.objects.create_user(email="admin@school.kz", password=None, role=Role.ADMIN, full_name="Админ Школы")
    set_password(user, PASSWORD)
    return user


@pytest.fixture
def as_admin(admin):
    api = APIClient()
    api.post("/api/auth/login/", {"email": admin.email, "password": PASSWORD}, format="json")
    return api


@pytest.fixture
def group(db):
    return StudyGroup.objects.create(code="9B", parallel=9)


def _student(api, group, last="Ахметова", first="Алия", **extra):
    made = api.post(
        "/api/users/",
        {"role": "student", "last_name": last, "first_name": first, "group": group.pk, **extra},
        format="json",
    )
    assert made.status_code == 201, made.data
    return User.objects.get(pk=made.data["id"]), made.data["password"]["password"]


def _sign_in(login: str, password: str) -> int:
    return APIClient().post("/api/auth/login/", {"login": login, "password": password}, format="json").status_code


@pytest.mark.django_db
def test_login_is_built_from_the_name_given_at_creation(as_admin, group):
    user, _ = _student(as_admin, group, first="Алина")
    assert user.login == "alina.akhmetova"
    teacher = as_admin.post("/api/users/", {"role": "teacher", "full_name": "Серикова Дана"}, format="json")
    assert teacher.status_code == 201 and teacher.data["password"]["login"] == "dana.serikova"


@pytest.mark.django_db
def test_renamed_student_signs_in_with_the_new_login_and_the_old_one_stops(as_admin, admin, group):
    user, password = _student(as_admin, group)
    assert user.login == "aliia.akhmetova" and _sign_in("aliia.akhmetova", password) == 200

    answer = as_admin.patch(f"/api/users/{user.pk}/", {"first_name": "Алина"}, format="json")

    assert answer.status_code == 200, answer.data
    assert answer.data["login_moved"] == {
        "was": "aliia.akhmetova",
        "now": "alina.akhmetova",
        "detail": "Логин сменился: теперь alina.akhmetova, прежний aliia.akhmetova не действует",
    }
    user.refresh_from_db()
    assert user.login == "alina.akhmetova" and user.full_name == "Ахметова Алина"
    assert find_user("aliia.akhmetova") is None
    # пароль не меняется: тот же временный подходит к новому логину
    assert _sign_in("alina.akhmetova", password) == 200
    assert _sign_in("aliia.akhmetova", password) == 401
    # след в журнале учётки: было → стало, кто
    row = AuditLog.objects.get(model_label="accounts.User", object_id=str(user.pk), field_name="login")
    assert (row.old_value, row.new_value, row.actor_id, row.source) == (
        "aliia.akhmetova",
        "alina.akhmetova",
        admin.pk,
        "manual",
    )


@pytest.mark.django_db
def test_rename_through_the_card_api_moves_the_login_too(as_admin, group):
    user, _ = _student(as_admin, group)
    answer = as_admin.patch(f"/api/students/{user.student.pk}/", {"last_name": "Сейткали"}, format="json")
    assert answer.status_code == 200, answer.data
    user.refresh_from_db()
    assert user.login == "aliia.seitkali"


@pytest.mark.django_db
def test_middle_name_phone_and_same_latin_keep_the_login(as_admin, group):
    user, _ = _student(as_admin, group)
    as_admin.patch(f"/api/users/{user.pk}/", {"middle_name": "Ерлановна", "phone": "87011234567"}, format="json")
    user.refresh_from_db()
    assert user.login == "aliia.akhmetova"
    # «Алия» → «Әлия» — та же паспортная латиница
    answer = as_admin.patch(f"/api/users/{user.pk}/", {"first_name": "Әлия"}, format="json")
    user.refresh_from_db()
    assert user.login == "aliia.akhmetova" and "login_moved" not in answer.data
    assert not AuditLog.objects.filter(model_label="accounts.User", field_name="login").exists()


@pytest.mark.django_db
def test_duplicate_rule_holds_and_a_number_does_not_grow_on_its_own(as_admin, group):
    alina, _ = _student(as_admin, group, first="Алина")
    aliia, _ = _student(as_admin, group)
    namesake, _ = _student(as_admin, StudyGroup.objects.create(code="10A", parallel=10))
    assert (alina.login, aliia.login, namesake.login) == ("alina.akhmetova", "aliia.akhmetova", "aliia.akhmetova2")

    # занятый логин — следующий с цифрой, как при заведении
    as_admin.patch(f"/api/users/{aliia.pk}/", {"first_name": "Алина"}, format="json")
    aliia.refresh_from_db()
    assert aliia.login == "alina.akhmetova2"
    # тёзка с цифрой правит отчество — цифра остаётся своей
    as_admin.patch(f"/api/users/{namesake.pk}/", {"middle_name": "Ерлановна"}, format="json")
    namesake.refresh_from_db()
    assert namesake.login == "aliia.akhmetova2"
    # освободившийся логин без цифры достаётся следующему переименованному
    as_admin.patch(f"/api/users/{alina.pk}/", {"first_name": "Дана"}, format="json")
    as_admin.patch(f"/api/users/{namesake.pk}/", {"first_name": "Арина"}, format="json")
    alina.refresh_from_db()
    namesake.refresh_from_db()
    assert (alina.login, namesake.login) == ("dana.akhmetova", "arina.akhmetova")


@pytest.mark.django_db
def test_staff_without_email_follows_the_name_unless_a_login_is_typed(as_admin):
    made = as_admin.post("/api/users/", {"role": "teacher", "full_name": "Серикова Дана"}, format="json")
    user = User.objects.get(pk=made.data["id"])
    # окно шлёт «Почту или логин» как есть: прежний логин — значит, не вписан руками
    answer = as_admin.patch(
        f"/api/users/{user.pk}/", {"full_name": "Серикова Дина", "handle": "dana.serikova"}, format="json"
    )
    assert answer.status_code == 200, answer.data
    user.refresh_from_db()
    assert user.login == "dina.serikova" and answer.data["login_moved"]["now"] == "dina.serikova"
    # логин, вписанный в том же сохранении, сильнее пересчёта
    typed = as_admin.patch(
        f"/api/users/{user.pk}/", {"full_name": "Серикова Дана", "handle": "d.serikova"}, format="json"
    )
    user.refresh_from_db()
    assert user.login == "d.serikova" and "login_moved" not in typed.data


@pytest.mark.django_db
def test_accounts_with_email_and_probe_accounts_keep_their_sign_in(as_admin, group):
    with_mail, _ = _student(as_admin, group, email="aliya@school.kz")
    as_admin.patch(f"/api/users/{with_mail.pk}/", {"first_name": "Алина"}, format="json")
    with_mail.refresh_from_db()
    assert with_mail.email == "aliya@school.kz" and with_mail.login is None

    staff = as_admin.post(
        "/api/users/", {"role": "teacher", "full_name": "Серикова Дана", "handle": "dana@school.kz"}, format="json"
    )
    member = User.objects.get(pk=staff.data["id"])
    as_admin.patch(f"/api/users/{member.pk}/", {"full_name": "Серикова Дина"}, format="json")
    member.refresh_from_db()
    assert member.email == "dana@school.kz" and member.login is None

    # запись прогона находит уборка по приставке логина — он не меняется
    probe, _ = _student(as_admin, group, first="Проба")
    User.objects.filter(pk=probe.pk).update(login="probe_student_1")
    as_admin.patch(f"/api/users/{probe.pk}/", {"first_name": "Алина"}, format="json")
    probe.refresh_from_db()
    assert probe.login == "probe_student_1"
    assert Student.objects.get(user=probe).first_name == "Алина"


def test_fits_reads_the_number_of_a_namesake():
    assert fits("aliia.akhmetova", "Алия", "Ахметова")
    assert fits("aliia.akhmetova2", "Әлия", "Ахметова")
    assert fits("aliia.akhmetova12", "Алия", "Ахметова")
    assert not fits("aliia.akhmetova1", "Алия", "Ахметова")
    assert not fits("alina.akhmetova", "Алия", "Ахметова")
    assert not fits("kanat.s", "Канат", "Сеитов")
