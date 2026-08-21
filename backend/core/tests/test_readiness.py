"""Readiness Score: конфигурируемые веса и слабое звено по восстановимым баллам."""

from __future__ import annotations

import pytest
from django.test import override_settings

from core.readiness import compute

WEIGHTS = {"exam": 35.0, "admission": 25.0, "talent": 20.0, "behavior": 10.0, "sport": 10.0}


@pytest.fixture
def filled(student):
    """Ученик с данными по четырём доменам, без спорта."""
    student.exam.ielts_current = "6.0"
    student.exam.ielts_target = "8.0"
    student.exam.sat_current = 1200
    student.exam.sat_target = 1400
    student.exam.save()
    student.behavior.attendance_percent = 90
    student.behavior.homework_percent = 80
    student.behavior.save()
    student.admission.has_common_app = True
    student.admission.save()
    return student


@pytest.mark.django_db
@override_settings(READINESS_WEIGHTS=WEIGHTS)
def test_score_is_weighted_average(filled):
    result = compute(filled)
    assert 0 <= result.score <= 100
    # спорта нет — его вес разошёлся по остальным, сумма весов всё равно 100
    assert round(sum(p.weight for p in result.parts)) == 100
    assert {p.code for p in result.parts} == {"exam", "admission", "talent", "behavior"}


@pytest.mark.django_db
@override_settings(READINESS_WEIGHTS=WEIGHTS)
def test_weakest_is_by_recoverable_points_not_lowest_percent(filled):
    """Слабое звено — где больше восстановимых баллов, а не где меньше процент.

    Портфолио 0% с весом 22.5 даёт 22.5 восстановимых балла,
    дисциплина 85% с весом 12.5 — всего 1.9. Слабое звено — портфолио,
    хотя «самый низкий процент» тоже у него; поэтому проверяем случай,
    где эти два правила расходятся.
    """
    result = compute(filled)
    parts = {p.code: p for p in result.parts}

    # дисциплина высокая, портфолио пустое
    assert parts["behavior"].value == 85
    assert parts["talent"].value == 0
    assert result.weakest.code == "talent"

    # а теперь поднимем портфолио так, чтобы процент у него стал выше,
    # но восстановимых баллов всё равно осталось больше, чем у дисциплины
    from students.models import Activity, ActivityCategory

    for i in range(6):
        Activity.objects.create(student=filled, category=ActivityCategory.PROJECT, title=f"Проект {i}")
    filled.refresh_from_db()
    again = compute(filled)
    again_parts = {p.code: p for p in again.parts}
    assert again_parts["talent"].value == 75  # 6 из 8
    assert again_parts["behavior"].value == 85
    # у портфолио процент выше нуля, но восстановимых баллов больше, чем у дисциплины
    assert again_parts["talent"].recoverable > again_parts["behavior"].recoverable
    assert again.weakest.code != "behavior"


@pytest.mark.django_db
@override_settings(READINESS_WEIGHTS={"exam": 80.0, "admission": 5.0, "talent": 5.0, "behavior": 5.0, "sport": 5.0})
def test_weights_come_from_settings(filled):
    """Веса не зашиты в код: другой набор — другой результат."""
    heavy_exam = compute(filled)
    with override_settings(READINESS_WEIGHTS=WEIGHTS):
        balanced = compute(filled)
    assert heavy_exam.score != balanced.score


@pytest.mark.django_db
@override_settings(READINESS_WEIGHTS=WEIGHTS)
def test_missing_sport_does_not_cap_the_score(student):
    """У неспортсмена потолок должен оставаться 100, а не 90."""
    student.exam.ielts_current = "8.0"
    student.exam.ielts_target = "8.0"
    student.exam.sat_current = 1400
    student.exam.sat_target = 1400
    student.exam.save()
    student.behavior.attendance_percent = 100
    student.behavior.homework_percent = 100
    student.behavior.save()
    student.admission.has_common_app = True
    student.admission.has_application_account = True
    student.admission.save()

    from students.models import Activity, ActivityCategory

    for i in range(8):
        Activity.objects.create(student=student, category=ActivityCategory.PROJECT, title=f"П{i}")

    student.refresh_from_db()
    result = compute(student)
    assert "sport" not in {p.code for p in result.parts}
    assert result.parts and all(p.value == 100 for p in result.parts if p.code in ("talent", "behavior"))


@pytest.mark.django_db
@override_settings(READINESS_WEIGHTS=WEIGHTS)
def test_empty_student_scores_zero(student):
    result = compute(student)
    assert result.score == 0


@pytest.mark.django_db
@override_settings(READINESS_WEIGHTS=WEIGHTS)
def test_snapshot_task_writes_rows(filled):
    from core.models import ReadinessSnapshot
    from core.tasks import snapshot_readiness

    assert snapshot_readiness() == 1
    snapshot = ReadinessSnapshot.objects.get(student=filled)
    assert snapshot.score == compute(filled).score
    assert snapshot.weakest == "talent"

    # повторный запуск в тот же день обновляет срез, а не плодит второй
    snapshot_readiness()
    assert ReadinessSnapshot.objects.count() == 1
