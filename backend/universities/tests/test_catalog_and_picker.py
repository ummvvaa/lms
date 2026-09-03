"""Фаза 10: каталог, добавление в свой список и подбор словами.

Инвариант №10 проверяется буквально: в ответе подбора не должно быть
названия, которого нет в справочнике.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.passwords import set_password
from students.models import AdmissionProfile, ExamProfile, Student
from universities.models import AddedBy, AdmissionRequirement, AdmissionRound, Program, StudentUniversity, University
from universities.picker import parse_request, pick, unknown_request

PASSWORD = "Каталог!Проверка2026"


@pytest.fixture
def student(db):
    user = User.objects.create_user(email="catalog.student@school.kz", password=None, role=Role.STUDENT)
    set_password(user, PASSWORD)
    person = Student.objects.create(
        last_name="Ким",
        first_name="Дана",
        email="catalog.student@school.kz",
        grade=11,
        graduation_year=2027,
        user=user,
    )
    ExamProfile.objects.create(student=person, ielts_current=Decimal("6.0"), sat_current=1250, gpa=Decimal("3.4"))
    AdmissionProfile.objects.create(student=person)
    return person


@pytest.fixture
def catalog(db):
    """Небольшой справочник: две страны, три программы."""
    from datetime import date, timedelta

    canada = University.objects.create(name="University of Toronto", country="Канада")
    netherlands = University.objects.create(name="Delft University of Technology", country="Нидерланды")

    programs = []
    for university, name, ielts in (
        (canada, "Computer Science", "6.5"),
        (canada, "Economics", "6.0"),
        (netherlands, "Aerospace Engineering", "7.0"),
    ):
        program = Program.objects.create(university=university, name=name)
        AdmissionRequirement.objects.create(program=program, min_ielts=Decimal(ielts))
        AdmissionRound.objects.create(program=program, round_type="RD", deadline=date.today() + timedelta(days=90))
        programs.append(program)
    return programs


@pytest.fixture
def api(student):
    client = APIClient()
    client.post("/api/auth/login/", {"email": student.email, "password": PASSWORD}, format="json")
    return client


# --- каталог -------------------------------------------------------------


@pytest.mark.django_db
def test_catalog_sorts_by_match(api, catalog):
    payload = api.get("/api/catalog/").data

    assert payload["count"] == 3
    percents = [row["percent"] for row in payload["results"]]
    assert percents == sorted(percents, reverse=True)
    assert all("breakdown" in row for row in payload["results"])


@pytest.mark.django_db
def test_catalog_filters_by_country_and_level(api, catalog):
    by_country = api.get("/api/catalog/?country=Нидерланды").data
    assert by_country["count"] == 1

    high = api.get("/api/catalog/?level=high").data
    assert all(row["percent"] >= 80 for row in high["results"])


@pytest.mark.django_db
def test_catalog_shows_deadlines_from_the_registry(api, catalog):
    row = api.get("/api/catalog/").data["results"][0]

    assert len(row["rounds"]) == 1
    assert row["rounds"][0]["round_type"] == "RD"


@pytest.mark.django_db
def test_facets_offer_only_what_is_in_the_registry(api, catalog):
    facets = api.get("/api/catalog/facets/").data

    assert set(facets["countries"]) == {"Канада", "Нидерланды"}
    assert "Япония" not in facets["countries"]


# --- добавление в свой список --------------------------------------------


@pytest.mark.django_db
def test_student_adds_program_and_it_waits_for_confirmation(api, catalog, student):
    response = api.post("/api/catalog/add/", {"program": catalog[0].pk, "tier": "target"}, format="json")

    assert response.status_code == 201
    entry = StudentUniversity.objects.get(student=student, program=catalog[0])
    assert entry.tier == "target"
    assert entry.added_by == AddedBy.STUDENT
    assert entry.is_confirmed is False


@pytest.mark.django_db
def test_student_removes_only_what_he_added(api, catalog, student):
    own = StudentUniversity.objects.create(
        student=student, program=catalog[0], added_by=AddedBy.STUDENT, is_confirmed=False
    )
    by_director = StudentUniversity.objects.create(student=student, program=catalog[1])

    assert api.delete(f"/api/catalog/remove/{own.pk}/").status_code == 204
    assert api.delete(f"/api/catalog/remove/{by_director.pk}/").status_code == 403
    assert StudentUniversity.objects.filter(pk=by_director.pk).exists()


@pytest.mark.django_db
@override_settings(STUDENT_LIST_LIMIT=2)
def test_list_has_a_limit(api, catalog):
    assert api.post("/api/catalog/add/", {"program": catalog[0].pk}, format="json").status_code == 201
    assert api.post("/api/catalog/add/", {"program": catalog[1].pk}, format="json").status_code == 201

    third = api.post("/api/catalog/add/", {"program": catalog[2].pk}, format="json")

    assert third.status_code == 400
    assert "потолок" in third.data["detail"]


@pytest.mark.django_db
def test_director_sees_and_confirms_student_additions(api, catalog, student, db):
    api.post("/api/catalog/add/", {"program": catalog[0].pk, "tier": "reach"}, format="json")

    director = User.objects.create_user(email="asem@school.kz", password=None, role=Role.DIRECTOR_ADMISSION)
    set_password(director, PASSWORD)
    staff = APIClient()
    staff.post("/api/auth/login/", {"email": director.email, "password": PASSWORD}, format="json")

    pending = staff.get("/api/catalog/pending/").data
    assert len(pending) == 1
    assert pending[0]["student_name"] == student.full_name

    confirmed = staff.post(f"/api/catalog/pending/{pending[0]['id']}/", {"decision": "confirm"}, format="json")
    assert confirmed.status_code == 200
    assert StudentUniversity.objects.get(pk=pending[0]["id"]).is_confirmed is True
    assert staff.get("/api/catalog/pending/").data == []


@pytest.mark.django_db
def test_student_cannot_see_the_confirmation_queue(api, catalog):
    assert api.get("/api/catalog/pending/").status_code == 403


# --- подбор словами ------------------------------------------------------


@pytest.mark.django_db
def test_picker_understands_declensions(catalog):
    filters = parse_request("хочу в Канаду на Computer Science", ["Канада", "Нидерланды"], ["Computer Science"])

    assert filters.country == "Канада"
    assert filters.major == "Computer Science"


@pytest.mark.django_db
def test_picker_names_only_programs_from_the_registry(student, catalog):
    result = pick(student=student, text="хочу в Канаду")

    known = {p.university.name for p in catalog}
    assert result.picks
    for row in result.picks:
        assert row.card["university_name"] in known


@pytest.mark.django_db
def test_picker_says_plainly_that_there_is_no_such_country(student, catalog):
    result = pick(student=student, text="хочу учиться в Японии")

    assert "нет программ по запросу" in result.note
    assert "Япония" in result.note
    # и всё равно показывает то, что есть, вместо пустого экрана
    assert result.picks


@pytest.mark.django_db
def test_unknown_request_detects_missing_country(catalog):
    assert unknown_request("хочу в Японию", ["Канада"], []) == "Япония"
    assert unknown_request("хочу в Канаду", ["Канада"], []) == ""


@pytest.mark.django_db
def test_picker_works_without_a_model_key(student, catalog):
    """Школа не должна вставать из-за недоступного провайдера."""
    result = pick(student=student, text="хочу в Канаду")

    assert result.offline is True
    assert all(row.why for row in result.picks)


@pytest.mark.django_db
def test_picker_never_promises_chances(student, catalog):
    """Инвариант №11: ни «шанса», ни «вероятности», ни «прогноза»."""
    import json

    result = pick(student=student, text="хочу в Канаду на Computer Science")
    text = json.dumps(result.as_dict(), ensure_ascii=False).lower()

    for word in ("шанс", "вероятност", "прогноз"):
        assert word not in text


@pytest.mark.django_db
def test_empty_registry_answers_honestly(student):
    result = pick(student=student, text="хочу в Канаду")

    assert result.picks == []
    assert "не наполнен" in result.note


class _StringsProvider:
    """Провайдер, отвечающий списком строк вместо объектов.

    Схема — просьба, а не гарантия: так уже ломался разбор файла
    (решение от 2026-08-24), и точно так же ломался подбор.
    """

    name = "fake"

    def __init__(self, parsed) -> None:
        self.parsed = parsed

    def is_configured(self) -> bool:
        return True

    def complete(self, **kwargs):
        from suggestions.providers import Completion, Usage

        return Completion(
            content="",
            parsed=self.parsed,
            model="fake-1",
            external_id="msg_1",
            usage=Usage(10, 5),
            raw={"id": "msg_1"},
        )


@pytest.mark.django_db
def test_picker_survives_a_list_of_strings(student, catalog, monkeypatch):
    """Ответ не той формы уводит подбор на правила, а не роняет запрос.

    Найдено прогоном фазы 51: `picks` пришли строками, и `row.get`
    отвечал ученику пятисоткой вместо подбора.
    """
    provider = _StringsProvider({"picks": ["Toronto", "Waterloo"], "note": ""})
    monkeypatch.setattr("suggestions.providers.get_provider", lambda: provider)
    monkeypatch.setattr("suggestions.llm.get_provider", lambda: provider)

    result = pick(student=student, text="хочу в Канаду")

    assert result.offline is True, "подбор ушёл на правила"
    assert result.picks, "и всё равно что-то показал"
