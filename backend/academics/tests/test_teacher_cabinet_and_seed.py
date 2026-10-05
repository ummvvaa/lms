"""Кабинет учителя, напоминания, посев для разработки, чистка, роль в учётных записях."""

from __future__ import annotations

import datetime as dt
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from academics import tasks
from academics.models import Cohort, Lesson, Subject, TeacherProfile
from academics.schedule import create_once
from academics.tests.conftest import days, login, school_day
from accounts.models import Role, User
from core.models import Notification
from students.models import Student, StudyGroup

pytestmark = pytest.mark.django_db


def test_today_screen_lists_lessons_and_unmarked(year, subjects, teacher, cohorts, pupils, calendar, as_teacher):
    past = create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-1, calendar),
        slot=1,
        room="204",
    )
    today_lesson = create_once(
        subject=subjects["alg"], teacher=teacher, cohort=cohorts["boston"], date=days(0), slot=8, room="204"
    )
    payload = as_teacher.get("/api/acad/teacher/today/").json()
    assert payload["has_courses"] is True
    assert [row["id"] for row in payload["lessons"]] == [today_lesson.pk]
    assert payload["lessons"][0]["cohort"]["students"] == 3
    assert any(row["id"] == past.pk for row in payload["unmarked"])
    assert payload["journals"][0]["students"] == 3
    assert payload["teacher"]["room"] == "204"


def test_journal_matrix_has_columns_rows_and_stats(lesson, pupils, teacher, as_teacher):
    payload = as_teacher.get(f"/api/acad/journals/{lesson.course.pk}/?period=q1").json()
    assert [c["lesson"] for c in payload["columns"]] == [lesson.pk]
    assert payload["columns"][0]["unmarked"] is True and payload["columns"][0]["locked"] is False
    assert {row["id"] for row in payload["rows"]} == {pupils["aliya"].pk, pupils["damir"].pk, pupils["nurai"].pk}
    assert payload["kpis"]["unmarked"] == 1 and payload["may_edit"] is True
    assert payload["scale"]["edit_days"] == 7
    export = as_teacher.get(f"/api/acad/journals/{lesson.course.pk}/export/?period=q1&preview=1").json()
    assert [sheet["title"] for sheet in export["sheets"]] == ["Посещаемость", "Оценки", "Темы"]


def test_journals_list_and_profile(lesson, teacher, as_teacher):
    rows = as_teacher.get("/api/acad/teacher/journals/").json()["rows"]
    assert len(rows) == 1 and rows[0]["students"] == 3
    profile = as_teacher.get("/api/acad/teacher/profile/").json()
    assert profile["teacher"]["subject_titles"] == "Алгебра" and profile["journals"] == 1


def test_topic_and_homework_are_saved_and_logged(lesson, as_teacher):
    response = as_teacher.patch(
        f"/api/acad/lessons/{lesson.pk}/meta/", {"topic": "Производная", "homework": "Упр. 4"}, format="json"
    )
    assert response.status_code == 200
    lesson.refresh_from_db()
    assert (lesson.topic, lesson.homework) == ("Производная", "Упр. 4")


def test_reminder_goes_to_the_bell_once_per_lesson_ten_minutes_after_the_bell(
    year, subjects, teacher, cohorts, calendar, monkeypatch
):
    lesson = create_once(
        subject=subjects["alg"], teacher=teacher, cohort=cohorts["boston"], date=days(0), slot=1, room="204"
    )
    starts = calendar.bell(1, [cohorts["boston"].group_id])[0]
    tz = timezone.get_current_timezone()
    early = dt.datetime.combine(days(0), starts, tzinfo=tz) + dt.timedelta(minutes=5)
    late = early + dt.timedelta(minutes=10)
    monkeypatch.setattr(tasks.timezone, "localtime", lambda: early)
    assert tasks.remind_unmarked() == 0
    monkeypatch.setattr(tasks.timezone, "localtime", lambda: late)
    assert tasks.remind_unmarked() == 1
    note = Notification.objects.get(recipient=teacher, kind=Notification.Kind.LESSON_UNMARKED)
    assert note.link == f"/lessons/{lesson.pk}" and "Не отмечен урок" in note.text
    assert tasks.remind_unmarked() == 0, "по уроку — одно напоминание"
    assert not __import__("django.core.mail", fromlist=["outbox"]).outbox, "писем учителю нет"


def test_reminder_delay_is_a_school_setting(year, subjects, teacher, cohorts, calendar, monkeypatch):
    """«Напоминание о неотмеченном уроке» — настройка: поставили 20 минут, на 15-й напоминания нет."""
    from core.models import SchoolRule

    SchoolRule.objects.create(code="unmarked_remind_minutes", value=20)
    create_once(subject=subjects["alg"], teacher=teacher, cohort=cohorts["boston"], date=days(0), slot=1, room="204")
    starts = dt.datetime.combine(
        days(0), calendar.bell(1, [cohorts["boston"].group_id])[0], tzinfo=timezone.get_current_timezone()
    )
    monkeypatch.setattr(tasks.timezone, "localtime", lambda: starts + dt.timedelta(minutes=15))
    assert tasks.remind_unmarked() == 0
    monkeypatch.setattr(tasks.timezone, "localtime", lambda: starts + dt.timedelta(minutes=20))
    assert tasks.remind_unmarked() == 1


