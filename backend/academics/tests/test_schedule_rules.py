"""Расписание: материализация, накладки, правка серии, замена, перенос, отмена, удаление в архив."""

from __future__ import annotations

import datetime as dt

import pytest

from academics import schedule
from academics.cohorts import make_stream, member_ids, students_share
from academics.models import Attendance, Break, Holiday, Lesson, LessonSeries, LessonStatus, RequestStatus
from academics.tests.conftest import days, login, school_day
from core.models import ArchiveEntry, AuditLog, Notification

pytestmark = pytest.mark.django_db


def _series(subjects, teacher, cohort, calendar, *, starts=None, slot=2, room="204", subject="alg", ends=None):
    starts = starts or school_day(1, calendar)
    return schedule.create_weekly(
        subject=subjects[subject],
        teacher=teacher,
        cohort=cohort,
        starts=starts,
        slot=slot,
        room=room,
        calendar=calendar,
        ends=ends,
    )


# --- Повтор по неделям ---------------------------------------------------------


def test_weekly_lesson_is_materialized_until_the_year_ends_and_skips_breaks(year, subjects, teacher, cohorts, calendar):
    start = school_day(1, calendar)
    Break.objects.create(
        year=year, title="Каникулы", starts=start + dt.timedelta(days=7), ends=start + dt.timedelta(days=13)
    )
    Holiday.objects.create(year=year, date=start + dt.timedelta(days=21), title="Праздник")
    fresh = __import__("academics.calendar", fromlist=["load"]).load(year)
    series = _series(subjects, teacher, cohorts["boston"], fresh, starts=start)
    dates = list(series.lessons.order_by("date").values_list("date", flat=True))
    assert dates[0] == start
    assert all(day.isoweekday() == start.isoweekday() for day in dates)
    assert start + dt.timedelta(days=7) not in dates, "каникулы пропускаются"
    assert start + dt.timedelta(days=21) not in dates, "праздник пропускается"
    assert start + dt.timedelta(days=14) in dates
    assert dates[-1] <= year.ends
    assert Lesson.objects.filter(series=series).count() == len(dates) >= 10


def test_weekly_lesson_must_start_on_a_school_day(year, subjects, teacher, cohorts, calendar):
    saturday = days(1)
    while saturday.weekday() != 5:
        saturday += dt.timedelta(days=1)
    with pytest.raises(schedule.ScheduleRefused):
        _series(subjects, teacher, cohorts["boston"], calendar, starts=saturday)


def test_one_off_lesson_stands_alone(year, subjects, teacher, cohorts, calendar):
    lesson = schedule.create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(3, calendar),
        slot=8,
        room="204",
        note="Консультация",
    )
    assert lesson.series_id is None
    assert Lesson.objects.count() == 1


# --- Накладки ---------------------------------------------------------------------


def test_conflict_when_the_teacher_leads_two_lessons_at_once(year, subjects, teacher, cohorts, calendar):
    day = school_day(1, calendar)
    _series(subjects, teacher, cohorts["boston"], calendar, starts=day, slot=2)
    found = schedule.conflicts_for(date=day, slot=2, teacher_id=teacher.pk, cohort=cohorts["chicago"], room="")
    assert [c.kind for c in found] == ["teacher"]
    assert "ведёт два урока сразу" in found[0].text


def test_conflict_when_the_room_is_taken(year, subjects, teacher, other_teacher, cohorts, calendar):
    day = school_day(1, calendar)
    _series(subjects, teacher, cohorts["boston"], calendar, starts=day, slot=2, room="204")
    found = schedule.conflicts_for(date=day, slot=2, teacher_id=other_teacher.pk, cohort=cohorts["chicago"], room="204")
    assert [c.kind for c in found] == ["room"]


def test_conflict_when_cohorts_share_students(year, subjects, teacher, other_teacher, cohorts, calendar):
    day = school_day(1, calendar)
    _series(subjects, teacher, cohorts["boston"], calendar, starts=day, slot=2)
    found = schedule.conflicts_for(date=day, slot=2, teacher_id=other_teacher.pk, cohort=cohorts["eng1"], room="305")
    assert [c.kind for c in found] == ["students"]


