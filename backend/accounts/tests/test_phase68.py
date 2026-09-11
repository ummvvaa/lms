"""Фаза 68: администратор видит и правит все домены.

Решение владельца, согласованное со школой. Проверяем не «администратору
всё можно», а три вещи, из-за которых это право опасно:

* право задано в реестре одним местом, и каждая правка помечена
  в журнале — владелец домена видит, что значение внёс не он;
* граница «ученик вносит, школа подтверждает» не сдвинулась:
  предложения о себе, документы и анкету администратор за ученика
  не делает — эти маршруты закрыты ему с причиной;
* страж по маршрутам: всё, что отвечает администратору 403, обязано
  быть в списке закрытого с причиной. Тихий отказ — дефект.
"""

from __future__ import annotations

import pytest
from django.urls import get_resolver
from rest_framework.test import APIClient

from accounts.models import Role
from accounts.permissions import ADMIN_CLOSED_ROUTES, ADMIN_CLOSED_WRITES, ADMIN_GATE_MESSAGE
from core.models import AuditLog
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, email="admin.phase68@example.kz", full_name="Администратор")


@pytest.fixture
def group(db):
    return StudyGroup.objects.create(code="CHICAGO", grade=11)


@pytest.fixture
def learner(group):
    student = Student.objects.create(
        last_name="Сериков",
        first_name="Данияр",
        email="serikov.phase68@school.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=student)
    return student


@pytest.fixture
def as_admin(admin) -> APIClient:
    # вход сессией, а не `force_authenticate`: шлюз стоит в middleware и видит
    # только опознанного Django пользователя
    client = APIClient()
    client.force_login(admin)
    return client


# --- Право в реестре и пометка в журнале ------------------------------------------


def test_the_right_lives_in_the_registry():
    from core.domains import ADMIN_WRITES_ALL_DOMAINS, DOMAINS, can_write

    assert ADMIN_WRITES_ALL_DOMAINS is True
    for domain in DOMAINS.values():
        for model in domain.models:
            for spec in model.fields:
                assert can_write(Role.ADMIN, model.label, spec.name), f"{model.label}.{spec.name}"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path, field, value, code",
    [
        ("/api/profiles/behavior/{pk}/", "attendance_percent", 91, "behavior"),
        ("/api/profiles/admission/{pk}/", "target_country", "Канада", "admission"),
        ("/api/profiles/exam/{pk}/", "ielts_target", "7.5", "exam"),
        ("/api/profiles/talent/{pk}/", "comment", "Готовит проект", "talent"),
        ("/api/profiles/sport/{pk}/", "rank", "КМС", "sport"),
    ],
)
def test_admin_edits_every_domain_and_the_journal_says_so(as_admin, learner, admin, path, field, value, code):
    """Правка в каждом домене проходит и помечена «правил администратор»."""
    response = as_admin.patch(path.format(pk=learner.pk), {field: value}, format="json")
    assert response.status_code == 200, response.data

    entry = AuditLog.objects.filter(field_name=field, student_id=learner.pk).latest("id")
    assert entry.actor_id == admin.pk
    assert entry.acting_for == code

    history = as_admin.get(f"/api/students/{learner.pk}/history/").json()
    row = next(r for r in history if r["field_title"] and r["acting_for"] == code)
    assert "правил администратор" in row["acting_for_title"]


@pytest.mark.django_db
def test_admin_edits_are_marked_in_the_digest_of_the_owner(as_admin, learner, make_user):
    """Владелец домена видит в дайджесте, что значение внёс администратор (D6)."""
    as_admin.patch(f"/api/profiles/exam/{learner.pk}/", {"ielts_target": "7.0"}, format="json")

    kymbat = APIClient()
    kymbat.force_authenticate(make_user(Role.DIRECTOR_EXAM, email="kymbat.phase68@example.kz"))
    digest = kymbat.get("/api/digest/").json()
    row = next(r for r in digest["recent"] if r["field_title"])
    assert row["actor_name"]
    assert "правил администратор" in row["acting_for_title"]


