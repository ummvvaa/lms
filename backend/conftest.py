"""Общие фикстуры pytest."""

from __future__ import annotations

import pytest
from django.core.cache import cache

from accounts.models import Role, User
from students.models import Student, StudyGroup


@pytest.fixture(autouse=True)
def reset_throttles():
    """Счётчики DRF живут в кэше и иначе перетекают из теста в тест."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def group(db) -> StudyGroup:
    return StudyGroup.objects.create(code="G01", parallel=11)


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
        extra.setdefault("must_change_password", False)
        return User.objects.create_user(email=email, password="pass12345", role=role, **extra)

    return _make


@pytest.fixture
def set_rules(db):
    """Подменить правила школы на время теста: `set_rules(student_list_limit=2)`.

    Значения пишутся строками `core.SchoolRule` через те же функции, что
    и экран администратора: проверяются границы, сумма и порядок группы.
    Правила одной группы можно задать не все — остальные берутся текущими,
    но группа сохраняется целиком. Транзакция теста откатывает правки сама.
    """
    from core import school_rules

    def _set(**numbers) -> None:
        groups: dict[str, dict] = {}
        for code, number in numbers.items():
            rule = school_rules.BY_CODE[code]
            if rule.group:
                groups.setdefault(rule.group, {})[code] = number
            else:
                school_rules.set_value(code, number, actor=None)
        current = school_rules.values() if groups else {}
        for group, given in groups.items():
            whole = {rule.code: current[rule.code] for rule in school_rules.members_of(group)}
            school_rules.set_group(group, {**whole, **given}, actor=None)

    return _set