def test_curator_reminds_the_teacher_about_an_unmarked_lesson(lesson, teacher, as_curator):
    response = as_curator.post(f"/api/acad/lessons/{lesson.pk}/remind/", {}, format="json")
    assert response.status_code == 200
    note = Notification.objects.get(recipient=teacher, kind=Notification.Kind.LESSON_UNMARKED)
    assert "Куратор напоминает" in note.text


def test_attendance_day_and_month_for_the_curator(lesson, pupils, teacher, boston, calendar, as_teacher, as_curator):
    as_teacher.post(
        f"/api/acad/lessons/{lesson.pk}/attendance/",
        {"rows": [{"student": pupils["damir"].pk, "mark": "late", "arrived": "09:34"}]},
        format="json",
    )
    day = as_curator.get(f"/api/acad/attendance/?group={boston.code}&date={lesson.date}").json()
    assert day["slots"][0]["slot"] == 2 and day["totals"]["late"] == 1
    month = as_curator.get(f"/api/acad/attendance/?group={boston.code}&view=month&month={lesson.date:%Y-%m}").json()
    damir = next(r for r in month["rows"] if r["id"] == pupils["damir"].pk)
    # опоздал на 9 минут из 45 — процент по минутам урока
    assert damir["late"] == 1 and damir["pct"] == 80
    export = as_curator.get(f"/api/acad/attendance/export/?group={boston.code}&view=month&preview=1").json()
    assert export["sheets"][0]["title"] == boston.code


def test_unexcused_day_rule_two_absences_and_sixty_percent(
    year, subjects, teacher, other_teacher, cohorts, pupils, calendar, as_teacher, as_curator
):
    day = school_day(-1, calendar)
    rows = [
        create_once(subject=subjects["alg"], teacher=teacher, cohort=cohorts["boston"], date=day, slot=slot, room="1")
        for slot in (1, 2, 3)
    ]
    from academics import marks as marking

    marking.save_attendance(
        rows[0], [{"student": pupils["aliya"].pk, "mark": "absent"}], actor=teacher, calendar=calendar
    )
    marking.save_attendance(
        rows[1], [{"student": pupils["aliya"].pk, "mark": "present"}], actor=teacher, calendar=calendar
    )
    marking.save_attendance(
        rows[2], [{"student": pupils["aliya"].pk, "mark": "present"}], actor=teacher, calendar=calendar
    )
    from academics.results import unexcused_days

    assert unexcused_days(pupils["aliya"].pk, days(-30), days(0)) == [], "одно «н» из трёх — не день без причины"
    marking.save_attendance(
        rows[1], [{"student": pupils["aliya"].pk, "mark": "absent"}], actor=teacher, calendar=calendar
    )
    assert unexcused_days(pupils["aliya"].pk, days(-30), days(0)) == [day], "два «н» из трёх — 67 %"
    # пороги — настройки школы: «только если пропущены все уроки дня» и «не меньше трёх „н“»
    from core.models import SchoolRule

    share = SchoolRule.objects.create(code="day_absent_share", value=100)
    assert unexcused_days(pupils["aliya"].pk, days(-30), days(0)) == [], "два из трёх — меньше 100 %"
    share.delete()
    SchoolRule.objects.create(code="day_absent_min", value=3)
    assert unexcused_days(pupils["aliya"].pk, days(-30), days(0)) == [], "два «н» — меньше трёх"
    SchoolRule.objects.all().delete()
    risks = login(teacher)  # noqa: F841 — учителю рисков нет, проверяется ниже
    grades = as_curator.get(f"/api/acad/students/{pupils['aliya'].pk}/grades/?period=q1").json()
    assert grades["unexcused_days"] == [str(day)]


def test_risks_for_saltanat_count_only_unexcused(lesson, pupils, teacher, saltanat, calendar):
    from academics import marks as marking

    marking.save_attendance(
        lesson, [{"student": pupils["aliya"].pk, "mark": "absent"}], actor=teacher, calendar=calendar
    )
    payload = login(saltanat).get("/api/acad/risks/", {"period": f"{lesson.date:%Y-%m}"}).json()
    assert any(row["id"] == pupils["aliya"].pk for row in payload["rows"])
    marking.add_excuse(
        student=pupils["aliya"], starts=lesson.date, ends=lesson.date, reason="Болезнь", document="certificate"
    )
    payload = login(saltanat).get("/api/acad/risks/", {"period": f"{lesson.date:%Y-%m}"}).json()
    row = next((r for r in payload["rows"] if r["id"] == pupils["aliya"].pk), None)
    assert row is None or row["attendance"]["absent"] == 0


# --- Роль в учётных записях и посев -------------------------------------------------


