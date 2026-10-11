"""Профориентация без оценок: «тест сдан DD.MM» или «не сдан» (решение владельца, 11.10.2026).

* сдан — попытка сдана и готов разбор (по умолчанию); правила школы снимают
  требование разбора и задают минимальный балл;
* попытка не позже конца периода, когда бы её ни сдали;
* в журнале предмета оценок нет: запись отвечает 403, строка несёт «сдан»;
* у ученика в «Оценках» и в отчётах родителям — одна строка.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from academics.models import AcademicYear, Quarter, ReportSettings, ReportTemplate
from academics.school_reports import CAREER_TEST, build_lines
from career.models import AnalysisStatus, CareerAnalysis, CareerAttempt
from career.passing import pass_map, passed_at
from career.tests.conftest import activate, answer_all, login

pytestmark = pytest.mark.django_db


@pytest.fixture
def year(db):
    day = timezone.localdate()
    year = AcademicYear.objects.create(
        title="2026–2027", starts=day - dt.timedelta(days=60), ends=day + dt.timedelta(days=260), is_current=True
    )
    Quarter.objects.create(
        year=year, number=1, title="1 четверть", starts=day - dt.timedelta(days=60), ends=day + dt.timedelta(days=40)
    )
    ReportSettings.objects.create(year=year)
    return year


@pytest.fixture
def attempt(karta, teacher, boston, pupils):
    """Алия сдала «Карту интересов», разбора пока нет."""
    activate(karta, [{"group": boston.pk}], by=teacher)
    client = login(pupils["aliya"].user)
    number = client.post(f"/api/career/my/tests/{karta.pk}/start/").json()["id"]
    answer_all(client, number, lambda n: {1: "++", 2: "−−"}.get((n - 1) % 24 + 1, "0"))
    assert client.post(f"/api/career/my/attempts/{number}/finish/").status_code == 200
    return CareerAttempt.objects.get(pk=number)


def analysed(attempt, teacher):
    row = CareerAnalysis.objects.create(
        student=attempt.student,
        fingerprint=str(attempt.pk),
        status=AnalysisStatus.DONE,
        created_by=teacher,
        finished_at=timezone.now(),
    )
    row.attempts.add(attempt)
    return row


# --- Что считается сданным ---------------------------------------------------------


def test_by_default_pass_needs_a_finished_attempt_and_a_ready_analysis(attempt, teacher, pupils):
    today = timezone.localdate()
    assert passed_at(attempt.student_id, today) is None, "без разбора не сдан"
    analysed(attempt, teacher)
    assert passed_at(attempt.student_id, today) == timezone.localtime(attempt.finished_at).date()
    assert passed_at(pupils["damir"].pk, today) is None


def test_school_can_drop_the_analysis_and_set_a_score_threshold(attempt, set_rules):
    today = timezone.localdate()
    set_rules(career_pass_needs_analysis=0)
    assert passed_at(attempt.student_id, today) is not None
    # сильнейшая шкала — биология, 12 баллов
    set_rules(career_pass_min_score=12)
    assert passed_at(attempt.student_id, today) is not None
    set_rules(career_pass_min_score=13)
    assert passed_at(attempt.student_id, today) is None


def test_attempt_counts_up_to_the_end_of_the_period_whenever_it_was_taken(attempt, set_rules):
    set_rules(career_pass_needs_analysis=0)
    day = timezone.localtime(attempt.finished_at).date()
    assert passed_at(attempt.student_id, day) == day
    assert passed_at(attempt.student_id, day + dt.timedelta(days=400)) == day, "сдан раз — сдан и через год"
    assert passed_at(attempt.student_id, day - dt.timedelta(days=1)) is None
    assert pass_map([attempt.student_id, 10**6], day) == {attempt.student_id: day, 10**6: None}


def test_archived_attempt_does_not_count(attempt, set_rules):
    set_rules(career_pass_needs_analysis=0)
    attempt.archived_at = timezone.now()
    attempt.save(update_fields=["archived_at"])
    assert passed_at(attempt.student_id, timezone.localdate()) is None


# --- Журнал и оценки -----------------------------------------------------------------


@pytest.fixture
def lesson(year, teacher, boston, career_subject):
    from academics.cohorts import group_cohort
    from academics.models import Course
    from academics.schedule import create_once

    course = Course.objects.get(subject=career_subject, cohort=group_cohort(boston))
    return create_once(
        subject=career_subject,
        teacher=teacher,
        cohort=course.cohort,
        date=timezone.localdate() - dt.timedelta(days=1),
        slot=1,
        room="101",
    )


def test_journal_has_no_grades_but_shows_who_passed(lesson, attempt, teacher, set_rules, pupils):
    set_rules(career_pass_needs_analysis=0)
    client = login(teacher)
    data = client.get(f"/api/acad/journals/{lesson.course_id}/").json()
    assert data["pass_only"] is True
    assert all(column["may_grade"] is False for column in data["columns"])
    by_id = {row["id"]: row for row in data["rows"]}
    assert (
        by_id[pupils["aliya"].pk]["career"]["passed_at"] == timezone.localtime(attempt.finished_at).date().isoformat()
    )
    assert by_id[pupils["damir"].pk]["career"]["passed_at"] is None
    refused = client.post(
        f"/api/acad/lessons/{lesson.pk}/grade/", {"student": pupils["aliya"].pk, "value": 9}, format="json"
    )
    assert refused.status_code == 403 and "сдан" in refused.json()["detail"]
    # посещаемость у профориентации остаётся
    marked = client.post(
        f"/api/acad/lessons/{lesson.pk}/attendance/",
        {"rows": [{"student": pupils["aliya"].pk, "mark": "absent"}]},
        format="json",
    )
    assert marked.status_code == 200, marked.content
    detail = client.get(f"/api/acad/lessons/{lesson.pk}/").json()
    assert detail["pass_only"] is True and detail["may_grade"] is False


def test_student_and_curator_see_the_line_in_grades(lesson, attempt, teacher, curator, set_rules, pupils):
    set_rules(career_pass_needs_analysis=0)
    day = timezone.localtime(attempt.finished_at).date().isoformat()
    mine = login(pupils["aliya"].user).get("/api/acad/me/grades/").json()
    rows = [row for row in mine["subjects"] if row["course"]["subject"]["is_career"]]
    assert rows and rows[0]["career"]["passed_at"] == day
    staff = login(curator).get(f"/api/acad/students/{pupils['damir'].pk}/grades/").json()
    rows = [row for row in staff["subjects"] if row["course"]["subject"]["is_career"]]
    assert rows and rows[0]["career"]["passed_at"] is None


# --- Отчёты родителям ----------------------------------------------------------------


def test_school_report_carries_one_line_and_no_fo_row(lesson, attempt, teacher, set_rules, pupils):
    set_rules(career_pass_needs_analysis=0)
    today = timezone.localdate()
    start = today - dt.timedelta(days=30)
    lines = build_lines(pupils["aliya"], template=ReportTemplate.REVIEW, language="ru", start=start, end=today)
    career = [line for line in lines if line["code"] == CAREER_TEST]
    assert len(career) == 1
    assert career[0]["title"] == "Профориентационный тест"
    assert career[0]["value"] == f"сдан {timezone.localtime(attempt.finished_at).date():%d.%m.%Y}"
    assert not [line for line in lines if line["code"] == "grade" and "Профориентац" in line["title"]]
    lines = build_lines(pupils["damir"], template=ReportTemplate.PROGRESS, language="kk", start=start, end=today)
    assert [line["value"] for line in lines if line["code"] == CAREER_TEST] == ["не сдан"]


def test_standard_report_says_passed_or_not(lesson, attempt, teacher, set_rules, pupils, year):
    from academics import calendar as school_calendar
    from academics.reports import build_lines as standard_lines

    set_rules(career_pass_needs_analysis=0)
    today = timezone.localdate()
    calendar = school_calendar.load(year)
    config = ReportSettings.objects.get(year=year)
    lines = standard_lines(
        pupils["aliya"], start=today - dt.timedelta(days=30), end=today, calendar=calendar, config=config
    )
    row = next(line for line in lines if line["section"] == "grades" and line["title"] == "Профориентация")
    assert row["value"].startswith("тест сдан ")
    lines = standard_lines(
        pupils["damir"], start=today - dt.timedelta(days=30), end=today, calendar=calendar, config=config
    )
    row = next(line for line in lines if line["section"] == "grades" and line["title"] == "Профориентация")
    assert row["value"] == "тест не сдан"
