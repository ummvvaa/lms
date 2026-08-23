"""Фаза 16: поиск по системе.

Главное здесь — не полнота выдачи, а границы: ученик не должен находить
одноклассников (инвариант №7), а архивные записи не должны находиться
вовсе (инвариант №13).
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.passwords import set_password
from core.archive import archive
from core.search import search
from students.models import Student, StudyGroup
from universities.models import Program, University

PASSWORD = "Поиск!Проверка2026"


@pytest.fixture
def data(db):
    group = StudyGroup.objects.create(code="11A", grade=11)
    person = Student.objects.create(
        last_name="Ахметова",
        first_name="Алия",
        email="aliya.search@school.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    university = University.objects.create(name="University of Toronto", country="Канада")
    program = Program.objects.create(university=university, name="Computer Science")
    return person, university, program


def make_user(email: str, role: str) -> User:
    user = User.objects.create_user(email=email, password=None, role=role)
    set_password(user, PASSWORD)
    return user


def login(user: User) -> APIClient:
    client = APIClient()
    client.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    return client


def codes(payload: dict) -> list[str]:
    return [group["code"] for group in payload["groups"]]


@pytest.mark.django_db
def test_staff_finds_student_by_surname(data):
    payload = search("Ахмет", role=Role.DIRECTOR_EXAM)

    assert "students" in codes(payload)
    students = next(g for g in payload["groups"] if g["code"] == "students")
    assert students["rows"][0]["title"] == "Ахметова Алия"
    # переход по клику ведёт на карточку, а не в никуда
    assert students["rows"][0]["path"].startswith("/students/")


@pytest.mark.django_db
def test_staff_finds_student_by_email(data):
    payload = search("aliya.search", role=Role.DIRECTOR_BEHAVIOR)
    assert payload["total"] == 1


@pytest.mark.django_db
def test_student_does_not_find_classmates(data):
    payload = search("Ахмет", role=Role.STUDENT)

    assert "students" not in codes(payload)
    assert payload["total"] == 0


@pytest.mark.django_db
def test_student_finds_universities_and_goes_to_the_catalog(data):
    payload = search("Toronto", role=Role.STUDENT)

    assert "universities" in codes(payload)
    row = next(g for g in payload["groups"] if g["code"] == "universities")["rows"][0]
    # ученику в справочник нельзя — его вузы живут в каталоге
    assert row["path"].startswith("/catalog")


@pytest.mark.django_db
def test_programs_are_found_by_their_own_name(data):
    payload = search("Computer", role=Role.DIRECTOR_ADMISSION)

    assert "programs" in codes(payload)
    row = next(g for g in payload["groups"] if g["code"] == "programs")["rows"][0]
    assert "University of Toronto" in row["title"]


@pytest.mark.django_db
def test_archived_student_is_not_found(data):
    person, _university, _program = data
    admin = make_user("search.admin@school.kz", Role.ADMIN)
    archive(person, actor=admin)

    payload = search("Ахмет", role=Role.DIRECTOR_EXAM)

    assert "students" not in codes(payload)


@pytest.mark.django_db
def test_short_query_asks_for_more_letters(data):
    payload = search("А", role=Role.DIRECTOR_EXAM)

    assert payload["total"] == 0
    assert "хотя бы" in payload["detail"]


@pytest.mark.django_db
def test_nothing_found_says_so(data):
    payload = search("зззчегототакогонет", role=Role.DIRECTOR_EXAM)
    assert payload["detail"] == "Ничего не нашлось"


@pytest.mark.django_db
def test_search_endpoint_respects_the_role(data):
    staff = login(make_user("search.exam@school.kz", Role.DIRECTOR_EXAM))
    assert "students" in codes(staff.get("/api/search/?q=Ахмет").data)

    learner_user = make_user("search.student@school.kz", Role.STUDENT)
    person, _u, _p = data
    person.user = learner_user
    person.save(update_fields=["user"])
    learner = login(learner_user)
    assert "students" not in codes(learner.get("/api/search/?q=Ахмет").data)
