"""Роадмап: генерация из шаблонов и дедлайнов, сдвиг дедлайна, эссе."""

from __future__ import annotations

from datetime import date

import pytest
from rest_framework.test import APIClient

from roadmap.models import Essay, EssayStatus, EssayType, Task, TaskCategory, TaskPriority, TaskTemplate
from roadmap.services import generate_from_deadlines, generate_from_templates
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    TalentProfile,
)
from universities.models import AdmissionRound, Program, StudentUniversity, University


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def asem(make_user):
    return make_user("director_admission", "asem@school.kz", full_name="Асем")


@pytest.fixture
def toronto(db):
    """Вуз с раундом — дедлайн живёт здесь и только здесь."""
    university = University.objects.create(name="University of Toronto", country="Канада", domain="utoronto.ca")
    program = Program.objects.create(university=university, name="Computer Science")
    admission_round = AdmissionRound.objects.create(
        program=program, round_type="RD", deadline=date(2027, 1, 15), source_url="https://utoronto.ca/apply"
    )
    return admission_round


@pytest.fixture
def three_applicants(db, group, toronto):
    """Трое подаются в один и тот же раунд."""
    students = []
    for i in range(3):
        s = Student.objects.create(
            last_name=f"Абитуриент{i}",
            first_name=f"Имя{i}",
            email=f"a{i}@school.kz",
            grade=11,
            group=group,
            graduation_year=2027,
        )
        for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
            model.objects.create(student=s)
        StudentUniversity.objects.create(student=s, program=toronto.program, admission_round=toronto, tier="target")
        students.append(s)
    return students


# --- Критерий: задача из дедлайна появляется у всех, кто туда подаётся ---


@pytest.mark.django_db
def test_deadline_task_appears_for_every_applicant(three_applicants, toronto):
    result = generate_from_deadlines(three_applicants)
    assert result.created == 3

    for student in three_applicants:
        task = student.tasks.get(admission_round=toronto)
        assert "University of Toronto" in task.title
        assert task.category == TaskCategory.UNIVERSITY
        assert task.effective_due_date == date(2027, 1, 15)


@pytest.mark.django_db
def test_generation_is_idempotent(three_applicants):
    generate_from_deadlines(three_applicants)
    second = generate_from_deadlines(three_applicants)
    assert second.created == 0
    assert second.skipped == 3
    assert Task.objects.count() == 3


# --- Критерий: сдвиг дедлайна в справочнике сдвигает задачи ---


@pytest.mark.django_db
def test_moving_the_deadline_moves_every_task(three_applicants, toronto):
    """Инвариант №4: дедлайн меняется один раз — пересчитывается у всех."""
    generate_from_deadlines(three_applicants)
    assert all(t.effective_due_date == date(2027, 1, 15) for t in Task.objects.all())

    toronto.deadline = date(2026, 12, 1)
    toronto.save(update_fields=["deadline"])

    for task in Task.objects.select_related("admission_round").all():
        assert task.effective_due_date == date(2026, 12, 1)

    # копии дедлайна в задаче нет — сдвигать по одной нечего
    assert all(task.due_date is None for task in Task.objects.all())


@pytest.mark.django_db
def test_deadline_shift_visible_through_api(api, asem, three_applicants, toronto):
    generate_from_deadlines(three_applicants)
    api.force_authenticate(asem)

    before = api.get(f"/api/tasks/?student={three_applicants[0].pk}").data["results"]
    assert before[0]["due_date_effective"] == "2027-01-15"
    assert before[0]["from_deadline"] is True

    toronto.deadline = date(2026, 11, 1)
    toronto.save(update_fields=["deadline"])

    after = api.get(f"/api/tasks/?student={three_applicants[0].pk}").data["results"]
    assert after[0]["due_date_effective"] == "2026-11-01"


# --- Генерация из шаблонов ---