def test_two_subgroups_of_one_group_at_the_same_time_are_not_a_conflict(
    year, subjects, teacher, other_teacher, cohorts, calendar
):
    day = school_day(1, calendar)
    _series(subjects, other_teacher, cohorts["eng1"], calendar, starts=day, slot=2, room="305", subject="eng")
    assert not students_share(cohorts["eng1"], cohorts["eng2"])
    found = schedule.conflicts_for(date=day, slot=2, teacher_id=teacher.pk, cohort=cohorts["eng2"], room="306")
    assert found == []


def test_stream_does_not_duplicate_a_student_in_a_group_and_its_subgroup(boston, cohorts, pupils):
    stream = make_stream(name="BOSTON + подгруппа", parts=[cohorts["boston"], cohorts["eng1"]])
    ids = member_ids(stream)
    assert len(ids) == len(set(ids)) == 3


def test_conflict_is_saved_only_with_force_and_hangs_in_the_list(year, subjects, teacher, cohorts, calendar, as_kymbat):
    day = school_day(1, calendar)
    _series(subjects, teacher, cohorts["boston"], calendar, starts=day, slot=2)
    payload = {
        "subject": subjects["alg"].pk,
        "teacher": teacher.pk,
        "cohort": cohorts["chicago"].pk,
        "date": day,
        "slot": 2,
        "room": "",
        "repeat": "once",
    }
    refused = as_kymbat.post("/api/acad/lessons/", payload, format="json")
    assert refused.status_code == 409
    assert refused.json()["conflicts"][0]["kind"] == "teacher"
    saved = as_kymbat.post("/api/acad/lessons/", {**payload, "force": True}, format="json")
    assert saved.status_code == 201
    week = as_kymbat.get(f"/api/acad/schedule/?from={day - dt.timedelta(days=day.weekday())}").json()
    assert any(c["kind"] == "teacher" for c in week["conflicts"])


# --- Правка -------------------------------------------------------------------------


def test_edit_only_this_lesson_moves_one_row_and_keeps_the_series(
    year, subjects, teacher, other_teacher, cohorts, calendar, kymbat
):
    series = _series(subjects, teacher, cohorts["boston"], calendar)
    second = series.lessons.order_by("date")[1]
    new_day = second.date + dt.timedelta(days=1)
    schedule.edit_this(second, date=new_day, slot=5, room="210", teacher=other_teacher, actor=kymbat)
    second.refresh_from_db()
    assert (second.date, second.slot, second.room, second.substitute_id, second.status) == (
        new_day,
        5,
        "210",
        other_teacher.pk,
        LessonStatus.MOVED,
    )
    assert series.lessons.exclude(pk=second.pk).filter(slot=2).count() == series.lessons.count() - 1
    assert AuditLog.objects.filter(model_label="academics.Lesson", object_id=str(second.pk), field_name="slot").exists()


def test_edit_this_and_following_closes_the_old_series_and_keeps_the_past(
    year, subjects, teacher, other_teacher, cohorts, calendar, kymbat
):
    series = _series(subjects, teacher, cohorts["boston"], calendar)
    rows = list(series.lessons.order_by("date"))
    cut = rows[2]
    new_series = schedule.edit_from(
        cut,
        subject=subjects["alg"],
        teacher=other_teacher,
        cohort=cohorts["boston"],
        date=cut.date,
        slot=6,
        room="211",
        calendar=calendar,
        actor=kymbat,
    )
    series.refresh_from_db()
    assert series.ends == cut.date - dt.timedelta(days=1)
    assert series.lessons.count() == 2, "первые два урока остались в старой серии"
    assert new_series.lessons.filter(slot=6, teacher=other_teacher).count() == new_series.lessons.count() > 0
    assert Lesson.objects.filter(pk=cut.pk).exists() is False, "будущий урок без отметок стёрт, не архивирован"


def test_past_lessons_are_never_edited(lesson, kymbat, calendar):
    with pytest.raises(schedule.ScheduleRefused):
        schedule.edit_this(lesson, date=lesson.date, slot=4, room="1", actor=kymbat)
    with pytest.raises(schedule.ScheduleRefused):
        schedule.cancel(lesson, reason="поздно", actor=kymbat)


