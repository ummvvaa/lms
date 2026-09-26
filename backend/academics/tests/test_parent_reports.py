"""Отчёты родителям: разделы, снимок, статусы, PDF, ZIP, «Обновить данные», сообщение."""

from __future__ import annotations

import io
import zipfile

import pytest
from django.utils import timezone

from academics import marks as marking
from academics import reports as reporting
from academics.calendar import scale_of
from academics.models import ParentReport, ReportPeriod, ReportSection, ReportSettings, ReportStatus
from academics.tests.conftest import days, login
from core.models import AuditLog, Notification

pytestmark = pytest.mark.django_db


@pytest.fixture
def graded(lesson, pupils, teacher, calendar):
    scale = scale_of(calendar.year)
    marking.set_grade(
        lesson, pupils["aliya"], 8, comment="Видят ученик и родители", actor=teacher, calendar=calendar, scale=scale
    )
    marking.save_attendance(
        lesson, [{"student": pupils["damir"].pk, "mark": "absent"}], actor=teacher, calendar=calendar
    )
    return lesson


@pytest.fixture
def built(graded, calendar, pupils, admin):
    start, end = reporting.month_bounds(days(0))
    rows = reporting.build_for_period(kind=ReportPeriod.MONTH, start=start, end=end, calendar=calendar, actor=admin)
    return {row.student_id: row for row in rows}


def test_sections_follow_the_settings_and_have_no_teacher_comments(built, pupils, year):
    report = built[pupils["aliya"].pk]
    sections = {line.section for line in report.lines.all()}
    assert ReportSection.ATTENDANCE in sections and ReportSection.GRADES in sections
    assert ReportSection.DISCIPLINE not in sections, "дисциплина выключена по умолчанию"
    texts = " ".join(f"{line.title} {line.value} {line.note}" for line in report.lines.all())
    assert "Видят ученик и родители" not in texts, "комментарий к оценке в отчёт не попадает"
    assert "Комментарии учителей" not in texts
    assert "Алгебра" in texts and "ФО 8" in texts
    config = ReportSettings.objects.get(year=year)
    config.section_grades = False
    config.section_discipline = True
    config.save()
    rebuilt = reporting.build_report(
        pupils["aliya"],
        kind=ReportPeriod.MONTH,
        start=report.period_start,
        end=report.period_end,
        calendar=__import__("academics.calendar", fromlist=["load"]).load(year),
        config=config,
    )
    sections = {line.section for line in rebuilt.lines.all()}
    assert ReportSection.GRADES not in sections and ReportSection.DISCIPLINE in sections


def test_report_is_a_snapshot_and_refresh_reverts_status_only_when_data_changed(
    built, pupils, teacher, calendar, curator, as_curator
):
    report = built[pupils["aliya"].pk]
    as_curator.post(f"/api/acad/reports/{report.pk}/check/", {"curator_word": "Хорошо"}, format="json")
    report.refresh_from_db()
    assert report.status == ReportStatus.CHECKED
    same = as_curator.post(f"/api/acad/reports/{report.pk}/refresh/", {}, format="json").json()
    assert same["changed"] is False and same["status"] == ReportStatus.CHECKED, "данные те же — статус остаётся"
    scale = scale_of(calendar.year)
    marking.set_grade(
        report.student.grades.first().lesson, pupils["aliya"], 10, actor=teacher, calendar=calendar, scale=scale
    )
    detail = as_curator.get(f"/api/acad/reports/{report.pk}/").json()
    assert "ФО 8" in str(detail["sections"]), "снимок при чтении не пересчитывается"
    changed = as_curator.post(f"/api/acad/reports/{report.pk}/refresh/", {}, format="json").json()
    assert (
        changed["changed"] is True and changed["status"] == ReportStatus.DRAFT and changed["curator_word"] == "Хорошо"
    )
    assert "ФО 10" in str(changed["sections"])


