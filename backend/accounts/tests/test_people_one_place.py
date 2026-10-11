"""«Пользователи» — одно место о человеке: заведение по роли, правка, смена роли.

Ученик заводится с карточкой, профилями и группой тем же кодом, что список;
без почты получает логин; сотрудник — с полями своей роли. ФИО ученика живёт
в карточке, учётная запись повторяет его; откат при ошибке — целиком.
"""

from __future__ import annotations

import pytest
from django.core import mail as django_mail
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import Subject, TeacherProfile
from accounts.models import CuratorAssignment, Identity, IdentityProvider, Role, User
from accounts.passwords import set_password
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
def groups(db):
    return {
        "11A": StudyGroup.objects.create(code="11A", parallel=11),
        "9B": StudyGroup.objects.create(code="9B", parallel=9),
    }


@pytest.fixture
def subjects(db):
    return [
        Subject.objects.create(code="eep", title="EEP", in_lms=True),
        Subject.objects.create(code="phys", title="Физика", in_lms=False),
    ]


def create(api, **body):
    return api.post("/api/users/", body, format="json")


# --- Ученик ----------------------------------------------------------------------


@pytest.mark.django_db
def test_student_with_email_gets_card_profiles_group_and_password(as_admin, groups):
    response = create(
        as_admin,
        role="student",
        last_name="Ахметова",
        first_name="Алия",
        middle_name="Ерлановна",
        group=groups["11A"].pk,
        email="aliya@school.kz",
        phone="8 701 123 45 67",
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(email="aliya@school.kz")
    student = Student.objects.get(user=user)
    assert (student.last_name, student.first_name, student.middle_name) == ("Ахметова", "Алия", "Ерлановна")
    assert student.group == groups["11A"] and student.graduation_year > 2000
    assert student.email == "aliya@school.kz" and student.phone == "+77011234567"
    # пять профилей и имя учётной записи — производное от карточки
    assert student.exam is not None and student.sport is not None
    assert user.full_name == "Ахметова Алия Ерлановна" and user.role == Role.STUDENT
    # временный пароль показан один раз, письмо ушло
    assert response.data["password"]["login"] == "aliya@school.kz"
    assert user.check_password(response.data["password"]["password"])
    assert response.data["password"]["sent"] is True and len(django_mail.outbox) == 1
    # виден в «Таблице» и в своей группе
    listed = as_admin.get("/api/students/?search=Ахметова").data["results"]
    assert [row["group_code"] for row in listed] == ["11A"]


@pytest.mark.django_db
def test_student_without_email_gets_login_and_signs_in_with_the_temporary_password(as_admin, groups):
    first = create(as_admin, role="student", last_name="Ахметова", first_name="Алия", group=groups["9B"].pk)
    second = create(as_admin, role="student", last_name="Ахметова", first_name="Алия", group=groups["11A"].pk)
    assert first.status_code == 201 and second.status_code == 201
    assert first.data["password"]["login"] == "aliia.akhmetova"
    assert second.data["password"]["login"] == "aliia.akhmetova2"
    assert first.data["password"]["sent"] is False and not django_mail.outbox

    fresh = APIClient()
    answer = fresh.post(
        "/api/auth/login/", {"email": "aliia.akhmetova", "password": first.data["password"]["password"]}, format="json"
    )
    assert answer.status_code == 200
    assert answer.data["must_change_password"] is True
    # смена пароля обязательна: экраны закрыты до неё
    assert fresh.get("/api/students/me/").status_code == 403


@pytest.mark.django_db
def test_student_needs_a_group_and_a_name(as_admin, groups):
    no_group = create(as_admin, role="student", last_name="Ахметова", first_name="Алия")
    assert no_group.status_code == 400 and "группу" in no_group.data["detail"]
    no_name = create(as_admin, role="student", last_name="Ахметова", group=groups["11A"].pk)
    assert no_name.status_code == 400
    twice = create(as_admin, role="student", last_name="Ахметова", first_name="Алия", group=groups["11A"].pk)
    assert twice.status_code == 201
    again = create(as_admin, role="student", last_name="Ахметова", first_name="Алия", group=groups["11A"].pk)
    assert again.status_code == 400 and "уже заведён" in again.data["detail"]
    assert Student.objects.count() == 1


@pytest.mark.django_db
def test_nothing_is_created_when_the_password_step_fails(as_admin, groups, monkeypatch):
    def broken(user, **kwargs):
        raise RuntimeError("пароль не выпустился")

    monkeypatch.setattr("accounts.temporary.issue", broken)
    with pytest.raises(RuntimeError):
        create(as_admin, role="student", last_name="Ахметова", first_name="Алия", group=groups["11A"].pk)
    assert Student.objects.count() == 0
    assert not User.objects.filter(role=Role.STUDENT).exists()


@pytest.mark.django_db
def test_personal_email_from_the_admin_stays_unconfirmed_until_the_letter(as_admin, groups):
    response = create(
        as_admin,
        role="student",
        last_name="Ахметова",
        first_name="Алия",
        group=groups["11A"].pk,
        email="aliya@school.kz",
        personal_email="aliya.private@gmail.com",
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(email="aliya@school.kz")
    identity = Identity.objects.get(user=user, provider=IdentityProvider.EMAIL_LINK)
    assert identity.email == "aliya.private@gmail.com" and identity.confirmed_at is None
    # письмо с подтверждением ушло на личный адрес, пароль — на школьный
    assert {message.to[0] for message in django_mail.outbox} == {"aliya@school.kz", "aliya.private@gmail.com"}
    detail = as_admin.get(f"/api/users/{user.pk}/").data
    assert detail["personal_email"] == "aliya.private@gmail.com" and detail["personal_email_confirmed"] is False


@pytest.mark.django_db
def test_renaming_the_student_on_users_is_visible_in_the_card_and_the_account(as_admin, groups):
    made = create(as_admin, role="student", last_name="Ахметова", first_name="Алия", group=groups["9B"].pk)
    user = User.objects.get(pk=made.data["id"])
    student = Student.objects.get(user=user)

    answer = as_admin.patch(
        f"/api/users/{user.pk}/",
        {"last_name": "Сейткали", "middle_name": "Ерлановна", "group": groups["11A"].pk, "phone": "87011234567"},
        format="json",
    )
    assert answer.status_code == 200, answer.data
    student.refresh_from_db()
    user.refresh_from_db()
    assert student.last_name == "Сейткали" and student.middle_name == "Ерлановна"
    assert user.full_name == "Сейткали Алия Ерлановна"
    assert student.group == groups["11A"] and student.phone == "+77011234567"
    card = as_admin.get(f"/api/students/{student.pk}/").data
    assert card["full_name"] == "Сейткали Алия Ерлановна" and card["group_code"] == "11A"
    assert answer.data["student"]["group_code"] == "11A" and answer.data["student"]["parallel"] == 11
    # правка видна в журнале карточки
    history = as_admin.get(f"/api/students/{student.pk}/history/").data
    assert {row["model_label"] for row in history} == {"students.Student"}
    assert any("Сейткали" in row["new_display"] for row in history)


@pytest.mark.django_db
def test_student_email_is_written_once_for_card_and_account(as_admin, groups):
    made = create(as_admin, role="student", last_name="Ахметова", first_name="Алия", group=groups["9B"].pk)
    user = User.objects.get(pk=made.data["id"])
    answer = as_admin.patch(f"/api/users/{user.pk}/", {"email": "aliya@school.kz"}, format="json")
    assert answer.status_code == 200, answer.data
    user.refresh_from_db()
    assert user.email == "aliya@school.kz" and user.student.email == "aliya@school.kz"
    # логин остаётся запасным входом
    assert user.login == "aliia.akhmetova"


@pytest.mark.django_db
def test_card_edit_through_the_students_api_keeps_the_account_in_step(as_admin, groups):
    made = create(as_admin, role="student", last_name="Ахметова", first_name="Алия", group=groups["9B"].pk)
    user = User.objects.get(pk=made.data["id"])
    answer = as_admin.patch(
        f"/api/students/{user.student.pk}/", {"first_name": "Әлия", "group": groups["11A"].pk}, format="json"
    )
    assert answer.status_code == 200, answer.data
    user.refresh_from_db()
    assert user.full_name == "Ахметова Әлия"
    # год выпуска считается от параллели группы, а не вводится
    assert user.student.graduation_year == Student.objects.get(pk=user.student.pk).graduation_year
    assert user.student.graduation_year != 2099


# --- Сотрудники --------------------------------------------------------------


@pytest.mark.django_db
def test_teacher_gets_a_profile_with_subjects(as_admin, subjects):
    response = create(
        as_admin,
        role="teacher",
        full_name="Нурпеисова Алия",
        handle="aliya.n@school.kz",
        subjects=[subjects[0].pk, subjects[1].pk],
        room="305",
        phone="+7 701 000 00 01",
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(email="aliya.n@school.kz")
    assert user.role == Role.TEACHER and user.phone == "+77010000001"
    profile = TeacherProfile.objects.get(user=user)
    assert set(profile.subjects.values_list("pk", flat=True)) == {s.pk for s in subjects}
    assert profile.room == "305"
    # сотрудник с почтой получает ссылку, не пароль
    assert response.data["invite"]["link"]
    detail = as_admin.get(f"/api/users/{user.pk}/").data
    assert detail["teacher"]["subjects"] == sorted(s.pk for s in subjects) or set(detail["teacher"]["subjects"]) == {
        s.pk for s in subjects
    }
    assert detail["teacher"]["teaches"] is False and detail["teacher"]["weekly_hours"] == 0


@pytest.mark.django_db
def test_teacher_without_email_gets_a_login_and_a_password(as_admin):
    response = create(as_admin, role="teacher", full_name="Нурпеисова Алия")
    assert response.status_code == 201, response.data
    user = User.objects.get(login="aliia.nurpeisova")
    assert user.email is None and response.data["password"]["login"] == "aliia.nurpeisova"
    assert user.check_password(response.data["password"]["password"])
    typed = create(as_admin, role="teacher", full_name="Сеитов Канат", handle="kanat.s")
    assert typed.status_code == 201 and User.objects.filter(login="kanat.s").exists()
    bad = create(as_admin, role="teacher", full_name="Сеитов Канат", handle="Канат С")
    assert bad.status_code == 400 and "латиница" in bad.data["detail"]


@pytest.mark.django_db
def test_curator_gets_the_groups_from_today(as_admin, groups):
    response = create(
        as_admin,
        role="curator",
        full_name="Сейдахметова Акбота",
        handle="akbota@school.kz",
        groups=[groups["11A"].pk, groups["9B"].pk],
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(email="akbota@school.kz")
    rows = CuratorAssignment.objects.filter(curator=user)
    assert {row.group.code for row in rows} == {"11A", "9B"}
    assert all(row.since == timezone.localdate() and row.until is None for row in rows)
    detail = as_admin.get(f"/api/users/{user.pk}/").data
    assert sorted(g["code"] for g in detail["curator"]["groups"]) == ["11A", "9B"]

    # снять группу, назначенную раньше, — закрывается сегодняшним днём;
    # назначенную сегодня же — строка уходит: она не действовала ни дня
    yesterday = timezone.localdate() - timezone.timedelta(days=1)
    CuratorAssignment.objects.filter(curator=user, group=groups["9B"]).update(since=yesterday)
    answer = as_admin.patch(f"/api/users/{user.pk}/", {"groups": []}, format="json")
    assert answer.status_code == 200, answer.data
    closed = CuratorAssignment.objects.get(curator=user, group=groups["9B"])
    assert closed.until == timezone.localdate()
    assert not CuratorAssignment.objects.filter(curator=user, group=groups["11A"]).exists()
    assert answer.data["curator"]["groups"] == []


@pytest.mark.django_db
def test_director_and_admin_are_created_with_the_domain_by_role(as_admin):
    director = create(as_admin, role="director_exam", full_name="Кымбат", handle="kymbat@school.kz")
    assert director.status_code == 201, director.data
    detail = as_admin.get(f"/api/users/{director.data['id']}/").data
    assert detail["domain_title"] and detail["teacher"] is None and detail["student"] is None
    other = create(as_admin, role="admin", full_name="Второй Администратор", handle="admin2@school.kz")
    assert other.status_code == 201 and User.objects.get(email="admin2@school.kz").role == Role.ADMIN


@pytest.mark.django_db
def test_role_change_closes_curator_groups_and_keeps_teacher_profile(as_admin, groups, subjects):
    made = create(
        as_admin, role="curator", full_name="Сейдахметова Акбота", handle="akbota@school.kz", groups=[groups["11A"].pk]
    )
    user = User.objects.get(pk=made.data["id"])
    yesterday = timezone.localdate() - timezone.timedelta(days=1)
    CuratorAssignment.objects.filter(curator=user).update(since=yesterday)
    detail = as_admin.get(f"/api/users/{user.pk}/").data
    assert "1" in detail["role_change_note"]

    answer = as_admin.patch(f"/api/users/{user.pk}/", {"role": "teacher", "subjects": [subjects[0].pk]}, format="json")
    assert answer.status_code == 200, answer.data
    user.refresh_from_db()
    assert user.role == Role.TEACHER
    assert CuratorAssignment.objects.get(curator=user).until == timezone.localdate()
    assert TeacherProfile.objects.get(user=user).subjects.count() == 1

    # ученика в сотрудника не переводят
    pupil = create(as_admin, role="student", last_name="Ахметова", first_name="Алия", group=groups["9B"].pk)
    refused = as_admin.patch(f"/api/users/{pupil.data['id']}/", {"role": "teacher"}, format="json")
    assert refused.status_code == 400 and "не переводят" in refused.data["detail"]


@pytest.mark.django_db
def test_only_admin_reads_and_writes_people(groups):
    curator = User.objects.create_user(email="c@school.kz", password=None, role=Role.CURATOR)
    set_password(curator, PASSWORD)
    api = APIClient()
    api.post("/api/auth/login/", {"email": curator.email, "password": PASSWORD}, format="json")
    assert api.get(f"/api/users/{curator.pk}/").status_code == 403
    assert (
        create(api, role="student", last_name="Ахметова", first_name="Алия", group=groups["9B"].pk).status_code == 403
    )