def test_substitute_sees_the_lesson_and_busy_teacher_is_refused(
    year, subjects, teacher, other_teacher, cohorts, calendar, kymbat
):
    day = school_day(1, calendar)
    first = _series(subjects, teacher, cohorts["boston"], calendar, starts=day, slot=2).lessons.order_by("date").first()
    _series(subjects, other_teacher, cohorts["chicago"], calendar, starts=day, slot=2, room="305")
    with pytest.raises(schedule.ScheduleRefused):
        schedule.substitute(first, teacher=other_teacher, reason="болеет", actor=kymbat)
    third = make_stream  # noqa: F841 — держит импорт для читателя
    free_day_lesson = (
        _series(subjects, teacher, cohorts["boston"], calendar, starts=day, slot=4).lessons.order_by("date").first()
    )
    schedule.substitute(free_day_lesson, teacher=other_teacher, reason="болеет", actor=kymbat)
    free_day_lesson.refresh_from_db()
    assert free_day_lesson.actual_teacher_id == other_teacher.pk
    assert Notification.objects.filter(recipient=other_teacher, kind=Notification.Kind.LESSON_CHANGED).exists()


def test_move_and_restore(year, subjects, teacher, cohorts, calendar, kymbat):
    series = _series(subjects, teacher, cohorts["boston"], calendar)
    row = series.lessons.order_by("date").first()
    origin = (row.date, row.slot)
    target = school_day(2, calendar) if school_day(2, calendar) != row.date else school_day(3, calendar)
    schedule.move(row, date=target, slot=7, reason="олимпиада", calendar=calendar, actor=kymbat)
    row.refresh_from_db()
    assert (row.date, row.slot, row.status, row.moved_from_date, row.moved_from_slot) == (
        target,
        7,
        LessonStatus.MOVED,
        *origin,
    )
    schedule.restore(row, actor=kymbat)
    row.refresh_from_db()
    assert (row.date, row.slot, row.status) == (*origin, LessonStatus.PLANNED)


def test_cancel_keeps_the_row_and_notifies_teacher_and_students(
    year, subjects, teacher, cohorts, pupils, calendar, kymbat
):
    row = _series(subjects, teacher, cohorts["boston"], calendar).lessons.order_by("date").first()
    schedule.cancel(row, reason="учитель на семинаре", actor=kymbat)
    row.refresh_from_db()
    assert row.status == LessonStatus.CANCELLED and row.reason == "учитель на семинаре"
    assert Notification.objects.filter(recipient=teacher, kind=Notification.Kind.LESSON_CHANGED).exists()
    assert Notification.objects.filter(recipient=pupils["aliya"].user, kind=Notification.Kind.LESSON_CHANGED).exists()


# --- Удаление ----------------------------------------------------------------------


def test_lesson_without_marks_is_deleted_for_good_and_with_marks_goes_to_archive(
    year, subjects, teacher, cohorts, pupils, calendar, kymbat
):
    series = _series(subjects, teacher, cohorts["boston"], calendar)
    empty, marked = list(series.lessons.order_by("date")[:2])
    Attendance.objects.create(lesson=marked, student=pupils["aliya"], mark="absent")
    schedule.delete(empty, scope="this", actor=kymbat)
    assert not Lesson.all_objects.filter(pk=empty.pk).exists()
    preview = schedule.delete_preview(marked, "this")
    assert preview == {"count": 1, "marked": 1, "from": marked.date, "to": marked.date}
    schedule.delete(marked, scope="this", actor=kymbat)
    assert Lesson.objects.filter(pk=marked.pk).exists() is False
    assert Lesson.all_objects.get(pk=marked.pk).is_archived
    assert Attendance.all_objects.get(lesson=marked).is_archived, "отметки ушли в архив вместе с уроком"
    entry = ArchiveEntry.objects.get(model_label="academics.Lesson", object_id=str(marked.pk))
    from core.archive import restore

    restore(entry, actor=kymbat)
    assert Lesson.objects.filter(pk=marked.pk).exists()
    assert Attendance.objects.filter(lesson=marked).exists(), "и вернулись из архива вместе с ним"


