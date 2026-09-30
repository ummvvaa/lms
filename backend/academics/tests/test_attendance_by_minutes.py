"""Время прихода опоздавшего и процент посещаемости по минутам (решение владельца, 30.09.2026).

Минуты урока — по звонкам группы урока. «Был» — все минуты, «опоздал» — от
прихода до конца, «не был» — 0, старое опоздание без времени — все минуты.
Уважительная и длина урока без звонка — правила «Настроек школы». Процент
считает одна функция, и на всех экранах он один.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from academics import calendar as school_calendar
from academics import marks as marking
from academics import reports as reporting
from academics.cohorts import make_stream
from academics.models import Attendance, Bell, BellSchedule, Cohort, CohortKind, CohortMembership, Lesson
from academics.results import attendance_by_students, recent_absences, student_attendance
from academics.schedule import create_once
from academics.tests.conftest import days, school_day
from core import school_rules

pytestmark = pytest.mark.django_db

#: сорокаминутные уроки, как у школы: 2 урок — 08:50–09:30
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


@pytest.fixture
def marked(forty, lesson, pupils, teacher):
    """Урок алгебры BOSTON (2 урок, 08:50–09:30): Дамир пришёл в 09:00, Алии не было."""
    calendar = school_calendar.load()
    marking.save_attendance(
        lesson,
        [
            {"student": pupils["aliya"].pk, "mark": "absent"},
            {"student": pupils["damir"].pk, "mark": "late", "arrived": "09:00"},
        ],
        actor=teacher,
        calendar=calendar,
    )
    lesson.refresh_from_db()
    return lesson


def pct(student, start=None, end=None) -> int | None:
    return student_attendance(student.pk, start or days(-30), end or days(0)).pct


def test_ten_minutes_late_of_forty_is_seventy_five_percent(marked, pupils):
    assert pct(pupils["damir"]) == 75
    assert pct(pupils["aliya"]) == 0
    assert pct(pupils["nurai"]) == 100
    totals = student_attendance(pupils["damir"].pk, days(-30), days(0))
    assert (totals.late, totals.late_minutes, totals.late_unknown) == (1, 10, 0)


def test_old_late_without_time_counts_as_present(forty, lesson, pupils):
    Attendance.objects.create(lesson=lesson, student=pupils["damir"], mark="late")
    Lesson.objects.filter(pk=lesson.pk).update(marked_at=timezone.now())
    assert pct(pupils["damir"]) == 100
    totals = student_attendance(pupils["damir"].pk, days(-30), days(0))
    assert totals.late_unknown == 1 and totals.late_minutes == 0


@pytest.mark.parametrize(
    ("arrived", "word"),
    [("09:30", "Не был"), ("09:45", "Не был"), ("08:50", "Был"), ("", "Укажите"), ("9 утра", "ЧЧ:ММ")],
)
def test_arrival_outside_the_lesson_is_refused(forty, lesson, pupils, teacher, arrived, word):
    with pytest.raises(marking.MarkRefused, match=word):
        marking.save_attendance(
            lesson,
            [{"student": pupils["damir"].pk, "mark": "late", "arrived": arrived}],
            actor=teacher,
            calendar=school_calendar.load(),
        )
    assert not Attendance.objects.filter(lesson=lesson).exists()


def test_arrival_through_the_api_is_checked_and_logged(forty, lesson, pupils, as_teacher):
    url = f"/api/acad/lessons/{lesson.pk}/attendance/"
    refused = as_teacher.post(
        url, {"rows": [{"student": pupils["damir"].pk, "mark": "late", "arrived": "09:31"}]}, format="json"
    )
    assert refused.status_code == 400 and "Не был" in refused.json()["detail"]
    ok = as_teacher.post(
        url, {"rows": [{"student": pupils["damir"].pk, "mark": "late", "arrived": "09:12"}]}, format="json"
    )
    assert ok.status_code == 200, ok.json()
    row = next(r for r in ok.json()["roster"] if r["id"] == pupils["damir"].pk)
    assert (row["mark"], row["arrived"], row["late_by"]) == ("late", "09:12", 22)
    from core.models import AuditLog

    assert AuditLog.objects.filter(
        model_label="academics.Attendance", field_name="arrived_at", new_value="09:12"
    ).exists()
    # экран шлёт опоздание ещё раз без времени — время остаётся прежним
    again = as_teacher.post(url, {"rows": [{"student": pupils["damir"].pk, "mark": "late"}]}, format="json")
    assert again.status_code == 200
    assert Attendance.objects.get(lesson=lesson, student=pupils["damir"]).arrived_at == dt.time(9, 12)


def test_lesson_going_now_takes_the_current_time(forty, year, subjects, teacher, cohorts, pupils, monkeypatch):
    today = school_calendar.today()
    now = timezone.localtime().replace(year=today.year, month=today.month, day=today.day, hour=9, minute=5)
    monkeypatch.setattr(school_calendar, "now_local", lambda: now)
    live = create_once(
        subject=subjects["alg"], teacher=teacher, cohort=cohorts["boston"], date=today, slot=2, room="204"
    )
    marking.save_attendance(
        live, [{"student": pupils["damir"].pk, "mark": "late"}], actor=teacher, calendar=school_calendar.load()
    )
    assert Attendance.objects.get(lesson=live, student=pupils["damir"]).arrived_at == dt.time(9, 5)


def test_subgroup_of_a_stream_takes_the_bells_of_the_stream_groups(forty, year, subjects, teacher, cohorts, pupils):
    """Подгруппа потока без своей группы: звонки — групп потока (40 минут, а не общие 45)."""
    stream = make_stream(name="BOSTON + CHICAGO", parts=[cohorts["boston"], cohorts["chicago"]])
    inner = Cohort.objects.create(kind=CohortKind.SUBGROUP, stream=stream, subject=subjects["eng"], name="ENG-1")
    CohortMembership.objects.create(cohort=inner, student=pupils["damir"], since=days(-60))
    day = school_day(-1, school_calendar.load())
    held = create_once(subject=subjects["eng"], teacher=teacher, cohort=inner, date=day, slot=2, room="305")
    marking.save_attendance(
        held,
        [{"student": pupils["damir"].pk, "mark": "late", "arrived": "09:00"}],
        actor=teacher,
        calendar=school_calendar.load(),
    )
    # по общим звонкам 2 урок — 09:25–10:10, и 09:00 было бы «до начала»
    assert pct(pupils["damir"], day, day) == 75


def test_excused_lowers_the_percent_by_school_rule(forty, marked, pupils, admin, curator):
    marking.add_excuse(
        student=pupils["aliya"], starts=days(-30), ends=days(0), reason="болела", document="certificate", actor=curator
    )
    second = create_once(
        subject=marked.course.subject,
        teacher=marked.teacher,
        cohort=marked.course.cohort,
        date=marked.date,
        slot=3,
        room="204",
    )
    Lesson.objects.filter(pk=second.pk).update(marked_at=timezone.now())  # на втором уроке Алия была
    assert pct(pupils["aliya"]) == 50, "по умолчанию уважительная — пропуск в проценте"
    school_rules.set_value(school_rules.EXCUSED_LOWERS_ATTENDANCE, "нет", actor=admin)
    assert pct(pupils["aliya"]) == 100, "«нет» — урок по уважительной в процент не входит"
    school_rules.reset(school_rules.EXCUSED_LOWERS_ATTENDANCE, actor=admin)
    assert pct(pupils["aliya"]) == 50


def test_lesson_without_a_bell_weighs_the_default_length(forty, marked, pupils, admin):
    """9 урока в сетке нет: он весит «Длину урока по умолчанию», опоздание — без проверки времени."""
    ninth = create_once(
        subject=marked.course.subject,
        teacher=marked.teacher,
        cohort=marked.course.cohort,
        date=marked.date,
        slot=9,
        room="204",
    )
    marking.save_attendance(
        ninth,
        [{"student": pupils["nurai"].pk, "mark": "absent"}],
        actor=marked.teacher,
        calendar=school_calendar.load(),
    )
    # Нурай: 40 минут на 2 уроке и 0 из 40 на 9-м — 50 %
    assert pct(pupils["nurai"]) == 50
    school_rules.set_value(school_rules.LESSON_MINUTES_DEFAULT, 120, actor=admin)
    assert pct(pupils["nurai"]) == 25
    marking.save_attendance(
        ninth,
        [{"student": pupils["aliya"].pk, "mark": "late", "arrived": "23:00"}],
        actor=marked.teacher,
        calendar=school_calendar.load(),
    )
    assert Attendance.objects.get(lesson=ninth, student=pupils["aliya"]).arrived_at == dt.time(23, 0)


def test_the_percent_is_the_same_on_every_screen(marked, pupils, boston, as_curator, as_admin, curator, year):
    damir = pupils["damir"]
    expected = 75
    assert student_attendance(damir.pk, days(-30), days(0)).pct == expected
    assert attendance_by_students([damir.pk], days(-30), days(0))[damir.pk].pct == expected
    assert recent_absences(damir.pk)["pct"] == expected

    month = as_curator.get(f"/api/acad/attendance/?group={boston.code}&view=month&month={marked.date:%Y-%m}").json()
    assert next(r for r in month["rows"] if r["id"] == damir.pk)["pct"] == expected
    card = as_curator.get(f"/api/curator/students/{damir.pk}/").json()
    assert card["behavior"]["attendance_percent"] == expected
    journal = as_admin.get(f"/api/acad/journals/{marked.course_id}/").json()
    row = next(r for r in journal["rows"] if r["id"] == damir.pk)
    assert row["stats"]["attendance_pct"] == expected and row["stats"]["late_minutes"] == 10
    cell = row["cells"][[c["lesson"] for c in journal["columns"]].index(marked.pk)]
    assert cell["late_by"] == 10 and cell["arrived"] == "09:00"
    grades = as_curator.get(f"/api/acad/students/{damir.pk}/grades/").json()
    assert grades["attendance"]["pct"] == expected

    start, end = reporting.month_bounds(marked.date)
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
    lines = {line.title: (line.value, line.note) for line in report.lines.all()}
    assert lines[reporting.ATTENDANCE_ROW][0] == f"{expected} %"
    assert lines["Опоздания"][0] == "1" and lines["Минут опозданий"][0] == "10"


def test_day_sheet_shows_late_minutes_and_none_without_arrival_time(marked, pupils, boston, as_curator):
    """Клетка дня «оп 10»: минуты опоздания в ответе; старое опоздание без времени — None."""
    Attendance.objects.create(lesson=marked, student=pupils["nurai"], mark="late")
    url = f"/api/acad/attendance/?group={boston.code}&date={marked.date}"
    day = as_curator.get(url).json()
    index = [s["slot"] for s in day["slots"]].index(marked.slot)
    cells = {r["id"]: r["cells"][index] for r in day["rows"]}
    damir, nurai, aliya = cells[pupils["damir"].pk], cells[pupils["nurai"].pk], cells[pupils["aliya"].pk]
    assert (damir["mark"], damir["late_by"], damir["arrived"]) == ("late", 10, "09:00")
    assert (nurai["mark"], nurai["late_by"], nurai["arrived"]) == ("late", None, None)
    assert aliya["mark"] == "absent" and aliya["late_by"] is None

    # выгрузка того же листа — с теми же минутами
    export = as_curator.get(f"/api/acad/attendance/export/?group={boston.code}&date={marked.date}&preview=1").json()
    sheet = export["sheets"][0]
    column = sheet["columns"].index(f"{marked.slot} урок")
    words = {row[0]: row[column] for row in sheet["rows"]}
    assert words[pupils["damir"].full_name] == "опоздал на 10 мин"
    assert words[pupils["nurai"].full_name] == "опоздал"


def test_month_sheet_sums_late_minutes_of_the_day(year, subjects, teacher, cohorts, calendar, pupils, as_curator):
    """Лист месяца: в клетке опоздания — минуты дня, «оп 10», а не только «оп»."""
    from academics import marks as marking
    from academics.exports import _month_cell
    from academics.schedule import create_once
    from academics.tests.conftest import school_day

    day = school_day(-2, calendar)
    lesson = create_once(subject=subjects["alg"], teacher=teacher, cohort=cohorts["boston"], date=day, slot=2, room="1")
    marking.save_attendance(
        lesson, [{"student": pupils["damir"].pk, "mark": "late", "arrived": "09:35"}], actor=teacher, calendar=calendar
    )
    body = as_curator.get(f"/api/acad/attendance/?group=BOSTON&view=month&month={day:%Y-%m}").json()
    row = next(r for r in body["rows"] if r["id"] == pupils["damir"].pk)
    cell = row["cells"][[d["date"] for d in body["days"]].index(str(day))]
    assert cell["late"] == 1 and cell["late_minutes"] == 10
    assert _month_cell(cell) == "1оп 10"
