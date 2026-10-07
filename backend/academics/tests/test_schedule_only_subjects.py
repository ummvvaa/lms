"""Предметы «только расписание»: урок в неделе есть, журнала, оценок и ДЗ нет.

Основной журнал школа ведёт в Kundelik, в LMS остаются EEP, GE, SAT,
Creative Writing и Профориентация (решение владельца, 07.10.2026).
"""

from __future__ import annotations

import pytest
from django.core.management import CommandError, call_command

from academics.keep_subjects import plan
from academics.models import Attendance, Course, Mark, Scheme, Subject
from academics.results import student_attendance, student_courses
from academics.schedule import create_once
from academics.tests.conftest import days, login, school_day
from accounts.models import Role


@pytest.fixture
def school_subjects(db):
    """Пять предметов школы, которые ведутся в LMS (SAT — один предмет)."""
    rows = {
        "eep": ("Английский язык (EEP)", Scheme.KZ),
        "ge": ("Английский язык (GE)", Scheme.KZ),
        "sat": ("SAT", Scheme.FO),
        "cw": ("Creative Writing", Scheme.KZ),
        "prof": ("Профориентация", Scheme.FO),
    }
    return {
        code: Subject.objects.create(code=code, title=title, short_title=title[:32], scheme=scheme)
        for code, (title, scheme) in rows.items()
    }


@pytest.fixture
def schedule_only(subjects):
    """Алгебра — «только расписание»."""
    alg = subjects["alg"]
    alg.in_lms = False
    alg.save(update_fields=["in_lms"])
    return alg


def test_plan_finds_the_school_subjects_and_lists_teachers(school_subjects, subjects, lesson, eng_lesson, teacher):
    result = plan()
    assert result.missing == []
    found = {label: [s.code for s in hits] for label, hits in result.found}
    assert found["SAT — Math и Verbal"] == ["sat"]
    kept = {row.subject.code for row in result.keep}
    assert kept == {"eep", "ge", "sat", "cw", "prof"}
    assert {"alg", "eng", "pe"} <= {row.subject.code for row in result.schedule_only}
    # EEP, GE и Creative Writing станут «Только ФО из 10»
    assert {row.subject.code for row in result.rescheme} == {"eep", "ge", "cw"}
    # оба учителя фикстуры ведут только «только расписание» — отключатся
    assert {row.user.pk for row in result.disable} == {teacher.pk, eng_lesson.teacher_id}


def test_dry_run_changes_nothing(school_subjects, subjects, lesson, teacher, capsys):
    call_command("keep_subjects", "--dry-run")
    out = capsys.readouterr().out
    assert "Сухой прогон" in out
    assert "Сапарова Гульнара" in out
    assert Subject.objects.filter(in_lms=False).count() == 0
    assert Subject.objects.get(code="eep").scheme == Scheme.KZ
    teacher.refresh_from_db()
    assert teacher.is_active


def test_missing_subject_stops_the_command(subjects):
    with pytest.raises(CommandError, match="Не найдены"):
        call_command("keep_subjects", "--apply")
    assert Subject.objects.filter(in_lms=False).count() == 0


def test_apply_marks_subjects_and_disables_teachers(school_subjects, subjects, lesson, teacher, make_user, cohorts):
    mixed = make_user(Role.TEACHER, "mixed.acad@example.kz", full_name="Смешанный Учитель")
    Course.objects.create(subject=school_subjects["sat"], teacher=mixed, cohort=cohorts["boston"])
    Course.objects.create(subject=subjects["eng"], teacher=mixed, cohort=cohorts["chicago"])
    call_command("keep_subjects", "--apply")
    assert set(Subject.objects.filter(in_lms=True).values_list("code", flat=True)) == {"eep", "ge", "sat", "cw", "prof"}
    assert Subject.objects.get(code="eep").scheme == Scheme.FO
    teacher.refresh_from_db()
    mixed.refresh_from_db()
    assert not teacher.is_active
    assert mixed.is_active
    # урок отключённого учителя остаётся в расписании с его фамилией
    lesson.refresh_from_db()
    assert lesson.teacher_id == teacher.pk


