"""Статус фоновой задачи отдаётся только тому, кто её запустил.

Раньше `/api/tasks/status/<id>/` отвечал любому вошедшему: зная id задачи,
куратор чужой группы или ученик читал результат чужого объяснения подбора
или вопросов по эссе. Теперь задача ищется среди операций вошедшего
(`BackgroundJob.owner`), чужая и несуществующая — 404.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core.models import BackgroundJob


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_task_status_is_visible_to_its_owner_only(make_user):
    owner = make_user("director_admission", "owner-task@example.kz")
    other = make_user("director_exam", "other-task@example.kz")
    pupil = make_user("student", "pupil-task@example.kz")
    BackgroundJob.objects.create(owner=owner, kind="explain_match", title="Объяснение", task_id="task-owner-1")

    mine = _client(owner).get("/api/tasks/status/task-owner-1/")
    assert mine.status_code == 200 and mine.json()["id"] == "task-owner-1"

    for user in (other, pupil):
        response = _client(user).get("/api/tasks/status/task-owner-1/")
        assert response.status_code == 404, user.role
        assert "state" not in response.json()


@pytest.mark.django_db
def test_unknown_task_is_not_found_for_anyone(make_user):
    # куратору маршрут закрывает шлюз (403) — здесь роли, которым он открыт
    for role in ("admin", "director_exam", "student"):
        client = _client(make_user(role, f"{role}-unknown-task@example.kz"))
        assert client.get("/api/tasks/status/no-such-task/").status_code == 404, role
