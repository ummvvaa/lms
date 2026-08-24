"""Справочники предметов и видов спорта: права, защита от удаления, замена."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import Role
from core.references import find
from directories.models import OlympiadSubject, SportType
from directories.services import duplicate_groups, normalized, usage_total
from students.models import Activity, ActivityCategory


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def arman(make_user):
    return make_user(Role.DIRECTOR_TALENT, email="arman@example.kz")


@pytest.fixture
def nurlybek(make_user):
    return make_user(Role.DIRECTOR_SPORT, email="nurlybek@example.kz")


@pytest.fixture
def math(db) -> OlympiadSubject:
    return OlympiadSubject.objects.create(name="Математика", area="exact", sort_order=10)


# --- Права --------------------------------------------------------------


@pytest.mark.django_db
def test_talent_director_keeps_the_subject_directory(api, arman):
    """Арман заводит предмет, и тот появляется в списке выбора."""
    api.force_authenticate(arman)
    created = api.post("/api/subjects/", {"name": "Физика", "area": "natural"}, format="json")
    assert created.status_code == 201, created.data

    meta = api.get("/api/meta/domains/").json()
    talent = next(d for d in meta["domains"] if d["code"] == "talent")
    activity = next(m for m in talent["models"] if m["label"] == "students.Activity")
    subject = next(f for f in activity["fields"] if f["name"] == "subject")
    assert {"value": "Физика", "title": "Физика"} in subject["choices"]


@pytest.mark.django_db
def test_sport_director_cannot_touch_subjects(api, nurlybek, math):
    """Чужой справочник виден, но не правится (инвариант №1)."""
    api.force_authenticate(nurlybek)
    assert api.get("/api/subjects/").status_code == 200
    assert api.post("/api/subjects/", {"name": "Химия"}, format="json").status_code == 403
    assert api.patch(f"/api/subjects/{math.pk}/", {"name": "Матан"}, format="json").status_code == 403
    assert api.delete(f"/api/subjects/{math.pk}/").status_code == 403


@pytest.mark.django_db
def test_student_sees_only_the_active_list(api, make_user, math):
    """Ученику скрытые записи не нужны — он их и не получает."""
    OlympiadSubject.objects.create(name="Астрономия", is_active=False)
    api.force_authenticate(make_user(Role.STUDENT, email="pupil@example.kz"))
    names = [row["name"] for row in api.get("/api/subjects/").json()["results"]]
    assert names == ["Математика"]


# --- Защита от удаления используемого ------------------------------------


@pytest.mark.django_db
def test_used_subject_cannot_be_deleted_and_offers_two_ways_out(api, arman, math, student):
    """«Используется в 14 активностях. Удалить нельзя» — плюс два выхода."""
    for i in range(14):
        Activity.objects.create(student=student, category=ActivityCategory.OLYMPIAD, title=f"Тур {i}", subject=math)

    api.force_authenticate(arman)
    verdict = api.get(f"/api/subjects/{math.pk}/usage/").json()
    assert verdict["can_delete"] is False
    assert verdict["usage_total"] == 14
    assert "14 — активности" in verdict["message"]
    assert [option["action"] for option in verdict["options"]] == ["hide", "replace"]

    refused = api.delete(f"/api/subjects/{math.pk}/")
    assert refused.status_code == 409
    assert "Удалить нельзя" in refused.json()["detail"]
    assert OlympiadSubject.objects.filter(pk=math.pk).exists()


@pytest.mark.django_db
def test_hiding_keeps_links_but_drops_the_choice(api, arman, math, student):
    """«Скрыть» убирает из списка выбора, ссылки не рвёт."""
    Activity.objects.create(student=student, category=ActivityCategory.OLYMPIAD, title="Тур", subject=math)
    api.force_authenticate(arman)

    assert api.post(f"/api/subjects/{math.pk}/hide/").json()["is_active"] is False
    meta = api.get("/api/meta/domains/").json()
    talent = next(d for d in meta["domains"] if d["code"] == "talent")
    activity = next(m for m in talent["models"] if m["label"] == "students.Activity")
    subject = next(f for f in activity["fields"] if f["name"] == "subject")
    assert subject["choices"] == []
    assert Activity.objects.get(title="Тур").subject_id == math.pk


@pytest.mark.django_db
def test_replace_moves_links_and_then_deletes(api, arman, math, student):
    """После замены ссылок не осталось, и предмет удаляется."""
    duplicate = OlympiadSubject.objects.create(name="Матем.", area="exact")
    Activity.objects.create(student=student, category=ActivityCategory.OLYMPIAD, title="Тур", subject=duplicate)

    api.force_authenticate(arman)
    result = api.post(f"/api/subjects/{duplicate.pk}/replace/", {"target": math.pk}, format="json").json()

    assert result["moved"] == 1
    assert "«Матем.» заменена на «Математика»" in result["detail"]
    assert not OlympiadSubject.objects.filter(pk=duplicate.pk).exists()
    assert Activity.objects.get(title="Тур").subject_id == math.pk

    # теперь на «Математику» ссылаются, а не на удалённую запись
    assert usage_total(math) == 1


@pytest.mark.django_db
def test_unused_entry_is_deleted_for_real(api, arman, math):
    """Справочник без истории удаляется физически (инвариант №13)."""
    api.force_authenticate(arman)
    assert api.get(f"/api/subjects/{math.pk}/usage/").json()["can_delete"] is True
    assert api.delete(f"/api/subjects/{math.pk}/").status_code == 200
    assert not OlympiadSubject.objects.filter(pk=math.pk).exists()


@pytest.mark.django_db
def test_replace_refuses_to_swap_a_record_with_itself(api, arman, math):
    api.force_authenticate(arman)
    answer = api.post(f"/api/subjects/{math.pk}/replace/", {"target": math.pk}, format="json")
    assert answer.status_code == 400
    assert "саму себя" in answer.json()["detail"]


@pytest.mark.django_db
def test_archived_link_holds_the_entry_too(api, arman, math, student):
    """Архивная активность держит предмет так же, как живая."""
    from django.utils import timezone

    activity = Activity.objects.create(student=student, category=ActivityCategory.OLYMPIAD, title="Тур", subject=math)
    activity.archived_at = timezone.now()
    activity.save(update_fields=["archived_at"])

    api.force_authenticate(arman)
    verdict = api.get(f"/api/subjects/{math.pk}/usage/").json()
    assert verdict["can_delete"] is False
    assert "в архиве: 1" in verdict["message"]


# --- Похожие написания ---------------------------------------------------


@pytest.mark.django_db
def test_similar_spellings_are_shown_but_never_merged_by_themselves(api, arman, math):
    """«Матем.» и «математика» попадают в одну группу, но не склеиваются."""
    OlympiadSubject.objects.create(name="математика")
    OlympiadSubject.objects.create(name="Матем.")
    OlympiadSubject.objects.create(name="Физика")

    groups = duplicate_groups(OlympiadSubject)
    assert len(groups) == 1
    assert {row["name"] for row in groups[0]["entries"]} == {"Математика", "математика", "Матем."}
    assert OlympiadSubject.objects.count() == 4, "склеивать самостоятельно нельзя"

    api.force_authenticate(arman)
    answer = api.get("/api/subjects/duplicates/").json()
    assert len(answer["groups"]) == 1
    assert "возможно, это одно и то же" in answer["detail"]


def test_normalization_ignores_case_dots_and_lookalikes():
    assert normalized("Матем.") == normalized("матем")
    assert normalized("Ёлка") == normalized("елка")
    # латинская «c» в кириллическом слове — частая беда копипасты
    assert normalized("Cпорт") == normalized("Спорт")


# --- Значение из файла ----------------------------------------------------


@pytest.mark.django_db
def test_text_value_resolves_to_a_directory_record(db):
    """«футбол» из файла находит заведённый «Футбол»."""
    football = SportType.objects.create(name="Футбол", category="team")
    assert find(SportType, "футбол") == football
    assert find(SportType, str(football.pk)) == football


@pytest.mark.django_db
def test_unknown_value_is_refused_with_a_hint(db):
    """Опечатка в файле не заводит новую запись справочника молча."""
    SportType.objects.create(name="Футбол")
    with pytest.raises(LookupError) as error:
        find(SportType, "Кёрлинг")
    assert "нет в справочнике «Виды спорта»" in str(error.value)
    assert SportType.objects.count() == 1


@pytest.mark.django_db
def test_table_cell_accepts_the_name_and_stores_the_link(api, nurlybek, student):
    """В ячейке таблицы директор пишет название, в базе оказывается ссылка."""
    football = SportType.objects.create(name="Футбол", category="team")
    api.force_authenticate(nurlybek)

    saved = api.post(
        "/api/batch/save/",
        {
            "changes": [
                {
                    "student": student.pk,
                    "model": "students.SportProfile",
                    "field": "sport_type",
                    "value": "футбол",
                }
            ]
        },
        format="json",
    ).json()

    assert saved["applied"] == 1
    student.sport.refresh_from_db()
    assert student.sport.sport_type == football

    # в журнале — название, а не ключ: строку читает человек
    from core.models import AuditLog

    entry = AuditLog.objects.get(field_name="sport_type")
    assert entry.new_value == "Футбол"


@pytest.mark.django_db
def test_unknown_sport_in_a_cell_is_refused_in_words(api, nurlybek, student):
    api.force_authenticate(nurlybek)
    answer = api.post(
        "/api/batch/save/",
        {
            "changes": [
                {
                    "student": student.pk,
                    "model": "students.SportProfile",
                    "field": "sport_type",
                    "value": "Кёрлинг",
                }
            ]
        },
        format="json",
    ).json()

    assert answer["applied"] == 0
    assert "нет в справочнике" in answer["rejected"][0]["reason"]
