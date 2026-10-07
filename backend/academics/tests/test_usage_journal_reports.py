"""Одна операция журнала или отчёта даёт одно событие независимо от размера списка."""

# ruff: noqa: F811 — общие фикстуры отчётов импортированы по имени

from unittest.mock import Mock

import pytest

from academics.models import Quarter
from academics.tests.test_parent_reports import built, graded  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def tracked(monkeypatch):
    tracker = Mock()
    monkeypatch.setattr("core.usage.track", tracker)
    return tracker


def test_attendance_first_mark_and_bulk_change_are_counted_but_empty_repeat_is_not(lesson, pupils, as_teacher, tracked):
    path = f"/api/acad/lessons/{lesson.pk}/attendance/"
    assert as_teacher.post(path, {"all_present": True}, format="json").status_code == 200
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == "journal.attendance.set"
    assert as_teacher.post(path, {"all_present": True}, format="json").status_code == 200
    assert tracked.call_count == 1
    response = as_teacher.post(
        path,
        {"rows": [{"student": pupils[key].pk, "mark": "absent"} for key in ("aliya", "damir")]},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["written"] == 2 and tracked.call_count == 2


def test_grade_emits_after_save_but_not_on_refusal(lesson, pupils, as_teacher, tracked):
    path = f"/api/acad/lessons/{lesson.pk}/grade/"
    response = as_teacher.post(path, {"student": pupils["aliya"].pk, "value": 99}, format="json")
    assert response.status_code == 400
    tracked.assert_not_called()
    response = as_teacher.post(path, {"student": pupils["aliya"].pk, "value": 8}, format="json")
    assert response.status_code == 200
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == "journal.grade.set"


def test_finals_bulk_is_one_operation_and_empty_list_is_zero(lesson, pupils, as_teacher, tracked, year):
    quarter = Quarter.objects.get(year=year, number=1)
    path = f"/api/acad/journals/{lesson.course_id}/final/"
    rows = [{"student": pupils[key].pk, "final": 4, "reason": "Итог учителя"} for key in ("aliya", "damir")]
    response = as_teacher.post(path, {"quarter": quarter.pk, "rows": rows}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["written"] == 2
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == "journal.final.set"
    assert as_teacher.post(path, {"quarter": quarter.pk, "rows": []}, format="json").status_code == 200
    assert tracked.call_count == 1


def test_report_edit_check_and_refresh_have_distinct_single_events(built, pupils, as_curator, tracked):
    row = built[pupils["aliya"].pk]
    path = f"/api/acad/reports/{row.pk}/"
    response = as_curator.patch(path, {"curator_word": "Готово к обсуждению"}, format="json")
    assert response.status_code == 200
    assert tracked.call_args.args[1] == "report.edit"
    assert as_curator.patch(path, {"curator_word": "Готово к обсуждению"}, format="json").status_code == 200
    assert tracked.call_count == 1
    assert as_curator.post(path + "check/", {}, format="json").status_code == 200
    assert tracked.call_args.args[1] == "report.check" and tracked.call_count == 2
    assert as_curator.post(path + "check/", {}, format="json").status_code == 200
    assert tracked.call_count == 2
    assert as_curator.post(path + "refresh/", {}, format="json").status_code == 200
    assert tracked.call_args.args[1] == "report.refresh" and tracked.call_count == 3


def test_bulk_reports_emit_once_and_empty_selection_emits_nothing(built, pupils, as_curator, tracked):
    ids = [built[pupils[key].pk].pk for key in ("aliya", "damir")]
    for suffix, key in (("check", "report.check"), ("refresh", "report.refresh"), ("sent", "report.sent.set")):
        before = tracked.call_count
        response = as_curator.post(f"/api/acad/reports/{suffix}/", {"ids": ids}, format="json")
        assert response.status_code == 200, response.data
        assert tracked.call_count == before + 1 and tracked.call_args.args[1] == key
        assert as_curator.post(f"/api/acad/reports/{suffix}/", {"ids": []}, format="json").status_code == 200
        assert tracked.call_count == before + 1


def test_report_file_counts_download_once_without_template_or_poll_events(
    built, pupils, as_curator, tracked, monkeypatch
):
    row = built[pupils["aliya"].pk]
    path = f"/api/acad/reports/{row.pk}/"
    assert as_curator.get(path + "pdf/").status_code == 400
    tracked.assert_not_called()
    assert as_curator.post(path + "check/", {}, format="json").status_code == 200
    tracked.reset_mock()
    monkeypatch.setattr("academics.report_files.render", lambda *args: (b"%PDF-test", "report.pdf", "application/pdf"))
    assert as_curator.get(path + "pdf/").status_code == 200
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == "export.download"


def test_report_export_acceptance_poll_and_download_are_not_double_counted(
    built, pupils, as_curator, tracked, monkeypatch
):
    row = built[pupils["aliya"].pk]
    assert as_curator.post(f"/api/acad/reports/{row.pk}/check/", {}, format="json").status_code == 200
    tracked.reset_mock()
    monkeypatch.setattr("academics.report_files.start_export", lambda **kwargs: "usage-job")
    accepted = as_curator.post("/api/acad/reports/export/", {"ids": [row.pk]}, format="json")
    assert accepted.status_code == 200, accepted.data
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == "report.export.start"
    monkeypatch.setattr("academics.report_files.export_state", lambda *args: {"state": "done"})
    assert as_curator.get("/api/acad/reports/export/usage-job/").status_code == 200
    assert tracked.call_count == 1
    monkeypatch.setattr("academics.report_files.export_file", lambda *args: (b"zip data", "reports.zip"))
    assert as_curator.get("/api/acad/reports/export/usage-job/file/").status_code == 200
    assert tracked.call_count == 2 and tracked.call_args.args[1] == "export.download"
