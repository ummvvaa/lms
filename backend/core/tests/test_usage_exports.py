"""Предпросмотр не считается скачиванием, общая сборка книги не дублирует событие."""

from unittest.mock import Mock

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_users_workbook_download_is_one_event_and_preview_is_zero(make_user, monkeypatch):
    tracked = Mock()
    monkeypatch.setattr("core.usage.track", tracked)
    api = APIClient()
    api.force_authenticate(make_user("admin"))
    assert api.get("/api/users/export/", {"preview": "1"}).status_code == 200
    tracked.assert_not_called()
    response = api.get("/api/users/export/")
    assert response.status_code == 200 and "spreadsheetml" in response["Content-Type"]
    tracked.assert_called_once()
    request, key = tracked.call_args.args
    assert request.resolver_match.url_name == "users-export" and key == "export.download"


@pytest.mark.django_db
def test_portfolio_cv_download_is_counted_only_for_its_student(make_user, student, monkeypatch):
    from core.usage_registry import EXPORT_SCREENS

    tracked = Mock()
    monkeypatch.setattr("core.usage.track", tracked)
    api = APIClient()
    api.force_authenticate(make_user("admin"))
    assert api.get("/api/portfolio/cv/").status_code == 403
    tracked.assert_not_called()

    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    api.force_authenticate(user)
    response = api.get("/api/portfolio/cv/")
    assert response.status_code == 200 and "attachment" in response["Content-Disposition"]
    tracked.assert_called_once()
    request, key = tracked.call_args.args
    assert key == "export.download"
    assert EXPORT_SCREENS[request.resolver_match.url_name] == "/my-data"
