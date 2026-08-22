"""Фаза 8, дефект I9: правка мимо `apply_changes` должна знать автора."""

from __future__ import annotations

import pytest

from accounts.models import Role, User
from core.actor import acting_as, get_actor
from core.models import AuditLog
from students.models import BehaviorProfile, Student


@pytest.fixture
def student(db):
    student = Student.objects.create(
        last_name="Тестов", first_name="Тест", email="actor@example.kz", grade=11, graduation_year=2027
    )
    BehaviorProfile.objects.create(student=student)
    return student


@pytest.mark.django_db
def test_signal_audit_records_actor_from_context(student):
    """Правка из админки или команды идёт мимо apply_changes — автор берётся из контекста."""
    director = User.objects.create_user(email="behavior@example.kz", password="x", role=Role.DIRECTOR_BEHAVIOR)

    profile = BehaviorProfile.objects.get(student=student)
    with acting_as(director):
        profile.attendance_percent = 77
        profile.save()

    entry = AuditLog.objects.get(field_name="attendance_percent")
    assert entry.actor == director
    assert entry.new_value == "77"


@pytest.mark.django_db
def test_actor_context_is_cleared_after_block(student):
    """Актор не должен протекать за пределы блока — иначе чужая правка получит чужого автора."""
    director = User.objects.create_user(email="exam@example.kz", password="x", role=Role.DIRECTOR_EXAM)

    with acting_as(director):
        assert get_actor() == director
    assert get_actor() is None

    profile = BehaviorProfile.objects.get(student=student)
    profile.attendance_percent = 55
    profile.save()

    assert AuditLog.objects.get(field_name="attendance_percent").actor is None
