"""Схема учеников: базовые инварианты моделей."""

from __future__ import annotations

import pytest
from django.db import connection

from students.models import Student


@pytest.mark.django_db
def test_database_starts_empty():
    """Инвариант №8: никаких фикстур с выдуманными учениками."""
    assert Student.objects.count() == 0


@pytest.mark.django_db
def test_no_jsonb_columns_in_domain_tables():
    """Инвариант №6: доменные данные лежат в типизированных колонках."""
    labels = (
        "students_behaviorprofile",
        "students_admissionprofile",
        "students_examprofile",
        "students_talentprofile",
        "students_sportprofile",
        "students_activity",
        "students_competition",
        "students_examattempt",
        "universities_studentuniversity",
    )
    with connection.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ANY(%s) AND data_type IN ('json', 'jsonb')",
            [list(labels)],
        )
        assert cur.fetchall() == []


@pytest.mark.django_db
def test_deadline_belongs_to_round(student):
    """Инвариант №4: у StudentUniversity нет своего поля дедлайна."""
    from universities.models import StudentUniversity

    field_names = {f.name for f in StudentUniversity._meta.get_fields()}
    assert "deadline" not in field_names