def test_delete_this_and_following_cuts_the_series(year, subjects, teacher, cohorts, calendar, kymbat):
    series = _series(subjects, teacher, cohorts["boston"], calendar)
    rows = list(series.lessons.order_by("date"))
    outcome = schedule.delete(rows[3], scope="next", actor=kymbat)
    assert outcome["deleted"] == len(rows) - 3
    series.refresh_from_db()
    assert series.lessons.count() == 3 and series.ends == rows[3].date - dt.timedelta(days=1)


# --- Просьбы учителей -------------------------------------------------------------


def test_teacher_request_goes_to_kymbat_and_approval_moves_the_lesson(
    year, subjects, teacher, cohorts, calendar, kymbat, as_teacher, as_kymbat
):
    row = _series(subjects, teacher, cohorts["boston"], calendar).lessons.order_by("date").first()
    sent = as_teacher.post(
        "/api/acad/requests/", {"lesson": row.pk, "wanted": "на 7 урок", "reason": "олимпиада"}, format="json"
    )
    assert sent.status_code == 201
    assert Notification.objects.filter(recipient=kymbat, kind=Notification.Kind.LESSON_REQUEST).exists()
    request_id = sent.json()["request"]["id"]
    decided = as_kymbat.post(f"/api/acad/requests/{request_id}/decide/", {"approve": True, "slot": 7}, format="json")
    assert decided.status_code == 200, decided.content
    row.refresh_from_db()
    assert row.slot == 7 and row.status == LessonStatus.MOVED
    assert Notification.objects.filter(recipient=teacher, kind=Notification.Kind.LESSON_REQUEST_DECIDED).exists()


def test_rejection_needs_an_answer(year, subjects, teacher, cohorts, calendar, as_teacher, as_kymbat):
    row = _series(subjects, teacher, cohorts["boston"], calendar).lessons.order_by("date").first()
    request_id = as_teacher.post(
        "/api/acad/requests/", {"lesson": row.pk, "reason": "олимпиада"}, format="json"
    ).json()["request"]["id"]
    assert (
        as_kymbat.post(f"/api/acad/requests/{request_id}/decide/", {"approve": False}, format="json").status_code == 400
    )
    ok = as_kymbat.post(
        f"/api/acad/requests/{request_id}/decide/", {"approve": False, "answer": "в другой день"}, format="json"
    )
    assert ok.status_code == 200 and ok.json()["request"]["status"] == RequestStatus.REJECTED


def test_reassign_moves_future_lessons_only(year, subjects, teacher, other_teacher, cohorts, calendar, kymbat):
    series = _series(subjects, teacher, cohorts["boston"], calendar)
    rows = list(series.lessons.order_by("date"))
    schedule.reassign(series.course, teacher=other_teacher, since=rows[2].date, actor=kymbat)
    assert Lesson.objects.filter(series=series, date__lt=rows[2].date, teacher=teacher).count() == 2
    assert Lesson.objects.filter(series=series, date__gte=rows[2].date, teacher=other_teacher).count() == len(rows) - 2


def test_schedule_changes_are_logged_in_words(year, subjects, teacher, cohorts, calendar, kymbat, as_kymbat):
    _series(subjects, teacher, cohorts["boston"], calendar)
    log = schedule.recent_changes()
    assert log and "Добавлен урок" in log[0]["text"]
    assert LessonSeries.objects.count() == 1
    week = as_kymbat.get("/api/acad/schedule/").json()
    assert week["log"][0]["text"].startswith("Добавлен урок")


def test_only_kymbat_and_admin_edit_the_schedule(lesson, as_curator, as_teacher, as_admin):
    for client in (as_curator, as_teacher):
        response = client.post(f"/api/acad/lessons/{lesson.pk}/cancel/", {"reason": "нет"}, format="json")
        assert response.status_code in (403, 404), client
    login  # noqa: B018 — импорт нужен другим тестам модуля
    assert as_admin.get("/api/acad/schedule/").status_code == 200
