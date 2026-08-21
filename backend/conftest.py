"""Общие фикстуры pytest."""

from __future__ import annotations

import pytest

from accounts.models import Role, User
from students.models import Student, StudyGroup


@pytest.fixture
def group(db) -> StudyGroup:
    return StudyGroup.objects.create(code="G01", grade=11)


@pytest.fixture
def student(db, group) -> Student:
    """Ученик с пустыми профилями — база стартует пустой (инвариант №8)."""
    from students.models import (
        AdmissionProfile,
        BehaviorProfile,
        ExamProfile,
        SportProfile,
        TalentProfile,
    )

    s = Student.objects.create(
        last_name="Тестов",
        first_name="Тест",
        email="test.student@example.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=s)
    return s


@pytest.fixture
def make_user(db):
    """Фабрика пользователей с заданной ролью."""

    def _make(role: str = Role.STUDENT, email: str | None = None, **extra) -> User:
        email = email or f"{role}@example.kz"
        return User.objects.create_user(email=email, password="pass12345", role=role, **extra)

    return _make
