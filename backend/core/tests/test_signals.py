"""Страховка инварианта №9: изменение мимо `apply_changes` тоже в журнале."""

from __future__ import annotations

import pytest

from core.audit import apply_changes
from core.models import AuditLog


@pytest.mark.django_db
def test_direct_save_is_audited(student):
    """Правка из админки или shell идёт мимо apply_changes — сигнал ловит её."""
    profile = student.behavior
    profile.attendance_percent = 88
    profile.save()

    log = AuditLog.objects.get(field_name="attendance_percent")
    assert (log.old_value, log.new_value) == ("", "88")
    assert log.domain_code == "behavior"
    assert log.actor is None


@pytest.mark.django_db
def test_apply_changes_does_not_double_write(student, make_user):
    """Основной путь пишет ровно одну запись, а не две."""
    actor = make_user("director_exam", "k@school.kz")
    apply_changes(student.exam, {"ielts_current": "7.0"}, actor=actor)
    logs = AuditLog.objects.filter(field_name="ielts_current")
    assert logs.count() == 1
    assert logs.get().actor == actor


@pytest.mark.django_db
def test_non_domain_field_is_not_audited(student):
    """Реестровые поля ученика к пяти доменам не относятся."""
    student.first_name = "Переименован"
    student.save()
    assert not AuditLog.objects.filter(field_name="first_name").exists()


@pytest.mark.django_db
def test_repeated_direct_save_logs_each_step(student):
    profile = student.behavior
    for value in (90, 75, 60):
        profile.attendance_percent = value
        profile.save()
    logs = list(AuditLog.objects.filter(field_name="attendance_percent").order_by("id"))
    assert [(x.old_value, x.new_value) for x in logs] == [("", "90"), ("90", "75"), ("75", "60")]
