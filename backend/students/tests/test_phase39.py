"""Фаза 39: цели по экзаменам, календарь, напоминания, автозадачи."""

from __future__ import annotations

import datetime as dt

import pytest
from rest_framework.test import APIClient

from core.models import Notification
from directories.models import ExamKind
from roadmap.reminders import create_registration_tasks, send_event_reminders
from students.calendar_feed import state as calendar_state
from students.models import ExamGoal


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
def kymbat(make_user):
    return make_user("director_exam", "kymbat@school.kz", full_name="Кымбат")


def ielts() -> ExamKind:
    return ExamKind.objects.get(name="IELTS")


# --- Справочник экзаменов --------------------------------------------------


@pytest.mark.django_db
def test_seven_exams_seeded_and_ent_is_among_them():
    names = set(ExamKind.objects.values_list("name", flat=True))
    assert {"IELTS", "TOEFL", "SAT", "ACT", "ЕНТ", "Duolingo", "HSK"} <= names


@pytest.mark.django_db
def test_exam_directory_is_led_by_exam_director(api, kymbat, make_user):
    api.force_authenticate(kymbat)
    made = api.post("/api/exam-kinds/", {"name": "GRE", "max_score": 340}, format="json")
    assert made.status_code == 201

    api.force_authenticate(make_user("director_sport", "n@school.kz"))
    assert api.post("/api/exam-kinds/", {"name": "Чужой"}, format="json").status_code == 403


# --- Цель: ученик предлагает, директор подтверждает ------------------------


def propose_goal(api, user, **values):
    rows = [
        {"model": "students.ExamGoal", "field": field, "value": value, "new_object_key": "g1"}
        for field, value in values.items()
    ]
    api.force_authenticate(user)
    return api.post("/api/suggestions/propose/", {"rows": rows}, format="json")


@pytest.mark.django_db
def test_goal_flows_from_student_to_exam_director(api, student_user, student, kymbat):
    response = propose_goal(api, student_user, exam="IELTS", target_score="7.0", exam_date="2027-03-20")
    assert response.status_code == 201, response.data
    assert ExamGoal.objects.count() == 0  # до решения записи нет

    from suggestions.models import Suggestion

    suggestion = Suggestion.objects.get()
    assert suggestion.domain_code == "exam"

    api.force_authenticate(kymbat)
    result = api.post(f"/api/suggestions/{suggestion.pk}/review/", {"decision": "confirm"}, format="json")
    assert result.status_code == 200, result.data

    goal = ExamGoal.objects.get()
    assert goal.student == student
    assert goal.exam.name == "IELTS"
    assert float(goal.target_score) == 7.0
    assert goal.exam_date == dt.date(2027, 3, 20)


# --- Календарь -------------------------------------------------------------


@pytest.mark.django_db
def test_calendar_collects_events_with_nearest_countdown(student, kymbat):
    today = dt.date(2027, 1, 10)
    ExamGoal.objects.create(student=student, exam=ielts(), target_score=7, exam_date=today + dt.timedelta(days=20))
    payload = calendar_state(student, today)
    titles = [e["title"] for e in payload["events"]]
    assert any("Экзамен: IELTS" in title for title in titles)
    assert payload["nearest"]["days_left"] == 20


@pytest.mark.django_db
def test_pending_goal_shows_in_calendar_as_waiting(api, student_user, student):
    propose_goal(api, student_user, exam="IELTS", exam_date="2027-03-20")
    payload = calendar_state(student, dt.date(2027, 1, 10))
    pending = [e for e in payload["events"] if e["pending"]]
    assert pending and "IELTS" in pending[0]["title"]


@pytest.mark.django_db
def test_calendar_answers_both_the_student_and_the_staff(api, student_user, kymbat):
    """У ученика свой календарь, у сотрудника — школьный (фаза 49).

    До фазы 49 сотруднику здесь отвечали 403: карточки ученика у него нет,
    а календарь строился только по ней. Но директору календарь нужен свой —
    события его учеников с числом сдающих, — и отказ был не запретом,
    а недостачей. Личных задач конкретного ребёнка в школьном нет.
    """
    api.force_authenticate(kymbat)
    staff = api.get("/api/calendar/")
    assert staff.status_code == 200
    assert all(event["kind"] != "task" for event in staff.json()["events"])

    api.force_authenticate(student_user)
    assert api.get("/api/calendar/").status_code == 200


# --- Автозадача о регистрации ----------------------------------------------


