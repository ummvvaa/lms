"""Страж параллелей: ученику 8–10 закрыты все ручки поступления.

Обходит маршруты поступления под учеником каждой параллели: у 8, 9 и 10
раздел поступления отвечает 403 с кодом `parallel_closed`, прочие ручки
приложений поступления — отказом (403 или 404), но никогда не данными.
У 11 шлюз не закрывает ничего. Второй страж — полнота: каждый маршрут
приложений поступления либо записан в раздел реестра `core/parallels.py`,
либо закрыт ученику своей проверкой — новая ручка без записи в реестре
падает здесь, а не у ученика 8 класса.
"""

from __future__ import annotations

import re

import pytest
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from core.parallels import ADMISSION_ONLY, PARALLELS, SECTIONS, sections_for, student_paths
from students.models import Student, StudyGroup

#: приложения, где у ученика нет ничего, кроме поступления
ADMISSION_APPS = ("universities", "roadmap", "prep")
#: маршруты поступления из общих приложений — тоже закрыты 8–10
ADMISSION_ROUTES_ELSEWHERE = (
    "portfolio",
    "portfolio-cv",
    "exam-goal-list",
    "exam-goals-attention",
    "attempt-list",
    "profile-admission-detail",
    "profile-exam-detail",
    "student-readiness",
    "career-state",
    "career-run",
    "journey-state",
    "journey-locks",
    "onboarding-state",
    "onboarding-answer",
    "achievements",
    "game-state",
    "home-cues",
    "resource-list",
    "resource-overview",
    "command-essay-questions",
    "command-explain-match",
    "command-parse-university",
    "command-verify-requirements",
    "credentials-state",
    "admission-imports",
    "mock-imports",
)
#: подстановки для аргументов маршрута
KWARGS = {"pk": 1, "program_id": 1, "student_id": 1, "exam": "IELTS", "section": "reading", "task_id": "x"}


def _routes() -> list[tuple[str, str, list[str]]]:
    """(приложение, имя, аргументы) всех именованных маршрутов API."""
    out: list[tuple[str, str, list[str]]] = []

    def walk(patterns):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns)
            elif isinstance(pattern, URLPattern) and pattern.name:
                module = getattr(pattern.callback, "__module__", "") or ""
                source = str(pattern.pattern)
                if "format" in source:
                    continue
                names = re.findall(r"<(?:\w+:)?(\w+)>|\(\?P<(\w+)>", source)
                args = [a or b for a, b in names]
                out.append((module.split(".")[0], pattern.name, args))

    walk(get_resolver().url_patterns)
    return out


def _url(name: str, args: list[str]) -> str:
    return reverse(name, kwargs={arg: KWARGS[arg] for arg in args})


def _student(parallel: int, make_user) -> tuple[Client, Student]:
    group = StudyGroup.objects.create(code=f"P{parallel}", parallel=parallel)
    user = make_user("student", f"parallel{parallel}@example.kz")
    student = Student.objects.create(
        last_name="Параллелев", first_name=str(parallel), group=group, graduation_year=2027, user=user
    )
    client = Client()
    client.force_login(user)
    return client, student


def _admission_routes() -> list[tuple[str, list[str]]]:
    wanted = set(ADMISSION_ROUTES_ELSEWHERE) | {r for s in SECTIONS if s.parallels == ADMISSION_ONLY for r in s.routes}
    return sorted(
        {(name, tuple(args)) for app, name, args in _routes() if app in ADMISSION_APPS or name in wanted},
    )


def test_every_section_route_exists():
    """Имя маршрута в реестре — настоящее: опечатка молча открыла бы раздел."""
    known = {name for _app, name, _args in _routes()}
    missing = [route for section in SECTIONS for route in section.routes if route not in known]
    assert not missing, f"в реестре параллелей нет таких маршрутов: {missing}"


@pytest.mark.django_db
@pytest.mark.parametrize("parallel", [p for p in PARALLELS if p not in ADMISSION_ONLY])
def test_junior_student_gets_no_admission_data(parallel, make_user):
    """8–10: каждая ручка поступления — отказ, раздел реестра — 403 с кодом."""
    client, _student_ = _student(parallel, make_user)
    gated = {route for section in SECTIONS if parallel not in section.parallels for route in section.routes}
    leaked = []
    for name, args in _admission_routes():
        url = _url(name, list(args))
        for method in ("get", "post"):
            response = getattr(client, method)(url, content_type="application/json")
            if name in gated:
                if response.status_code != 403 or response.json().get("code") != "parallel_closed":
                    leaked.append(f"{method.upper()} {url} ({name}) → {response.status_code}, а не 403 шлюза")
            elif 200 <= response.status_code < 300:
                leaked.append(f"{method.upper()} {url} ({name}) → {response.status_code}")
    assert not leaked, "ученику 8–10 открыто поступление:\n" + "\n".join(leaked)


