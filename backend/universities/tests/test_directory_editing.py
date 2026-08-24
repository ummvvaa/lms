"""Фаза 29: справочник правится, а не только удаляется.

Раньше, чтобы поднять порог IELTS с 6.0 до 6.5, требования надо было
стереть и завести заново — вместе с их историей и ссылками. Проверяем,
что правка работает на всех уровнях, снимает плашку «не подтверждено»
и по-прежнему закрыта для чужой роли.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.models import Role
from universities.models import AdmissionRequirement, AdmissionRound, CatalogSource, Program, University


@pytest.fixture
def asem(make_user):
    return make_user(Role.DIRECTOR_ADMISSION, email="asem.editing@example.kz")


@pytest.fixture
def catalog(db):
    university = University.objects.create(
        name="Университет",
        country="Канада",
        domain="uni.example",
        data_source=CatalogSource.SEED,
        is_verified=False,
    )
    program = Program.objects.create(
        university=university,
        name="Computer Science",
        level="bachelor",
        data_source=CatalogSource.SEED,
        is_verified=False,
    )
    requirement = AdmissionRequirement.objects.create(
        program=program, min_ielts=Decimal("6.0"), data_source=CatalogSource.SEED, is_verified=False
    )
    return university, program, requirement


@pytest.mark.django_db
def test_threshold_changes_without_deleting_anything(client, asem, catalog):
    """Порог поднимается правкой: программа и требования остаются теми же."""
    _university, program, requirement = catalog
    client.force_login(asem)

    response = client.patch(
        f"/api/requirements/{requirement.pk}/", {"min_ielts": "6.5"}, content_type="application/json"
    )

    assert response.status_code == 200
    requirement.refresh_from_db()
    assert requirement.min_ielts == Decimal("6.5")
    assert Program.objects.filter(pk=program.pk).exists()
    assert AdmissionRequirement.objects.count() == 1


@pytest.mark.django_db
def test_manual_edit_removes_the_unverified_mark(client, asem, catalog):
    """Правка руками от владельца домена и есть подтверждение.

    Иначе справочник живёт с плашками просто потому, что после каждой
    правки не дошли руки нажать вторую кнопку.
    """
    _university, _program, requirement = catalog
    client.force_login(asem)

    client.patch(f"/api/requirements/{requirement.pk}/", {"min_ielts": "6.5"}, content_type="application/json")

    requirement.refresh_from_db()
    assert requirement.is_verified is True
    assert requirement.verified_by_id == asem.pk


@pytest.mark.django_db
def test_every_level_can_be_edited(client, asem, catalog):
    university, program, _requirement = catalog
    client.force_login(asem)

    assert (
        client.patch(
            f"/api/universities/{university.pk}/",
            {"name": "Новое название", "domain": "new.example"},
            content_type="application/json",
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/programs/{program.pk}/", {"name": "Информатика"}, content_type="application/json"
        ).status_code
        == 200
    )

    university.refresh_from_db()
    program.refresh_from_db()
    assert university.name == "Новое название"
    assert program.name == "Информатика"


@pytest.mark.django_db
def test_new_program_requirement_and_round_can_be_created(client, asem, catalog):
    university, program, _requirement = catalog
    client.force_login(asem)

    created = client.post(
        "/api/programs/",
        {"university": university.pk, "name": "Экономика", "level": "bachelor"},
        content_type="application/json",
    )
    assert created.status_code == 201

    fresh = created.json()["id"]
    assert (
        client.post(
            "/api/requirements/", {"program": fresh, "min_ielts": "7.0"}, content_type="application/json"
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/rounds/",
            {"program": program.pk, "round_type": "RD", "deadline": "2027-01-15"},
            content_type="application/json",
        ).status_code
        == 201
    )
    assert AdmissionRound.objects.filter(program=program).count() == 1


@pytest.mark.django_db
def test_another_director_cannot_edit_the_catalog(client, make_user, catalog):
    """Справочник ведёт домен поступления — инвариант №1 не смягчён."""
    _university, _program, requirement = catalog
    kymbat = make_user(Role.DIRECTOR_EXAM, email="kymbat.editing@example.kz")
    client.force_login(kymbat)

    response = client.patch(
        f"/api/requirements/{requirement.pk}/", {"min_ielts": "9.0"}, content_type="application/json"
    )

    assert response.status_code == 403
    requirement.refresh_from_db()
    assert requirement.min_ielts == Decimal("6.0")
    assert requirement.is_verified is False
