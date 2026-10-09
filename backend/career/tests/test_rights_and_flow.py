"""Права и путь профтеста: кто ведёт, кому открыт тест, прохождение, результаты, разбор.

* тесты ведёт учитель профориентации при любой роли и администратор; другой
  учитель, куратор без профориентации и Кымбат получают отказ словами;
* ученик видит только назначенные включённые тесты, в ответах нет ключа;
* одна попытка на тест, заново — только с разрешения учителя;
* результаты читают учитель, администратор, Асем и куратор своих групп;
* разбор идёт по шкалам выше порога, тот же набор попыток второй раз
  не разбирается, ученик видит разбор только после «Показать ученику».
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from career.models import AnalysisStatus, CareerAnalysis, CareerAttempt, CareerTest
from career.tests.conftest import FakeProvider, activate, answer_all, login

pytestmark = pytest.mark.django_db


def upload(client, data: bytes, *, preview: bool = False):
    path = "/api/career/tests/preview/" if preview else "/api/career/tests/"
    return client.post(path, {"file": SimpleUploadedFile("karta.xlsx", data)}, format="multipart")


# --- Кто ведёт ---------------------------------------------------------------------


def test_only_career_teacher_and_admin_upload(teacher, other_teacher, curator, kymbat, admin, example_bytes):
    assert upload(login(teacher), example_bytes, preview=True).status_code == 200
    assert upload(login(admin), example_bytes).status_code == 201
    for user in (other_teacher, curator, kymbat):
        response = upload(login(user), example_bytes)
        assert response.status_code == 403, user.role
        assert "учитель профориентации" in response.json()["detail"]
    assert CareerTest.objects.count() == 1


def test_me_tells_the_menu_who_manages(teacher, other_teacher, admin, curator):
    for user, expected in ((teacher, True), (admin, True), (other_teacher, False), (curator, False)):
        assert login(user).get("/api/auth/me/").json()["career_tests"] is expected, user.email


def test_broken_file_is_refused_with_report(teacher):
    response = upload(login(teacher), b"not a workbook")
    assert response.status_code == 400
    assert response.json()["errors"] == ["Файл не читается как книга xlsx"]
    assert CareerTest.objects.count() == 0


def test_test_detail_keeps_the_key_and_the_file(karta, teacher):
    client = login(teacher)
    detail = client.get(f"/api/career/tests/{karta.pk}/").json()
    assert len(detail["items"]) == 144 and detail["items"][0]["scale"] == "bio"
    assert detail["is_active"] is False and detail["groups"] == []
    assert client.get(f"/api/career/tests/{karta.pk}/file/").status_code == 200
    assert client.get("/api/career/tests/template/").status_code == 200


def test_assignment_only_to_own_groups(karta, teacher, boston, riga, pupils, admin):
    client = login(teacher)
    other = type(boston).objects.create(code="OSAKA", parallel=10)
    response = client.put(
        f"/api/career/tests/{karta.pk}/assignments/", {"groups": [{"group": other.pk}]}, format="json"
    )
    assert response.status_code == 400
    response = client.put(
        f"/api/career/tests/{karta.pk}/assignments/",
        {"groups": [{"group": boston.pk, "students": None}, {"group": riga.pk, "students": [pupils["nurai"].pk]}]},
        format="json",
    )
    assert response.status_code == 200
    groups = {row["code"]: row for row in response.json()["groups"]}
    assert groups["BOSTON"]["whole"] is True and groups["RIGA"]["students"] == [pupils["nurai"].pk]
    # администратор назначает любой группе
    assert (
        login(admin)
        .put(f"/api/career/tests/{karta.pk}/assignments/", {"groups": [{"group": other.pk}]}, format="json")
        .status_code
        == 200
    )


# --- Ученик -------------------------------------------------------------------------


def test_student_sees_only_assigned_and_active_tests(karta, teacher, boston, riga, pupils):
    aliya, nurai = login(pupils["aliya"].user), login(pupils["nurai"].user)
    assert aliya.get("/api/career/my/").json()["tests"] == []
    activate(karta, [{"group": boston.pk}], by=teacher)
    assert [t["id"] for t in aliya.get("/api/career/my/").json()["tests"]] == [karta.pk]
    assert nurai.get("/api/career/my/").json()["tests"] == [], "RIGA не назначали"
    assert nurai.post(f"/api/career/my/tests/{karta.pk}/start/").status_code == 404
    # выключили — ученик теста не видит, но начатое ему не стереть
    login(teacher).patch(f"/api/career/tests/{karta.pk}/", {"is_active": False}, format="json")
    assert aliya.get("/api/career/my/").json()["tests"] == []


def test_junior_student_is_not_stopped_by_the_parallel_gate(karta, teacher, riga, pupils):
    activate(karta, [{"group": riga.pk, "students": [pupils["nurai"].pk]}], by=teacher)
    nurai = login(pupils["nurai"].user)
    response = nurai.get("/api/career/my/")
    assert response.status_code == 200 and [t["id"] for t in response.json()["tests"]] == [karta.pk]


def test_student_takes_the_test_and_gets_bars(karta, teacher, boston, pupils):
    activate(karta, [{"group": boston.pk}], by=teacher)
    client = login(pupils["aliya"].user)
    started = client.post(f"/api/career/my/tests/{karta.pk}/start/").json()
    attempt = started["id"]
    assert started["status"] == "in_progress" and len(started["items"]) == 144
    assert "scale" not in started["items"][0] and "sign" not in started["items"][0], "ключ ученику не отдаётся"
    # та же попытка при повторном старте
    assert client.post(f"/api/career/my/tests/{karta.pk}/start/").json()["id"] == attempt
    # не всё отвечено — сдать нельзя
    options = {o["label"]: o["id"] for o in started["options"]}
    client.post(
        f"/api/career/my/attempts/{attempt}/answers/",
        {"answers": [{"item": started["items"][0]["id"], "option": options["++"]}]},
        format="json",
    )
    refused = client.post(f"/api/career/my/attempts/{attempt}/finish/")
    assert refused.status_code == 400 and "143" in refused.json()["detail"]
    # биология — «++», физика — «−−», остальное «0»
    answer_all(client, attempt, lambda n: {1: "++", 2: "−−"}.get((n - 1) % 24 + 1, "0"))
    finished = client.post(f"/api/career/my/attempts/{attempt}/finish/").json()
    assert finished["status"] == "done"
    scores = finished["scores"]
    assert (
        scores[0]["title"] == "Биология"
        and scores[0]["score"] == 12
        and scores[0]["low"] == -12
        and scores[0]["high"] == 12
    )
    assert scores[-1]["title"] == "Физика" and scores[-1]["score"] == -12
    # в списке тест сдан, ответы после сдачи не принимаются
    mine = client.get("/api/career/my/").json()["tests"][0]
    assert mine["status"] == "done" and mine["attempt"] == attempt
    assert client.post(f"/api/career/my/attempts/{attempt}/answers/", {"answers": []}, format="json").status_code == 400


def test_one_attempt_until_the_teacher_allows_a_retake(karta, teacher, boston, pupils):
    activate(karta, [{"group": boston.pk}], by=teacher)
    client = login(pupils["aliya"].user)
    attempt = client.post(f"/api/career/my/tests/{karta.pk}/start/").json()["id"]
    answer_all(client, attempt, lambda n: "+")
    client.post(f"/api/career/my/attempts/{attempt}/finish/")
    assert client.post(f"/api/career/my/tests/{karta.pk}/start/").json()["id"] == attempt, "сданная попытка — та же"
    staff = login(teacher)
    assert staff.post(f"/api/career/attempts/{attempt}/retake/").status_code == 200
    fresh = client.post(f"/api/career/my/tests/{karta.pk}/start/").json()
    assert fresh["id"] != attempt and fresh["status"] == "in_progress"
    assert CareerAttempt.objects.filter(student=pupils["aliya"], archived_at__isnull=False).count() == 1


# --- Результаты -------------------------------------------------------------------


@pytest.fixture
def passed(karta, teacher, boston, pupils):
    """Алия сдала с биологией 12 и физикой −12, Дамир — всё по нулям."""
    activate(karta, [{"group": boston.pk}], by=teacher)
    aliya = login(pupils["aliya"].user)
    attempt = aliya.post(f"/api/career/my/tests/{karta.pk}/start/").json()["id"]
    answer_all(aliya, attempt, lambda n: {1: "++", 2: "−−", 17: "+"}.get((n - 1) % 24 + 1, "0"))
    aliya.post(f"/api/career/my/attempts/{attempt}/finish/")
    damir = login(pupils["damir"].user)
    second = damir.post(f"/api/career/my/tests/{karta.pk}/start/").json()["id"]
    answer_all(damir, second, lambda n: "0")
    damir.post(f"/api/career/my/attempts/{second}/finish/")
    return {"aliya": attempt, "damir": second}


def test_results_matrix_and_who_reads(
    passed, karta, teacher, curator, asem, admin, kymbat, other_teacher, boston, pupils
):
    for user in (teacher, curator, asem, admin):
        response = login(user).get(f"/api/career/results/?group={boston.pk}")
        assert response.status_code == 200, user.email
        rows = {row["id"]: row for row in response.json()["students"]}
        assert rows[pupils["aliya"].pk]["cells"][str(karta.pk)]["status"] == "done"
        assert response.json()["tests"][0]["assigned"] == 2
    assert login(kymbat).get(f"/api/career/results/?group={boston.pk}").status_code == 403
    assert login(other_teacher).get(f"/api/career/results/?group={boston.pk}").status_code == 403
    # блок в карточке: куратор BOSTON читает Алию, чужую группу — нет
    client = login(curator)
    block = client.get(f"/api/career/students/{pupils['aliya'].pk}/").json()
    assert block["attempts"][0]["scores"][0]["score"] == 12
    assert client.get(f"/api/career/students/{pupils['nurai'].pk}/").status_code == 404
    assert client.get(f"/api/career/attempts/{passed['aliya']}/").status_code == 200
    # куратор не ведёт тесты
    assert client.post(f"/api/career/attempts/{passed['aliya']}/retake/").status_code == 403
    assert client.put(f"/api/career/tests/{karta.pk}/assignments/", {"groups": []}, format="json").status_code == 403


def test_tests_list_counts(passed, karta, teacher):
    row = login(teacher).get("/api/career/tests/").json()["tests"][0]
    assert row["assigned"] == 2 and row["done"] == 2 and row["in_progress"] == 0 and row["items"] == 144


def test_test_with_attempts_is_archived_not_deleted(passed, karta, teacher, boston):
    client = login(teacher)
    assert client.delete(f"/api/career/tests/{karta.pk}/").json()["archived"] is True
    karta.refresh_from_db()
    assert karta.archived_at is not None and not karta.is_active
    assert client.get("/api/career/tests/").json()["tests"] == []


def test_test_without_attempts_is_deleted(karta, teacher):
    assert login(teacher).delete(f"/api/career/tests/{karta.pk}/").json()["archived"] is False
    assert not CareerTest.objects.filter(pk=karta.pk).exists()


# --- Разбор ------------------------------------------------------------------------

PARSED = {
    "summary": "Интересы лежат в области биологии и права.",
    "directions": [
        {
            "title": "Биотехнологии",
            "why": "Биология — 12, ярко выраженный интерес",
            "professions": "биотехнолог, генетик",
            "subjects": "биология, химия",
            "exams": "IELTS, SAT",
            "programs": [999999],
        },
        {"title": "Право", "why": "Юриспруденция — 6", "professions": "юрист", "subjects": "история", "exams": "IELTS"},
        {"title": "Экология", "why": "смежно с биологией", "professions": "эколог"},
    ],
}


def test_analysis_runs_on_positive_scales_only_and_is_cached(passed, karta, teacher, boston, pupils, fake):
    provider = fake(FakeProvider(PARSED))
    client = login(teacher)
    body = {"group": boston.pk, "tests": [karta.pk]}
    response = client.post("/api/career/analyses/", body, format="json")
    assert response.status_code == 202, response.content
    assert response.json()["created"] == 1 and response.json()["reused"] == 0
    assert [row["reason"] for row in response.json()["skipped"]] == ["ни одна шкала не выше порога — разбирать нечего"]
    assert len(provider.calls) == 1
    prompt = provider.calls[0]["user"]
    assert "Биология: 12" in prompt and "Юриспруденция: 6" in prompt
    assert "Физика" not in prompt and "Математика" not in prompt, "минусы и нули в разбор не идут"
    assert "Ахметова" not in prompt and "Алия" not in prompt
    row = CareerAnalysis.objects.get()
    assert row.status == AnalysisStatus.DONE and row.student == pupils["aliya"]
    assert [d.title for d in row.directions.all()] == ["Биотехнологии", "Право", "Экология"]
    assert row.directions.first().programs.count() == 0, "программа мимо справочника отброшена"
    # тот же набор второй раз — готовый разбор, модель не зовётся
    again = client.post("/api/career/analyses/", body, format="json")
    assert again.status_code == 200 and again.json() == {
        "created": 0,
        "reused": 1,
        "skipped": again.json()["skipped"],
        "job": None,
    }
    assert len(provider.calls) == 1
    forced = client.post("/api/career/analyses/", {**body, "force": True}, format="json")
    assert forced.status_code == 202 and len(provider.calls) == 2
    listing = client.get(f"/api/career/analyses/?group={boston.pk}").json()
    assert len(listing["analyses"]) == 2 and listing["tests"][0]["done"] == 2


def test_failed_analysis_keeps_the_reason(passed, karta, teacher, boston, fake):
    fake(FakeProvider(None, fail=True))
    response = login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    assert response.status_code == 202
    row = CareerAnalysis.objects.get()
    assert row.status == AnalysisStatus.FAILED and "503" in row.error
    # неудавшийся набор можно запустить снова без «Пересчитать»
    fake(FakeProvider(PARSED))
    assert (
        login(teacher)
        .post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
        .json()["created"]
        == 1
    )


STUDENT_PARSED = {
    "summary": "У тебя выраженный интерес к биологии и праву.",
    "directions": [
        {"order": 1, "why": "Тебе интересна биология — 12 баллов."},
        {"order": 2, "why": "Право — 6, тебе близко."},
    ],
}


class TwoStepProvider(FakeProvider):
    """Первый вызов — разбор для учителя, второй — версия для ученика."""

    def complete(self, **kwargs):
        from suggestions.providers import Completion, Usage

        self.calls.append(kwargs)
        parsed = STUDENT_PARSED if len(self.calls) > 1 else PARSED
        return Completion(content="", parsed=parsed, model="fake-1", external_id="msg", usage=Usage(100, 50), raw={})


def test_student_sees_analysis_only_when_shown_and_teacher_edits_text(
    passed, karta, teacher, boston, pupils, fake, curator
):
    provider = fake(TwoStepProvider(PARSED))
    staff = login(teacher)
    staff.post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    row = CareerAnalysis.objects.get()
    student = login(pupils["aliya"].user)
    assert student.get("/api/career/my/").json()["analyses"] == []
    direction = row.directions.first()
    edited = staff.patch(
        f"/api/career/analyses/{row.pk}/",
        {
            "summary": "Правка учителя",
            "directions": [{"id": direction.pk, "reasoning": "по-другому"}],
            "visible_to_student": True,
        },
        format="json",
    )
    assert edited.status_code == 200, edited.content
    body = edited.json()
    assert body["summary"] == "Правка учителя" and body["edited_at"]
    assert body["edited_by"]["full_name"] == "Жанар Профориентатор"
    # первый показ — второй вызов модели: версия для ученика на «ты», учитель видит обе
    assert len(provider.calls) == 2 and "Разбор для учителя" in provider.calls[1]["user"]
    assert body["summary_student"] == STUDENT_PARSED["summary"] and body["has_student_version"] is True
    assert body["directions"][0]["reasoning_student"] == "Тебе интересна биология — 12 баллов."
    # ученику разборы скрыты (решение владельца, 09.10.2026): только баллы; версия на «ты»
    # остаётся у учителя и включится флагом `STUDENT_SEES_ANALYSIS`
    assert student.get("/api/career/my/").json()["analyses"] == []
    from career import views

    monkeypatch_flag = views.STUDENT_SEES_ANALYSIS
    views.STUDENT_SEES_ANALYSIS = True
    try:
        shown = student.get("/api/career/my/").json()["analyses"]
    finally:
        views.STUDENT_SEES_ANALYSIS = monkeypatch_flag
    assert len(shown) == 1
    assert shown[0]["summary"] == STUDENT_PARSED["summary"], "ученику — его версия"
    assert shown[0]["directions"][0]["reasoning"] == "Тебе интересна биология — 12 баллов."
    assert "created_by" not in shown[0] and "edited_by" not in shown[0] and "summary_student" not in shown[0]
    # повторный показ версию не переписывает; учитель правит версию ученика
    staff.patch(f"/api/career/analyses/{row.pk}/", {"visible_to_student": False}, format="json")
    staff.patch(
        f"/api/career/analyses/{row.pk}/",
        {"visible_to_student": True, "summary_student": "Своими словами"},
        format="json",
    )
    assert len(provider.calls) == 2
    row.refresh_from_db()
    assert row.summary_student == "Своими словами"
    # куратор читает разбор своей группы, но не правит
    assert login(curator).get(f"/api/career/analyses/{row.pk}/").status_code == 200
    assert login(curator).patch(f"/api/career/analyses/{row.pk}/", {"summary": "x"}, format="json").status_code == 403


def test_show_to_student_fails_without_the_model(passed, karta, teacher, boston, fake):
    fake(FakeProvider(PARSED))
    staff = login(teacher)
    staff.post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    row = CareerAnalysis.objects.get()
    fake(FakeProvider(None, fail=True))
    refused = staff.patch(f"/api/career/analyses/{row.pk}/", {"visible_to_student": True}, format="json")
    assert refused.status_code == 503 and "503" in refused.json()["detail"]
    row.refresh_from_db()
    assert not row.visible_to_student and row.summary_student == ""


def test_analysis_requires_all_chosen_tests(passed, karta, teacher, boston, example_bytes, pupils, fake):
    """Второй тест никто не сдал: разбор по двум тестам никому не запускается."""
    fake(FakeProvider(PARSED))
    client = login(teacher)
    second = CareerTest.objects.get(pk=upload(client, example_bytes).json()["id"])
    response = client.post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk, second.pk]}, format="json")
    assert response.status_code == 200 and response.json()["created"] == 0
    assert {row["reason"] for row in response.json()["skipped"]} == {"сданы не все выбранные тесты"}


def test_admin_runs_analysis_for_any_group(passed, karta, admin, boston, fake):
    fake(FakeProvider(PARSED))
    assert (
        login(admin).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json").status_code
        == 202
    )
