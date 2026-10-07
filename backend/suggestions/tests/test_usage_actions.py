"""Помощник учитывает принятый запуск, а не опросы очереди и её завершение."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def tracked(monkeypatch):
    tracker = Mock()
    monkeypatch.setattr("core.usage.track", tracker)
    return tracker


@pytest.mark.parametrize(
    "endpoint,task,key",
    [("paste", "parse_paste", "assistant.text.parse"), ("upload", "parse_file", "assistant.file.parse")],
)
def test_accepted_async_operation_emits_once_and_polling_does_not(make_user, monkeypatch, tracked, endpoint, task, key):
    from suggestions import views

    api = APIClient()
    api.force_authenticate(make_user("admin"))
    queued = SimpleNamespace(id="usage-task")
    monkeypatch.setattr(getattr(views.background, task), "delay", lambda **kwargs: queued)
    payload = {"domain": "exam"}
    if endpoint == "paste":
        payload["text"] = "Текст для разбора"
    else:
        payload["file"] = SimpleUploadedFile("data.csv", b"one,two\n1,2")
    response = api.post(f"/api/commands/{endpoint}/", payload, format="multipart")
    assert response.status_code == 202, response.data
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == key
    monkeypatch.setattr(
        views,
        "AsyncResult",
        lambda task_id: SimpleNamespace(state="SUCCESS", successful=lambda: True, result={"done": True}),
    )
    assert api.get(f"/api/tasks/status/{queued.id}/").status_code == 200
    assert tracked.call_count == 1


def test_denied_and_invalid_assistant_requests_emit_nothing(make_user, tracked):
    api = APIClient()
    api.force_authenticate(make_user("student"))
    assert api.post("/api/commands/paste/", {"text": "Текст"}, format="json").status_code == 403
    api.force_authenticate(make_user("admin"))
    assert api.post("/api/commands/paste/", {"text": "Текст"}, format="json").status_code == 400
    tracked.assert_not_called()


def test_synchronous_answer_has_one_event_after_the_saved_reply(make_user, tracked, monkeypatch):
    from suggestions import assistant
    from suggestions.models import AssistantMessage

    monkeypatch.setattr(
        assistant,
        "free_text",
        lambda **kwargs: {"text": "Готово", "lines": [], "suggestion": None, "offline": True, "affected": 0},
    )
    api = APIClient()
    api.force_authenticate(make_user("admin"))
    response = api.post("/api/assistant/ask/", {"text": "Что сделано?"}, format="json")
    assert response.status_code == 200, response.data
    assert AssistantMessage.objects.filter(author="assistant").exists()
    tracked.assert_called_once()
    assert tracked.call_args.args[1] == "assistant.ask"
