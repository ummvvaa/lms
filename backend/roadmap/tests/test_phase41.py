"""Фаза 41: план поступления по конкретному вузу.

Задачи собираются под программу и уходят предложением (инвариант №3),
применяет их сам ученик. Дедлайн плана — из раунда, не копия: сдвиг
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


def create_and_apply(api, user, program) -> ApplicationPlan:
    api.force_authenticate(user)
    made = api.post("/api/application-plans/", {"program": program.pk}, format="json")
    assert made.status_code == 201, made.data
    plan = ApplicationPlan.objects.get(pk=made.data["id"])
    # eager celery выполнил генерацию синхронно
    plan.refresh_from_db()
    assert plan.generation_status == "done"
    applied = api.post(f"/api/application-plans/{plan.pk}/apply_tasks/", {}, format="json")
    assert applied.status_code == 200, applied.data
    return plan


# --- Создание и генерация --------------------------------------------------


@pytest.mark.django_db
def test_plan_generates_tasks_through_suggestion(api, student_user, student, program):
    api.force_authenticate(student_user)
    made = api.post("/api/application-plans/", {"program": program.pk}, format="json")
    assert made.status_code == 201
    plan = ApplicationPlan.objects.get(pk=made.data["id"])
    plan.refresh_from_db()

    # раунд подтянулся автоматически, дедлайн — из него
    assert plan.admission_round is not None
    assert plan.deadline == dt.date(2027, 1, 15)

    # Задачи по-прежнему проходят через предложение (инвариант №3),
    # но применяются сразу же (фаза 48): подтверждением стало добавление
    # вуза, а второго нажатия человек не находил — и до фазы 48 задачи
    # не доходили ни до роадмапа, ни до календаря
    assert plan.pending_suggestion is not None
    preview = api.get(f"/api/application-plans/{plan.pk}/preview/").data
    assert len(preview["changes"]) > 0

    tasks = Task.objects.filter(plan=plan)
    assert tasks.count() > 0
    # задачи привязаны к плану и относятся к этому вузу
    assert all(t.plan_id == plan.pk for t in tasks)
    assert any("Test University" in t.title for t in tasks)
    # и видны в общем роадмапе ученика — не только внутри плана
    mine = api.get("/api/tasks/my/").data
    assert any(row["plan"] == plan.pk for row in mine)

    # повторное применение ничего не удваивает
    again = api.post(f"/api/application-plans/{plan.pk}/apply_tasks/", {}, format="json")
    assert again.status_code == 200
    assert Task.objects.filter(plan=plan).count() == tasks.count()


@pytest.mark.django_db
def test_second_plan_for_same_program_is_rejected(api, student_user, student, program):
    api.force_authenticate(student_user)
    first = api.post("/api/application-plans/", {"program": program.pk}, format="json")
    assert first.status_code == 201
    second = api.post("/api/application-plans/", {"program": program.pk}, format="json")
    assert second.status_code == 409


# --- Дедлайн из раунда, а не копия (инвариант №4) --------------------------


@pytest.mark.django_db
def test_deadline_moves_with_the_round(api, student_user, student, program):
    plan = create_and_apply(api, student_user, program)
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


# --- Счётчики и несколько планов -------------------------------------------


@pytest.mark.django_db
def test_counters_are_per_plan(api, student_user, student, program):
    plan = create_and_apply(api, student_user, program)
    tasks = list(Task.objects.filter(plan=plan))
    tasks[0].status = "done"
    tasks[0].save(update_fields=["status"])

    api.force_authenticate(student_user)
    payload = api.get(f"/api/application-plans/{plan.pk}/").data
    assert payload["counters"]["total"] == len(tasks)
    assert payload["counters"]["done"] == 1
    assert payload["counters"]["remaining"] == len(tasks) - 1
    assert payload["progress"] == round(1 / len(tasks) * 100)


@pytest.mark.django_db
def test_multiple_plans_switch_and_count_separately(api, student_user, student):
    api.force_authenticate(student_user)
    plans = []
    for name in ("Alpha Uni", "Beta Uni"):
        university = University.objects.create(name=name, country="США")
        prog = Program.objects.create(university=university, name="Physics", level="bachelor")
        AdmissionRequirement.objects.create(program=prog, min_ielts=6.0)
        AdmissionRound.objects.create(program=prog, round_type="RD", deadline=dt.date(2027, 3, 1))
        plans.append(create_and_apply(api, student_user, prog))

    listing = api.get("/api/application-plans/").data
    rows = listing["results"] if isinstance(listing, dict) else listing
    assert len(rows) == 2
    # у каждого плана свои задачи
    assert all(row["counters"]["total"] > 0 for row in rows)


# --- Связь с общим роадмапом ----------------------------------------------


@pytest.mark.django_db
def test_plan_tasks_appear_in_roadmap_with_university_mark(api, student_user, student, program):
    plan = create_and_apply(api, student_user, program)
    api.force_authenticate(student_user)
    roadmap = api.get(f"/api/tasks/?student={student.pk}&page_size=200").data
    rows = roadmap["results"] if isinstance(roadmap, dict) else roadmap
    plan_tasks = [t for t in rows if t.get("plan") == plan.pk]
    assert plan_tasks
    assert all(t["plan_university"] == "Test University" for t in plan_tasks)


@pytest.mark.django_db
def test_tasks_grouped_by_stage(api, student_user, student, program):
    plan = create_and_apply(api, student_user, program)
    api.force_authenticate(student_user)
    grouped = api.get(f"/api/application-plans/{plan.pk}/tasks/").data
    categories = [stage["category"] for stage in grouped["stages"]]
    assert "test" in categories or "documents" in categories
    assert categories == sorted(set(categories), key=categories.index)  # без дублей


# --- Права -----------------------------------------------------------------


@pytest.mark.django_db
def test_staff_reads_plans_but_does_not_create(api, student_user, student, program, make_user):
    plan = create_and_apply(api, student_user, program)

    asem = make_user("director_admission", "asem41@school.kz")
    api.force_authenticate(asem)
    # директор читает планы
    assert api.get("/api/application-plans/").status_code == 200
    # но не создаёт и не применяет
    assert api.post("/api/application-plans/", {"program": program.pk}, format="json").status_code in (403, 405)
    assert api.post(f"/api/application-plans/{plan.pk}/apply_tasks/", {}, format="json").status_code == 403


@pytest.mark.django_db
def test_plan_attention_for_admission_director(api, student_user, student, program, make_user):
    plan = create_and_apply(api, student_user, program)
    # дедлайн близко, прогресс нулевой
    plan.admission_round.deadline = dt.date.today() + dt.timedelta(days=10)
    plan.admission_round.save(update_fields=["deadline"])

    asem = make_user("director_admission", "asem41b@school.kz")
    api.force_authenticate(asem)
    payload = api.get("/api/application-plans/attention/").data
    assert any(row["id"] == plan.pk for row in payload["stalled"])

    api.force_authenticate(make_user("director_sport", "n41@school.kz"))
    assert api.get("/api/application-plans/attention/").status_code == 403


@pytest.mark.django_db
def test_student_deletes_own_plan(api, student_user, student, program):
    plan = create_and_apply(api, student_user, program)
    api.force_authenticate(student_user)
    removed = api.delete(f"/api/application-plans/{plan.pk}/")
    assert removed.status_code == 200
    assert ApplicationPlan.objects.filter(pk=plan.pk).count() == 0
    assert ApplicationPlan.all_objects.filter(pk=plan.pk).count() == 1  # мягкое удаление
