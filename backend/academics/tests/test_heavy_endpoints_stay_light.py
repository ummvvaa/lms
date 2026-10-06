"""Тяжёлые экраны учёбы не раздуваются (06.10.2026, блок F).

На проде «Журналы», «Успеваемость» и «Расписание» грузились долго:
`grades/school/` — 383 КБ и по запросу на урок, `journals/<id>/` — 61 КБ
на двух учеников. Здесь сторожится, что журнал читает только свои уроки,
список уроков в нём короткий, а успеваемость школы читает уроки, отметки,
оценки и ДЗ по одному разу, а не на каждый курс.
"""

from __future__ import annotations

import pytest

from academics.models import Course, Lesson
from academics.schedule import create_once
from academics.tests.conftest import school_day

pytestmark = pytest.mark.django_db


@pytest.fixture
def busy_school(year, subjects, teacher, other_teacher, cohorts, calendar, pupils):
    """Два курса с уроками у двух учителей: чужие уроки журналу читать незачем."""
    for back in range(1, 6):
        create_once(
            subject=subjects["alg"],
            teacher=teacher,
            cohort=cohorts["boston"],
            date=school_day(-back, calendar),
            slot=1,
            room="204",
        )
        create_once(
            subject=subjects["eng"],
            teacher=other_teacher,
            cohort=cohorts["chicago"],
            date=school_day(-back, calendar),
            slot=2,
            room="305",
        )
    return Course.objects.get(subject=subjects["alg"], cohort=cohorts["boston"])


def test_journal_reads_only_its_own_lessons_and_lists_them_briefly(
    busy_school, as_teacher, django_assert_max_num_queries
):
    with django_assert_max_num_queries(40):
        answer = as_teacher.get(f"/api/acad/journals/{busy_school.pk}/")
    assert answer.status_code == 200
    body = answer.json()
    assert len(body["all_lessons"]) == 5
    assert set(body["all_lessons"][0]) == {
        "id",
        "date",
        "weekday",
        "slot",
        "kind",
        "kind_label",
        "state",
        "is_live",
        "marked",
        "topic",
    }
    assert all(
        lesson["id"] in {row.pk for row in Lesson.objects.filter(course=busy_school)} for lesson in body["all_lessons"]
    )


def test_school_grades_read_the_school_once_not_per_course(busy_school, as_kymbat, django_assert_max_num_queries):
    # 40 запросов на два курса — прежний путь давал по два-три на курс и по одному на урок
    with django_assert_max_num_queries(45):
        answer = as_kymbat.get("/api/acad/grades/school/?period=q1")
    assert answer.status_code == 200
    body = answer.json()
    assert body["kpis"]["empty_journals"] == 2 and len(body["empty_journals"]) == 2
    row = body["empty_journals"][0]
    assert set(row) == {"id", "title", "teacher"} and " · " in row["title"] and row["teacher"]["full_name"]


def test_teacher_today_does_not_ask_per_lesson(busy_school, as_teacher, django_assert_max_num_queries):
    with django_assert_max_num_queries(45):
        answer = as_teacher.get("/api/acad/teacher/today/")
    assert answer.status_code == 200
