"""Фаза 40: прогон подбора, воронка, категории, стратегия, избранное.

Все проценты — соответствие требованиям, не шанс поступления
(инвариант №11): слово «шанс» стерегут тесты по текстам сервера
и интерфейса.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from universities.models import (
    AdmissionRequirement,
    FavoriteProgram,
    MatchRun,
    Program,
    University,
)
from universities.selection import execute, filter_programs, start_run, tier_for

# в контейнере репозиторий примонтирован в /repo только на чтение
_ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
FRONT_SELECTION = _ROOT / "frontend" / "src" / "screens" / "Selection.tsx"


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
def catalog(db):
    """Три вуза с требованиями и один без — маленький справочник."""
    rows = []
    for name, country, rank, ielts in (
        ("Alpha University", "Канада", 20, 7.5),
        ("Beta University", "Канада", 200, 6.5),
        ("Gamma University", "Германия", None, 5.5),
    ):
        university = University.objects.create(name=name, country=country, world_rank=rank)
        program = Program.objects.create(university=university, name="Computer Science", level="bachelor")
        AdmissionRequirement.objects.create(program=program, min_ielts=ielts)
        rows.append(program)
    plain = University.objects.create(name="Delta University", country="Канада", world_rank=50)
    rows.append(Program.objects.create(university=plain, name="Computer Science", level="bachelor"))
    # программа мимо специальности — не должна пройти фильтр
    Program.objects.create(university=plain, name="Economics", level="bachelor")
    return rows


def run_for(student, **kwargs) -> MatchRun:
    run = start_run(student, **kwargs)
    execute(run.pk)
    run.refresh_from_db()
    return run


# --- Категории и фильтр ----------------------------------------------------


def test_tier_boundaries_come_from_settings(settings):
    assert tier_for(95) == "safety"
    assert tier_for(75) == "match"
    assert tier_for(50) == "reach"
    assert tier_for(20) == "dream"
    settings.MATCH_TIERS = {"safety": 99.0, "match": 90.0, "reach": 80.0}
    assert tier_for(95) == "match"


@pytest.mark.django_db
def test_filter_by_major_and_countries(catalog):
    assert len(filter_programs("Computer Science", "", [])) == 4
    assert len(filter_programs("Computer Science", "", ["Канада"])) == 3
    assert len(filter_programs("Economics", "", [])) == 1
    assert len(filter_programs("", "", [])) == 5


# --- Прогон: воронка, снимок, секции ---------------------------------------


@pytest.mark.django_db
def test_run_builds_funnel_sections_and_snapshot(student, catalog):
    student.exam.ielts_current = 6.5
    student.exam.gpa = 3.5
    student.exam.save()

    run = run_for(student, major="Computer Science")
    assert run.status == "done"
    assert run.progress == 100
    assert run.funnel_catalog == 5
    assert run.funnel_filtered == 4
    assert run.funnel_analyzed == 3  # у Delta требований нет — подробно не разбирается
    assert run.funnel_final == 3
    assert str(run.snapshot_ielts) == "6.5"

    rows = list(run.results.all())
    sections = {row.section for row in rows}
    assert sections == {"top", "other"}
    top = [row for row in rows if row.section == "top"]
    # Gamma с порогом 5.5 закрыт целиком — категория safety
    tiers = {row.program.university.name: row.tier for row in top}
    assert tiers["Gamma University"] == "safety"
    assert all(row.tier for row in top)

    # стратегия без ключа — правилами, с пометкой
    assert run.strategy_offline
    assert run.strategy_position and run.strategy_improve and run.strategy_next


@pytest.mark.django_db
def test_goal_percent_uses_exam_goals(student, catalog):
    from directories.models import ExamKind
    from students.models import ExamGoal

    student.exam.ielts_current = 6.0
    student.exam.save()
    ExamGoal.objects.create(student=student, exam=ExamKind.objects.get(name="IELTS"), target_score=7.5)

    run = run_for(student, major="Computer Science")
    alpha = run.results.get(program__university__name="Alpha University")
    assert alpha.percent_goal > alpha.percent_now
    assert alpha.percent_goal == 100


@pytest.mark.django_db
def test_rerun_with_country_filter_differs_and_both_in_history(api, student_user, student, catalog):
    run_for(student, major="Computer Science")
    run_for(student, major="Computer Science", countries=["Германия"])

    api.force_authenticate(student_user)
    history = api.get("/api/selection/runs/").data["results"]
    assert len(history) == 2
    assert {tuple(r["countries"]) for r in history} == {(), ("Германия",)}
    filtered = next(r for r in history if r["countries"])
    assert filtered["funnel"]["filtered"] == 1


@pytest.mark.django_db
def test_run_detail_and_explain(api, student_user, student, catalog):
    student.exam.ielts_current = 6.5
    student.exam.save()
    run = run_for(student, major="Computer Science")

    api.force_authenticate(student_user)
    payload = api.get(f"/api/selection/runs/{run.pk}/").data
    assert payload["funnel"]["catalog"] == 5
    assert payload["methodology"]
    assert payload["results"]

    program = payload["results"][0]["program"]
    explain = api.get(f"/api/selection/runs/{run.pk}/explain/{program}/").data
    assert explain["breakdown"]
    assert explain["snapshot_percent"] == payload["results"][0]["percent_now"]
    assert explain["profile_changed"] is False

    # чужой прогон недоступен
    other = make_other_student_client(api)
    assert other.get(f"/api/selection/runs/{run.pk}/").status_code == 404


def make_other_student_client(api):
    from accounts.models import User
    from students.models import Student, StudyGroup

    group = StudyGroup.objects.get_or_create(code="G40", defaults={"grade": 11})[0]
    student = Student.objects.create(
        last_name="Чужой",
        first_name="Ученик",
        email="stranger40@example.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    user = User.objects.create_user(email=student.email, password="pass12345", role="student")
    student.user = user
    student.save(update_fields=["user"])
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.mark.django_db
def test_second_running_run_is_rejected(api, student_user, student, catalog, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False  # иначе прогон завершится синхронно
    api.force_authenticate(student_user)
    first = api.post("/api/selection/runs/start/", {"major": "Computer Science"}, format="json")
    assert first.status_code == 201
    second = api.post("/api/selection/runs/start/", {"major": "Computer Science"}, format="json")
    assert second.status_code == 409
    active = api.get("/api/selection/runs/active/").data
    assert active["run"]["id"] == first.data["id"]


# --- Избранное --------------------------------------------------------------


@pytest.mark.django_db
def test_favorites_are_separate_from_my_list(api, student_user, student, catalog):
    api.force_authenticate(student_user)
    program = catalog[0].pk
    made = api.post("/api/favorites/", {"program": program}, format="json")
    assert made.status_code == 201

    listing = api.get("/api/favorites/").data
    assert listing["count"] == 1
    assert listing["results"][0]["in_my_list"] is False

    # повторное сердечко не создаёт дубля
    again = api.post("/api/favorites/", {"program": program}, format="json")
    assert again.status_code == 200
    assert FavoriteProgram.objects.count() == 1

    removed = api.delete(f"/api/favorites/program/{program}/")
    assert removed.status_code == 200
    assert FavoriteProgram.objects.count() == 0


@pytest.mark.django_db
def test_staff_has_no_favorites(api, make_user, catalog):
    api.force_authenticate(make_user("director_admission", "asem40@school.kz"))
    assert api.get("/api/favorites/").status_code == 403
    assert api.post("/api/favorites/", {"program": catalog[0].pk}, format="json").status_code == 403


# --- Не «шанс» --------------------------------------------------------------


@pytest.mark.django_db
def test_strategy_rules_never_say_chance(student, catalog):
    run = run_for(student, major="Computer Science")
    text = " ".join([run.strategy_position, run.strategy_improve, run.strategy_next]).lower()
    for word in ("шанс", "вероятност", "прогноз"):
        assert word not in text


def test_selection_screen_texts_have_no_chance_words():
    """Инвариант №11 — тестом по текстам интерфейса, как требует приёмка.

    Оговорка «не шанс поступления» разрешена — это и есть честная подпись;
    запрещено называть шансом само число.
    """
    source = FRONT_SELECTION.read_text(encoding="utf-8").lower()
    cleaned = source.replace("не шанс", "").replace("не шансы", "")
    for word in ("шанс", "вероятност"):
        assert word not in cleaned, f"«{word}» на экране подбора без отрицания"
    assert "соответствие" in source


def test_methodology_explains_from_the_same_settings():
    from universities.selection import methodology

    text = " ".join(methodology())
    assert "не шанс поступления" in text
    assert "Safety" in text and "Dream" in text
    assert re.search(r"\d+%", text)
