"""Импорт учеников: заводит, обновляет, идемпотентен, пишет аудит."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from core.domains import Source
from core.models import AuditLog
from students.management.commands.import_students import run_import
from students.models import Student, StudyGroup

SAMPLE = Path(__file__).parent / "data" / "students_sample.csv"


@pytest.fixture(autouse=True)
def sport_directory(db):
    """Виды спорта в файле должны быть заведены заранее.

    Импорт не заводит записи справочника сам: иначе опечатка в файле
    создаст ещё один «Футб.» и справочник перестанет быть справочником.
    """
    from directories.models import SportType

    for name in ("Футбол", "Плавание", "Волейбол"):
        SportType.objects.get_or_create(name=name)


@pytest.mark.django_db
def test_import_creates_students():
    report = run_import(SAMPLE)
    assert report.errors == []
    assert report.created == 3
    assert Student.objects.count() == 3

    s = Student.objects.get(email="alikhan@school.kz")
    assert s.full_name == "Абдрахманов Алихан Ерланович"
    assert s.group == StudyGroup.objects.get(code="G01")
    assert s.graduation_year == 2027
    assert s.behavior.attendance_percent == 94
    assert s.admission.has_common_app is True
    assert s.exam.ielts_current == Decimal("6.5")
    assert s.exam.sat_target == 1450
    assert s.talent.main_track == "olympiad"
    assert s.sport.sport_type.name == "Футбол"


@pytest.mark.django_db
def test_import_is_idempotent_by_email():
    run_import(SAMPLE)
    second = run_import(SAMPLE)
    assert Student.objects.count() == 3
    assert second.created == 0
    assert second.unchanged == 3
    assert second.audit_entries == 0


@pytest.mark.django_db
def test_import_writes_audit_on_change(tmp_path):
    run_import(SAMPLE)
    changed = tmp_path / "changed.csv"
    text = SAMPLE.read_text(encoding="utf-8").replace(",94,0,88,", ",81,2,88,")
    changed.write_text(text, encoding="utf-8")

    before = AuditLog.objects.count()
    report = run_import(changed)
    assert report.updated == 1
    assert report.unchanged == 2

    # первичное заполнение тоже пишется в журнал, поэтому смотрим только новые записи
    new_logs = AuditLog.objects.order_by("id")[before:]
    changed_fields = {(log.field_name, log.old_value, log.new_value) for log in new_logs}
    assert changed_fields == {("attendance_percent", "94", "81"), ("remarks_count", "0", "2")}
    assert all(log.source == Source.IMPORT for log in new_logs)


@pytest.mark.django_db
def test_import_reports_bad_row(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "last_name,first_name,email,grade,graduation_year,ielts_current\n" "Тестов,Тест,t@school.kz,11,2027,шесть\n",
        encoding="utf-8",
    )
    report = run_import(bad)
    assert report.created == 0
    assert len(report.errors) == 1
    assert "ielts_current" in report.errors[0]


@pytest.mark.django_db
def test_import_requires_mandatory_columns(tmp_path):
    bad = tmp_path / "nocols.csv"
    bad.write_text("name,ielts\nТестов Тест,6.5\n", encoding="utf-8")
    report = run_import(bad)
    assert report.errors and "нет обязательных колонок" in report.errors[0]


@pytest.mark.django_db
def test_dry_run_writes_nothing():
    report = run_import(SAMPLE, dry_run=True)
    assert report.created == 3
    assert Student.objects.count() == 0
