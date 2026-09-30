"""Предложение, собранное помощником, в журнале — с источником «ИИ», а не «вручную».

Разбор вуза, разбор активности и задачи помощника раньше писались как
«заведено руками», и применение попадало в журнал с `manual` — будто
значение внёс человек (инвариант №9). Теперь источник у них «Собрал
помощник», а в журнале — `ai`.
"""

from __future__ import annotations

import pytest

from accounts.models import Role
from core.domains import Source
from core.models import AuditLog
from students.models import Student, StudyGroup
from suggestions import operations
from suggestions.engine import apply_suggestion
from suggestions.models import Suggestion, SuggestionSource

pytestmark = pytest.mark.django_db


def test_assistant_tasks_are_applied_with_the_ai_source(make_user):
    group = StudyGroup.objects.create(code="SRC11", parallel=11)
    student = Student.objects.create(last_name="Источникова", first_name="Дана", group=group, graduation_year=2027)
    asem = make_user(Role.DIRECTOR_ADMISSION, "source.asem@example.kz")

    outcome = operations.bulk_tasks(
        student_ids=[student.pk], wish="Сдать мотивационное письмо", actor=asem, role=asem.role
    )
    suggestion = Suggestion.objects.get(pk=outcome.suggestion)
    assert suggestion.source_type == SuggestionSource.ASSISTANT

    result = apply_suggestion(suggestion, actor=asem, change_ids=list(suggestion.changes.values_list("pk", flat=True)))
    assert result["applied"] == 2, result
    entries = AuditLog.objects.filter(suggestion=suggestion)
    assert entries.exists()
    assert set(entries.values_list("source", flat=True)) == {Source.AI}


def test_the_parsers_of_the_assistant_are_not_marked_manual():
    """Разбор вуза и активности создают предложения с источником помощника."""
    from pathlib import Path

    for name in ("operations.py", "extraction.py"):
        source = (Path(__file__).resolve().parents[1] / name).read_text(encoding="utf-8")
        assert 'source_type="manual"' not in source, name
