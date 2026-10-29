"""План поступления по конкретному вузу.

План заводится сам, когда программа попадает в список ученика; задачи
собираются под программу и уходят предложением (инвариант №3). Дедлайн плана — из раунда, не копия: сдвиг
в справочнике двигает и план, и его задачи (инвариант №4).
"""

from __future__ import annotations

import datetime as dt

import pytest
from rest_framework.test import APIClient

from roadmap.models import ApplicationPlan, Task
from universities.models import AdmissionRequirement, AdmissionRound, Program, University


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
def program(db):
    university = University.objects.create(name="Test University", country="Канада")
    program = Program.objects.create(university=university, name="Computer Science", level="bachelor")
    AdmissionRequirement.objects.create(program=program, min_ielts=6.5, portfolio_required=True)
    AdmissionRound.objects.create(program=program, round_type="RD", deadline=dt.date(2027, 1, 15))
    return program


def create_plan(student_user, student, program) -> ApplicationPlan:
    """План заводится добавлением вуза в список; eager celery собирает его синхронно."""
    from roadmap.plans import ensure_for_program

    plan = ensure_for_program(student, program, user=student_user)
    plan.refresh_from_db()
    assert plan.generation_status == "done"
    return plan


# --- Создание и генерация --------------------------------------------------


@pytest.mark.django_db
def test_plan_generates_tasks_through_suggestion(api, student_user, student, program):
    from roadmap.plans import apply_plan, ensure_for_program

    plan = create_plan(student_user, student, program)

    # раунд подтянулся автоматически, дедлайн — из него
    assert plan.admission_round is not None
    assert plan.deadline == dt.date(2027, 1, 15)

    # задачи проходят через предложение (инвариант №3) и применяются сразу
    # же (фаза 48): подтверждением стало добавление вуза
    assert plan.pending_suggestion is not None
    assert plan.pending_suggestion.changes.exists()

    tasks = Task.objects.filter(plan=plan)
    assert tasks.count() > 0
    assert any("Test University" in t.title for t in tasks)
    # задачи видны в общем списке задач ученика
    api.force_authenticate(student_user)
    mine = api.get("/api/tasks/my/").data
    assert any(row["plan"] == plan.pk for row in mine)

    # повторное применение и повторное добавление ничего не удваивают
    apply_plan(plan, actor=student_user)
    assert Task.objects.filter(plan=plan).count() == tasks.count()
    assert ensure_for_program(student, program, user=student_user).pk == plan.pk


# --- Дедлайн из раунда, а не копия (инвариант №4) --------------------------


@pytest.mark.django_db
def test_deadline_moves_with_the_round(api, student_user, student, program):
    plan = create_plan(student_user, student, program)
    submit_task = Task.objects.filter(plan=plan, category="university").first()
    assert submit_task is not None
    assert submit_task.effective_due_date == dt.date(2027, 1, 15)

    # директор сдвигает дедлайн раунда в справочнике
    round_row = plan.admission_round
    round_row.deadline = dt.date(2027, 2, 20)
    round_row.save(update_fields=["deadline"])

    plan.refresh_from_db()
    assert plan.deadline == dt.date(2027, 2, 20)
    submit_task.refresh_from_db()
    assert submit_task.effective_due_date == dt.date(2027, 2, 20)


@pytest.mark.django_db
def test_plan_tasks_appear_in_roadmap_with_university_mark(api, student_user, student, program):
    plan = create_plan(student_user, student, program)
    api.force_authenticate(student_user)
    roadmap = api.get(f"/api/tasks/?student={student.pk}&page_size=200").data
    rows = roadmap["results"] if isinstance(roadmap, dict) else roadmap
    plan_tasks = [t for t in rows if t.get("plan") == plan.pk]
    assert plan_tasks
    assert all(t["plan_university"] == "Test University" for t in plan_tasks)


@pytest.mark.django_db
def test_plan_attention_for_admission_director(api, student_user, student, program, make_user):
    plan = create_plan(student_user, student, program)
    # дедлайн близко, прогресс нулевой
    plan.admission_round.deadline = dt.date.today() + dt.timedelta(days=10)
    plan.admission_round.save(update_fields=["deadline"])

    asem = make_user("director_admission", "asem41b@school.kz")
    api.force_authenticate(asem)
    payload = api.get("/api/application-plans/attention/").data
    assert any(row["id"] == plan.pk for row in payload["stalled"])

    api.force_authenticate(make_user("director_sport", "n41@school.kz"))
    assert api.get("/api/application-plans/attention/").status_code == 403