@pytest.mark.django_db
def test_admin_confirms_but_does_not_propose(as_admin, learner):
    """Подтверждать и править — да; вносить первичное за ученика — нет."""
    refused = as_admin.post(
        "/api/suggestions/propose/",
        {"rows": [{"model": "students.ExamProfile", "field": "ielts_current", "value": "7.0"}]},
        format="json",
    )
    assert refused.status_code == 403
    assert ADMIN_GATE_MESSAGE in refused.json()["detail"]


@pytest.mark.django_db
def test_admin_does_not_upload_documents_for_a_student(as_admin, learner):
    from django.core.files.uploadedfile import SimpleUploadedFile

    refused = as_admin.post(
        "/api/documents/",
        {"student": learner.pk, "doc_type": "passport", "file": SimpleUploadedFile("p.pdf", b"%PDF-1.4")},
        format="multipart",
    )
    assert refused.status_code == 403


# --- Страж по маршрутам --------------------------------------------------------------


def _api_routes():
    import re

    def walk(resolver, prefix=""):
        for pattern in resolver.url_patterns:
            if hasattr(pattern, "url_patterns"):
                yield from walk(pattern, prefix + str(pattern.pattern))
            else:
                yield prefix + str(pattern.pattern), pattern.name

    for raw, name in walk(get_resolver()):
        if not raw.startswith("api/") or raw.startswith(("api/schema", "api/docs")):
            continue
        if "\\." in raw:
            continue
        path = "/" + re.sub(r"\(\?P<\w+>[^)]*\)", "1", raw)
        path = re.sub(r"<(?:\w+:)?\w+>", "1", path)
        path = re.sub(r"[\^$]", "", path)
        yield path, name


@pytest.mark.django_db
def test_every_api_route_is_either_open_or_closed_to_the_admin(as_admin):
    """Страж: маршрут, отвечающий администратору 403, обязан быть в списке с причиной.

    Обходим все маршруты `/api/` с заглушками параметров. Открытый
    маршрут не отвечает 403; закрытый — отвечает 403 от шлюза и назван
    в `ADMIN_CLOSED_ROUTES` с причиной. Ни одного 500 и ни одного тихого
    403 у маршрута, о котором список не знает.
    """
    silent: list[tuple[str, str, int]] = []
    seen = 0
    for path, name in _api_routes():
        response = as_admin.get(path)
        seen += 1
        assert response.status_code < 500, (path, name, response.status_code)
        if name in ADMIN_CLOSED_ROUTES:
            assert response.status_code == 403, (path, name, response.status_code)
            assert ADMIN_GATE_MESSAGE in response.content.decode(), path
        elif response.status_code == 403:
            silent.append((path, name or "", response.content.decode()[:80]))
    assert seen > 100
    assert not silent, "тихие 403 администратору:\n" + "\n".join(f"  {n} {p} — {t}" for p, n, t in silent)


@pytest.mark.django_db
def test_write_only_closures_keep_reading_open(as_admin):
    """Список документов и эссе администратор читает, а вносит их ученик."""
    routes = dict(_api_routes())
    by_name = {name: path for path, name in routes.items()}
    for name, reason in ADMIN_CLOSED_WRITES.items():
        path = by_name[name]
        assert as_admin.get(path).status_code != 403, name
        refused = as_admin.post(path, {}, format="json")
        assert refused.status_code == 403, name
        assert reason in refused.json()["detail"], name


def test_the_closed_list_names_only_real_routes():
    names = {name for _path, name in _api_routes()}
    for name in (*ADMIN_CLOSED_ROUTES, *ADMIN_CLOSED_WRITES):
        assert name in names, f"в списке закрытого нет такого маршрута: {name}"


def test_every_closed_route_has_a_reason():
    for name, reason in ADMIN_CLOSED_ROUTES.items():
        assert reason.strip(), name
