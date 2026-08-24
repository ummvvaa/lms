"""Дашборды: содержание и скорость на реальном объёме."""

from __future__ import annotations

import time

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from directories.models import SportType
from students.models import (
    Activity,
    ActivityCategory,
    AdmissionProfile,
    BehaviorProfile,
    Competition,
    ExamAttempt,
    ExamProfile,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)
from universities.models import (
    AdmissionRound,
    Program,
    StudentUniversity,
    University,
)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def school(db):
    """250 учеников — рабочий объём школы."""
    groups = [StudyGroup.objects.create(code=f"G{i:02d}", grade=10 + i % 2) for i in range(14)]
    university = University.objects.create(name="Test University", country="Канада", domain="test.ca")
    program = Program.objects.create(university=university, name="Computer Science")
    round_ = AdmissionRound.objects.create(program=program, round_type="RD", deadline="2027-01-15")
    football = SportType.objects.create(name="Футбол", category="team")

    students = []
    for i in range(250):
        s = Student.objects.create(
            last_name=f"Фамилия{i:03d}",
            first_name=f"Имя{i:03d}",
            email=f"s{i:03d}@school.kz",
            grade=10 + i % 2,
            group=groups[i % 14],
            graduation_year=2027,
        )
        BehaviorProfile.objects.create(
            student=s,
            attendance_percent=72 + i % 28,
            homework_percent=50 + i % 50,
            remarks_count=i % 4,
            status=("critical", "needs_supervision", "can_execute")[i % 3],
        )
        AdmissionProfile.objects.create(
            student=s,
            has_common_app=i % 2 == 0,
            has_application_account=i % 3 == 0,
            status=("A", "B", "C")[i % 3],
            target_country="Канада",
        )
        ExamProfile.objects.create(
            student=s,
            ielts_current=5.0 + (i % 9) * 0.5,
            ielts_target=8.0,
            sat_current=1000 + (i % 12) * 50,
            sat_target=1500,
        )
        TalentProfile.objects.create(
            student=s,
            main_track=("olympiad", "research", "startup", "leadership", "volunteering", "competition")[i % 6],
            portfolio_status=("strong", "medium", "weak")[i % 3],
        )
        SportProfile.objects.create(
            student=s,
            sport_type=football if i % 2 else None,
            level=("school", "city", "regional", "national")[i % 4],
        )
        if i % 3 == 0:
            Activity.objects.create(student=s, category=ActivityCategory.PROJECT, title=f"Проект {i}")
        if i % 2:
            Competition.objects.create(
                student=s, name="Городская спартакиада", date="2026-10-12", has_certificate=i % 4 == 1
            )
        if i % 5 == 0:
            StudentUniversity.objects.create(student=s, program=program, admission_round=round_, tier="target")
        # история моков строками — по ним считается падение
        ExamAttempt.objects.create(
            student=s, exam_type="SAT", attempt_format="mock", date="2026-06-01", total_score=1200
        )
        ExamAttempt.objects.create(
            student=s,
            exam_type="SAT",
            attempt_format="mock",
            date="2026-08-01",
            total_score=1200 - (60 if i % 7 == 0 else -20),
        )
        students.append(s)
    return students


@pytest.mark.django_db
@pytest.mark.parametrize("code", ["behavior", "admission", "exam", "talent", "sport"])
def test_dashboard_loads_under_a_second(api, make_user, school, code):
    """Критерий приёмки: дашборд грузится меньше секунды на 250 учениках."""
    role = {
        "behavior": "director_behavior",
        "admission": "director_admission",
        "exam": "director_exam",
        "talent": "director_talent",
        "sport": "director_sport",
    }[code]
    api.force_authenticate(make_user(role, f"{role}@school.kz"))

    started = time.perf_counter()
    response = api.get(f"/api/dashboards/{code}/")
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 1.0, f"дашборд {code} собирался {elapsed:.2f} с"


@pytest.mark.django_db
def test_dashboard_does_not_run_query_per_student(api, make_user, school):
    """Агрегаты считаются в базе, а не перебором 250 строк в память."""
    api.force_authenticate(make_user("director_behavior", "s@school.kz"))
    with CaptureQueriesContext(connection) as queries:
        api.get("/api/dashboards/behavior/")
    assert len(queries) < 30, f"запросов слишком много: {len(queries)}"


@pytest.mark.django_db
def test_behavior_dashboard_content(api, make_user, school):
    api.force_authenticate(make_user("director_behavior", "saltanat@school.kz"))
    body = api.get("/api/dashboards/behavior/").data
    assert body["total"] == 250
    assert sum(body["traffic"].values()) == 250
    assert len(body["worst_attendance"]) == 20
    assert len(body["groups"]) == 14
    # худшие идут первыми
    values = [row["attendance_percent"] for row in body["worst_attendance"]]
    assert values == sorted(values)


@pytest.mark.django_db
def test_exam_dashboard_buckets_and_drops(api, make_user, school):
    api.force_authenticate(make_user("director_exam", "kymbat@school.kz"))
    body = api.get("/api/dashboards/exam/").data
    buckets = body["buckets"]
    assert buckets["ielts_low"] + buckets["ielts_mid"] + buckets["ielts_high"] == 250
    assert buckets["sat_low"] + buckets["sat_mid"] + buckets["sat_high"] == 250
    # падения моков видны из истории попыток, а не из поля профиля
    assert body["mock_drops"]
    assert all(row["delta"] < 0 for row in body["mock_drops"])


@pytest.mark.django_db
def test_admission_dashboard_counts_slots_and_deadlines(api, make_user, school):
    api.force_authenticate(make_user("director_admission", "asem@school.kz"))
    body = api.get("/api/dashboards/admission/").data
    assert body["slots"] == 50
    assert body["slots_target"] == 750
    assert sum(body["statuses"].values()) == 250
    assert body["no_common_app"]


@pytest.mark.django_db
def test_overview_only_for_admin(api, make_user, school):
    api.force_authenticate(make_user("director_exam", "k@school.kz"))
    assert api.get("/api/dashboards/overview/").status_code == 403

    api.force_authenticate(make_user("admin", "director@school.kz"))
    body = api.get("/api/dashboards/overview/").data
    assert body["total"] == 250
    assert 0 <= body["average_readiness"] <= 100


@pytest.mark.django_db
def test_student_gets_no_dashboards(api, make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    api.force_authenticate(user)
    assert api.get("/api/dashboards/behavior/").status_code == 403