def test_disabled_teacher_cannot_log_in(teacher):
    teacher.is_active = False
    teacher.save(update_fields=["is_active"])
    from rest_framework.test import APIClient

    answer = APIClient().post("/api/auth/login/", {"email": teacher.email, "password": "pass12345"}, format="json")
    assert answer.status_code in (400, 401, 403)


def test_schedule_only_lesson_has_no_journal_marks_or_grades(schedule_only, lesson, as_teacher, as_admin, pupils):
    assert as_teacher.get(f"/api/acad/journals/{lesson.course_id}/").status_code == 404
    assert as_admin.get(f"/api/acad/journals/{lesson.course_id}/").status_code == 404
    journals = as_teacher.get("/api/acad/teacher/journals/").json()
    assert all(row["id"] != lesson.course_id for row in journals.get("rows", journals.get("journals", [])))
    for client in (as_teacher, as_admin):
        mark = client.post(f"/api/acad/lessons/{lesson.pk}/attendance/", {"all_present": True}, format="json")
        assert mark.status_code == 403
        assert "только расписание" in mark.json()["detail"]
        grade = client.post(
            f"/api/acad/lessons/{lesson.pk}/grade/", {"student": pupils["aliya"].pk, "value": 8}, format="json"
        )
        assert grade.status_code == 403
        homework = client.put(f"/api/homework/lessons/{lesson.pk}/", {"requires_submission": True}, format="json")
        assert homework.status_code in (403, 404)
    detail = as_admin.get(f"/api/acad/lessons/{lesson.pk}/").json()
    assert detail["may_mark"] is False and detail["may_grade"] is False
    assert detail["lesson"]["subject"]["in_lms"] is False


def test_schedule_only_lesson_stays_in_the_week(schedule_only, lesson, as_student, as_teacher):
    week = as_student.get(f"/api/acad/lessons/?from={lesson.date.isoformat()}").json()
    found = [row for row in week["lessons"] if row["id"] == lesson.pk]
    assert found and found[0]["subject"]["in_lms"] is False
    assert found[0]["actual_teacher"]["full_name"] == "Сапарова Гульнара"


def test_schedule_only_lesson_drops_out_of_grades_and_attendance(schedule_only, lesson, pupils, teacher, calendar):
    aliya = pupils["aliya"]
    Attendance.objects.create(lesson=lesson, student=aliya, mark=Mark.ABSENT)
    lesson.marked_at = lesson.created_at
    lesson.save(update_fields=["marked_at"])
    assert all(course.subject.in_lms for course in student_courses(aliya.pk))
    totals = student_attendance(aliya.pk, days(-30), days(0))
    assert totals.total == 0, "прежняя отметка предмета «только расписание» в процент не идёт"


def test_teacher_sees_only_kept_subjects_in_today(school_subjects, schedule_only, lesson, teacher, cohorts, calendar):
    kept = create_once(
        subject=school_subjects["sat"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-2, calendar),
        slot=5,
        room="204",
    )
    answer = login(teacher).get("/api/acad/teacher/today/").json()
    ids = {row["id"] for row in answer.get("journals", [])}
    assert kept.course_id in ids
    assert lesson.course_id not in ids


def test_year_screen_lists_subjects_with_counts_and_switch(subjects, lesson, as_kymbat, as_curator):
    rows = {row["code"]: row for row in as_kymbat.get("/api/acad/year/").json()["subject_rows"]}
    assert rows["alg"]["in_lms"] is True
    assert rows["alg"]["teachers"] == 1
    answer = as_kymbat.patch(f"/api/acad/subjects/{subjects['alg'].pk}/", {"in_lms": False}, format="json")
    assert answer.status_code == 200
    assert {row["code"]: row["in_lms"] for row in answer.json()["rows"]}["alg"] is False
    from core.models import AuditLog

    assert AuditLog.objects.filter(field_name="in_lms", new_value="нет").exists()
    assert (
        as_curator.patch(f"/api/acad/subjects/{subjects['alg'].pk}/", {"in_lms": True}, format="json").status_code
        == 403
    )
    subjects["alg"].refresh_from_db()
    assert subjects["alg"].in_lms is False
