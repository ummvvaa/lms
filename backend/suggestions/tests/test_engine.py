"""Движок предложений: применение, конфликты, откат, чужой домен."""

from __future__ import annotations

import pytest

from core.domains import Source
from core.models import AuditLog
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    TalentProfile,
)
from suggestions.engine import (
    accept_above,
    apply_suggestion,
    create_suggestion,
    refresh_old_values,
    revert_suggestion,
)
from suggestions.models import SuggestionStatus
from suggestions.validators import validate_changes


def make(last: str, first: str, email: str, group) -> Student:
    s = Student.objects.create(
        last_name=last, first_name=first, email=email, grade=11, group=group, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=s)
    return s


@pytest.fixture
def kymbat(make_user):
    return make_user("director_exam", "kymbat@school.kz", full_name="Кымбат")


@pytest.fixture
def students(db, group):
    return [make(f"Фамилия{i}", f"Имя{i}", f"s{i}@school.kz", group) for i in range(8)]


# --- Валидатор: чужой домен отбрасывается в коде ---


def test_validator_drops_foreign_domain_rows():
    """Критерий приёмки: предложение с полем чужого домена отбрасывается."""
    outcome = validate_changes(
        [
            {"model": "students.ExamProfile", "field": "ielts_current", "value": "6.5"},
            {"model": "students.AdmissionProfile", "field": "status", "value": "A"},
        ],
        role="director_exam",
    )
    assert len(outcome.accepted) == 1
    assert outcome.accepted[0]["field"] == "ielts_current"
    assert len(outcome.rejected) == 1
    assert "Асем" in outcome.rejected[0]["reason"]


def test_validator_drops_unknown_model():
    outcome = validate_changes([{"model": "accounts.User", "field": "email", "value": "x@y.kz"}], role="director_exam")
    assert outcome.accepted == []


def test_validator_drops_everything_for_roleless_user():
    outcome = validate_changes(
        [{"model": "students.ExamProfile", "field": "ielts_current", "value": "7"}], role="student"
    )
    assert outcome.accepted == []


@pytest.mark.django_db
def test_foreign_domain_row_never_reaches_the_suggestion(kymbat, students):
    """Строка чужого домена не попадает даже в предложение."""
    suggestion, rejected = create_suggestion(
        author=kymbat,
        role="director_exam",
        domain_code="exam",
        source_type="paste",
        rows=[
            {"student": students[0].pk, "model": "students.ExamProfile", "field": "sat_current", "value": 1300},
            {"student": students[0].pk, "model": "students.AdmissionProfile", "field": "status", "value": "A"},
        ],
    )
    assert suggestion.changes.count() == 1
    assert suggestion.changes.get().field_name == "sat_current"
    assert len(rejected) == 1


# --- Критерий приёмки: восемь учеников, принять шесть, откатить ---


@pytest.fixture
def eight_scores(kymbat, students):
    """Предложение с баллами восьми учеников."""
    rows = [
        {
            "student": s.pk,
            "model": "students.ExamProfile",
            "field": "sat_current",
            "value": 1200 + i * 25,
            "confidence": 0.99 if i < 6 else 0.55,
            "source_quote": f"{s.full_name} — {1200 + i * 25}",
        }
        for i, s in enumerate(students)
    ]
    suggestion, _ = create_suggestion(
        author=kymbat,
        role="director_exam",
        domain_code="exam",
        source_type="paste",
        command="paste_as_is",
        rows=rows,
    )
    return suggestion


@pytest.mark.django_db
def test_accepting_six_of_eight_applies_only_six(kymbat, students, eight_scores):
    ids = list(eight_scores.changes.order_by("-confidence", "id").values_list("pk", flat=True)[:6])
    result = apply_suggestion(eight_scores, actor=kymbat, change_ids=ids)

    assert result["applied"] == 6
    assert result["conflicts"] == []

    applied_students = {c.student_id for c in eight_scores.changes.filter(is_applied=True)}
    assert len(applied_students) == 6

    # у остальных двоих значение не изменилось
    untouched = [s for s in students if s.pk not in applied_students]
    for s in untouched:
        s.exam.refresh_from_db()
        assert s.exam.sat_current is None

    eight_scores.refresh_from_db()
    assert eight_scores.status == SuggestionStatus.PARTIALLY_APPLIED


