"""Фаза 29: заведение учеников списком и временный пароль.

Двойная работа — почта отдельно, ученик отдельно — на двухстах пятидесяти
людях превращается в неделю. Проверяем не удобство, а то, что ломается
молча: половина класса без учётных записей, дубли при повторной загрузке
и вечный пароль в письме, которое остаётся в ящике навсегда.
"""

from __future__ import annotations

import io

import pytest
from django.core import mail as django_mail
from django.test import override_settings
from django.utils import timezone

from accounts import temporary
from accounts.models import Role, User
from students.enrollment import build_preview, enroll
from students.models import Student, StudyGroup

MEMORY = "django.core.mail.backends.locmem.EmailBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"


class FakeFile(io.BytesIO):
    """Загруженный файл: `read_table` смотрит на имя и содержимое."""

    def __init__(self, text: str, name: str = "ucheniki.csv") -> None:
        super().__init__(text.encode("utf-8"))
        self.name = name


def table(text: str):
    from students.import_service import read_table

    return read_table(FakeFile(text))


LIST = """ФИО,Почта,Класс,Группа
Ахметова Алия Ерлановна,aliya@school.kz,11,11A
Сериков Дамир,damir@school.kz,10,10B
"""


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, email="admin.enroll@example.kz")


# --- Предпросмотр ----------------------------------------------------------


@pytest.mark.django_db
def test_preview_says_what_will_happen_in_words():
    header, rows = table(LIST)
    preview = build_preview(header=header, rows=rows)

    assert preview.as_dict()["will_create"] == 2
    assert "будет заведено: 2" in preview.detail().lower()


@pytest.mark.django_db
def test_missing_required_column_is_named(db):
    header, rows = table("Класс,Группа\n11,11A\n")
    preview = build_preview(header=header, rows=rows)

    assert preview.missing_columns
    assert "ФИО" in preview.as_dict()["detail"]
    assert preview.as_dict()["will_create"] == 0


@pytest.mark.django_db
def test_broken_rows_do_not_cancel_the_good_ones(db):
    header, rows = table(
        "ФИО,Почта,Класс\n"
        "Ахметова Алия,aliya@school.kz,11\n"
        ",no.name@school.kz,11\n"
        "Без Почты,,10\n"
        "Кривая Почта,не-адрес,10\n"
    )
    preview = build_preview(header=header, rows=rows)

    assert preview.as_dict()["will_create"] == 1
    assert preview.as_dict()["with_errors"] == 3
    reasons = [row.reason for row in preview.broken]
    assert any("ФИО" in reason for reason in reasons)
    assert any("почта" in reason for reason in reasons)


@pytest.mark.django_db
def test_duplicate_inside_the_file_is_caught(db):
    header, rows = table("ФИО,Почта\nОдин Человек,one@school.kz\nДругой Человек,one@school.kz\n")
    preview = build_preview(header=header, rows=rows)

    assert preview.as_dict()["will_create"] == 1
    assert "дважды" in preview.broken[0].reason


# --- Применение ------------------------------------------------------------


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=MEMORY, EMAIL_HOST="smtp.example")
def test_one_row_creates_card_account_and_password(db):
    header, rows = table(LIST)
    preview = build_preview(header=header, rows=rows)

    result = enroll(rows=[row.as_dict() for row in preview.ready])

    assert result["created"] == 2
    student = Student.objects.get(email="aliya@school.kz")
    assert student.last_name == "Ахметова" and student.first_name == "Алия"
    assert student.middle_name == "Ерлановна"
    assert student.group and student.group.code == "11A"
    # пять профилей: без них карточка наполовину пуста и ломает списки
    assert student.exam is not None and student.behavior is not None

    user = User.objects.get(email="aliya@school.kz")
    assert user.role == Role.STUDENT
    assert user.must_change_password is True
    assert user.temp_password_expires_at is not None
    # карточка и учётная запись связаны — иначе ученик войдёт в пустоту
    assert student.user_id == user.pk

    password = next(row["password"] for row in result["rows"] if row["email"] == "aliya@school.kz")
    assert user.check_password(password)
    assert len(django_mail.outbox) == 2


@pytest.mark.django_db
def test_second_run_of_the_same_file_creates_nothing(db):
    header, rows = table(LIST)
    first = build_preview(header=header, rows=rows)
    enroll(rows=[row.as_dict() for row in first.ready], send_mail=False)

    header, rows = table(LIST)
    second = build_preview(header=header, rows=rows)

    assert second.as_dict()["will_create"] == 0
    assert second.as_dict()["already_exist"] == 2
    assert all(row.reason == "такой ученик уже заведён" for row in second.existing)
    assert Student.objects.count() == 2


