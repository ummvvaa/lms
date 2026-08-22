"""Фаза 8, дефект B3: мусор в ячейке отклоняется, а не роняет запрос."""

from __future__ import annotations

import pytest

from accounts.models import Role, User
from students.batch import apply_batch
from students.models import ExamProfile, Student


@pytest.fixture
def student(db):
    student = Student.objects.create(
        last_name="Сериков", first_name="Дамир", email="batch@example.kz", grade=11, graduation_year=2027
    )
    ExamProfile.objects.create(student=student)
    return student


def change(student, field, value, **extra):
    return {"student": student.pk, "model": "students.ExamProfile", "field": field, "value": value, **extra}


@pytest.mark.django_db
def test_non_numeric_value_is_rejected_with_reason(student):
    result = apply_batch(changes=[change(student, "ielts_current", "не число")], role=Role.DIRECTOR_EXAM)

    assert result.applied == 0
    assert len(result.rejected) == 1
    assert "не подходит" in result.rejected[0]["reason"]
    student.exam.refresh_from_db()
    assert student.exam.ielts_current is None


@pytest.mark.django_db
def test_bad_row_does_not_block_good_rows(student):
    """Одна испорченная ячейка не должна отменять правки по остальным полям."""
    result = apply_batch(
        changes=[
            change(student, "ielts_current", "abc"),
            change(student, "teacher", "Кымбат"),
        ],
        role=Role.DIRECTOR_EXAM,
    )

    assert result.applied == 1
    assert len(result.rejected) == 1
    student.exam.refresh_from_db()
    assert student.exam.teacher == "Кымбат"


@pytest.mark.django_db
def test_api_answers_200_not_500(client, student):
    """Раньше здесь была страница 500 с трассировкой Django."""
    user = User.objects.create_user(email="k@example.kz", password="Пароль!2026x", role=Role.DIRECTOR_EXAM)
    client.force_login(user)

    response = client.post(
        "/api/batch/save/",
        data={"changes": [change(student, "ielts_current", "не число")]},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["applied"] == 0
    assert response.json()["rejected"]
