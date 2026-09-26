"""Три сквозные цепочки из `docs/academics.md` — на уровне API.

1. Учитель ставит «н» → куратор видит пропуск → оформляет причину за период →
   в журнале учителя «у».
2. Кымбат добавляет урок подгруппе → урок есть у учителя и только у учеников
   этой подгруппы.
3. Отчёт собрался → куратор проверил и скачал PDF → статус «выгружен»
   с датой → отметка «отправлен родителям».
"""

from __future__ import annotations

import pytest

from academics import reports as reporting
from academics.models import ParentReport, ReportPeriod, ReportStatus
from academics.tests.conftest import days, login, school_day

pytestmark = pytest.mark.django_db


def test_chain_absent_to_excused(lesson, pupils, teacher, curator, boston, as_teacher, as_curator):
    # 1. учитель ставит «н»
    marked = as_teacher.post(
        f"/api/acad/lessons/{lesson.pk}/attendance/",
        {"rows": [{"student": pupils["aliya"].pk, "mark": "absent"}]},
        format="json",
    )
    assert marked.status_code == 200
    # 2. куратор видит пропуск в посещаемости группы за день
    sheet = as_curator.get(f"/api/acad/attendance/?group={boston.code}&date={lesson.date}").json()
    row = next(r for r in sheet["rows"] if r["id"] == pupils["aliya"].pk)
    cell = next(c for c in row["cells"] if c.get("has_lesson"))
    assert cell["mark"] == "absent" and row["absent"] == 1
    # 3. оформляет уважительную причину за период
    excuse = as_curator.post(
        "/api/acad/excuses/",
        {
            "student": pupils["aliya"].pk,
            "starts": str(lesson.date),
            "ends": str(lesson.date),
            "reason": "Болезнь",
            "document": "certificate",
        },
        format="json",
    )
    assert excuse.status_code == 201
    # 4. в журнале учителя — «у»
    journal = as_teacher.get(f"/api/acad/journals/{lesson.course.pk}/?period=q1").json()
    row = next(r for r in journal["rows"] if r["id"] == pupils["aliya"].pk)
    assert row["cells"][0]["mark"] == "excused"
    assert row["stats"]["excused"] == 1 and row["stats"]["absent"] == 0
    detail = as_teacher.get(f"/api/acad/lessons/{lesson.pk}/").json()
    aliya = next(r for r in detail["roster"] if r["id"] == pupils["aliya"].pk)
    assert aliya["mark"] == "excused" and aliya["excused"] is True


def test_chain_subgroup_lesson_reaches_teacher_and_its_students_only(
    year, subjects, other_teacher, cohorts, pupils, calendar, as_kymbat
):
    day = school_day(1, calendar)
    created = as_kymbat.post(
        "/api/acad/lessons/",
        {
            "subject": subjects["eng"].pk,
            "teacher": other_teacher.pk,
            "cohort": cohorts["eng1"].pk,
            "date": str(day),
            "slot": 4,
            "room": "305",
            "repeat": "weekly",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    lesson_id = created.json()["lesson"]["id"]
    # у учителя урок есть
    week = login(other_teacher).get(f"/api/acad/lessons/?from={day}&to={day}").json()
    assert any(row["id"] == lesson_id for row in week["lessons"])
    # у ученика первой подгруппы есть, у ученика второй — нет
    aliya = login(pupils["aliya"].user).get(f"/api/acad/me/lessons/?date={day}").json()
    assert any(row["id"] == lesson_id for row in aliya["lessons"])
    from students.models import Student

    nurai = pupils["nurai"]
    from academics.tests.conftest import make_student

    del make_student
    nurai_user = __import__("accounts.models", fromlist=["User"]).User.objects.create_user(
        email="nurai.user@example.kz", password="pass12345", role="student", must_change_password=False
    )
    Student.objects.filter(pk=nurai.pk).update(user=nurai_user)
    nurai_week = login(nurai_user).get(f"/api/acad/me/lessons/?date={day}").json()
    assert not any(row["id"] == lesson_id for row in nurai_week["lessons"])
    # состав урока — только первая подгруппа
    detail = as_kymbat.get(f"/api/acad/lessons/{lesson_id}/").json()
    assert {row["id"] for row in detail["roster"]} == {pupils["aliya"].pk, pupils["damir"].pk}


def test_chain_report_built_checked_downloaded_sent(
    lesson, pupils, teacher, parent, calendar, admin, as_curator, as_teacher
):
    as_teacher.post(f"/api/acad/lessons/{lesson.pk}/grade/", {"student": pupils["aliya"].pk, "value": 9}, format="json")
    start, end = reporting.month_bounds(days(0))
    reporting.build_for_period(kind=ReportPeriod.MONTH, start=start, end=end, calendar=calendar, actor=admin)
    report = ParentReport.objects.get(student=pupils["aliya"], period_kind=ReportPeriod.MONTH, period_start=start)
    listed = as_curator.get("/api/acad/reports/").json()
    row = next(r for r in listed["rows"] if r["id"] == report.pk)
    assert row["status"] == ReportStatus.DRAFT and listed["counts"]["draft"] >= 1
    checked = as_curator.post(f"/api/acad/reports/{report.pk}/check/", {"curator_word": "Алия молодец"}, format="json")
    assert checked.status_code == 200 and checked.json()["status"] == ReportStatus.CHECKED
    pdf = as_curator.get(f"/api/acad/reports/{report.pk}/pdf/")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    report.refresh_from_db()
    assert report.status == ReportStatus.EXPORTED and report.exported_at is not None
    sent = as_curator.post("/api/acad/reports/sent/", {"ids": [report.pk]}, format="json").json()
    assert sent["sent"] == 1
    report.refresh_from_db()
    assert report.status == ReportStatus.SENT and report.sent_at is not None
    detail = as_curator.get(f"/api/acad/reports/{report.pk}/").json()
    assert detail["status_title"] == "Отправлен родителям" and detail["sent_by"] == "Асель Куратор"
