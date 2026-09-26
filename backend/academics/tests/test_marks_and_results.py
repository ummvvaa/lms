"""Посещаемость, оценки, уважительная причина, окно правки, формула и итоги четверти."""

from __future__ import annotations

import datetime as dt

import pytest

from academics import marks as marking
from academics import results
from academics.calendar import scale_of
from academics.models import Attendance, Grade, GradingScale, LessonKind, Quarter, QuarterResult
from academics.schedule import create_once
from academics.tests.conftest import days, school_day
from core.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def scale(year):
    return GradingScale.objects.get(year=year)


# --- Посещаемость ----------------------------------------------------------------


def test_teacher_marks_only_the_absent_and_the_rest_are_present(lesson, pupils, teacher, calendar, as_teacher):
    response = as_teacher.post(
        f"/api/acad/lessons/{lesson.pk}/attendance/",
        {"rows": [{"student": pupils["aliya"].pk, "mark": "absent"}, {"student": pupils["damir"].pk, "mark": "late"}]},
        format="json",
    )
    assert response.status_code == 200, response.content
    roster = {row["id"]: row["mark"] for row in response.json()["roster"]}
    assert roster[pupils["aliya"].pk] == "absent"
    assert roster[pupils["damir"].pk] == "late"
    assert roster[pupils["nurai"].pk] == "present", "без строки — был"
    lesson.refresh_from_db()
    assert lesson.is_marked and lesson.marked_by_id == teacher.pk
    assert AuditLog.objects.filter(
        model_label="academics.Attendance", field_name="mark", new_value="absent", actor=teacher
    ).exists()


def test_all_present_clears_the_marks(lesson, pupils, teacher, calendar, as_teacher):
    Attendance.objects.create(lesson=lesson, student=pupils["aliya"], mark="absent")
    response = as_teacher.post(f"/api/acad/lessons/{lesson.pk}/attendance/", {"all_present": True}, format="json")
    assert response.status_code == 200
    assert not Attendance.objects.filter(lesson=lesson).exists()
    lesson.refresh_from_db()
    assert lesson.is_marked


def test_future_lesson_cannot_be_marked(year, subjects, teacher, cohorts, calendar, as_teacher, pupils):
    future = create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(5, calendar),
        slot=2,
        room="204",
    )
    response = as_teacher.post(f"/api/acad/lessons/{future.pk}/attendance/", {"all_present": True}, format="json")
    assert response.status_code == 400 and "впереди" in response.json()["detail"]


def test_teacher_has_no_excused_mark(lesson, pupils, teacher, calendar, as_teacher):
    as_teacher.post(
        f"/api/acad/lessons/{lesson.pk}/attendance/",
        {"rows": [{"student": pupils["aliya"].pk, "mark": "excused"}]},
        format="json",
    )
    assert not Attendance.objects.filter(lesson=lesson).exists(), "«у» учитель поставить не может — строка отброшена"


def test_excuse_turns_absent_into_excused_without_touching_rows(lesson, pupils, curator, teacher, calendar):
    Attendance.objects.create(lesson=lesson, student=pupils["aliya"], mark="absent")
    lesson.marked_at = __import__("django.utils.timezone", fromlist=["now"]).now()
    lesson.save()
    before = marking.marks_map([lesson], [pupils["aliya"].pk])
    assert before[(lesson.pk, pupils["aliya"].pk)] == "absent"
    excuse = marking.add_excuse(
        student=pupils["aliya"],
        starts=lesson.date,
        ends=lesson.date,
        reason="Болезнь",
        document="certificate",
        actor=curator,
    )
    after = marking.marks_map([lesson], [pupils["aliya"].pk])
    assert after[(lesson.pk, pupils["aliya"].pk)] == "excused"
    assert Attendance.objects.get(lesson=lesson, student=pupils["aliya"]).mark == "absent", "строка не переписана"
    marking.drop_excuse(excuse, actor=curator)
    again = marking.marks_map([lesson], [pupils["aliya"].pk])
    assert again[(lesson.pk, pupils["aliya"].pk)] == "absent", "сняли причину — снова «н»"
    assert AuditLog.objects.filter(student_id=pupils["aliya"].pk, field_name="excuse").exists()
    assert AuditLog.objects.filter(student_id=pupils["aliya"].pk, field_name="excuse_dropped").exists()