@pytest.mark.django_db
def test_applied_changes_are_audited_with_suggestion_link(kymbat, students, eight_scores):
    ids = list(eight_scores.changes.values_list("pk", flat=True)[:6])
    apply_suggestion(eight_scores, actor=kymbat, change_ids=ids)

    logs = AuditLog.objects.filter(field_name="sat_current")
    assert logs.count() == 6
    assert all(log.suggestion_id == eight_scores.pk for log in logs)
    assert all(log.source == Source.AI for log in logs)
    assert all(log.actor == kymbat for log in logs)


@pytest.mark.django_db
def test_revert_restores_previous_values(kymbat, students, eight_scores):
    """Критерий приёмки: откат возвращает прежние значения."""
    students[0].exam.sat_current = 1100
    students[0].exam.save()
    # предпросмотр перед применением перечитывает текущие значения,
    # иначе правка после создания предложения справедливо считается конфликтом
    refresh_old_values(eight_scores)

    ids = list(eight_scores.changes.values_list("pk", flat=True))
    apply_suggestion(eight_scores, actor=kymbat, change_ids=ids)

    students[0].exam.refresh_from_db()
    assert students[0].exam.sat_current == 1200

    result = revert_suggestion(eight_scores, actor=kymbat)
    assert result["reverted"] == 8

    students[0].exam.refresh_from_db()
    assert students[0].exam.sat_current == 1100  # прежнее значение вернулось
    for s in students[1:]:
        s.exam.refresh_from_db()
        assert s.exam.sat_current is None

    eight_scores.refresh_from_db()
    assert eight_scores.status == SuggestionStatus.REVERTED


@pytest.mark.django_db
def test_revert_is_audited_too(kymbat, students, eight_scores):
    ids = list(eight_scores.changes.values_list("pk", flat=True))[:2]
    apply_suggestion(eight_scores, actor=kymbat, change_ids=ids)
    before = AuditLog.objects.count()
    revert_suggestion(eight_scores, actor=kymbat)
    # откат не переписывает историю, а дополняет её
    assert AuditLog.objects.count() == before + 2


# --- Конфликты ---


@pytest.mark.django_db
def test_stale_value_is_a_conflict_not_an_overwrite(kymbat, students, eight_scores):
    """Кто-то поправил поле после создания предложения — не затираем."""
    target = students[0]
    target.exam.sat_current = 1450
    target.exam.save()

    change = eight_scores.changes.get(student=target)
    result = apply_suggestion(eight_scores, actor=kymbat, change_ids=[change.pk])

    assert result["applied"] == 0
    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["actual"] == "1450"

    target.exam.refresh_from_db()
    assert target.exam.sat_current == 1450

    change.refresh_from_db()
    assert "поправил раньше вас" in change.conflict


@pytest.mark.django_db
def test_revert_skips_fields_changed_after_apply(kymbat, students, eight_scores):
    change = eight_scores.changes.get(student=students[0])
    apply_suggestion(eight_scores, actor=kymbat, change_ids=[change.pk])

    students[0].exam.sat_current = 1590
    students[0].exam.save()

    result = revert_suggestion(eight_scores, actor=kymbat)
    assert result["reverted"] == 0
    assert len(result["skipped"]) == 1

    students[0].exam.refresh_from_db()
    assert students[0].exam.sat_current == 1590


# --- Приём по порогу уверенности ---


@pytest.mark.django_db
def test_accept_above_threshold_takes_only_confident_rows(kymbat, students, eight_scores):
    result = accept_above(eight_scores, threshold=0.9, actor=kymbat)
    assert result["selected"] == 6
    assert result["applied"] == 6
    assert eight_scores.changes.filter(is_applied=False).count() == 2


@pytest.mark.django_db
def test_changes_are_sorted_doubtful_first(eight_scores):
    """В предпросмотре сомнительное должно быть сверху."""
    confidences = [float(c.confidence) for c in eight_scores.changes.all()]
    assert confidences == sorted(confidences)
