"""Сдача и проверка фиксируются только после успешной операции сервиса."""

# ruff: noqa: F811 — общая фикстура задания импортирована по имени

from unittest.mock import Mock

import pytest

from homework.models import Submission
from homework.tests.test_homework_submission import algebra  # noqa: F401

pytestmark = pytest.mark.django_db


def test_submit_and_check_use_two_distinct_events(algebra, pupils, as_student, as_teacher, monkeypatch):
    tracked = Mock()
    monkeypatch.setattr("core.usage.track", tracked)
    path = f"/api/homework/my/{algebra.pk}/submit/"
    assert as_student.post(path, {}, format="json").status_code == 400
    tracked.assert_not_called()
    assert as_student.post(path, {"text": "Решение задачи"}, format="json").status_code == 200
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == "homework.submit"
    submission = Submission.objects.get(assignment=algebra, student=pupils["aliya"])
    check_path = f"/api/homework/submissions/{submission.pk}/check/"
    assert as_teacher.post(check_path, {"grade": 99}, format="json").status_code == 400
    assert tracked.call_count == 1
    assert as_teacher.post(check_path, {"grade": 8}, format="json").status_code == 200
    assert tracked.call_count == 2 and tracked.call_args.args[1] == "homework.check"
