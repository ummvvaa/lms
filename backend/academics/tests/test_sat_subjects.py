"""SAT: один предмет с разделами отчёта или два предмета — настройкой и командой (11.10.2026).

* правило «SAT: два предмета» хранит целевой режим, журналы разносит и сводит
  команда `sat_subjects` с сухим прогоном;
* разнести: журнал уходит на SAT Math или SAT Verbal по разделу отчёта; журнал
  без раздела — отказ с перечнем; оценки остаются при журнале;
* свести: журналы возвращаются на SAT, раздел отчёта — по прежнему предмету;
* `keep_subjects` после разнесения не возвращает скрытый SAT;
* книга школы при двух предметах не принимает строку «SAT».
"""

from __future__ import annotations

import io

import pytest
from django.core.management import CommandError, call_command

from academics import sat_subjects
from academics.models import Course, Grade, ReportRole, Scheme, Subject
from academics.schedule import create_once
from academics.tests.conftest import school_day
from core import school_rules

pytestmark = pytest.mark.django_db


@pytest.fixture
def sat(db) -> Subject:
    return Subject.objects.create(code="sat", title="SAT", short_title="SAT", scheme=Scheme.FO, in_lms=True, order=5)


@pytest.fixture
def journals(sat, teacher, other_teacher, cohorts):
    math = Course.objects.create(
        subject=sat, teacher=teacher, cohort=cohorts["boston"], report_role=ReportRole.SAT_MATH
    )
    verbal = Course.objects.create(
        subject=sat, teacher=other_teacher, cohort=cohorts["boston"], report_role=ReportRole.SAT_VERBAL
    )
    return {"math": math, "verbal": verbal}


def run(*flags) -> str:
    out = io.StringIO()
    call_command("sat_subjects", *flags, stdout=out)
    return out.getvalue()


def test_dry_run_changes_nothing_and_names_the_moves(journals, sat):
    text = run("--split", "--dry-run")
    assert "SAT Math" in text and "SAT Verbal" in text and "Сухой прогон" in text
    assert Subject.objects.count() == Subject.objects.filter(pk=sat.pk).count() + 3  # alg, eng, pe из посева
    assert not Subject.objects.filter(title="SAT Math").exists()
    assert school_rules.value(school_rules.SAT_TWO_SUBJECTS) == 0


def test_split_moves_journals_by_report_role_and_keeps_grades(journals, sat, year, pupils, teacher, calendar):
    lesson = create_once(
        subject=sat, teacher=teacher, cohort=journals["math"].cohort, date=school_day(-2, calendar), slot=2, room="204"
    )
    grade = Grade.objects.create(lesson=lesson, student=pupils["aliya"], value=9)
    run("--split", "--apply")
    math, verbal = Subject.objects.get(title="SAT Math"), Subject.objects.get(title="SAT Verbal")
    assert math.in_lms and verbal.in_lms and math.scheme == Scheme.FO and verbal.scheme == Scheme.FO
    journals["math"].refresh_from_db()
    journals["verbal"].refresh_from_db()
    assert journals["math"].subject == math and journals["verbal"].subject == verbal
    grade.refresh_from_db()
    assert grade.lesson.course_id == journals["math"].pk, "оценка осталась при журнале"
    sat.refresh_from_db()
    assert not sat.is_active and not sat.in_lms
    assert school_rules.value(school_rules.SAT_TWO_SUBJECTS) == 1
    # повторный запуск ничего не меняет
    assert "менять нечего" in run("--split", "--dry-run")


def test_journal_without_report_role_stops_the_split(journals, sat, teacher, cohorts):
    bare = Course.objects.create(subject=sat, teacher=teacher, cohort=cohorts["chicago"])
    with pytest.raises(CommandError, match="раздел отчёта"):
        run("--split", "--apply")
    assert not Subject.objects.filter(title="SAT Math").exists()
    bare.refresh_from_db()
    assert bare.subject == sat


