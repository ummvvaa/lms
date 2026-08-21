"""Батч-сохранение: транзакция, аудит, отсечение чужого домена."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core.models import AuditLog
from students.models import Student


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def kymbat(make_user):
    return make_user("director_exam", "kymbat@school.kz", full_name="Кымбат")


@pytest.fixture
def twenty(db, group):
    """Двадцать учеников с пустыми профилями — как после импорта списка."""
    from students.models import (
        AdmissionProfile,
        BehaviorProfile,
        ExamProfile,
        SportProfile,
        TalentProfile,
    )

    students = []
    for i in range(20):
        s = Student.objects.create(
            last_name=f"Фамилия{i:02d}",
            first_name=f"Имя{i:02d}",
            email=f"s{i:02d}@school.kz",
            grade=11,
            group=group,
            graduation_year=2027,
        )
        for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
            model.objects.create(student=s)
        students.append(s)
    return students


@pytest.mark.django_db
def test_twenty_students_saved_in_one_request(api, kymbat, twenty):
    """Критерий приёмки: 20 учеников, один запрос, всё в аудите."""
    changes = [
        {"student": s.pk, "model": "students.ExamProfile", "field": "ielts_current", "value": "6.5"} for s in twenty
    ] + [{"student": s.pk, "model": "students.ExamProfile", "field": "sat_current", "value": 1300} for s in twenty]

    api.force_authenticate(kymbat)
    response = api.post("/api/batch/save/", {"changes": changes}, format="json")

    assert response.status_code == 200, response.data
    assert response.data["applied"] == 40
    assert response.data["rejected"] == []
    assert response.data["audit_entries"] == 40

    for s in twenty:
        s.exam.refresh_from_db()
        assert str(s.exam.ielts_current) == "6.5"
        assert s.exam.sat_current == 1300

    logs = AuditLog.objects.filter(field_name="ielts_current")
    assert logs.count() == 20
    assert all(log.actor == kymbat and log.domain_code == "exam" for log in logs)


@pytest.mark.django_db
def test_foreign_domain_rows_are_rejected_not_applied(api, kymbat, twenty):
    """Строка чужого домена отбрасывается, своя — применяется."""
    target = twenty[0]
    changes = [
        {"student": target.pk, "model": "students.ExamProfile", "field": "ielts_current", "value": "7.0"},
        {"student": target.pk, "model": "students.AdmissionProfile", "field": "status", "value": "A"},
    ]

    api.force_authenticate(kymbat)
    response = api.post("/api/batch/save/", {"changes": changes}, format="json")

    assert response.status_code == 200
    assert response.data["applied"] == 1
    assert len(response.data["rejected"]) == 1
    assert response.data["rejected"][0]["field"] == "status"

    target.exam.refresh_from_db()
    target.admission.refresh_from_db()
    assert str(target.exam.ielts_current) == "7.0"
    assert target.admission.status == ""


@pytest.mark.django_db
def test_stale_value_is_reported_as_conflict(api, kymbat, twenty):
    """Кто-то успел поправить поле раньше — строка не затирает чужую правку."""
    target = twenty[0]
    target.exam.ielts_current = "7.5"
    target.exam.save()

    api.force_authenticate(kymbat)
    response = api.post(
        "/api/batch/save/",
        {
            "changes": [
                {
                    "student": target.pk,
                    "model": "students.ExamProfile",
                    "field": "ielts_current",
                    "value": "6.0",
                    "expected": "5.5",
                }
            ]
        },
        format="json",
    )

    assert response.data["skipped"] == 1
    assert response.data["conflicts"][0]["actual"] == "7.5"
    target.exam.refresh_from_db()
    assert str(target.exam.ielts_current) == "7.5"


@pytest.mark.django_db
def test_student_cannot_batch_save(api, make_user, student):
    student_user = make_user("student", student.email)
    student.user = student_user
    student.save(update_fields=["user"])
    api.force_authenticate(student_user)
    response = api.post(
        "/api/batch/save/",
        {"changes": [{"student": student.pk, "model": "students.ExamProfile", "field": "ielts_current", "value": 9}]},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_unknown_model_is_rejected(api, kymbat, twenty):
    api.force_authenticate(kymbat)
    response = api.post(
        "/api/batch/save/",
        {"changes": [{"student": twenty[0].pk, "model": "accounts.User", "field": "email", "value": "x@y.kz"}]},
        format="json",
    )
    assert response.data["applied"] == 0
    assert len(response.data["rejected"]) == 1
