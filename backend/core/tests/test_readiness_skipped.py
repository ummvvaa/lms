"""Фаза 8, дефект C4: домены без данных не должны молча исчезать из разбивки."""

from __future__ import annotations

import pytest

from core.readiness import compute
from students.models import AdmissionProfile, BehaviorProfile, ExamProfile, Student, TalentProfile


@pytest.mark.django_db
def test_domains_without_data_are_listed_as_skipped():
    student = Student.objects.create(
        last_name="Пустой", first_name="Профиль", email="empty@example.kz", grade=11, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile):
        model.objects.create(student=student)

    payload = compute(student).as_dict()

    counted = {p["code"] for p in payload["parts"]}
    skipped = {p["code"] for p in payload["skipped"]}

    # вместе они покрывают все пять доменов: ученик видит полную картину
    assert counted | skipped == {"exam", "admission", "talent", "behavior", "sport"}
    assert "sport" in skipped
    assert all(p["title"] for p in payload["skipped"])
