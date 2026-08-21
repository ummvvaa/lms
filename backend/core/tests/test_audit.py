"""Инвариант №9: изменение доменного поля попадает в журнал."""

from __future__ import annotations

from core.audit import apply_changes
from core.domains import Source
from core.models import AuditLog


def test_apply_changes_writes_audit(student, make_user):
    actor = make_user("director_exam", "kymbat@example.kz")
    entries = apply_changes(student.exam, {"ielts_current": "6.5"}, actor=actor, source=Source.MANUAL)
    assert len(entries) == 1
    log = AuditLog.objects.get()
    assert log.model_label == "students.ExamProfile"
    assert log.field_name == "ielts_current"
    assert log.old_value == ""
    assert log.new_value == "6.5"
    assert log.domain_code == "exam"
    assert log.source == Source.MANUAL
    assert log.student_id == student.pk
    assert log.actor == actor


def test_no_audit_when_value_unchanged(student):
    apply_changes(student.behavior, {"attendance_percent": 90})
    apply_changes(student.behavior, {"attendance_percent": 90})
    assert AuditLog.objects.filter(field_name="attendance_percent").count() == 1


def test_old_value_captured(student):
    apply_changes(student.behavior, {"attendance_percent": 90})
    apply_changes(student.behavior, {"attendance_percent": 75})
    last = AuditLog.objects.filter(field_name="attendance_percent").first()
    assert (last.old_value, last.new_value) == ("90", "75")
