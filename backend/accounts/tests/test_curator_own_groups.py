"""Куратор видит только свои группы — источник один, действующие назначения (фаза 80).

Владелец вошёл новым куратором группы «тест» и увидел «AMSTERDAM · 0 учеников»:
вкладка браузера помнила группу прежнего куратора, выбор уходил в запросы как
`?group=AMSTERDAM`, сервер на чужой код отвечал «пусто», а шапка печатала
запомненное слово. Чужих данных куратор не получал, но и своих не видел —
и с одной группой выбраться не мог: переключателя у него нет.

Здесь закреплено:

- выбор группы сверяется с назначениями на каждом запросе: чужой, снятый
  и несуществующий код заменяется первой назначенной группой;
- страж по всем маршрутам, открытым куратору, — с одной группой, с двумя
  и без групп, с чужим выбором в запросе и без него: ни группы, ни ученика
  вне назначений в ответах нет;
- снятое администратором назначение действует на следующем запросе,
  без выхода из системы.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.curators import ALL_GROUPS, assign, picked_groups
from accounts.permissions import CURATOR_READ_ROUTES
from accounts.tests.test_curator_role_matrix import _api_routes, _student, propose
from roadmap.models import Task
from students.models import StudyGroup

# приметы чужого: код группы, фамилия и почта ученика — таких строк в ответах быть не должно
ALIEN_GROUP = "AMSTERDAM"
ALIEN_NAME = "Чужестранцев"
ALIEN_EMAIL = "alien80@example.kz"
ALIEN_TASK = "Задача чужой группы 80"
ALIEN_MARKS = (ALIEN_GROUP, ALIEN_NAME, ALIEN_EMAIL, ALIEN_TASK)

MONTH_AGO = dt.timedelta(days=30)


@pytest.fixture
def admin(make_user):
    return make_user("admin", "admin80@example.kz")


@pytest.fixture
def alien(db, make_user, admin):
    """Чужая группа с учеником, задачей, предложением и своим куратором."""
    group = StudyGroup.objects.create(code=ALIEN_GROUP, grade=11)
    student = _student(ALIEN_EMAIL, group, ALIEN_NAME)
    Task.objects.create(student=student, title=ALIEN_TASK, category="documents")
    user = make_user("student", ALIEN_EMAIL, full_name=f"{ALIEN_NAME} Ученик")
    student.user = user
    student.save(update_fields=["user"])
    propose(None, user, [{"model": "students.ExamProfile", "field": "ielts_current", "value": "6.5"}])
    other = make_user("curator", "other-curator80@example.kz", full_name="Другой Куратор")
    assign(group=group, curator=other, since=timezone.localdate() - MONTH_AGO, actor=admin)
    return student


def _curator(make_user, admin, *codes: str):
    """Куратор с группами `codes`; в каждой — по ученику."""
    user = make_user("curator", f"curator80-{len(codes)}@example.kz", full_name="Куратор Восьмидесятой")
    for code in codes:
        group = StudyGroup.objects.create(code=code, grade=11)
        _student(f"{code.lower()}80@example.kz", group, f"Свой{code.title()}")
        assign(group=group, curator=user, since=timezone.localdate() - MONTH_AGO, actor=admin)
    client = APIClient()
    client.force_login(user)
    return user, client


# --- Сверка выбора с назначениями ------------------------------------------------


@pytest.mark.django_db
def test_picked_group_is_checked_against_assignments(make_user, admin, alien):
    user, _ = _curator(make_user, admin, "TEST", "BERLIN")
    ids = {g.code: g.pk for g in StudyGroup.objects.all()}

    assert picked_groups(user, "") == ([ids["BERLIN"], ids["TEST"]], ALL_GROUPS)
    assert picked_groups(user, "all") == ([ids["BERLIN"], ids["TEST"]], ALL_GROUPS)
    assert picked_groups(user, "test") == ([ids["TEST"]], "TEST"), "свой код — без оглядки на регистр"
    # чужая и несуществующая группа — первая назначенная по коду, а не пусто и не чужая
    assert picked_groups(user, ALIEN_GROUP) == ([ids["BERLIN"]], "BERLIN")
    assert picked_groups(user, "NOWHERE") == ([ids["BERLIN"]], "BERLIN")


@pytest.mark.django_db
def test_nobody_but_a_curator_gets_groups(make_user, admin, alien):
    assert picked_groups(admin, ALIEN_GROUP) == ([], ALL_GROUPS)
    loner, _ = _curator(make_user, admin)
    assert picked_groups(loner, ALIEN_GROUP) == ([], ALL_GROUPS)


@pytest.mark.django_db
def test_remembered_alien_group_shows_own_group_not_an_empty_cabinet(make_user, admin, alien):
    """Сценарий владельца: назначен на «тест», вкладка помнит AMSTERDAM — видит «тест»."""
    _, client = _curator(make_user, admin, "TEST")

    home = client.get(f"/api/curator/overview/?group={ALIEN_GROUP}").json()
    assert home["group"] == "TEST" and home["students_total"] == 1
    assert [g["code"] for g in home["groups"]] == ["TEST"]

    students = client.get(f"/api/curator/students/?group={ALIEN_GROUP}").json()
    assert [row["group"] for row in students["results"]] == ["TEST"] and students["group"] == "TEST"

    # очередь сверяет выбор тем же правилом
    own = StudyGroup.objects.get(code="TEST").students.get()
    own.user = make_user("student", own.email, full_name="Свой Ученик")
    own.save(update_fields=["user"])
    propose(None, own.user, [{"model": "students.ExamProfile", "field": "ielts_current", "value": "7.0"}])
    queue = client.get(f"/api/suggestions/from-students/?group={ALIEN_GROUP}").json()
    assert [row["student"] for row in queue["results"]] == [own.pk], "очередь — своей группы, не пустая и не чужая"
    # пробников файлом у куратора нет вовсе: раздел закрыт шлюзом
    assert client.get(f"/api/mock-imports/?group={ALIEN_GROUP}").status_code == 403

    # имя файла выгрузки — тоже по своей группе
    export = client.get(f"/api/curator/students/export/?group={ALIEN_GROUP}&preview=1").json()
    assert "TEST" in export["filename"] and ALIEN_GROUP not in export["filename"]


# --- Страж: ни группы, ни ученика вне назначений ---------------------------------


def _open_paths(alien_student):
    """Маршруты чтения, открытые куратору: с заглушкой и с ключами чужой группы и ученика."""
    for path, name in _api_routes():
        if name not in CURATOR_READ_ROUTES:
            continue
        yield path
        if "/1/" in path or path.endswith("/1"):
            yield path.replace("/1", f"/{alien_student.pk}", 1)
            yield path.replace("/1", f"/{alien_student.group_id}", 1)


@pytest.mark.django_db
@pytest.mark.parametrize("codes", [("TEST",), ("TEST", "BERLIN"), ()], ids=["одна", "две", "ни одной"])
def test_no_route_gives_a_group_or_a_student_outside_the_assignments(make_user, admin, alien, codes):
    _, client = _curator(make_user, admin, *codes)

    seen = 0
    for path in _open_paths(alien):
        for query in ("", f"?group={ALIEN_GROUP}", f"?group={alien.group_id}", f"?student={alien.pk}"):
            response = client.get(path + query)
            assert response.status_code < 500, (path + query, response.status_code)
            body = response.content.decode(errors="ignore")
            for mark in ALIEN_MARKS:
                assert mark not in body, f"{path + query}: в ответе куратора «{mark}» чужой группы"
            seen += 1
    assert seen > 200


@pytest.mark.django_db
def test_curator_without_groups_gets_nothing_but_an_empty_cabinet(make_user, admin, alien):
    _, client = _curator(make_user, admin)

    home = client.get(f"/api/curator/overview/?group={ALIEN_GROUP}").json()
    assert home["groups"] == [] and home["group"] == ALL_GROUPS
    assert home["students_total"] == 0 and home["queue"] == [] and home["tasks"] == []
    assert client.get("/api/curator/profile/").json()["groups"] == []
    assert client.get("/api/curator/students/").json()["results"] == []
    assert client.get(f"/api/curator/students/{alien.pk}/").status_code == 404


# --- Снятие с группы -------------------------------------------------------------


@pytest.mark.django_db
def test_removed_assignment_works_on_the_next_request_without_logout(make_user, admin, alien):
    user, client = _curator(make_user, admin, "TEST", "BERLIN")
    test_group = StudyGroup.objects.get(code="TEST")
    mine = test_group.students.get()
    assert client.get(f"/api/curator/students/{mine.pk}/").status_code == 200

    # администратор передаёт группу другому куратору — той же ручкой, что в интерфейсе
    successor = make_user("curator", "successor80@example.kz", full_name="Сменщик")
    office = APIClient()
    office.force_login(admin)
    moved = office.post(
        "/api/curator-assignments/",
        {"group": test_group.pk, "curator": successor.pk, "since": str(timezone.localdate())},
        format="json",
    )
    assert moved.status_code == 201, moved.content

    # та же сессия, следующий запрос: группы нет ни в шапке, ни в ответах, выбор сброшен
    home = client.get("/api/curator/overview/?group=TEST").json()
    assert [g["code"] for g in home["groups"]] == ["BERLIN"] and home["group"] == "BERLIN"
    assert client.get(f"/api/curator/students/{mine.pk}/").status_code == 404
    names = [row["full_name"] for row in client.get("/api/curator/students/?group=TEST").json()["results"]]
    assert names and all("Test" not in name for name in names)
