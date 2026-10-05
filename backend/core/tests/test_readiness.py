"""Readiness Score: конфигурируемые веса и слабое звено по восстановимым баллам."""

from __future__ import annotations

import pytest

from core.readiness import compute


@pytest.fixture
def filled(student):
    """Ученик с данными по четырём доменам, без спорта."""
    student.exam.ielts_current = "6.0"
    student.exam.ielts_target = "8.0"
    student.exam.sat_current = 1200
    student.exam.sat_target = 1400
    student.exam.save()
    # выполнение ДЗ считается из сдач — без заданий дисциплина равна посещаемости
    student.behavior.attendance_percent = 85
    student.behavior.save()
    student.admission.has_common_app = True
    student.admission.save()
    return student


@pytest.mark.django_db
def test_score_is_weighted_average(filled):
    result = compute(filled)
    assert 0 <= result.score <= 100
    # спорта нет — его вес разошёлся по остальным, сумма весов всё равно 100
    assert round(sum(p.weight for p in result.parts)) == 100
    assert {p.code for p in result.parts} == {"exam", "admission", "talent", "behavior"}


@pytest.mark.django_db
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
def test_weights_come_from_school_rules(filled, set_rules):
    """Веса не зашиты в код: администратор задал другой набор — другой результат."""
    balanced = compute(filled)
    set_rules(
        readiness_w_exam=80, readiness_w_admission=5, readiness_w_talent=5, readiness_w_behavior=5, readiness_w_sport=5
    )
    heavy_exam = compute(filled)
    assert heavy_exam.score != balanced.score


@pytest.mark.django_db
def test_floors_targets_and_points_come_from_school_rules(filled, set_rules):
    """Планки, цели и баллы внутри доменов — те же правила школы, не константы."""
    from students.models import Activity, ActivityCategory

    for i in range(4):
        Activity.objects.create(student=filled, category=ActivityCategory.PROJECT, title=f"Проект {i}")
    filled.refresh_from_db()
    parts = {p.code: p.value for p in compute(filled).parts}
    # IELTS (6 − 4) / (8 − 4) = 50 %, SAT (1200 − 800) / (1400 − 800) = 67 %; 4 активности из 8; Common App — 25 из 100
    assert round(parts["exam"]) == 58 and parts["talent"] == 50 and parts["admission"] == 25

    set_rules(readiness_ielts_floor=5.0, readiness_sat_floor=1000, readiness_talent_target=4)
    set_rules(
        readiness_points_list=10, readiness_points_common_app=60, readiness_points_account=10, readiness_points_ready=20
    )
    parts = {p.code: p.value for p in compute(filled).parts}
    # IELTS (6 − 5) / (8 − 5) = 33 %, SAT (1200 − 1000) / (1400 − 1000) = 50 %
    assert round(parts["exam"]) == 42 and parts["talent"] == 100 and parts["admission"] == 60


@pytest.mark.django_db
def test_rules_are_read_once_for_a_list_of_students(filled, group):
    """Снимок готовности идёт циклом по ученикам: правила школы читаются одним запросом на расчёт."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from core.tasks import snapshot_readiness
    from students.models import AdmissionProfile, BehaviorProfile, ExamProfile, Student

    for index in range(4):
        other = Student.objects.create(
            last_name=f"Ученик{index}",
            first_name="Правил",
            email=f"rules{index}@example.kz",
            group=group,
            graduation_year=2027,
        )
        for model in (ExamProfile, AdmissionProfile, BehaviorProfile):
            model.objects.create(student=other)
    with CaptureQueriesContext(connection) as queries:
        assert snapshot_readiness() == 5
    assert sum("core_schoolrule" in query["sql"] for query in queries.captured_queries) == 1


@pytest.mark.django_db
def test_missing_sport_does_not_cap_the_score(student):
    """У неспортсмена потолок должен оставаться 100, а не 90."""
    student.exam.ielts_current = "8.0"
    student.exam.ielts_target = "8.0"
    student.exam.sat_current = 1400
    student.exam.sat_target = 1400
    student.exam.save()
    student.behavior.attendance_percent = 100
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
def test_empty_student_scores_zero(student):
    result = compute(student)
    assert result.score == 0


@pytest.mark.django_db
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
