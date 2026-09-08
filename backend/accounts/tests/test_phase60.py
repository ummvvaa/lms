"""Фаза 60: роль куратора — модель, права, очередь.

Матрица прав из задания, каждая клетка — минимум одним тестом. Куратор
ходит через сессию (`force_login`), а не `force_authenticate`: шлюз
маршрутов стоит в middleware, и минуя его тесты доказывали бы не то.

| Что                                   | своя группа                    | чужая группа |
| карточка ученика целиком              | читает (с ярлыками)            | 404          |
| очередь в доменах куратора            | видит, решает, правит, отклоняет | не видит   |
| очередь в остальных доменах           | не видит                       | не видит     |
| внесение данных за ученика            | нет                            | нет          |
| справочники                           | 403                            | 403          |
| внутренние метки и заметки директоров | читает                         | 404          |
| список групп и учеников               | только свои                    | нет          |
| настройки, пользователи, архив        | нет                            | нет          |
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import get_resolver
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.curators import AssignmentRefused, active_assignments, assign, curated_group_ids
from accounts.models import CuratorAssignment, Role, User
from accounts.permissions import (
    CURATOR_READ_ROUTES,
    CURATOR_SESSION_ROUTES,
    CURATOR_WRITE_ROUTES,
    curator_may,
)
from core.domains import CURATOR_DOMAINS, DOMAINS, ROLE_TITLES, curator_confirms, domain_of_role, domains_of_role
from core.models import AuditLog
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    StudentDocument,
    StudyGroup,
    TalentProfile,
)
from suggestions.models import Suggestion, SuggestionStatus

PDF = b"%PDF-1.4\n%test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
CURATOR_NAME = "Асель Куратор"
IELTS_ROW = {"model": "students.ExamProfile", "field": "ielts_current", "value": "7.0"}
COUNTRY_ROW = {"model": "students.AdmissionProfile", "field": "target_country", "value": "Канада"}


# --- Фикстуры: две группы, по ученику в каждой, куратор одной из них -------


def _student(email: str, group: StudyGroup, last_name: str) -> Student:
    s = Student.objects.create(
        last_name=last_name, first_name="Ученик", email=email, grade=11, group=group, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=s)
    return s


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def chicago(db) -> StudyGroup:
    return StudyGroup.objects.create(code="CHICAGO", grade=11, curator="Асель")


@pytest.fixture
def boston(db) -> StudyGroup:
    return StudyGroup.objects.create(code="BOSTON", grade=11)


@pytest.fixture
def mine(chicago) -> Student:
    """Ученик из группы куратора; в поле «статус» — внутренний ярлык."""
    s = _student("mine60@example.kz", chicago, "Свой")
    s.behavior.status = "needs_supervision"
    s.behavior.comment = "заметка директора школы"
    s.behavior.save()
    return s


@pytest.fixture
def foreign(boston) -> Student:
    return _student("foreign60@example.kz", boston, "Чужой")


@pytest.fixture
def mine_user(make_user, mine) -> User:
    user = make_user("student", mine.email, full_name="Свой Ученик")
    mine.user = user
    mine.save(update_fields=["user"])
    return user


@pytest.fixture
def foreign_user(make_user, foreign) -> User:
    user = make_user("student", foreign.email, full_name="Чужой Ученик")
    foreign.user = user
    foreign.save(update_fields=["user"])
    return user


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin", "admin60@example.kz", full_name="Администратор", is_staff=True)


@pytest.fixture
def kymbat(make_user) -> User:
    return make_user("director_exam", "kymbat60@example.kz", full_name="Кымбат")


@pytest.fixture
def asem(make_user) -> User:
    return make_user("director_admission", "asem60@example.kz", full_name="Асем")


@pytest.fixture
def curator(make_user, chicago, admin) -> User:
    user = make_user("curator", "curator60@example.kz", full_name=CURATOR_NAME)
    assign(group=chicago, curator=user, since=timezone.localdate() - dt.timedelta(days=30), actor=admin)
    return user


@pytest.fixture
def as_curator(api, curator) -> APIClient:
    api.force_login(curator)
    return api


def propose(_api, user, rows):
    """Ученик подаёт предложение — своим клиентом, чтобы не делить сессию с куратором."""
    client = APIClient()
    client.force_login(user)
    response = client.post("/api/suggestions/propose/", {"rows": rows}, format="json")
    assert response.status_code == 201, response.content
    return response.json()["suggestions"][0]


def upload(_api, user) -> int:
    client = APIClient()
    client.force_login(user)
    payload = {"doc_type": "passport", "file": SimpleUploadedFile("scan.pdf", PDF, "application/pdf")}
    response = client.post("/api/documents/", payload, format="multipart")
    assert response.status_code == 201, response.content
    return response.json()["id"]


# --- Реестр: роль, домен документов, домены куратора ------------------------


def test_curator_is_a_role_without_a_domain():
    assert Role.CURATOR == "curator"
    assert ROLE_TITLES["curator"] == "Куратор"
    assert domain_of_role("curator") is None
    assert domains_of_role("curator") == []


def test_documents_domain_belongs_to_asem_and_has_no_profile():
    """Документы заведены доменом (фаза 60): владелец — директор по поступлению."""
    domain = DOMAINS["documents"]
    assert domain.role == "director_admission"
    assert domain.owner_name == "Асем"
    assert domain.model("students.StudentDocument") is not None
    # основной домен Асем не сменился
    assert domain_of_role("director_admission").code == "admission"


def test_curator_domains_are_exam_and_documents():
    assert CURATOR_DOMAINS == ("exam", "documents")
    assert curator_confirms("exam") and curator_confirms("documents")
    assert not curator_confirms("admission") and not curator_confirms("behavior")


# --- Назначение ---------------------------------------------------------------


def test_one_active_curator_per_group_and_history_is_kept(db, chicago, make_user, admin):
    first = make_user("curator", "first60@example.kz", full_name="Первая")
    second = make_user("curator", "second60@example.kz", full_name="Вторая")
    start = timezone.localdate() - dt.timedelta(days=60)
    change = timezone.localdate() - dt.timedelta(days=5)

    assign(group=chicago, curator=first, since=start, actor=admin)
    assert curated_group_ids(first) == [chicago.pk]

    assign(group=chicago, curator=second, since=change, actor=admin)
    rows = list(CuratorAssignment.objects.filter(group=chicago).order_by("since"))
    assert [r.curator for r in rows] == [first, second]
    # старая запись закрыта датой смены, не удалена
    assert rows[0].until == change and rows[1].until is None
    assert curated_group_ids(first) == []
    assert curated_group_ids(second) == [chicago.pk]
    assert active_assignments().filter(group=chicago).count() == 1


def test_assignment_refusals(db, chicago, make_user, admin, kymbat):
    curator = make_user("curator", "one60@example.kz")
    assign(group=chicago, curator=curator, since=timezone.localdate(), actor=admin)
    with pytest.raises(AssignmentRefused, match="уже ведёт"):
        assign(group=chicago, curator=curator, since=timezone.localdate(), actor=admin)
    other = make_user("curator", "two60@example.kz")
    with pytest.raises(AssignmentRefused, match="не раньше"):
        assign(group=chicago, curator=other, since=timezone.localdate() - dt.timedelta(days=1), actor=admin)
    with pytest.raises(AssignmentRefused, match="Куратор"):
        assign(group=chicago, curator=kymbat, since=timezone.localdate(), actor=admin)


def test_future_assignment_is_not_active_yet(db, chicago, make_user, admin):
    curator = make_user("curator", "later60@example.kz")
    assign(group=chicago, curator=curator, since=timezone.localdate() + dt.timedelta(days=1), actor=admin)
    assert curated_group_ids(curator) == []
    assert curated_group_ids(curator, on=timezone.localdate() + dt.timedelta(days=1)) == [chicago.pk]


def test_admin_assigns_and_changes_through_the_api(api, admin, chicago, make_user):
    one = make_user("curator", "api-one60@example.kz", full_name="Одна")
    two = make_user("curator", "api-two60@example.kz", full_name="Другая")
    api.force_login(admin)

    # подсказка «по записи», пока назначения нет
    row = api.get(f"/api/groups/{chicago.pk}/").json()
    assert row["curator_user"] is None and row["curator_hint"] == "Асель"

    since = str(timezone.localdate() - dt.timedelta(days=10))
    made = api.post(
        "/api/curator-assignments/", {"group": chicago.pk, "curator": one.pk, "since": since}, format="json"
    )
    assert made.status_code == 201, made.data
    row = api.get(f"/api/groups/{chicago.pk}/").json()
    assert row["curator_user"]["full_name"] == "Одна" and row["curator_hint"] == ""

    changed = api.post(
        "/api/curator-assignments/",
        {"group": chicago.pk, "curator": two.pk, "since": str(timezone.localdate())},
        format="json",
    )
    assert changed.status_code == 201
    history = api.get(f"/api/curator-assignments/?group={chicago.pk}").json()["results"]
    assert [h["curator_name"] for h in history] == ["Другая", "Одна"]
    assert history[1]["until"] == str(timezone.localdate()) and history[0]["is_active"]

    refused = api.post(
        "/api/curator-assignments/",
        {"group": chicago.pk, "curator": two.pk, "since": str(timezone.localdate())},
        format="json",
    )
    assert refused.status_code == 400 and "уже ведёт" in refused.data["detail"]

    curators = api.get("/api/curators/").json()
    by_email = {row["email"]: row for row in curators["results"]}
    assert [g["code"] for g in by_email[two.email]["groups"]] == ["CHICAGO"]
    assert by_email[one.email]["groups"] == []


def test_assignments_are_admin_only(api, kymbat, curator, chicago):
    for user in (kymbat, curator):
        api.force_login(user)
        assert api.get("/api/curator-assignments/").status_code == 403
        assert api.get("/api/curators/").status_code == 403
        made = api.post(
            "/api/curator-assignments/",
            {"group": chicago.pk, "curator": curator.pk, "since": str(timezone.localdate())},
            format="json",
        )
        assert made.status_code == 403


# --- Текстовое поле куратора у группы: только на чтение ------------------------


def test_group_curator_text_field_cannot_be_changed_via_api(api, admin, chicago):
    api.force_login(admin)
    response = api.patch(f"/api/groups/{chicago.pk}/", {"curator": "Кто-то"}, format="json")
    assert response.status_code == 400 and "Пользователи" in response.data["detail"]
    chicago.refresh_from_db()
    assert chicago.curator == "Асель"
    # остальное правится как раньше
    assert api.patch(f"/api/groups/{chicago.pk}/", {"grade": 10}, format="json").status_code == 200
    made = api.post("/api/groups/", {"code": "TOKYO", "grade": 11, "curator": "X"}, format="json")
    assert made.status_code == 400
    assert api.post("/api/groups/", {"code": "TOKYO", "grade": 11}, format="json").status_code == 201


# --- Матрица: карточка ученика целиком, чужая группа — 404 ---------------------


def test_curator_reads_own_students_card_with_internal_labels(as_curator, mine, foreign):
    card = as_curator.get(f"/api/students/{mine.pk}/")
    assert card.status_code == 200
    body = card.json()
    # все пять доменов и внутренние ярлыки: фильтр — по роли `student`, не «не директор»
    assert set(body) >= {"behavior", "admission", "exam", "talent", "sport"}
    assert body["behavior"]["status"] == "needs_supervision"
    assert body["behavior"]["comment"] == "заметка директора школы"
    assert as_curator.get(f"/api/students/{mine.pk}/history/").status_code == 200
    assert as_curator.get(f"/api/students/{mine.pk}/readiness/").status_code == 200
    for domain in ("behavior", "admission", "exam", "talent", "sport"):
        assert as_curator.get(f"/api/profiles/{domain}/{mine.pk}/").status_code == 200, domain

    # чужая группа — 404 везде, чтобы не выдать, что ученик существует
    assert as_curator.get(f"/api/students/{foreign.pk}/").status_code == 404
    assert as_curator.get(f"/api/students/{foreign.pk}/history/").status_code == 404
    assert as_curator.get(f"/api/students/{foreign.pk}/readiness/").status_code == 404
    for domain in ("behavior", "admission", "exam", "talent", "sport"):
        assert as_curator.get(f"/api/profiles/{domain}/{foreign.pk}/").status_code == 404, domain


def test_curator_lists_only_own_groups_and_students(as_curator, mine, foreign, chicago, boston):
    students = as_curator.get("/api/students/?page_size=100").json()
    assert {row["id"] for row in students["results"]} == {mine.pk}
    # фильтр по чужой группе не открывает её
    assert as_curator.get("/api/students/?group=BOSTON").json()["count"] == 0
    groups = as_curator.get("/api/groups/").json()
    assert [g["code"] for g in groups["results"]] == ["CHICAGO"]
    assert as_curator.get(f"/api/groups/{boston.pk}/").status_code == 404
    assert as_curator.get(f"/api/groups/{chicago.pk}/").status_code == 200


def test_child_rows_and_documents_follow_the_same_border(as_curator, api, mine, foreign, mine_user, foreign_user):
    own_doc = upload(api, mine_user)
    foreign_doc = upload(api, foreign_user)
    as_curator.force_login(User.objects.get(email="curator60@example.kz"))

    docs = as_curator.get("/api/documents/?page_size=100").json()
    assert {row["id"] for row in docs["results"]} == {own_doc}
    assert as_curator.get(f"/api/documents/?student={foreign.pk}").json()["count"] == 0
    assert as_curator.get(f"/api/documents/{own_doc}/file/").status_code == 200
    assert as_curator.get(f"/api/documents/{foreign_doc}/file/").status_code == 404

    for path in ("attempts", "activities", "competitions", "contacts", "exam-goals", "tasks", "essays"):
        listing = as_curator.get(f"/api/{path}/?student={foreign.pk}")
        assert listing.status_code == 200, path
        assert listing.json()["count"] == 0, path


# --- Матрица: внесение данных за ученика — нет ----------------------------------


def test_curator_writes_nothing(as_curator, mine, chicago):
    assert (
        as_curator.patch(f"/api/profiles/exam/{mine.pk}/", {"ielts_current": "8.0"}, format="json").status_code == 403
    )
    assert as_curator.post("/api/batch/save/", {"changes": []}, format="json").status_code == 403
    assert (
        as_curator.post(
            "/api/attempts/",
            {"student": mine.pk, "exam_type": "IELTS", "attempt_format": "mock", "date": "2026-09-01"},
            format="json",
        ).status_code
        == 403
    )
    assert as_curator.post("/api/documents/", {"doc_type": "passport"}, format="json").status_code == 403
    assert as_curator.patch(f"/api/students/{mine.pk}/", {"grade": 10}, format="json").status_code == 403
    assert as_curator.patch(f"/api/groups/{chicago.pk}/", {"grade": 10}, format="json").status_code == 403
    assert as_curator.post("/api/suggestions/propose/", {"rows": [IELTS_ROW]}, format="json").status_code == 403
    ExamProfile.objects.get(student=mine).refresh_from_db()
    assert ExamProfile.objects.get(student=mine).ielts_current is None


# --- Матрица: справочники, настройки, пользователи, архив — 403 ------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/prep/theory/",
        "/api/prep/questions/",
        "/api/prep/mocks/",
        "/api/prep/bank/",
        "/api/exam-kinds/",
        "/api/subjects/",
        "/api/sport-types/",
        "/api/universities/",
        "/api/programs/",
        "/api/requirements/",
        "/api/task-templates/",
        "/api/resources/",
        "/api/call-rules/",
        "/api/home-cues/",
        "/api/users/",
        "/api/archive/",
        "/api/imports/",
        "/api/llm/spend/",
        "/api/dashboards/exam/",
        "/api/dashboards/overview/",
        "/api/digest/",
        "/api/search/?q=а",
        "/api/commands/",
        "/api/olympiad-group/",
        "/api/exam-goals/attention/",
        "/api/students/me/",
    ],
)
def test_directories_and_settings_are_closed_to_the_curator(as_curator, path):
    response = as_curator.get(path)
    assert response.status_code == 403, (path, response.status_code)
    assert "куратору не открыт" in response.json()["detail"]


def test_every_api_route_is_either_allowed_or_closed_to_the_curator(as_curator):
    """Страж: новый маршрут без записи в шлюзе закрыт куратору сам по себе.

    Обходим все маршруты `/api/` с заглушками параметров и требуем: либо
    имя в списке открытого, либо 403 от шлюза. Ни одного 500 и ни одного
    тихого 200 у маршрута, о котором шлюз не знает.
    """
    seen = 0
    for path, name in _api_routes():
        response = as_curator.get(path)
        seen += 1
        if name in CURATOR_READ_ROUTES or name in CURATOR_SESSION_ROUTES:
            assert response.status_code != 403 or "куратору не открыт" not in response.content.decode(), path
        else:
            assert response.status_code == 403, (path, name, response.status_code)
            assert "куратору не открыт" in response.content.decode(), path
        assert response.status_code < 500, path
    assert seen > 100


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
        # суффиксы формата роутера (`\.json`) обходу не нужны
        if "\\." in raw:
            continue
        # сначала группы регулярных выражений роутера, потом `<int:pk>` обычных путей
        path = "/" + re.sub(r"\(\?P<\w+>[^)]*\)", "1", raw)
        path = re.sub(r"<(?:\w+:)?\w+>", "1", path)
        path = re.sub(r"[\^$]", "", path)
        yield path, name


def test_the_gate_lists_no_route_that_does_not_exist():
    """Имя в списке шлюза без маршрута — опечатка, которая открывала бы ничего."""
    names = {name for _path, name in _api_routes()}
    unknown = (CURATOR_READ_ROUTES | CURATOR_WRITE_ROUTES | CURATOR_SESSION_ROUTES) - names
    assert not unknown, unknown
    assert curator_may("auth-logout", "POST") and not curator_may("users", "GET")
    # блокировки входа — экран администратора, хоть имя и начинается с `auth-`
    assert not curator_may("auth-locks", "GET") and not curator_may("auth-unlock", "POST")
    assert not curator_may("student-list", "POST") and curator_may("suggestion-review", "POST")


# --- Матрица: очередь в доменах куратора ---------------------------------------


def test_curator_sees_queue_of_own_students_in_curator_domains_only(as_curator, api, mine_user, foreign_user, mine):
    own_exam = propose(api, mine_user, [IELTS_ROW])
    own_admission = propose(api, mine_user, [COUNTRY_ROW])
    foreign_exam = propose(api, foreign_user, [IELTS_ROW])
    as_curator.force_login(User.objects.get(email="curator60@example.kz"))

    queue = as_curator.get("/api/suggestions/from-students/").json()["results"]
    assert [row["id"] for row in queue] == [own_exam]
    listing = as_curator.get("/api/suggestions/").json()
    assert {row["id"] for row in listing["results"]} == {own_exam}
    # чужой ученик и чужой домен — 404, не 403
    for pk in (own_admission, foreign_exam):
        assert as_curator.get(f"/api/suggestions/{pk}/").status_code == 404
        assert (
            as_curator.post(f"/api/suggestions/{pk}/review/", {"decision": "confirm"}, format="json").status_code == 404
        )
        assert as_curator.post(f"/api/suggestions/{pk}/reject/", {"reason": "нет"}, format="json").status_code == 404
    # массовое подтверждение молча пропускает чужое
    confirmed = as_curator.post(
        "/api/suggestions/from-students/confirm/", {"suggestions": [own_admission, foreign_exam]}, format="json"
    )
    assert confirmed.status_code == 200 and confirmed.json()["confirmed"] == 0
    assert Suggestion.objects.get(pk=foreign_exam).status == SuggestionStatus.PENDING


def test_curator_confirms_and_the_journal_names_role_and_group(as_curator, api, mine_user, mine, curator):
    pk = propose(api, mine_user, [IELTS_ROW])
    as_curator.force_login(curator)
    done = as_curator.post(f"/api/suggestions/{pk}/review/", {"decision": "confirm"}, format="json")
    assert done.status_code == 200 and done.json()["applied"] == 1
    mine.exam.refresh_from_db()
    assert str(mine.exam.ielts_current) == "7.0"

    entry = AuditLog.objects.get(suggestion_id=pk, field_name="ielts_current")
    assert entry.actor == curator and entry.actor_role == "curator" and entry.student_group == "CHICAGO"
    suggestion = Suggestion.objects.get(pk=pk)
    assert suggestion.resolved_by == curator and suggestion.resolved_role == "curator"

    # и то же самое видно в истории карточки, а не только в базе
    row = next(
        item
        for item in as_curator.get(f"/api/students/{mine.pk}/history/").json()
        if item["field_title"].startswith("Текущий балл IELTS")
    )
    assert row["actor_name"] == CURATOR_NAME
    assert row["actor_role_title"] == "Куратор"
    assert row["student_group"] == "CHICAGO"


def test_curator_edits_then_confirms(as_curator, api, mine_user, mine):
    pk = propose(api, mine_user, [IELTS_ROW])
    change = Suggestion.objects.get(pk=pk).changes.get()
    as_curator.force_login(User.objects.get(email="curator60@example.kz"))
    done = as_curator.post(
        f"/api/suggestions/{pk}/review/", {"decision": "confirm", "values": {str(change.pk): "6.5"}}, format="json"
    )
    assert done.status_code == 200
    mine.exam.refresh_from_db()
    assert str(mine.exam.ielts_current) == "6.5"


def test_curator_declines_only_with_a_reason_same_code_as_director(as_curator, api, mine_user, mine, kymbat):
    pk = propose(api, mine_user, [IELTS_ROW])
    as_curator.force_login(User.objects.get(email="curator60@example.kz"))
    for body in ({"decision": "decline"}, {"decision": "decline", "reason": "  "}):
        assert as_curator.post(f"/api/suggestions/{pk}/review/", body, format="json").status_code == 400
    assert as_curator.post(f"/api/suggestions/{pk}/reject/", {"reason": ""}, format="json").status_code == 400
    assert Suggestion.objects.get(pk=pk).status == SuggestionStatus.PENDING

    done = as_curator.post(
        f"/api/suggestions/{pk}/review/",
        {"decision": "decline", "reason": "Скан сертификата не приложен"},
        format="json",
    )
    assert done.status_code == 200 and done.json()["reject_reason"] == "Скан сертификата не приложен"

    # директор идёт тем же кодом: тот же 400 без причины
    second = propose(api, mine_user, [IELTS_ROW])
    as_curator.force_login(kymbat)
    assert (
        as_curator.post(f"/api/suggestions/{second}/review/", {"decision": "decline"}, format="json").status_code == 400
    )


def test_curator_does_not_revert_or_accept_above_threshold(as_curator, api, mine_user, mine):
    pk = propose(api, mine_user, [IELTS_ROW])
    as_curator.force_login(User.objects.get(email="curator60@example.kz"))
    assert as_curator.post(f"/api/suggestions/{pk}/revert/", {}, format="json").status_code == 403
    assert as_curator.post(f"/api/suggestions/{pk}/accept-above/", {"threshold": 0.5}, format="json").status_code == 403


# --- Очередь общая: первый подтверждает, второй получает 409 --------------------


def test_second_decision_gets_409_with_who_and_when(as_curator, api, mine_user, mine, kymbat, curator):
    pk = propose(api, mine_user, [IELTS_ROW])
    as_curator.force_login(curator)
    assert as_curator.post(f"/api/suggestions/{pk}/review/", {"decision": "confirm"}, format="json").status_code == 200

    as_curator.force_login(kymbat)
    again = as_curator.post(f"/api/suggestions/{pk}/review/", {"decision": "confirm"}, format="json")
    assert again.status_code == 409
    body = again.json()
    assert body["detail"].startswith("Уже подтверждено")
    assert CURATOR_NAME in body["detail"] and "Куратор" in body["detail"]
    assert timezone.localdate().strftime("%d.%m.%Y") in body["detail"]
    assert body["suggestion"]["id"] == pk and body["suggestion"]["status"] == "applied"
    assert body["suggestion"]["resolved_by_name"] == CURATOR_NAME
    # журнал — у первого, второй записи не оставил
    assert AuditLog.objects.filter(suggestion_id=pk).count() == 1
    assert AuditLog.objects.get(suggestion_id=pk).actor == curator

    # и отклонить решённое тоже нельзя
    declined = as_curator.post(
        f"/api/suggestions/{pk}/review/", {"decision": "decline", "reason": "нет"}, format="json"
    )
    assert declined.status_code == 409
    assert as_curator.post(f"/api/suggestions/{pk}/reject/", {"reason": "нет"}, format="json").status_code == 409


def test_director_first_then_curator_gets_409(as_curator, api, mine_user, mine, kymbat, curator):
    pk = propose(api, mine_user, [IELTS_ROW])
    as_curator.force_login(kymbat)
    assert as_curator.post(f"/api/suggestions/{pk}/review/", {"decision": "confirm"}, format="json").status_code == 200
    as_curator.force_login(curator)
    again = as_curator.post(f"/api/suggestions/{pk}/review/", {"decision": "confirm"}, format="json")
    assert again.status_code == 409 and "Кымбат" in again.json()["detail"]
    assert AuditLog.objects.get(suggestion_id=pk).actor == kymbat
    assert AuditLog.objects.get(suggestion_id=pk).actor_role == "director_exam"


def test_mass_confirm_skips_already_resolved_rows(as_curator, api, mine_user, mine, kymbat, curator):
    first = propose(api, mine_user, [IELTS_ROW])
    second = propose(api, mine_user, [{**IELTS_ROW, "value": "6.0"}])
    as_curator.force_login(kymbat)
    assert (
        as_curator.post(f"/api/suggestions/{first}/review/", {"decision": "confirm"}, format="json").status_code == 200
    )
    as_curator.force_login(curator)
    result = as_curator.post("/api/suggestions/from-students/confirm/", {"suggestions": [first, second]}, format="json")
    assert result.status_code == 200
    body = result.json()
    assert body["confirmed"] == 1 and [row["id"] for row in body["skipped"]] == [first]
    assert "Уже подтверждено" in body["skipped"][0]["detail"]


# --- Ученик ничего нового не видит: причина есть, имени куратора нет -------------


def test_student_sees_reason_but_never_the_curators_name(as_curator, api, mine_user, mine, curator):
    pk = propose(api, mine_user, [IELTS_ROW])
    as_curator.force_login(curator)
    reason = "Приложите скан сертификата"
    assert (
        as_curator.post(
            f"/api/suggestions/{pk}/review/", {"decision": "decline", "reason": reason}, format="json"
        ).status_code
        == 200
    )
    confirmed = propose(api, mine_user, [{**IELTS_ROW, "value": "6.5"}])
    assert (
        as_curator.post(f"/api/suggestions/{confirmed}/review/", {"decision": "confirm"}, format="json").status_code
        == 200
    )

    api = APIClient()
    api.force_login(mine_user)
    mine_rows = api.get("/api/suggestions/mine/")
    assert mine_rows.status_code == 200
    statuses = {row["id"]: row for row in mine_rows.json()["results"]}
    assert statuses[pk]["reject_reason"] == reason
    for path in ("/api/suggestions/mine/", "/api/students/me/", "/api/portfolio/", "/api/auth/me/", "/api/journey/"):
        body = api.get(path).content.decode()
        assert CURATOR_NAME not in body, path
        assert "Асель" not in body, path
        assert "curator60@example.kz" not in body, path
        assert "resolved_by" not in body, path
    # и по-прежнему без внутренних ярлыков (D27)
    me = api.get("/api/students/me/").json()
    assert "status" not in me["behavior"]
    assert api.get(f"/api/suggestions/{pk}/").status_code == 404


def test_student_visibility_did_not_widen(api, mine_user, foreign, mine):
    api.force_login(mine_user)
    assert api.get(f"/api/students/{foreign.pk}/").status_code == 404
    assert api.get("/api/students/").json()["count"] == 1
    assert api.get("/api/groups/").status_code == 200


# --- Кабинет-заглушка и остальные роли не тронуты ----------------------------------


def test_curator_cabinet_stub_lists_own_groups(as_curator, mine, chicago, api, mine_user):
    propose(api, mine_user, [IELTS_ROW])
    as_curator.force_login(User.objects.get(email="curator60@example.kz"))
    cabinet = as_curator.get("/api/cabinet/")
    assert cabinet.status_code == 200
    body = cabinet.json()
    assert body["title"] == "Кабинет куратора" and body["role"] == "curator"
    assert [g["code"] for g in body["groups"]] == ["CHICAGO"]
    assert body["groups"][0]["students"] == 1
    assert {s["code"]: s["value"] for s in body["stats"]} == {"groups": 1, "students": 1, "queue": 1}
    me = as_curator.get("/api/auth/me/").json()
    assert me["role"] == "curator" and me["role_title"] == "Куратор" and me["domain"] is None


def test_directors_and_admin_keep_their_rights(api, kymbat, asem, admin, mine, foreign, chicago):
    for user in (kymbat, asem, admin):
        api.force_login(user)
        assert api.get(f"/api/students/{foreign.pk}/").status_code == 200, user.role
        assert api.get("/api/students/").json()["count"] == 2, user.role
        assert api.get("/api/groups/").json()["count"] == 2, user.role
    api.force_login(kymbat)
    assert api.patch(f"/api/profiles/exam/{foreign.pk}/", {"ielts_current": "8.0"}, format="json").status_code == 200
    assert api.get("/api/prep/theory/").status_code == 200


# --- Документы: чтение куратором закрыто той же границей; подтверждение — фаза 62 ---


def test_curator_reads_documents_of_own_group_only(as_curator, api, mine_user, foreign_user, mine, foreign):
    own = upload(api, mine_user)
    other = upload(api, foreign_user)
    as_curator.force_login(User.objects.get(email="curator60@example.kz"))
    rows = as_curator.get(f"/api/documents/?student={mine.pk}").json()
    assert [row["id"] for row in rows["results"]] == [own]
    assert as_curator.get(f"/api/documents/{other}/file/").status_code == 404
    assert StudentDocument.objects.filter(pk=other).exists()


@pytest.mark.skip(reason="фаза 62: очередь подтверждения документов и статус «ждёт проверки / подтверждён / отклонён»")
def test_curator_confirms_a_document_of_own_group(as_curator, api, mine_user, mine):
    own = upload(api, mine_user)
    as_curator.force_login(User.objects.get(email="curator60@example.kz"))
    done = as_curator.post(f"/api/documents/{own}/review/", {"decision": "confirm"}, format="json")
    assert done.status_code == 200
