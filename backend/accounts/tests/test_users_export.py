"""Выгрузка пользователей у администратора — по фильтру экрана, без паролей и ссылок.

Проверяется: колонки ровно те, что заказаны; фильтр выгрузки — тот же, что
у списка; предпросмотр и файл собраны из одних строк; ни пароля, ни хэша,
ни ссылки-приглашения в ответе нет; никому, кроме администратора, ручка
не открыта.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import load_workbook
from rest_framework.test import APIClient

from accounts import magic_link
from accounts.models import LinkPurpose
from students.models import Student, StudyGroup

pytestmark = pytest.mark.django_db

COLUMNS = ["ФИО", "Почта", "Логин", "Роль", "Группа", "Состояние пароля", "Активен"]


@pytest.fixture
def school(make_user):
    group = StudyGroup.objects.create(code="CHICAGO")
    pupil_user = make_user("student", "pupil-export@example.kz", full_name="Сериков Данияр")
    Student.objects.create(
        last_name="Сериков",
        first_name="Данияр",
        email=pupil_user.email,
        group=group,
        graduation_year=2027,
        user=pupil_user,
    )
    make_user("director_exam", "kymbat-export@example.kz", full_name="Кымбат")
    gone = make_user("curator", "gone-export@example.kz", full_name="Ушедший Куратор")
    gone.is_active = False
    gone.save(update_fields=["is_active"])
    return group


def as_admin(make_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(make_user("admin", "admin-export@example.kz", full_name="Администратор"))
    return client


def rows_of(response) -> list[list[str]]:
    page = load_workbook(BytesIO(response.content)).active
    return [["" if cell is None else str(cell) for cell in row] for row in page.values]


def test_the_export_follows_the_filter_and_matches_its_preview(school, make_user):
    client = as_admin(make_user)
    everyone = client.get("/api/users/export/?preview=1").json()["sheets"][0]
    assert everyone["columns"] == COLUMNS
    assert everyone["total"] == 4

    students = client.get("/api/users/export/?role=student&group=chicago&preview=1").json()["sheets"][0]
    assert students["rows"] == [
        ["Сериков Данияр", "pupil-export@example.kz", "", "Ученик", "CHICAGO", students["rows"][0][5], "да"]
    ]
    assert students["rows"][0][5]  # состояние пароля названо словами

    inactive = client.get("/api/users/export/?is_active=false&preview=1").json()["sheets"][0]
    assert [row[0] for row in inactive["rows"]] == ["Ушедший Куратор"]
    assert inactive["rows"][0][6] == "нет"

    # файл — те же строки, что предпросмотр
    in_file = rows_of(client.get("/api/users/export/?role=student&group=chicago"))
    assert in_file == [students["columns"], *students["rows"]]


def test_no_password_hash_or_link_gets_into_the_export(school, make_user):
    client = as_admin(make_user)
    token = magic_link.issue("pupil-export@example.kz", purpose=LinkPurpose.INVITE)
    body = client.get("/api/users/export/?preview=1").content.decode()
    in_file = " ".join(" ".join(row) for row in rows_of(client.get("/api/users/export/")))
    for text in (body, in_file):
        assert str(token) not in text
        assert "pbkdf2" not in text and "argon2" not in text
        assert "/invite" not in text and "token" not in text.lower()


@pytest.mark.parametrize("role", ["director_behavior", "director_admission", "curator", "student"])
def test_only_the_admin_exports_users(role, make_user):
    client = APIClient()
    client.force_login(make_user(role, f"{role}-noexport@example.kz"))
    assert client.get("/api/users/export/?preview=1").status_code == 403