def test_merge_brings_journals_back_with_report_roles(journals, sat):
    run("--split", "--apply")
    # разделы отчёта у журналов стираются — свести должно восстановить их по предмету
    Course.objects.filter(pk__in=[c.pk for c in journals.values()]).update(report_role=ReportRole.NONE)
    run("--merge", "--apply")
    sat.refresh_from_db()
    assert sat.is_active and sat.in_lms
    journals["math"].refresh_from_db()
    journals["verbal"].refresh_from_db()
    assert journals["math"].subject == sat and journals["math"].report_role == ReportRole.SAT_MATH
    assert journals["verbal"].subject == sat and journals["verbal"].report_role == ReportRole.SAT_VERBAL
    assert not Subject.objects.get(title="SAT Math").is_active
    assert school_rules.value(school_rules.SAT_TWO_SUBJECTS) == 0


def test_keep_subjects_ignores_the_hidden_sat_after_the_split(journals, sat, set_rules):
    for code, title in (
        ("eep", "Английский язык (EEP)"),
        ("ge", "Английский язык (GE)"),
        ("cw", "Creative Writing"),
        ("prof", "Профориентация"),
    ):
        Subject.objects.create(code=code, title=title, short_title=title[:32])
    run("--split", "--apply")
    call_command("keep_subjects", "--apply")
    sat.refresh_from_db()
    assert not sat.in_lms and not sat.is_active
    assert Subject.objects.get(title="SAT Math").in_lms and Subject.objects.get(title="SAT Verbal").in_lms


def test_year_screen_says_when_the_base_lags_behind_the_rule(journals, as_kymbat, set_rules):
    assert as_kymbat.get("/api/acad/year/").json()["sat"] == {"two": False, "pending": False}
    set_rules(sat_two_subjects=1)
    assert as_kymbat.get("/api/acad/year/").json()["sat"] == {"two": True, "pending": True}
    run("--split", "--apply")
    assert as_kymbat.get("/api/acad/year/").json()["sat"] == {"two": True, "pending": False}


def test_book_with_sat_is_refused_in_two_subjects_mode(set_rules, admin, year):
    from academics import schedule_import
    from academics.tests.test_schedule_import import SUBJECTS, small_book

    set_rules(sat_two_subjects=1)
    report = schedule_import.preview(small_book(subjects=[*SUBJECTS, {"Предмет": "SAT"}]))
    assert any("укажите SAT Math или SAT Verbal" in error for error in report["errors"])
    set_rules(sat_two_subjects=0)
    report = schedule_import.preview(small_book(subjects=[*SUBJECTS, {"Предмет": "SAT"}]))
    assert not any("SAT" in error for error in report["errors"])


def test_book_rows_sat_math_and_verbal_go_to_sat_in_one_subject_mode(sat, admin, year, cohorts):
    from academics import schedule_import
    from academics.tests.test_schedule_import import LESSONS, SUBJECTS, _lesson, small_book

    book = small_book(
        subjects=[*SUBJECTS, {"Предмет": "SAT Math"}, {"Предмет": "SAT Verbal"}],
        lessons=[
            *LESSONS,
            _lesson(11, "Вт", 1, "10:15", "10:55", "SAT Math", "С01", "206", group="BOSTON"),
            # другой учитель: у одного учителя в одной группе один журнал SAT
            _lesson(11, "Вт", 2, "11:00", "11:40", "SAT Verbal", "С02", "206", group="BOSTON"),
        ],
    )
    report = schedule_import.apply(book, actor=admin, expected=schedule_import.fingerprint(book))
    assert report["errors"] == []
    assert not Subject.objects.filter(title__in=["SAT Math", "SAT Verbal"]).exists()
    roles = sorted(Course.objects.filter(subject=sat).values_list("report_role", flat=True))
    assert roles == [ReportRole.SAT_MATH, ReportRole.SAT_VERBAL]
    assert sat_subjects.state() == {"two": False, "pending": False}
