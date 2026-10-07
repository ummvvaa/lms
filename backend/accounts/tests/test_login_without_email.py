"""Вход без почты школы: логин, ссылка на пароль на экране, личная почта.

У 8–10 почты @bhs.kz нет. Учётная запись получает логин «имя.фамилия»,
форма входа принимает почту или логин, ссылку на пароль выдаёт куратор
или администратор на экране, а письмо уходит, только если почта есть.
Личная почта становится входом и адресом «Забыли пароль» только после
подтверждения письмом — привязка без подтверждения закрыта.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.core import mail as django_mail
from django.test import override_settings
from rest_framework.test import APIClient

from accounts import magic_link
from accounts.logins import base_login, find_user, latin, make_login
from accounts.models import CuratorAssignment, Identity, IdentityProvider, LinkPurpose, Role, User
from core.models import AuditLog
from students.models import Student, StudyGroup

MEMORY = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def junior(db):
    """Ученик 9 параллели без почты — логин вместо неё."""
    group = StudyGroup.objects.create(code="LISBON", parallel=9)
    user = User.objects.create_user(login="aigerim.serikova", full_name="Серикова Айгерим", role=Role.STUDENT)
    user.set_password("Своё!Слово2026")
    user.must_change_password = False
    user.save()
    student = Student.objects.create(
        last_name="Серикова", first_name="Айгерим", group=group, graduation_year=2029, user=user
    )
    return student


def test_passport_latin():
    assert latin("Әлихан") == "alikhan"
    assert latin("Қайратұлы") == "kairatuly"
    assert latin("Жұлдыз-Ая") == "zhuldyz-aia"
    assert latin("Ерлан Серікұлы") == "erlanserikuly"
    assert base_login("Юлия", "Щукина") == "iuliia.shchukina"
    assert base_login("", "") == "uchenik"


@pytest.mark.django_db
def test_namesakes_get_a_digit(junior):
    assert make_login("Айгерим", "Серикова") == "aigerim.serikova2"
    assert make_login("Айгерим", "Серикова", taken={"aigerim.serikova2"}) == "aigerim.serikova3"


@pytest.mark.django_db
def test_sign_in_by_login_or_email_same_answer_for_unknown(junior, make_user):
    api = APIClient()
    ok = api.post("/api/auth/login/", {"login": " Aigerim.Serikova ", "password": "Своё!Слово2026"}, format="json")
    assert ok.status_code == 200, ok.content
    assert ok.json()["email"] is None and ok.json()["login"] == "aigerim.serikova"

    staff = make_user(Role.CURATOR, "curator.login@example.kz")
    by_mail = APIClient().post(
        "/api/auth/login/", {"email": "Curator.Login@example.kz", "password": "pass12345"}, format="json"
    )
    assert by_mail.status_code == 200, by_mail.content
    assert by_mail.json()["id"] == staff.pk

    wrong = APIClient().post("/api/auth/login/", {"login": "aigerim.serikova", "password": "не то"}, format="json")
    unknown = APIClient().post("/api/auth/login/", {"login": "nobody.here", "password": "не то"}, format="json")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


@pytest.mark.django_db
def test_lockout_counts_one_series_per_account(junior):
    """Пять неудач по логину — и почта того же человека тоже заперта."""
    Identity.objects.create(
        user=junior.user,
        provider=IdentityProvider.EMAIL_LINK,
        email="aigerim@gmail.com",
        confirmed_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
    )
    api = APIClient()
    for _ in range(5):
        api.post("/api/auth/login/", {"login": "aigerim.serikova", "password": "не то"}, format="json")
    locked = api.post("/api/auth/login/", {"login": "aigerim@gmail.com", "password": "Своё!Слово2026"}, format="json")
    assert locked.status_code == 429


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=MEMORY, EMAIL_HOST="smtp.example")
def test_curator_issues_a_reset_link_on_screen_without_mail(junior, make_user):
    """Куратор своей группы выдаёт ссылку: на экране, в журнал, письма нет."""
    curator = make_user(Role.CURATOR, "curator.reset@example.kz")
    CuratorAssignment.objects.create(curator=curator, group=junior.group, since=dt.date(2026, 9, 1))
    stranger = make_user(Role.CURATOR, "stranger.reset@example.kz")

    other = APIClient()
    other.force_login(stranger)
    assert other.post(f"/api/students/{junior.pk}/password-link/").status_code == 404

    api = APIClient()
    api.force_login(curator)
    response = api.post(f"/api/students/{junior.pk}/password-link/")
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["sent_to"] == ""
    assert "Письмо не отправлено" in body["detail"]
    assert body["login"] == "aigerim.serikova"
    assert django_mail.outbox == []
    token = body["link"].split("token=")[1]
    assert AuditLog.objects.filter(student_id=junior.pk, field_name="password_link", actor=curator).exists()

    # по ссылке ученик задаёт пароль и входит — почта для этого не нужна
    done = APIClient().post(
        "/api/auth/password/set/", {"token": token, "new_password": "Новое!Слово2026"}, format="json"
    )
    assert done.status_code == 200, done.content
    again = APIClient().post(
        "/api/auth/login/", {"login": "aigerim.serikova", "password": "Новое!Слово2026"}, format="json"
    )
    assert again.status_code == 200


@pytest.mark.django_db
def test_student_and_teacher_cannot_issue_links(junior, make_user):
    api = APIClient()
    api.force_login(junior.user)
    assert api.post(f"/api/students/{junior.pk}/password-link/").status_code == 403


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=MEMORY, EMAIL_HOST="smtp.example")
def test_personal_email_works_only_after_confirmation(junior):
    """Личная почта: письмо-подтверждение, до него — ни входа, ни сброса."""
    api = APIClient()
    api.force_login(junior.user)
    linked = api.post("/api/auth/identities/link/", {"email": "Aigerim@Gmail.com"}, format="json")
    assert linked.status_code == 201, linked.content
    assert linked.json()["confirmed_at"] is None
    assert "письмо" in linked.json()["detail"]
    assert len(django_mail.outbox) == 1 and django_mail.outbox[0].to == ["aigerim@gmail.com"]
    token = django_mail.outbox[0].body.split("token=")[1].split()[0]

    # до подтверждения адрес не вход и не адрес сброса
    assert find_user("aigerim@gmail.com") is None
    assert magic_link.issue("aigerim@gmail.com", purpose=LinkPurpose.RESET) is None
    refused = APIClient().post(
        "/api/auth/login/", {"login": "aigerim@gmail.com", "password": "Своё!Слово2026"}, format="json"
    )
    assert refused.status_code == 401

    confirmed = APIClient().post("/api/auth/identities/confirm/", {"token": token}, format="json")
    assert confirmed.status_code == 200, confirmed.content
    assert APIClient().post("/api/auth/identities/confirm/", {"token": token}, format="json").status_code == 400

    # после — и вход, и «Забыли пароль»
    assert find_user("aigerim@gmail.com") == junior.user
    signed = APIClient().post(
        "/api/auth/login/", {"login": "aigerim@gmail.com", "password": "Своё!Слово2026"}, format="json"
    )
    assert signed.status_code == 200
    django_mail.outbox.clear()
    reset = APIClient().post("/api/auth/password/reset/", {"email": "aigerim@gmail.com"}, format="json")
    assert reset.status_code == 200
    assert django_mail.outbox[0].to == ["aigerim@gmail.com"]


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=MEMORY, EMAIL_HOST="smtp.example")
def test_unconfirmed_address_does_not_hold_someone_else(junior, make_user):
    """Кто первым набрал чужой адрес без подтверждения, адрес за собой не держит."""
    intruder = make_user(Role.STUDENT, "intruder@example.kz")
    api = APIClient()
    api.force_login(intruder)
    assert api.post("/api/auth/identities/link/", {"email": "aigerim@gmail.com"}, format="json").status_code == 201

    owner = APIClient()
    owner.force_login(junior.user)
    taken = owner.post("/api/auth/identities/link/", {"email": "aigerim@gmail.com"}, format="json")
    assert taken.status_code == 201
    identity = Identity.objects.get(email="aigerim@gmail.com")
    assert identity.user == junior.user
    # ссылка, ушедшая первому, уже не подтверждает адрес за ним
    first_token = django_mail.outbox[0].body.split("token=")[1].split()[0]
    assert magic_link.confirm(first_token) is None


@pytest.mark.django_db
def test_handout_file_has_login_where_there_is_no_email(junior, make_user):
    from accounts import handout

    admin = make_user(Role.ADMIN, "admin.handout.login@example.kz")
    outcome = handout.issue(User.objects.filter(pk=junior.user.pk), actor=admin, include_ready=True)
    assert outcome["rows"][0]["login"] == "aigerim.serikova"
    assert handout.EXPORT_COLUMNS[1] == "Почта или логин"