@pytest.mark.django_db
def test_graduate_is_not_stopped_by_the_gate(make_user):
    """11: шлюз ничего не закрывает — разделы поступления на месте."""
    client, _student_ = _student(11, make_user)
    stopped = []
    for section in SECTIONS:
        for name in section.routes:
            args = next(a for _app, n, a in _routes() if n == name)
            response = client.get(_url(name, args))
            if response.status_code == 403 and "parallel_closed" in response.content.decode():
                stopped.append(name)
    assert not stopped, f"шлюз закрыл 11 параллели: {stopped}"


def test_every_admission_app_route_is_in_the_registry_or_staff_only():
    """Полнота: маршрут приложений поступления, которым пользуется ученик,
    записан в раздел реестра. Остальные — ручки сотрудников, ученику их
    закрывает собственная проверка (её держит страж выше)."""
    in_registry = {route for section in SECTIONS for route in section.routes}
    staff_only = {
        "catalog-pending",
        "catalog-review",
        "catalog-seed",
        "catalog-verify",
        "requirements-import",
        "scholarships-import",
        "prep-open-answers",
        "prep-open-answer-review",
        "prep-questions-import",
        "prep-review-mock",
    }
    loose = [
        name
        for app, name, _args in _routes()
        if app in ADMISSION_APPS and name not in in_registry and name not in staff_only
    ]
    assert not loose, f"маршрут поступления вне реестра параллелей: {loose}"


@pytest.mark.django_db
def test_menu_follows_the_registry(make_user):
    """Меню ученика — из того же реестра: у 9 нет ни одного раздела поступления,
    у 11 нет отдельных «Олимпиад» и «Спорта» — его кабинет не меняется."""
    _client9, nine = _student(9, make_user)
    _client11, eleven = _student(11, make_user)
    junior = student_paths(nine)
    assert junior == [
        "/dashboard",
        "/schedule",
        "/grades",
        "/homework",
        "/calendar",
        "/profile",
        "/materials",
        "/olympiads",
        "/sport",
        # профтест — тесты учителя профориентации, открыт всем параллелям (08.10.2026)
        "/career",
    ]
    graduate = student_paths(eleven)
    assert "/catalog" in graduate and "/my-data" in graduate
    assert "/homework" in graduate, "сдача ДЗ — у всех параллелей"
    assert "/olympiads" not in graduate and "/sport" not in graduate
    assert [s.code for s in sections_for(10)] == [s.code for s in sections_for(8)]


@pytest.mark.django_db
def test_me_tells_the_menu(make_user):
    client, _student_ = _student(8, make_user)
    me = client.get("/api/auth/me/").json()
    assert me["has_admission"] is False
    assert "/catalog" not in me["sections"]
    assert "/olympiads" in me["sections"]
    card = client.get("/api/students/me/").json()
    assert "admission" not in card and "exam" not in card
    assert card["readiness"] is None
    domains = {d["code"] for d in client.get("/api/meta/domains/").json()["domains"]}
    assert domains == {"behavior", "talent", "sport"}


@pytest.mark.django_db
def test_junior_proposes_only_olympiads_and_sport(make_user):
    client, student = _student(9, make_user)
    refused = client.post(
        "/api/suggestions/propose/",
        {"rows": [{"model": "students.ExamProfile", "field": "ielts_current", "value": "6.5"}]},
        content_type="application/json",
    )
    assert refused.status_code == 400
    assert "11 параллели" in refused.json()["rejected"][0]["reason"]
    other = client.post(
        "/api/suggestions/propose/",
        {
            "rows": [
                {"model": "students.Activity", "field": "category", "value": "volunteering", "new_object_key": "n1"},
                {"model": "students.Activity", "field": "title", "value": "Субботник", "new_object_key": "n1"},
            ]
        },
        content_type="application/json",
    )
    assert other.status_code == 400


@pytest.mark.django_db
def test_junior_uploads_only_proof_scans(make_user):
    """Документы поступления у 8–10 закрыты; скан диплома олимпиады — можно."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from students.models import StudentDocument

    client, student = _student(10, make_user)
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    passport = client.post(
        "/api/documents/", {"doc_type": "passport", "file": SimpleUploadedFile("p.png", png, "image/png")}
    )
    assert passport.status_code == 403
    assert passport.json()["code"] == "parallel_closed"
    proof = client.post("/api/documents/", {"doc_type": "other", "file": SimpleUploadedFile("d.png", png, "image/png")})
    assert proof.status_code == 201, proof.content
    StudentDocument.objects.create(student=student, doc_type="attestat", title="Аттестат от куратора")
    listed = client.get("/api/documents/").json()
    rows = listed["results"] if isinstance(listed, dict) else listed
    assert [row["doc_type"] for row in rows] == ["other"]
