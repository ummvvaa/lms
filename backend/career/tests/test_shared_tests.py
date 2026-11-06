"""Тест профориентации общий для школы (решение владельца, 06.11.2026).

* каждый живой тест видят и ведут все учителя профориентации и администратор —
  кто бы его ни загрузил и кому бы он ни был назначен;
* граница по группам — только там, где ученики: «Кому» учитель выбирает из своих
  групп, чужие назначения не видит и не стирает, счётчики, результаты и попытки —
  по своим группам;
* удаляют и убирают в архив автор и администратор;
* учитель без предмета профориентации и куратор получают отказ, как раньше.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from career.models import CareerAssignment, CareerTest
from career.tests.conftest import answer_all, login, make_student

pytestmark = pytest.mark.django_db


@pytest.fixture
def osaka(db, boston):
    return type(boston).objects.create(code="OSAKA", parallel=10)


@pytest.fixture
def osaka_pupil(osaka, make_user):
    return make_student(osaka, "Касымова", "Дана", "dana.career@example.kz", make_user)


@pytest.fixture
def osaka_teacher(make_user, career_subject, osaka):
    """Второй учитель профориентации: журнал только в OSAKA."""
    from academics.cohorts import group_cohort
    from academics.models import Course, TeacherProfile
    from accounts.models import Role

    user = make_user(Role.TEACHER, "osaka.career@example.kz", full_name="Ерлан Профориентатор")
    TeacherProfile.objects.create(user=user, room="105").subjects.set([career_subject])
    Course.objects.create(subject=career_subject, teacher=user, cohort=group_cohort(osaka))
    return user


@pytest.fixture
def admin_test(admin, example_bytes):
    """Тест загружен администратором, «Кому» не задано."""
    response = login(admin).post(
        "/api/career/tests/", {"file": SimpleUploadedFile("karta.xlsx", example_bytes)}, format="multipart"
    )
    assert response.status_code == 201, response.content
    return CareerTest.objects.get(pk=response.data["id"])


def test_teacher_sees_and_opens_a_test_uploaded_by_the_admin(admin_test, teacher, admin):
    client = login(teacher)
    rows = client.get("/api/career/tests/").json()["tests"]
    assert [row["id"] for row in rows] == [admin_test.pk]
    row = rows[0]
    assert row["created_by"]["full_name"] == "Администратор"
    assert row["assigned"] == 0 and row["used"] is False and row["can_remove"] is False
    detail = client.get(f"/api/career/tests/{admin_test.pk}/")
    assert detail.status_code == 200 and detail.json()["groups"] == []
    assert client.get(f"/api/career/tests/{admin_test.pk}/file/").status_code == 200
    # включить, выключить, поправить порог — как свой
    assert client.patch(f"/api/career/tests/{admin_test.pk}/", {"is_active": True}, format="json").status_code == 200
    response = client.patch(f"/api/career/tests/{admin_test.pk}/", {"analysis_min_score": 2}, format="json")
    assert response.status_code == 200
    admin_test.refresh_from_db()
    assert admin_test.is_active and admin_test.analysis_min_score == 2
    # администратору свой тест удалить можно
    assert login(admin).get("/api/career/tests/").json()["tests"][0]["can_remove"] is True


def test_teacher_assigns_own_group_but_not_a_foreign_one(admin_test, teacher, boston, osaka):
    client = login(teacher)
    url = f"/api/career/tests/{admin_test.pk}/assignments/"
    response = client.put(url, {"groups": [{"group": boston.pk}]}, format="json")
    assert response.status_code == 200
    assert [g["code"] for g in response.json()["groups"]] == ["BOSTON"]
    refused = client.put(url, {"groups": [{"group": osaka.pk}]}, format="json")
    assert refused.status_code == 400
    assert set(admin_test.assignments.values_list("group__code", flat=True)) == {"BOSTON"}


def test_teacher_keeps_assignments_of_other_groups(admin_test, teacher, osaka_teacher, admin, boston, riga, osaka):
    """Тест общий: сохранение «Кому» одним учителем не снимает группы другого."""
    login(osaka_teacher).put(
        f"/api/career/tests/{admin_test.pk}/assignments/", {"groups": [{"group": osaka.pk}]}, format="json"
    )
    client = login(teacher)
    response = client.put(
        f"/api/career/tests/{admin_test.pk}/assignments/", {"groups": [{"group": riga.pk}]}, format="json"
    )
    assert [g["code"] for g in response.json()["groups"]] == ["RIGA"]
    assert set(CareerAssignment.objects.values_list("group__code", flat=True)) == {"OSAKA", "RIGA"}
    # снять свои — чужие остаются
    client.put(f"/api/career/tests/{admin_test.pk}/assignments/", {"groups": []}, format="json")
    assert set(CareerAssignment.objects.values_list("group__code", flat=True)) == {"OSAKA"}
    # администратор заменяет всё
    login(admin).put(
        f"/api/career/tests/{admin_test.pk}/assignments/", {"groups": [{"group": boston.pk}]}, format="json"
    )
    assert set(CareerAssignment.objects.values_list("group__code", flat=True)) == {"BOSTON"}


def test_teacher_does_not_see_results_of_foreign_groups(
    admin_test, teacher, osaka_teacher, admin, boston, osaka, osaka_pupil, pupils
):
    login(admin).patch(f"/api/career/tests/{admin_test.pk}/", {"is_active": True}, format="json")
    login(admin).put(
        f"/api/career/tests/{admin_test.pk}/assignments/",
        {"groups": [{"group": boston.pk}, {"group": osaka.pk}]},
        format="json",
    )
    dana = login(osaka_pupil.user)
    attempt = dana.post(f"/api/career/my/tests/{admin_test.pk}/start/").json()["id"]
    answer_all(dana, attempt, lambda n: "+")
    assert dana.post(f"/api/career/my/attempts/{attempt}/finish/").status_code == 200

    client = login(teacher)
    # в строке теста — только свои группы: двое из BOSTON назначены, сдавших нет
    row = client.get("/api/career/tests/").json()["tests"][0]
    assert row["assigned"] == 2 and row["done"] == 0 and row["used"] is True
    assert [g["code"] for g in client.get(f"/api/career/tests/{admin_test.pk}/").json()["groups"]] == ["BOSTON"]
    # чужая группа: ни матрицы, ни попытки, ни карточки ученика
    assert client.get(f"/api/career/results/?group={osaka.pk}").json()["group"] is None
    assert client.get(f"/api/career/attempts/{attempt}/").status_code == 404
    assert client.post(f"/api/career/attempts/{attempt}/retake/").status_code == 404
    assert client.get(f"/api/career/students/{osaka_pupil.pk}/").status_code == 404
    # учитель OSAKA и администратор видят сдачу
    own = login(osaka_teacher).get("/api/career/tests/").json()["tests"][0]
    assert own["assigned"] == 1 and own["done"] == 1
    everyone = login(admin).get("/api/career/tests/").json()["tests"][0]
    assert everyone["assigned"] == 3 and everyone["done"] == 1


def test_only_the_author_and_the_admin_remove_a_shared_test(admin_test, karta, teacher, osaka_teacher, admin):
    other = login(osaka_teacher)
    assert other.delete(f"/api/career/tests/{admin_test.pk}/").status_code == 403
    assert other.delete(f"/api/career/tests/{karta.pk}/").status_code == 403
    rows = {row["id"]: row for row in other.get("/api/career/tests/").json()["tests"]}
    assert rows[karta.pk]["can_remove"] is False
    assert {row["id"]: row["can_remove"] for row in login(teacher).get("/api/career/tests/").json()["tests"]} == {
        admin_test.pk: False,
        karta.pk: True,
    }
    assert login(teacher).delete(f"/api/career/tests/{karta.pk}/").status_code == 200
    assert login(admin).delete(f"/api/career/tests/{admin_test.pk}/").status_code == 200
    assert not CareerTest.objects.exists()


def test_teacher_without_the_subject_and_curator_are_refused(admin_test, other_teacher, curator):
    for user in (other_teacher, curator):
        client = login(user)
        assert client.get("/api/career/tests/").status_code == 403, user.email
        assert client.get(f"/api/career/tests/{admin_test.pk}/").status_code == 403, user.email
        assert client.get(f"/api/career/tests/{admin_test.pk}/file/").status_code == 403, user.email