@pytest.mark.django_db
def test_registration_task_is_created_and_follows_the_goal(student):
    today = dt.date(2027, 1, 10)
    goal = ExamGoal.objects.create(student=student, exam=ielts(), exam_date=today + dt.timedelta(days=25))
    assert create_registration_tasks(today) == 1
    assert create_registration_tasks(today) == 0  # повторный запуск не дублирует

    task = goal.tasks.get()
    assert "Зарегистрироваться" in task.title
    assert task.effective_due_date == goal.exam_date

    # сдвиг даты экзамена сдвигает срок задачи: дата не копировалась (инвариант №4)
    goal.exam_date = goal.exam_date + dt.timedelta(days=10)
    goal.save(update_fields=["exam_date"])
    task.refresh_from_db()
    assert task.effective_due_date == goal.exam_date

    # появилась дата регистрации — срок считается по ней
    goal.registration_date = today + dt.timedelta(days=5)
    goal.save(update_fields=["registration_date"])
    task.refresh_from_db()
    assert task.effective_due_date == goal.registration_date


@pytest.mark.django_db
def test_far_exam_does_not_create_task_yet(student):
    today = dt.date(2027, 1, 10)
    ExamGoal.objects.create(student=student, exam=ielts(), exam_date=today + dt.timedelta(days=90))
    assert create_registration_tasks(today) == 0


# --- Напоминания -----------------------------------------------------------


@pytest.mark.django_db
def test_reminder_arrives_n_days_before_and_once_a_day(student_user, student):
    today = dt.date(2027, 1, 10)
    ExamGoal.objects.create(student=student, exam=ielts(), exam_date=today + dt.timedelta(days=14))

    assert send_event_reminders(today) == 1
    note = Notification.objects.get(recipient=student_user)
    assert note.kind == "event_reminder"
    assert "IELTS" in note.text

    # повторный запуск в тот же день ничего не дублирует
    assert send_event_reminders(today) == 0


@pytest.mark.django_db
def test_deadline_reminder_uses_its_own_horizon(student_user, student):
    from universities.models import AdmissionRound, Program, RoundType, StudentUniversity, University

    today = dt.date(2027, 1, 10)
    university = University.objects.create(name="Тест", country="Казахстан")
    program = Program.objects.create(university=university, name="CS", level="bachelor")
    round_row = AdmissionRound.objects.create(
        program=program, round_type=RoundType.RD, deadline=today + dt.timedelta(days=14)
    )
    StudentUniversity.objects.create(student=student, program=program, admission_round=round_row)

    assert send_event_reminders(today) == 1
    assert "Дедлайн" in Notification.objects.get(recipient=student_user).text


# --- Директору -------------------------------------------------------------


@pytest.mark.django_db
def test_attention_lists_for_exam_director(api, student, kymbat, make_user):
    api.force_authenticate(kymbat)
    payload = api.get("/api/exam-goals/attention/").data
    assert any(row["name"] == student.full_name for row in payload["no_goals"])

    from django.utils import timezone

    today = timezone.localdate()
    ExamGoal.objects.create(student=student, exam=ielts(), exam_date=today + dt.timedelta(days=3))
    payload = api.get("/api/exam-goals/attention/").data
    assert not any(row["name"] == student.full_name for row in payload["no_goals"])
    assert any(row["exam"] == "IELTS" for row in payload["exam_this_week"])
    assert any(row["exam"] == "IELTS" for row in payload["not_registered"])

    api.force_authenticate(make_user("director_sport", "n2@school.kz"))
    assert api.get("/api/exam-goals/attention/").status_code == 403


# --- «Если сдашь на цель» --------------------------------------------------


@pytest.mark.django_db
def test_goal_score_participates_in_matching(api, student_user, student):
    from universities.matching import at_goal
    from universities.models import AdmissionRequirement, Program, University

    university = University.objects.create(name="Целевой", country="Казахстан")
    program = Program.objects.create(university=university, name="CS", level="bachelor")
    AdmissionRequirement.objects.create(program=program, min_ielts=7.0)

    student.exam.ielts_current = 6.0
    student.exam.save()
    ExamGoal.objects.create(student=student, exam=ielts(), target_score=7.0)

    payload = at_goal(student)
    assert payload["available"]
    assert payload["open_after"] > payload["open_before"]
    assert any(row["program"] == program.pk for row in payload["unlocked"])

    api.force_authenticate(student_user)
    assert api.get("/api/match/at-goal/").status_code == 200
