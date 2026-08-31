"""Фаза 37: ученик вносит, директор подтверждает.

Ограничения проверяются на сервере, а не в интерфейсе: чужой ученик,
чужие поля и оценочные ярлыки отбиваются кодом. Подтверждает владелец
домена, и в журнале видно, что значение предложил ученик.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core.domains import Source, can_student_propose, internal_label_fields, iter_field_specs
from core.models import AuditLog
from suggestions.engine import create_student_suggestions
from suggestions.models import Suggestion, SuggestionStatus
from suggestions.student_queue import divergence, queue_payload


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.fixture
def other_student(db, group):
    from students.models import (
        AdmissionProfile,
        BehaviorProfile,
        ExamProfile,
        SportProfile,
        Student,
        TalentProfile,
    )

    s = Student.objects.create(
        last_name="Другой", first_name="Ученик", email="other@example.kz", grade=11, group=group, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=s)
    return s


@pytest.fixture
def kymbat(make_user):
    return make_user("director_exam", "kymbat@school.kz", full_name="Кымбат")


def propose_rows(api, user, rows):
    api.force_authenticate(user)
    return api.post("/api/suggestions/propose/", {"rows": rows}, format="json")


IELTS_ROW = {"model": "students.ExamProfile", "field": "ielts_current", "value": "7.0"}


# --- Реестр: что ученику можно и что нельзя никогда ----------------------


def test_internal_labels_are_never_proposable():
    """Оценочный ярлык не предлагается, даже если флаг появится по ошибке."""
    for label in ("students.BehaviorProfile", "students.AdmissionProfile", "students.TalentProfile"):
        for field in internal_label_fields(label):
            assert not can_student_propose(label, field), f"{label}.{field}"


def test_discipline_fields_are_not_proposable():
    """Посещаемость и дисциплину ученик не предлагает вовсе."""
    for _d, model, spec in iter_field_specs():
        if model.label == "students.BehaviorProfile":
            assert not spec.student_proposable, f"{model.label}.{spec.name}"


def test_scores_and_targets_are_proposable():
    assert can_student_propose("students.ExamProfile", "ielts_current")
    assert can_student_propose("students.AdmissionProfile", "target_country")
    assert can_student_propose("students.AdmissionProfile", "cost_priority")
    assert can_student_propose("students.Activity", "title")
    assert can_student_propose("students.Competition", "result")
    # решение о подтверждении — не ученика
    assert not can_student_propose("students.Activity", "is_confirmed")


# --- Подача: только про себя, только разрешённое -------------------------


@pytest.mark.django_db
def test_student_proposes_own_ielts(api, student_user, student):
    response = propose_rows(api, student_user, [IELTS_ROW])
    assert response.status_code == 201
    assert response.data["accepted"] == 1

    suggestion = Suggestion.objects.get(pk=response.data["suggestions"][0])
    assert suggestion.role == "student"
    assert suggestion.domain_code == "exam"
    assert suggestion.status == SuggestionStatus.PENDING

    # в профиль ничего не легло: решение ещё не принято
    student.exam.refresh_from_db()
    assert student.exam.ielts_current is None


@pytest.mark.django_db
def test_forbidden_fields_are_rejected_by_server(api, student_user):
    response = propose_rows(
        api,
        student_user,
        [
            {"model": "students.AdmissionProfile", "field": "status", "value": "A"},
            {"model": "students.BehaviorProfile", "field": "attendance_percent", "value": "100"},
        ],
    )
    assert response.status_code == 400
    assert len(response.data["rejected"]) == 2
    assert Suggestion.objects.count() == 0


@pytest.mark.django_db
def test_row_about_another_student_is_rejected(api, student_user, other_student):
    response = propose_rows(api, student_user, [{**IELTS_ROW, "student": other_student.pk}])
    assert response.status_code == 400
    assert "про себя" in response.data["rejected"][0]["reason"]


@pytest.mark.django_db
def test_editing_foreign_object_is_rejected(api, student_user, other_student):
    """Правка чужой записи по object_id отбивается той же проверкой."""
    from students.models import Activity

    foreign = Activity.objects.create(student=other_student, title="Чужая олимпиада", category="olympiad")
    response = propose_rows(
        api,
        student_user,
        [{"model": "students.Activity", "field": "title", "value": "Моя!", "object_id": str(foreign.pk)}],
    )
    assert response.status_code == 400
    foreign.refresh_from_db()
    assert foreign.title == "Чужая олимпиада"


@pytest.mark.django_db
def test_staff_cannot_use_propose(api, kymbat):
    response = propose_rows(api, kymbat, [IELTS_ROW])
    assert response.status_code == 403


# --- Очередь у директора --------------------------------------------------


@pytest.mark.django_db
def test_queue_is_visible_to_owner_domain_only(api, student_user, student, kymbat, make_user):
    propose_rows(api, student_user, [IELTS_ROW])

    api.force_authenticate(kymbat)
    exam_queue = api.get("/api/suggestions/from-students/").data["results"]
    assert len(exam_queue) == 1
    assert exam_queue[0]["student_name"] == student.full_name

    api.force_authenticate(make_user("director_sport", "sport@school.kz"))
    assert api.get("/api/suggestions/from-students/").data["results"] == []


@pytest.mark.django_db
def test_queue_sorts_by_divergence(api, student_user, student, kymbat):
    """IELTS 8.5 вместо 6.0 директор видит первым."""
    student.exam.ielts_current = 6.0
    student.exam.sat_current = 1200
    student.exam.save()

    propose_rows(api, student_user, [{"model": "students.ExamProfile", "field": "sat_current", "value": "1220"}])
    propose_rows(api, student_user, [{"model": "students.ExamProfile", "field": "ielts_current", "value": "8.5"}])

    rows = queue_payload("director_exam")
    assert rows[0]["changes"][0]["field_title"] == "Текущий балл IELTS"
    assert rows[0]["divergence"] > rows[1]["divergence"]


def test_divergence_scales_by_registry_bounds(db, student):
    student.exam.ielts_current = 6.0
    student.exam.save()
    [s], _ = create_student_suggestions(
        author=None, student=student, rows=[{"model": "students.ExamProfile", "field": "ielts_current", "value": 8.5}]
    )
    change = s.changes.get()
    assert divergence(change) == pytest.approx((8.5 - 6.0) / 9, abs=0.01)
    # пустое текущее значение ни с чем не расходится
    change.old_value = ""
    assert divergence(change) == 0.0


# --- Решение: подтвердить, поправить, отклонить ---------------------------


@pytest.mark.django_db
def test_confirm_applies_with_student_source(api, student_user, student, kymbat):
    response = propose_rows(api, student_user, [IELTS_ROW])
    suggestion_id = response.data["suggestions"][0]

    api.force_authenticate(kymbat)
    result = api.post(f"/api/suggestions/{suggestion_id}/review/", {"decision": "confirm"}, format="json")
    assert result.status_code == 200
    assert result.data["applied"] == 1

    student.exam.refresh_from_db()
    assert float(student.exam.ielts_current) == 7.0

    # в журнале видно: применил директор, а значение предложил ученик
    entry = AuditLog.objects.get(suggestion_id=suggestion_id)
    assert entry.source == Source.STUDENT_PROPOSAL
    assert entry.actor == kymbat


@pytest.mark.django_db
def test_edit_and_confirm_applies_edited_value(api, student_user, student, kymbat):
    response = propose_rows(api, student_user, [IELTS_ROW])
    suggestion_id = response.data["suggestions"][0]
    change_id = Suggestion.objects.get(pk=suggestion_id).changes.get().pk

    api.force_authenticate(kymbat)
    result = api.post(
        f"/api/suggestions/{suggestion_id}/review/",
        {"decision": "confirm", "values": {str(change_id): "6.5"}},
        format="json",
    )
    assert result.status_code == 200
    student.exam.refresh_from_db()
    assert float(student.exam.ielts_current) == 6.5


@pytest.mark.django_db
def test_decline_requires_reason_and_shows_it_to_student(api, student_user, kymbat):
    response = propose_rows(api, student_user, [IELTS_ROW])
    suggestion_id = response.data["suggestions"][0]

    api.force_authenticate(kymbat)
    assert (
        api.post(f"/api/suggestions/{suggestion_id}/review/", {"decision": "decline"}, format="json").status_code == 400
    )
    result = api.post(
        f"/api/suggestions/{suggestion_id}/review/",
        {"decision": "decline", "reason": "Приложите сертификат — по нему сверим"},
        format="json",
    )
    assert result.status_code == 200

    api.force_authenticate(student_user)
    mine = api.get("/api/suggestions/mine/").data["results"]
    assert mine[0]["status"] == "rejected"
    assert "сертификат" in mine[0]["reject_reason"]


@pytest.mark.django_db
def test_admin_does_not_confirm_student_suggestions(api, student_user, make_user):
    """Решение принимает владелец домена, а не техническая роль."""
    response = propose_rows(api, student_user, [IELTS_ROW])
    suggestion_id = response.data["suggestions"][0]

    api.force_authenticate(make_user("admin", "admin@school.kz"))
    for path, body in (
        (f"/api/suggestions/{suggestion_id}/review/", {"decision": "confirm"}),
        (f"/api/suggestions/{suggestion_id}/apply/", {}),
        (f"/api/suggestions/{suggestion_id}/reject/", {}),
    ):
        assert api.post(path, body, format="json").status_code == 403, path


@pytest.mark.django_db
def test_mass_confirm_takes_only_own_domain(api, student_user, student, kymbat):
    propose_rows(api, student_user, [IELTS_ROW])
    propose_rows(
        api, student_user, [{"model": "students.AdmissionProfile", "field": "target_country", "value": "Канада"}]
    )
    ids = list(Suggestion.objects.values_list("pk", flat=True))

    api.force_authenticate(kymbat)
    result = api.post("/api/suggestions/from-students/confirm/", {"suggestions": ids}, format="json")
    assert result.status_code == 200
    assert result.data["confirmed"] == 1  # чужой домен не тронут

    student.exam.refresh_from_db()
    student.admission.refresh_from_db()
    assert float(student.exam.ielts_current) == 7.0
    assert student.admission.target_country == ""


@pytest.mark.django_db
def test_student_sees_pending_mark_data(api, student_user):
    propose_rows(api, student_user, [IELTS_ROW])
    mine = api.get("/api/suggestions/mine/").data["results"]
    assert mine[0]["status"] == "pending"
    row = mine[0]["changes"][0]
    assert row["field"] == "ielts_current"
    assert row["new_value"] == "7.0"


@pytest.mark.django_db
def test_new_activity_row_goes_to_talent_director(api, student_user, student, make_user):
    """Новая запись (олимпиада) уезжает предложением Арману, а не в базу."""
    from students.models import Activity

    response = propose_rows(
        api,
        student_user,
        [
            {
                "model": "students.Activity",
                "field": "title",
                "value": "Республиканская олимпиада",
                "new_object_key": "a1",
            },
            {"model": "students.Activity", "field": "category", "value": "olympiad", "new_object_key": "a1"},
        ],
    )
    assert response.status_code == 201
    assert Activity.objects.count() == 0

    arman = make_user("director_talent", "arman@school.kz")
    api.force_authenticate(arman)
    queue = api.get("/api/suggestions/from-students/").data["results"]
    assert len(queue) == 1
    result = api.post(f"/api/suggestions/{queue[0]['id']}/review/", {"decision": "confirm"}, format="json")
    assert result.status_code == 200

    activity = Activity.objects.get()
    assert activity.student_id == student.pk
    assert activity.title == "Республиканская олимпиада"