def test_excuse_is_written_by_curator_and_admin_only(lesson, pupils, as_teacher, as_kymbat, as_curator, as_admin):
    payload = {"student": pupils["aliya"].pk, "starts": str(lesson.date), "ends": str(lesson.date), "reason": "Болезнь"}
    assert as_teacher.post("/api/acad/excuses/", payload, format="json").status_code == 404
    assert as_kymbat.post("/api/acad/excuses/", payload, format="json").status_code == 403
    assert as_curator.post("/api/acad/excuses/", payload, format="json").status_code == 201
    assert (
        as_admin.post(
            "/api/acad/excuses/", {**payload, "starts": str(days(-9)), "ends": str(days(-8))}, format="json"
        ).status_code
        == 201
    )


def test_curator_cannot_excuse_a_student_of_another_group(lesson, pupils, as_curator):
    payload = {
        "student": pupils["stranger"].pk,
        "starts": str(lesson.date),
        "ends": str(lesson.date),
        "reason": "Болезнь",
    }
    assert as_curator.post("/api/acad/excuses/", payload, format="json").status_code == 404


# --- Оценки ----------------------------------------------------------------------


def test_grade_to_an_absent_student_makes_them_present(lesson, pupils, teacher, calendar, scale):
    Attendance.objects.create(lesson=lesson, student=pupils["aliya"], mark="absent")
    grade = marking.set_grade(lesson, pupils["aliya"], 8, actor=teacher, calendar=calendar, scale=scale)
    assert grade.value == 8
    assert not Attendance.objects.filter(lesson=lesson, student=pupils["aliya"]).exists()


def test_marking_absent_removes_the_grade(lesson, pupils, teacher, calendar, scale, as_teacher):
    marking.set_grade(lesson, pupils["aliya"], 8, actor=teacher, calendar=calendar, scale=scale)
    response = as_teacher.post(
        f"/api/acad/lessons/{lesson.pk}/attendance/",
        {"rows": [{"student": pupils["aliya"].pk, "mark": "absent"}]},
        format="json",
    )
    assert response.json()["grades_dropped"] == 1
    assert not Grade.objects.filter(lesson=lesson, student=pupils["aliya"]).exists()


def test_fo_grade_is_bounded_and_sor_by_its_maximum(lesson, pupils, teacher, calendar, scale):
    with pytest.raises(marking.MarkRefused):
        marking.set_grade(lesson, pupils["aliya"], 11, actor=teacher, calendar=calendar, scale=scale)
    with pytest.raises(marking.MarkRefused):
        marking.set_grade(lesson, pupils["aliya"], 0, actor=teacher, calendar=calendar, scale=scale)
    marking.set_lesson_meta(lesson, actor=teacher, kind=LessonKind.SOR, number=1, max_score=20)
    with pytest.raises(marking.MarkRefused):
        marking.set_grade(lesson, pupils["aliya"], 21, actor=teacher, calendar=calendar, scale=scale)
    assert marking.set_grade(lesson, pupils["aliya"], 0, actor=teacher, calendar=calendar, scale=scale).value == 0


def test_grade_edit_window_closes_after_seven_days_for_the_teacher_but_not_for_kymbat(
    year, subjects, teacher, cohorts, pupils, calendar, scale, kymbat
):
    old = create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-10, calendar),
        slot=2,
        room="204",
    )
    with pytest.raises(marking.MarkRefused) as error:
        marking.set_grade(old, pupils["aliya"], 7, actor=teacher, calendar=calendar, scale=scale)
    assert "7 дней" in str(error.value)
    assert marking.edit_locked(old, teacher, scale)
    assert marking.set_grade(old, pupils["aliya"], 7, actor=kymbat, calendar=calendar, scale=scale).value == 7
    assert not marking.edit_locked(old, kymbat, scale)