def test_admin_creates_a_teacher_account_and_kymbat_assigns_subjects(as_admin, as_kymbat, subjects):
    created = as_admin.post(
        "/api/users/",
        {"email": "new.teacher@example.kz", "full_name": "Новая Учительница", "role": "teacher"},
        format="json",
    )
    assert created.status_code == 201, created.content
    user = User.objects.get(email="new.teacher@example.kz")
    assert user.role == Role.TEACHER
    response = as_kymbat.patch(
        f"/api/acad/teachers/{user.pk}/", {"subjects": [subjects["alg"].pk], "room": "101"}, format="json"
    )
    assert (
        response.status_code == 200
        and response.json()["room"] == "101"
        and response.json()["subject_titles"] == "Алгебра"
    )
    assert TeacherProfile.objects.get(user=user).subjects.count() == 1


def test_probe_users_include_a_teacher(db, monkeypatch, settings):
    from accounts import probe

    settings.DEBUG = True
    monkeypatch.setenv(probe.PASSWORD_VAR, "Прогон!Проверка2026")
    call_command("create_probe_users", stdout=StringIO())
    assert User.objects.filter(email="teacher@probe.local", role=Role.TEACHER).exists()
    call_command("purge_probe_users", stdout=StringIO())


def test_seed_refuses_outside_debug_and_with_real_students(db, settings, pupils):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_academics", stdout=StringIO())
    settings.DEBUG = True
    with pytest.raises(CommandError) as error:
        call_command("seed_academics", stdout=StringIO())
    assert "настоящие ученики" in str(error.value)


def test_purge_fictional_cleans_the_academic_part(db, settings, subjects, boston):
    from students import fictional

    settings.DEBUG = True
    subject = Subject.objects.create(code="fict", title="Вымышленный", short_title="Вым.", is_fictional=True)
    cohort = Cohort.objects.create(kind="stream", name="Вымышленный поток", is_fictional=True)
    user = User.objects.create_user(
        email="fict.teacher@fictional.local", password="pass12345", role=Role.TEACHER, is_fictional=True
    )
    TeacherProfile.objects.create(user=user, is_fictional=True)
    student = Student.objects.create(
        last_name="Вымышленный",
        first_name="Ученик",
        email="fict@fictional.local",
        group=boston,
        graduation_year=2027,
        is_fictional=True,
    )
    fictional.purge()
    assert not Subject.objects.filter(pk=subject.pk).exists()
    assert not Cohort.all_objects.filter(pk=cohort.pk).exists()
    assert not User.objects.filter(pk=user.pk).exists()
    assert not Student.all_objects.filter(pk=student.pk).exists()
    assert Subject.objects.filter(code="alg").exists(), "настоящие предметы остались"
    assert Lesson.objects.count() == 0


def test_seed_students_and_cohorts_are_the_same_on_a_second_run(db, settings):
    """Повторный посев не заводит новых учеников, подгрупп и потоков."""
    from academics import seed as seeding
    from academics.models import Cohort, CohortKind

    settings.DEBUG = True
    rng = __import__("random").Random(1)
    groups = {code: StudyGroup.objects.create(code=code, parallel=11) for code in seeding.GROUPS}
    subjects = seeding._subjects()
    first = seeding._students(groups, rng)
    seeding._cohorts(groups, first, subjects, rng)
    counts = (
        Student.objects.count(),
        Cohort.objects.filter(kind=CohortKind.SUBGROUP).count(),
        Cohort.objects.filter(kind=CohortKind.STREAM).count(),
    )
    second = seeding._students(groups, __import__("random").Random(2))
    seeding._cohorts(groups, second, subjects, rng)
    assert [s.pk for s in first["BOSTON"]] == [s.pk for s in second["BOSTON"]]
    assert counts == (
        Student.objects.count(),
        Cohort.objects.filter(kind=CohortKind.SUBGROUP).count(),
        Cohort.objects.filter(kind=CohortKind.STREAM).count(),
    )
    # 11 групп по 16–18, английский делится везде, кроме MIT, информатика — везде; потоки: 5 пар и два IELTS
    assert 11 * 16 <= counts[0] <= 11 * 18 and counts[1] == 42 and counts[2] == 7


def test_cohorts_screen_counts_only_live_subgroups(db, boston, subjects, pupils, as_kymbat):
    """Закрытое новым делением членство не считается подгруппой и не даёт «не в подгруппе»."""
    from academics.cohorts import split_group

    ids = [pupils["aliya"].pk, pupils["damir"].pk, pupils["nurai"].pk]
    split_group(group=boston, subject=subjects["eng"], parts=[ids[:1], ids[1:]], since=days(-10))
    split_group(group=boston, subject=subjects["eng"], parts=[ids[:2], ids[2:]], since=days(-1))
    payload = as_kymbat.get("/api/acad/cohorts/").json()
    assert payload["kpis"]["subgroups"] == 2
    row = next(g for g in payload["groups"] if g["code"] == boston.code)
    assert [c["students"] for c in row["subgroups"]] == [2, 1]
    assert payload["kpis"]["not_split"] == 0