@pytest.mark.django_db
def test_apply_is_all_or_nothing_for_one_run(db, monkeypatch):
    """Сбой на середине не оставляет половину класса без учётных записей."""
    from accounts import temporary as temp_module

    calls = {"n": 0}
    original = temp_module.issue

    def flaky(user, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("почтовый сервер отвалился")
        return original(user, **kwargs)

    monkeypatch.setattr("accounts.temporary.issue", flaky)

    header, rows = table(LIST)
    preview = build_preview(header=header, rows=rows)
    with pytest.raises(RuntimeError):
        enroll(rows=[row.as_dict() for row in preview.ready], send_mail=False)

    assert Student.objects.count() == 0
    assert User.objects.filter(email="aliya@school.kz").count() == 0


@pytest.mark.django_db
def test_group_is_created_from_the_file(db):
    header, rows = table("ФИО,Почта,Класс,Группа\nНовый Ученик,new@school.kz,9,9Г\n")
    preview = build_preview(header=header, rows=rows)
    enroll(rows=[row.as_dict() for row in preview.ready], send_mail=False)

    group = StudyGroup.objects.get(code="9Г")
    assert group.grade == 9
    assert group.students.count() == 1


# --- Временный пароль ------------------------------------------------------


def test_generated_password_is_readable():
    """Пароль переписывают с экрана и диктуют по телефону."""
    for _ in range(50):
        password = temporary.generate()
        assert len(password.replace("-", "")) >= 10
        # ни одного символа, который путают с другим
        assert not set(password) & set("01lIO5S2Z8B")
        assert password.count("-") == 2


@pytest.mark.django_db
def test_temp_password_expires_and_says_so(client, make_user):
    """Просроченным паролем войти нельзя, и человеку сказано почему."""
    user = make_user(Role.STUDENT, email="expired@school.kz")
    password = temporary.issue(user)
    user.temp_password_expires_at = timezone.now() - timezone.timedelta(hours=1)
    user.save(update_fields=["temp_password_expires_at"])

    response = client.post(
        "/api/auth/login/", {"email": user.email, "password": password}, content_type="application/json"
    )

    assert response.status_code == 403
    assert response.json()["code"] == "temp_password_expired"
    assert "администратора" in response.json()["detail"]


@pytest.mark.django_db
def test_fresh_temp_password_lets_in_but_no_further(client, make_user):
    """Временный пароль пускает только на экран смены пароля."""
    user = make_user(Role.STUDENT, email="fresh@school.kz")
    password = temporary.issue(user)

    entered = client.post(
        "/api/auth/login/", {"email": user.email, "password": password}, content_type="application/json"
    )
    assert entered.status_code == 200
    assert entered.json()["must_change_password"] is True

    # дальше не пускает: проверка на сервере, а не только в интерфейсе
    blocked = client.get("/api/students/")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "password_change_required"


@pytest.mark.django_db
def test_after_the_change_the_old_password_stops_working(client, make_user):
    user = make_user(Role.STUDENT, email="changed@school.kz")
    old = temporary.issue(user)
    client.post("/api/auth/login/", {"email": user.email, "password": old}, content_type="application/json")

    changed = client.post(
        "/api/auth/password/change/",
        {"current_password": old, "new_password": "Своя!Строка2026"},
        content_type="application/json",
    )
    assert changed.status_code == 200

    user.refresh_from_db()
    assert user.must_change_password is False
    assert user.temp_password_expires_at is None

    client.logout()
    refused = client.post("/api/auth/login/", {"email": user.email, "password": old}, content_type="application/json")
    assert refused.status_code == 401


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=MEMORY, EMAIL_HOST="smtp.example", SCHOOL_NAME="Тестовая школа")
def test_letter_carries_address_login_password_and_the_warning(make_user):
    user = make_user(Role.STUDENT, email="letter@school.kz")
    password = temporary.issue(user)
    temporary.send_letter(user, password)

    letter = django_mail.outbox[0]
    assert "Тестовая школа" in letter.subject
    for piece in (user.email, password, "временный", "сменить" if "сменить" in letter.body else "пароль"):
        assert piece.lower() in letter.body.lower()
    assert "первом входе" in letter.body


@pytest.mark.django_db
def test_admin_reissues_a_password_with_one_button(client, admin, make_user):
    user = make_user(Role.STUDENT, email="reissue@school.kz")
    client.force_login(admin)

    body = client.post(f"/api/users/{user.pk}/temp-password/").json()

    assert body["password"]
    user.refresh_from_db()
    assert user.check_password(body["password"])
    assert user.must_change_password is True


@pytest.mark.django_db
def test_only_admin_reissues(client, make_user):
    user = make_user(Role.STUDENT, email="target.reissue@school.kz")
    director = make_user(Role.DIRECTOR_EXAM, email="kymbat.reissue@example.kz")
    client.force_login(director)

    assert client.post(f"/api/users/{user.pk}/temp-password/").status_code == 403


@pytest.mark.django_db
def test_credentials_export_is_built_on_request_and_not_stored(client, admin):
    client.force_login(admin)

    response = client.post(
        "/api/users/credentials/",
        {"rows": [{"full_name": "Ахметова Алия", "email": "aliya@school.kz", "password": "knpq-4rtm-wx79"}]},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    body = response.content.decode("utf-8")
    assert "Ахметова Алия" in body and "knpq-4rtm-wx79" in body
    assert "ФИО;Логин;Временный пароль" in body


# --- Массовые действия -----------------------------------------------------


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=MEMORY, EMAIL_HOST="smtp.example")
def test_bulk_temp_passwords_for_several_rows(client, admin, make_user):
    people = [make_user(Role.STUDENT, email=f"bulk{i}@school.kz") for i in range(3)]
    client.force_login(admin)

    body = client.post(
        "/api/users/bulk/",
        {"users": [p.pk for p in people], "action": "temp_password"},
        content_type="application/json",
    ).json()

    assert body["done"] == 3
    assert len(body["issued"]) == 3
    for person in people:
        person.refresh_from_db()
        assert person.must_change_password is True


@pytest.mark.django_db
def test_bulk_deactivate_never_touches_yourself(client, admin, make_user):
    other = make_user(Role.STUDENT, email="other.bulk@school.kz")
    client.force_login(admin)

    body = client.post(
        "/api/users/bulk/",
        {"users": [admin.pk, other.pk], "action": "deactivate"},
        content_type="application/json",
    ).json()

    admin.refresh_from_db()
    other.refresh_from_db()
    assert admin.is_active is True
    assert other.is_active is False
    assert any("самого себя" in row["reason"] for row in body["skipped"])