def test_closed_quarter_blocks_teacher_grades(lesson, pupils, teacher, calendar, scale, kymbat, year):
    quarter = Quarter.objects.get(year=year, number=1)
    results.close_quarter(quarter, actor=kymbat)
    fresh = __import__("academics.calendar", fromlist=["load"]).load(year)
    with pytest.raises(marking.MarkRefused):
        marking.set_grade(lesson, pupils["aliya"], 7, actor=teacher, calendar=fresh, scale=scale)
    assert marking.set_grade(lesson, pupils["aliya"], 7, actor=kymbat, calendar=fresh, scale=scale).value == 7


def test_grade_comment_goes_to_the_journal_and_student_reads_it(lesson, pupils, teacher, calendar, scale, as_student):
    marking.set_grade(
        lesson, pupils["aliya"], 9, comment="Отличная работа с текстом", actor=teacher, calendar=calendar, scale=scale
    )
    assert AuditLog.objects.filter(
        model_label="academics.Grade", field_name="comment", new_value="Отличная работа с текстом"
    ).exists()
    mine = as_student.get(f"/api/acad/lessons/{lesson.pk}/").json()
    assert mine["mine"]["grade"] == 9 and mine["mine"]["comment"] == "Отличная работа с текстом"


def test_grade_only_for_a_student_of_the_cohort(lesson, pupils, teacher, calendar, scale):
    with pytest.raises(marking.MarkRefused):
        marking.set_grade(lesson, pupils["stranger"], 5, actor=teacher, calendar=calendar, scale=scale)


# --- Формула и пороги --------------------------------------------------------------


def test_quarter_formula_with_all_parts_and_thresholds(scale):
    assert results.quarter_percent(80.0, 80.0, 80.0, scale) == pytest.approx(80.0)
    assert results.quarter_percent(100.0, 50.0, 50.0, scale) == pytest.approx(62.5)
    assert results.grade_of(85, scale) == 5
    assert results.grade_of(84.9, scale) == 4
    assert results.grade_of(65, scale) == 4
    assert results.grade_of(40, scale) == 3
    assert results.grade_of(39.9, scale) == 2
    assert results.grade_of(None, scale) is None


def test_missing_part_shares_its_weight_between_the_others(scale):
    assert results.quarter_percent(80.0, 60.0, None, scale) == pytest.approx(70.0), "СОЧ не было: 25 и 25 → поровну"
    assert results.quarter_percent(80.0, None, None, scale) == pytest.approx(80.0)
    assert results.quarter_percent(None, None, None, scale) is None


def test_student_row_in_the_journal_counts_marks_and_parts(year, subjects, teacher, cohorts, pupils, calendar, scale):
    fo = create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-4, calendar),
        slot=1,
        room="1",
    )
    sor = create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-3, calendar),
        slot=1,
        room="1",
    )
    marking.set_lesson_meta(sor, actor=teacher, kind=LessonKind.SOR, number=1, max_score=20)
    aliya = pupils["aliya"]
    marking.set_grade(fo, aliya, 8, actor=teacher, calendar=calendar, scale=scale)
    marking.set_grade(sor, aliya, 15, actor=teacher, calendar=calendar, scale=scale)
    for row in (fo, sor):
        marking.save_attendance(row, [], actor=teacher, calendar=calendar)
    marking.save_attendance(fo, [{"student": pupils["damir"].pk, "mark": "absent"}], actor=teacher, calendar=calendar)
    context = results.course_context(fo.course, days(-30), days(0), scale)
    stats = context.stats(aliya.pk)
    assert (stats.total, stats.absent, stats.fo_avg, stats.sor_got, stats.sor_max) == (2, 0, 8.0, 15, 20)
    assert stats.quarter_pct == pytest.approx((80 * 25 + 75 * 25) / 50)
    assert stats.quarter_grade == 4
    damir = context.stats(pupils["damir"].pk)
    assert damir.absent == 1 and damir.attendance_pct == 50