def test_statuses_draft_checked_exported_sent(built, pupils, parent, as_curator, curator):
    report = built[pupils["aliya"].pk]
    assert as_curator.get(f"/api/acad/reports/{report.pk}/pdf/").status_code == 400, "черновик не выгружается"
    checked = as_curator.post(
        f"/api/acad/reports/{report.pk}/check/", {"curator_word": "Молодец"}, format="json"
    ).json()
    assert checked["status"] == ReportStatus.CHECKED and checked["checked_by"] == "Асель Куратор"
    pdf = as_curator.get(f"/api/acad/reports/{report.pk}/pdf/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    report.refresh_from_db()
    assert report.status == ReportStatus.EXPORTED and report.exported_at is not None
    sent = as_curator.post(f"/api/acad/reports/{report.pk}/sent/", {"sent": True}, format="json").json()
    assert sent["status"] == ReportStatus.SENT and sent["sent_at"]
    assert AuditLog.objects.filter(student_id=pupils["aliya"].pk, field_name="report_sent").exists()
    back = as_curator.post(f"/api/acad/reports/{report.pk}/sent/", {"sent": False}, format="json").json()
    assert back["status"] == ReportStatus.EXPORTED
    assert as_curator.patch(f"/api/acad/reports/{report.pk}/", {"curator_word": "x"}, format="json").status_code == 200


def test_pdf_has_cyrillic_and_the_file_name_is_by_the_rule(built, pupils, parent, as_curator):
    from pypdf import PdfReader

    report = built[pupils["aliya"].pk]
    as_curator.post(
        f"/api/acad/reports/{report.pk}/check/", {"curator_word": "Алия уверенно идёт к цели"}, format="json"
    )
    response = as_curator.get(f"/api/acad/reports/{report.pk}/pdf/")
    disposition = response["Content-Disposition"]
    assert (
        "filename*=UTF-8''" in disposition and "%D0%90%D1%85%D0%BC%D0%B5%D1%82%D0%BE%D0%B2%D0%B0" in disposition
    ), disposition
    assert 'filename="ahmetova aliya - otchet za ' in disposition and disposition.split('"')[1].endswith(".pdf")
    reader = PdfReader(io.BytesIO(response.content))
    assert 1 <= len(reader.pages) <= 2
    text = "".join(page.extract_text() for page in reader.pages)
    assert "Ахметова Алия" in text and "Алгебра" in text and "Слово куратора" in text and "уверенно" in text
    assert "needs_supervision" not in text and "critical" not in text


def test_zip_holds_one_pdf_per_student_and_only_checked_ones(built, pupils, boston, as_curator):
    aliya, damir = built[pupils["aliya"].pk], built[pupils["damir"].pk]
    refused = as_curator.get(f"/api/acad/reports/zip/?group={boston.code}")
    assert refused.status_code == 400, "проверенных нет — архива нет"
    for report in (aliya, damir):
        as_curator.post(f"/api/acad/reports/{report.pk}/check/", {}, format="json")
    response = as_curator.get(f"/api/acad/reports/zip/?group={boston.code}")
    assert response.status_code == 200 and response["Content-Type"] == "application/zip"
    assert "%D0%BE%D1%82%D1%87%D1%91%D1%82%D1%8B" in response["Content-Disposition"], "«BOSTON — отчёты за …»"
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert len(names) == 2 and all(name.endswith(".pdf") for name in names)
    assert any(name.startswith("Ахметова Алия — отчёт за") for name in names)
    assert not any("Абдрахман" in name for name in names), "черновик Нурай в архив не вошёл"
    for report in (aliya, damir):
        report.refresh_from_db()
        assert report.status == ReportStatus.EXPORTED
    picked = as_curator.get(f"/api/acad/reports/zip/?ids={aliya.pk}")
    assert len(zipfile.ZipFile(io.BytesIO(picked.content)).namelist()) == 1


def test_message_and_parent_phone_come_with_the_report(built, pupils, parent, as_curator, settings):
    settings.SCHOOL_SHORT_NAME = "BHS"
    report = built[pupils["aliya"].pk]
    detail = as_curator.get(f"/api/acad/reports/{report.pk}/").json()
    assert detail["phones"][0]["phone"] == "+77071234567", "казахстанский номер приведён к +7"
    expected = "Добрый день! Отчёт BHS за сентябрь по ученику Ахметова Алия во вложении. Куратор группы BOSTON, Асель"
    assert detail["message"] == expected or detail["message"].startswith("Добрый день! Отчёт BHS за ")
    assert detail["file_name"].startswith("Ахметова Алия — отчёт за ")


def test_no_phone_is_a_hint_not_a_block(built, pupils, as_curator):
    report = built[pupils["damir"].pk]
    detail = as_curator.get(f"/api/acad/reports/{report.pk}/").json()
    assert detail["phones"] == []
    as_curator.post(f"/api/acad/reports/{report.pk}/check/", {}, format="json")
    assert as_curator.get(f"/api/acad/reports/{report.pk}/pdf/").status_code == 200


def test_curators_get_one_notification_per_group(built, pupils, curator):
    rows = list(ParentReport.objects.filter(student__group=pupils["aliya"].group))
    sent = reporting.notify_curators(rows, rows[0].title)
    assert sent == 1
    note = Notification.objects.get(recipient=curator, kind=Notification.Kind.REPORTS_BUILT)
    assert "ждут проверки" in note.text and note.link == "/reports"


def test_reports_are_visible_to_curator_of_the_group_kymbat_and_admin_and_not_to_others(
    built, pupils, curator, kymbat, admin, teacher, saltanat
):
    report = built[pupils["aliya"].pk]
    stranger = built[pupils["stranger"].pk]
    assert login(curator).get(f"/api/acad/reports/{report.pk}/").status_code == 200
    assert login(curator).get(f"/api/acad/reports/{stranger.pk}/").status_code == 404
    assert login(kymbat).get(f"/api/acad/reports/{stranger.pk}/").status_code == 200
    assert login(admin).get(f"/api/acad/reports/{stranger.pk}/").status_code == 200
    assert login(teacher).get(f"/api/acad/reports/{report.pk}/").status_code == 404
    assert login(saltanat).get(f"/api/acad/reports/{report.pk}/").status_code == 403


def test_monthly_task_builds_only_on_the_last_friday(year, graded, pupils, monkeypatch):
    from academics import tasks

    friday_last = days(0)
    while not reporting.is_last_friday(friday_last):
        friday_last += __import__("datetime").timedelta(days=1)
    monkeypatch.setattr(
        tasks.school_calendar, "today", lambda: days(0) if not reporting.is_last_friday(days(0)) else days(1)
    )
    if not reporting.is_last_friday(tasks.school_calendar.today()):
        assert tasks.build_monthly_reports() == 0
    monkeypatch.setattr(tasks.school_calendar, "today", lambda: friday_last)
    assert tasks.build_monthly_reports() >= 4
    assert ParentReport.objects.filter(period_kind=ReportPeriod.MONTH).count() >= 4


def test_quarter_only_cadence_skips_the_monthly_build(year, graded, monkeypatch):
    from academics import tasks

    config = ReportSettings.objects.get(year=year)
    config.cadence = "quarter"
    config.save()
    monkeypatch.setattr(reporting, "is_last_friday", lambda day: True)
    assert tasks.build_monthly_reports() == 0
    assert tasks.build_monthly_reports(force=True) > 0


def test_closing_a_quarter_builds_quarter_reports(year, graded, pupils, as_kymbat):
    from academics.models import Quarter

    quarter = Quarter.objects.get(year=year, number=1)
    response = as_kymbat.post(f"/api/acad/year/quarters/{quarter.pk}/close/", {"closed": True}, format="json")
    assert response.status_code == 200 and response.json()["quarter"]["closed"]
    rows = ParentReport.objects.filter(period_kind=ReportPeriod.QUARTER, period_start=quarter.starts)
    assert rows.count() >= 4 and rows.first().title.startswith("1 четверть")
    assert timezone.now() is not None