@pytest.mark.django_db
def test_templates_produce_tasks_with_dates(three_applicants):
    TaskTemplate.objects.create(
        title="Черновик Personal Statement",
        category=TaskCategory.ESSAY,
        priority=TaskPriority.HIGH,
        due_month=10,
        due_day=5,
    )
    TaskTemplate.objects.create(
        title="Подать Regular Decision", category=TaskCategory.UNIVERSITY, due_month=1, due_day=15
    )

    result = generate_from_templates(three_applicants)
    assert result.created == 6

    student = three_applicants[0]
    essay_task = student.tasks.get(title="Черновик Personal Statement")
    # сентябрь–декабрь относятся к году перед выпуском
    assert essay_task.due_date == date(2026, 10, 5)
    rd_task = student.tasks.get(title="Подать Regular Decision")
    assert rd_task.due_date == date(2027, 1, 15)


@pytest.mark.django_db
def test_template_filters_by_graduation_year(three_applicants):
    TaskTemplate.objects.create(title="Только для 2028", category=TaskCategory.TEST, graduation_year=2028)
    result = generate_from_templates(three_applicants)
    assert result.created == 0


@pytest.mark.django_db
def test_generate_all_through_api(api, asem, three_applicants):
    TaskTemplate.objects.create(title="Сдать мок", category=TaskCategory.TEST, due_month=9, due_day=12)
    api.force_authenticate(asem)
    response = api.post("/api/roadmap/generate/", {"graduation_year": 2027}, format="json")
    assert response.status_code == 200
    assert response.data["templates"]["created"] == 3
    assert response.data["deadlines"]["created"] == 3


@pytest.mark.django_db
def test_student_cannot_generate_roadmap(api, make_user, three_applicants):
    student = three_applicants[0]
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    api.force_authenticate(user)
    assert api.post("/api/roadmap/generate/", {}, format="json").status_code == 403


# --- Доска и таймлайн ---


@pytest.mark.django_db
def test_student_sees_only_own_tasks(api, make_user, three_applicants):
    generate_from_deadlines(three_applicants)
    student = three_applicants[0]
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])

    api.force_authenticate(user)
    tasks = api.get("/api/tasks/my/").data
    assert len(tasks) == 1
    assert tasks[0]["student"] == student.pk


@pytest.mark.django_db
def test_status_change_marks_completion(api, asem, three_applicants):
    generate_from_deadlines(three_applicants)
    task = Task.objects.first()
    api.force_authenticate(asem)

    response = api.post(f"/api/tasks/{task.pk}/status/", {"status": "done"}, format="json")
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.status == "done"
    assert task.completed_at is not None

    api.post(f"/api/tasks/{task.pk}/status/", {"status": "in_progress"}, format="json")
    task.refresh_from_db()
    assert task.completed_at is None


# --- Эссе ---


@pytest.mark.django_db
def test_essay_versions_are_numbered_by_server(api, make_user, three_applicants):
    student = three_applicants[0]
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    essay = Essay.objects.create(student=student, essay_type=EssayType.PERSONAL_STATEMENT, title="Personal Statement")

    api.force_authenticate(user)
    first = api.post(f"/api/essays/{essay.pk}/versions/", {"text": "Первый черновик из трёх слов"}, format="json")
    second = api.post(f"/api/essays/{essay.pk}/versions/", {"text": "Второй вариант"}, format="json")

    assert first.data["number"] == 1
    assert first.data["word_count"] == 5
    assert second.data["number"] == 2
    assert essay.versions.count() == 2


@pytest.mark.django_db
def test_essay_is_private_to_its_student(api, make_user, three_applicants):
    owner, other = three_applicants[0], three_applicants[1]
    essay = Essay.objects.create(student=owner, essay_type=EssayType.MOTIVATION, title="Моё эссе")

    other_user = make_user("student", other.email)
    other.user = other_user
    other.save(update_fields=["user"])

    api.force_authenticate(other_user)
    assert api.get(f"/api/essays/{essay.pk}/").status_code == 404


@pytest.mark.django_db
def test_curator_comments_on_essay(api, asem, three_applicants):
    essay = Essay.objects.create(
        student=three_applicants[0], essay_type=EssayType.PERSONAL_STATEMENT, title="PS", status=EssayStatus.REVIEW
    )
    api.force_authenticate(asem)
    response = api.post(
        "/api/essay-comments/", {"essay": essay.pk, "text": "Раскрой историю про олимпиаду"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["author_name"] == "Асем"