def test_fo_only_subject_has_no_quarter_grade(year, subjects, teacher, cohorts, pupils, calendar, scale):
    pe = create_once(
        subject=subjects["pe"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-3, calendar),
        slot=1,
        room="зал",
    )
    marking.set_grade(pe, pupils["aliya"], 9, actor=teacher, calendar=calendar, scale=scale)
    stats = results.course_context(pe.course, days(-30), days(0), scale).stats(pupils["aliya"].pk)
    assert stats.fo_avg == 9.0 and stats.quarter_pct is None and stats.quarter_grade is None


# --- Итоги четверти ------------------------------------------------------------------


def test_final_differs_from_the_computed_only_with_a_reason(
    year, subjects, teacher, cohorts, pupils, calendar, scale, as_teacher
):
    fo = create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-3, calendar),
        slot=1,
        room="1",
    )
    marking.set_grade(fo, pupils["aliya"], 9, actor=teacher, calendar=calendar, scale=scale)
    quarter = Quarter.objects.get(year=year, number=1)
    refused = as_teacher.post(
        f"/api/acad/journals/{fo.course.pk}/final/",
        {"quarter": quarter.pk, "rows": [{"student": pupils["aliya"].pk, "final": 4}]},
        format="json",
    )
    assert refused.status_code == 400 and "причину" in refused.json()["detail"]
    ok = as_teacher.post(
        f"/api/acad/journals/{fo.course.pk}/final/",
        {"quarter": quarter.pk, "rows": [{"student": pupils["aliya"].pk, "final": 4, "reason": "пропустил СОР"}]},
        format="json",
    )
    assert ok.status_code == 200, ok.content
    row = QuarterResult.objects.get(course=fo.course, student=pupils["aliya"], quarter=quarter)
    assert row.grade == 4 and row.reason == "пропустил СОР" and float(row.computed_percent) == 90.0
    assert AuditLog.objects.filter(model_label="academics.QuarterResult", field_name="grade", new_value="4").exists()


def test_after_closing_the_quarter_only_kymbat_and_admin_change_finals(
    year, subjects, teacher, cohorts, pupils, calendar, scale, kymbat, as_teacher, as_kymbat
):
    fo = create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-3, calendar),
        slot=1,
        room="1",
    )
    quarter = Quarter.objects.get(year=year, number=1)
    results.close_quarter(quarter, actor=kymbat)
    payload = {"quarter": quarter.pk, "rows": [{"student": pupils["aliya"].pk, "final": 5}]}
    assert as_teacher.post(f"/api/acad/journals/{fo.course.pk}/final/", payload, format="json").status_code == 400
    assert as_kymbat.post(f"/api/acad/journals/{fo.course.pk}/final/", payload, format="json").status_code == 200


def test_scale_lives_in_the_base_and_is_edited_with_the_year(year, as_kymbat):
    response = as_kymbat.patch(
        "/api/acad/year/",
        {"scale": {"weight_fo": 30, "weight_sor": 30, "weight_soch": 40, "threshold_5": 90}},
        format="json",
    )
    assert response.status_code == 200, response.content
    scale = scale_of(year)
    assert (scale.weight_fo, scale.weight_sor, scale.weight_soch, scale.threshold_5) == (30, 30, 40, 90)
    assert results.grade_of(89, scale) == 4
    bad = as_kymbat.patch("/api/acad/year/", {"scale": {"weight_fo": 50}}, format="json")
    assert bad.status_code == 400 and "Сумма весов" in bad.json()["detail"]


def test_dates_come_from_almaty_not_utc(monkeypatch):
    """«Сегодня» учебной части — `timezone.localdate()`, а не `date.today()`."""
    import inspect
    import re

    from academics import calendar as school_calendar
    from academics import marks, reports, results, schedule, teacher_views, views

    for module in (school_calendar, marks, results, schedule, reports, views, teacher_views):
        source = inspect.getsource(module)
        assert not re.search(r"(?<![`\w])date\.today\(\)", source), module.__name__
        assert not re.search(r"(?<![`\w])datetime\.now\(\)", source), module.__name__
    assert school_calendar.today() == dt.date.today() or abs((school_calendar.today() - dt.date.today()).days) <= 1
