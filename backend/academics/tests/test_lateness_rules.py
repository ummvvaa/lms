"""Два правила школы про опоздания (05.10.2026), оба выключены нулём.

«Опоздание больше N минут считается пропуском»: такое опоздание читается как
«н» в одном месте — в карте отметок, — и за ним идут процент, «день без
причины», лист, журнал, выгрузка и отчёты родителям. Отметка учителя в базе
остаётся опозданием: выключили правило — всё вернулось.

«Опоздания в „Рисках“»: столько опозданий за выбранный в «Рисках» период —
ученик в списке с причиной «опоздания»; число опозданий видно и в карточке.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from academics import calendar as school_calendar
from academics import marks as marking
from academics import reports as reporting
from academics.models import Attendance, Bell, BellSchedule, Grade, Lesson
from academics.results import attendance_by_students, recent_absences, student_attendance, unexcused_days
from academics.schedule import create_once
from academics.tests.conftest import days, login

pytestmark = pytest.mark.django_db

#: сорокаминутные уроки: 1 — 08:00–08:40, 2 — 08:50–09:30, 3 — 09:40–10:20
FORTY = (("08:00", "08:40"), ("08:50", "09:30"), ("09:40", "10:20"))


@pytest.fixture
def forty(year, boston, chicago):
    rows = BellSchedule.objects.create(year=year, title="По 40 минут")
    for number, (starts, ends) in enumerate(FORTY, start=1):
        Bell.objects.create(
            year=year,
            schedule=rows,
            number=number,
            starts=dt.time.fromisoformat(starts),
            ends=dt.time.fromisoformat(ends),
        )
    rows.groups.add(boston, chicago)
    return rows


def late(lesson, student, arrived: str, teacher) -> None:
    marking.save_attendance(
        lesson,
        [{"student": student.pk, "mark": "late", "arrived": arrived}],
        actor=teacher,
        calendar=school_calendar.load(),
    )
    lesson.refresh_from_db()


@pytest.fixture
def long_late(forty, lesson, pupils, teacher):
    """Урок алгебры BOSTON (2 урок, 08:50–09:30): Дамир пришёл в 09:15 — опоздал на 25 минут."""
    late(lesson, pupils["damir"], "09:15", teacher)
    return lesson


def totals_of(student):
    return student_attendance(student.pk, days(-30), days(0))


# --- Правило 5: опоздание больше N минут — пропуск ------------------------------


def test_the_rule_is_off_by_default(long_late, pupils):
    totals = totals_of(pupils["damir"])
    assert (totals.pct, totals.absent, totals.late, totals.late_minutes) == (38, 0, 1, 25)


def test_turned_on_the_percent_changes_and_turned_off_it_returns(long_late, pupils, set_rules):
    damir = pupils["damir"]
    set_rules(late_as_absent_minutes=20)
    totals = totals_of(damir)
    # урок идёт пропуском: 0 минут из 40, в счёт «н», в счёт опозданий не идёт
    assert (totals.pct, totals.absent, totals.late, totals.late_minutes) == (0, 1, 0, 0)
    # отметка учителя не тронута
    row = Attendance.objects.get(lesson=long_late, student=damir)
    assert (row.mark, row.arrived_at) == ("late", dt.time(9, 15))
    set_rules(late_as_absent_minutes=0)
    totals = totals_of(damir)
    assert (totals.pct, totals.absent, totals.late) == (38, 0, 1)


def test_only_a_lateness_longer_than_the_rule_is_an_absence(forty, lesson, pupils, teacher, set_rules):
    """Ровно N минут — ещё опоздание; без времени прихода и без звонка — тоже: минуты посчитать не из чего."""
    set_rules(late_as_absent_minutes=20)
    late(lesson, pupils["damir"], "09:10", teacher)  # ровно 20 минут
    Attendance.objects.create(lesson=lesson, student=pupils["nurai"], mark="late")  # опоздание до 30.09, без времени
    assert (totals_of(pupils["damir"]).absent, totals_of(pupils["damir"]).late) == (0, 1)
    assert (totals_of(pupils["nurai"]).absent, totals_of(pupils["nurai"]).late) == (0, 1)
    late(lesson, pupils["damir"], "09:11", teacher)  # 21 минута
    assert (totals_of(pupils["damir"]).absent, totals_of(pupils["damir"]).late) == (1, 0)

    ninth = create_once(
        subject=lesson.course.subject, teacher=teacher, cohort=lesson.course.cohort, date=lesson.date, slot=9, room="1"
    )
    late(ninth, pupils["aliya"], "23:00", teacher)  # 9 урока в сетке нет
    assert (totals_of(pupils["aliya"]).absent, totals_of(pupils["aliya"]).late) == (0, 1)


def test_long_lateness_makes_a_day_without_a_reason(long_late, pupils, teacher, set_rules):
    """Два долгих опоздания за день — «день без причины»: 2 «н» и все уроки дня."""
    damir = pupils["damir"]
    third = create_once(
        subject=long_late.course.subject,
        teacher=teacher,
        cohort=long_late.course.cohort,
        date=long_late.date,
        slot=3,
        room="204",
    )
    late(third, damir, "10:05", teacher)  # 25 минут
    assert unexcused_days(damir.pk, days(-30), days(0)) == []
    set_rules(late_as_absent_minutes=20)
    assert unexcused_days(damir.pk, days(-30), days(0)) == [long_late.date]


def test_inside_an_excuse_the_long_lateness_reads_excused(long_late, pupils, curator, set_rules):
    """«н» из опоздания — обычная «н»: внутри уважительного периода читается «у»."""
    set_rules(late_as_absent_minutes=20)
    marking.add_excuse(
        student=pupils["damir"], starts=days(-30), ends=days(0), reason="врач", document="certificate", actor=curator
    )
    totals = totals_of(pupils["damir"])
    assert (totals.absent, totals.excused, totals.late) == (0, 1, 0)


def test_every_screen_export_and_report_take_the_same_count(
    long_late, pupils, boston, as_curator, as_admin, curator, set_rules
):
    """Лист, журнал, карточка, выгрузка и оба отчёта родителям считают одно и то же."""
    from academics.school_reports import attendance_days

    damir = pupils["damir"]
    set_rules(late_as_absent_minutes=20)
    assert attendance_by_students([damir.pk], days(-30), days(0))[damir.pk].pct == 0
    assert recent_absences(damir.pk)["pct"] == 0 and recent_absences(damir.pk)["late"] == 0

    # лист дня: клетка «н», но видно, что ученик пришёл и на сколько опоздал
    day = as_curator.get(f"/api/acad/attendance/?group={boston.code}&date={long_late.date}").json()
    index = [s["slot"] for s in day["slots"]].index(long_late.slot)
    cell = next(r for r in day["rows"] if r["id"] == damir.pk)["cells"][index]
    assert (cell["mark"], cell["late_as_absent"], cell["late_by"], cell["arrived"]) == ("absent", True, 25, "09:15")
    assert day["totals"] == {"absent": 1, "excused": 0, "late": 0}

    # лист месяца и его процент
    month = as_curator.get(f"/api/acad/attendance/?group={boston.code}&view=month&month={long_late.date:%Y-%m}").json()
    row = next(r for r in month["rows"] if r["id"] == damir.pk)
    assert (row["pct"], row["absent"], row["late"]) == (0, 1, 0)
    cell = row["cells"][[d["date"] for d in month["days"]].index(str(long_late.date))]
    assert (cell["absent"], cell["late"], cell["late_minutes"]) == (1, 0, 0)

    # выгрузка листа дня — тем же словом
    export = as_curator.get(f"/api/acad/attendance/export/?group={boston.code}&date={long_late.date}&preview=1").json()
    sheet = export["sheets"][0]
    words = {line[0]: line[sheet["columns"].index(f"{long_late.slot} урок")] for line in sheet["rows"]}
    assert words[damir.full_name] == "не был"

    # журнал: клетка и статистика строки
    journal = as_admin.get(f"/api/acad/journals/{long_late.course_id}/").json()
    row = next(r for r in journal["rows"] if r["id"] == damir.pk)
    cell = row["cells"][[c["lesson"] for c in journal["columns"]].index(long_late.pk)]
    assert (cell["mark"], cell["late_as_absent"], cell["late_by"]) == ("absent", True, 25)
    assert (row["stats"]["attendance_pct"], row["stats"]["absent"], row["stats"]["late"]) == (0, 1, 0)

    # карточка куратора и успеваемость ученика
    card = as_curator.get(f"/api/curator/students/{damir.pk}/").json()
    assert card["behavior"]["attendance_percent"] == 0 and card["behavior"]["late_count"] == 0
    grades = as_curator.get(f"/api/acad/students/{damir.pk}/grades/?period={long_late.date:%Y-%m}").json()
    assert (grades["attendance"]["pct"], grades["attendance"]["absent"], grades["attendance"]["late"]) == (0, 1, 0)

    # стандартный отчёт родителям
    start, end = reporting.month_bounds(long_late.date)
    calendar = school_calendar.load()
    report = reporting.build_report(
        student=damir,
        kind="month",
        start=start,
        end=end,
        calendar=calendar,
        config=reporting.report_settings(calendar),
        actor=curator,
    )
    lines = {line.title: line.value for line in report.lines.all()}
    assert lines[reporting.ATTENDANCE_ROW] == "0 %"
    assert lines["Пропуски без причины"] == "1" and lines["Опоздания"] == "0"
    assert "Минут опозданий" not in lines

    # шаблоны школы: день пропущен, опозданий нет, процент тот же
    school = attendance_days(damir.pk, start, end)
    assert (school.total, school.missed, school.late, school.pct) == (1, 1, 0, 0)


def test_lesson_screen_keeps_the_teachers_mark(long_late, pupils, as_teacher, teacher, set_rules):
    """Экран урока шлёт на запись весь состав: опоздание не должно записаться пропуском, оценка — пропасть."""
    damir = pupils["damir"]
    Grade.objects.create(lesson=long_late, student=damir, value=8, created_by=teacher)
    set_rules(late_as_absent_minutes=20)
    body = as_teacher.get(f"/api/acad/lessons/{long_late.pk}/").json()
    row = next(r for r in body["roster"] if r["id"] == damir.pk)
    assert (row["mark"], row["arrived"], row["late_by"], row["late_as_absent"]) == ("late", "09:15", 25, True)
    assert row["grade"] == 8
    assert row["short"] in body["absent"] and not body["late"]

    # учитель сохраняет экран как есть
    saved = as_teacher.post(
        f"/api/acad/lessons/{long_late.pk}/attendance/",
        {
            "rows": [
                {"student": r["id"], "mark": r["mark"] or "present", "arrived": r["arrived"]} for r in body["roster"]
            ]
        },
        format="json",
    )
    assert saved.status_code == 200, saved.json()
    stored = Attendance.objects.get(lesson=long_late, student=damir)
    assert (stored.mark, stored.arrived_at) == ("late", dt.time(9, 15))
    assert Grade.objects.filter(lesson=long_late, student=damir, value=8).exists()


def test_the_student_sees_the_absence_and_that_he_came(forty, lesson, pupils, teacher, as_student, set_rules):
    """Ученик у себя видит «н» с пояснением, что пришёл и на сколько опоздал."""
    late(lesson, pupils["aliya"], "09:15", teacher)
    set_rules(late_as_absent_minutes=20)
    mine = as_student.get(f"/api/acad/lessons/{lesson.pk}/").json()["mine"]
    assert (mine["mark"], mine["late_as_absent"], mine["late_by"], mine["arrived"]) == ("absent", True, 25, "09:15")


# --- Правило 6: опоздания в «Рисках» ---------------------------------------------


@pytest.fixture
def three_lates(forty, lesson, pupils, teacher):
    """Дамир трижды опоздал на 5 минут: три урока одного дня, посещаемость 88 % — выше порога."""
    first = create_once(
        subject=lesson.course.subject, teacher=teacher, cohort=lesson.course.cohort, date=lesson.date, slot=1, room="1"
    )
    third = create_once(
        subject=lesson.course.subject, teacher=teacher, cohort=lesson.course.cohort, date=lesson.date, slot=3, room="1"
    )
    late(first, pupils["damir"], "08:05", teacher)
    late(lesson, pupils["damir"], "08:55", teacher)
    late(third, pupils["damir"], "09:45", teacher)
    return lesson


def risks_of(saltanat, period: str) -> dict:
    return login(saltanat).get(f"/api/acad/risks/?period={period}").json()


def test_lateness_is_not_a_risk_until_the_rule_is_on(three_lates, pupils, saltanat, set_rules):
    period = f"{three_lates.date:%Y-%m}"
    body = risks_of(saltanat, period)
    assert body["late_limit"] == 0
    assert pupils["damir"].pk not in {row["id"] for row in body["rows"]}

    set_rules(late_risk_count=3)
    body = risks_of(saltanat, period)
    assert body["late_limit"] == 3
    row = next(r for r in body["rows"] if r["id"] == pupils["damir"].pk)
    assert row["reasons"] == ["late"]
    assert (row["attendance"]["late"], row["attendance"]["pct"]) == (3, 88)

    # четырёх опозданий у него нет — в списке его снова нет
    set_rules(late_risk_count=4)
    assert pupils["damir"].pk not in {r["id"] for r in risks_of(saltanat, period)["rows"]}


def test_lateness_is_counted_over_the_period_picked_in_risks(three_lates, pupils, saltanat, set_rules):
    """Опоздания считаются за выбранный период, а не за календарный месяц: в другом месяце их нет."""
    set_rules(late_risk_count=3)
    other = (three_lates.date.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    assert pupils["damir"].pk not in {r["id"] for r in risks_of(saltanat, other)["rows"]}
    assert pupils["damir"].pk in {r["id"] for r in risks_of(saltanat, f"{three_lates.date:%Y-%m}")["rows"]}


def test_a_lateness_counted_as_an_absence_is_not_counted_twice(three_lates, pupils, saltanat, set_rules):
    """Опоздание, ставшее пропуском, — уже «н»: в счёт опозданий не идёт, причина — посещаемость."""
    set_rules(late_risk_count=3, late_as_absent_minutes=4)
    row = next(r for r in risks_of(saltanat, f"{three_lates.date:%Y-%m}")["rows"] if r["id"] == pupils["damir"].pk)
    assert "late" not in row["reasons"] and "attendance" in row["reasons"]
    assert (row["attendance"]["late"], row["attendance"]["absent"]) == (0, 3)


def test_the_card_shows_the_number_of_latenesses_always(three_lates, pupils, as_curator):
    """Число опозданий в карточке видно и при выключенном правиле: это факт, а не ярлык."""
    card = as_curator.get(f"/api/curator/students/{pupils['damir'].pk}/").json()
    assert (card["behavior"]["late_count"], card["behavior"]["late_window_days"]) == (3, 30)
    grades = as_curator.get(f"/api/acad/students/{pupils['damir'].pk}/grades/?period={three_lates.date:%Y-%m}").json()
    assert grades["attendance"]["late"] == 3


def test_both_rules_are_off_by_default_and_suggest_a_start(as_admin):
    rules = {row["code"]: row for row in as_admin.get("/api/school-rules/").json()["rules"]}
    minutes, count = rules["late_as_absent_minutes"], rules["late_risk_count"]
    assert (minutes["value"], minutes["default"], minutes["suggested"], minutes["section"]) == (0, 0, 20, "attendance")
    assert (count["value"], count["default"], count["suggested"], count["section"]) == (0, 0, 3, "attendance")
    assert rules["attendance_below"]["suggested"] == 0


def test_marks_are_not_touched_when_the_lesson_has_no_marked_time(forty, lesson, pupils, set_rules):
    """Страж чтения: правило включено, а опозданий со временем нет — отметки читаются как раньше."""
    set_rules(late_as_absent_minutes=20)
    Attendance.objects.create(lesson=lesson, student=pupils["aliya"], mark="absent")
    Lesson.objects.filter(pk=lesson.pk).update(marked_at=timezone.now())
    lesson.refresh_from_db()
    marks = marking.marks_map([lesson], [pupils["aliya"].pk, pupils["damir"].pk])
    assert marks == {(lesson.pk, pupils["aliya"].pk): "absent", (lesson.pk, pupils["damir"].pk): "present"}
