"""Фаза 45, часть 1: ресурсы школы.

Открытый раздел, в отличие от материалов олимпиадников: читают все,
ведут пять директоров. Проверяем то, что легко разъезжается: кто пишет,
кто читает, что видно ученику и что отметка «прочитано» — его дело.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from materials.models import Resource, ResourceCategory, ResourceRead


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.fixture
def category(db) -> ResourceCategory:
    return ResourceCategory.objects.get(code="scholarships")


@pytest.fixture
def article(db, category) -> Resource:
    return Resource.objects.create(
        title="Как искать гранты",
        category=category,
        summary="Короткая памятка о том, с чего начать",
        body="Первый абзац.\nВторой абзац.",
        reading_minutes=4,
        tags="гранты, деньги",
        is_featured=True,
    )


@pytest.mark.django_db
def test_seven_categories_are_seeded(db):
    """Стартовые категории посеяны миграцией — это справочник, а не данные."""
    assert ResourceCategory.objects.count() >= 7
    assert ResourceCategory.objects.filter(code="olympiads").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    ["director_behavior", "director_admission", "director_exam", "director_talent", "director_sport"],
)
def test_every_director_can_write(api, make_user, category, role):
    """Раздел ведут пять директоров: владельца-домена у ресурса нет."""
    api.force_authenticate(make_user(role))
    made = api.post(
        "/api/resources/",
        {"title": f"Памятка {role}", "category": category.pk, "reading_minutes": 3},
        format="json",
    )
    assert made.status_code == 201, made.data
    # автор проставляется сервером: в карточке видно, чья это памятка
    assert Resource.objects.get(pk=made.data["id"]).author is not None


@pytest.mark.django_db
def test_student_reads_but_does_not_write(api, student_user, article):
    api.force_authenticate(student_user)
    listing = api.get("/api/resources/")
    assert listing.status_code == 200
    assert listing.data["results"][0]["title"] == article.title
    assert api.post("/api/resources/", {"title": "X", "category": article.category_id}).status_code == 403


@pytest.mark.django_db
def test_unpublished_article_is_hidden_from_the_student(api, student_user, article):
    article.is_published = False
    article.save(update_fields=["is_published"])
    api.force_authenticate(student_user)
    assert api.get("/api/resources/").data["count"] == 0


@pytest.mark.django_db
def test_filters_by_category_and_words(api, student_user, article, category):
    other = ResourceCategory.objects.get(code="prep")
    Resource.objects.create(title="Как готовиться к IELTS", category=other, tags="ielts")
    api.force_authenticate(student_user)
    assert api.get("/api/resources/?category=scholarships").data["count"] == 1
    assert api.get("/api/resources/?q=IELTS").data["count"] == 1
    assert api.get("/api/resources/?featured=1").data["count"] == 1


@pytest.mark.django_db
def test_reading_mark_is_the_students_own(api, student_user, student, article):
    api.force_authenticate(student_user)
    marked = api.post(f"/api/resources/{article.pk}/read/")
    assert marked.status_code == 200 and marked.data["is_read"] is True
    assert ResourceRead.objects.filter(student=student, resource=article).exists()
    assert api.get("/api/resources/").data["results"][0]["is_read"] is True
    assert api.get("/api/resources/?read=1").data["count"] == 1

    removed = api.delete(f"/api/resources/{article.pk}/read/")
    assert removed.status_code == 200 and removed.data["is_read"] is False
    assert not ResourceRead.objects.filter(student=student).exists()


@pytest.mark.django_db
def test_director_cannot_mark_read(api, make_user, article):
    """Отметка «прочитано» — про ученика: у сотрудника её нет."""
    api.force_authenticate(make_user("director_exam"))
    assert api.post(f"/api/resources/{article.pk}/read/").status_code == 403


@pytest.mark.django_db
def test_reading_gives_no_xp(api, student_user, student, article):
    """Инвариант №12: XP за нажатие «прочитано» не начисляется."""
    from engagement.models import XPEvent

    api.force_authenticate(student_user)
    api.post(f"/api/resources/{article.pk}/read/")
    assert not XPEvent.objects.filter(student=student).exists()


@pytest.mark.django_db
def test_overview_counts_categories(api, student_user, article):
    api.force_authenticate(student_user)
    data = api.get("/api/resources/overview/").data
    assert data["total"] == 1
    assert data["featured"] == 1
    scholarships = next(row for row in data["categories"] if row["code"] == "scholarships")
    assert scholarships["count"] == 1


@pytest.mark.django_db
def test_category_with_articles_is_not_deleted(api, make_user, article):
    """Справочник не сносит категорию, на которую ссылаются материалы."""
    api.force_authenticate(make_user("director_admission"))
    answer = api.delete(f"/api/resource-categories/{article.category_id}/")
    assert answer.status_code == 400
    assert "материалы" in answer.data["detail"]


@pytest.mark.django_db
def test_resource_section_is_not_closed_by_the_olympiad_group(api, student_user, article):
    """Ресурсы — не материалы олимпиадников: группа их не закрывает."""
    api.force_authenticate(student_user)
    assert api.get("/api/resources/").status_code == 200
    # а закрытый раздел по-прежнему закрыт
    assert api.get("/api/materials/").status_code in (403, 404)


def test_registry_calls_resources_a_shared_model():
    """Право на ресурсы живёт в реестре, а не во вьюхе (инвариант №2)."""
    from core.domains import SHARED_MODELS, can_delete, can_write_shared

    assert "materials.Resource" in SHARED_MODELS
    assert can_write_shared("director_sport", "materials.Resource")
    assert not can_write_shared("student", "materials.Resource")
    assert not can_write_shared("admin", "materials.Resource")
    assert can_delete("director_talent", "materials.Resource")
