"""Словарь аналитики покрывает маршруты, ключи клиента и серверные вызовы."""

from __future__ import annotations

import re
from pathlib import Path

from core.domains import ROLE_TITLES, USAGE_READERS, USAGE_WRITERS
from core.usage_registry import ACTIONS, ACTIONS_BY_KEY, CLIENT_ACTIONS, EXPORT_SCREENS, SCREENS, SCREENS_BY_KEY

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]


def test_registry_keys_are_unique_and_every_server_action_has_a_known_screen():
    assert len(ACTIONS) == len(ACTIONS_BY_KEY)
    assert len(SCREENS) == len(SCREENS_BY_KEY)
    assert {action.key for action in ACTIONS if action.source == "client"} == set(CLIENT_ACTIONS)
    for action in ACTIONS:
        assert action.title
        if action.source == "server" and action.key != "export.download":
            assert action.screen in SCREENS_BY_KEY
    for screen in SCREENS:
        assert screen.title and set(screen.roles) <= set(ROLE_TITLES)
        assert not any(char in screen.key for char in ("?", "#"))
    assert set(EXPORT_SCREENS.values()) <= set(SCREENS_BY_KEY)
    assert SCREENS_BY_KEY["/usage"].roles == USAGE_READERS
    assert set(USAGE_WRITERS) == set(ROLE_TITLES)


def test_every_real_frontend_route_has_a_canonical_screen():
    body = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    routes = set(re.findall(r'<Route\s+path="([^"]+)"', body)) - {"*"}
    assert routes <= set(SCREENS_BY_KEY), routes - set(SCREENS_BY_KEY)


def test_frontend_hook_literals_are_client_keys_and_server_calls_are_server_keys():
    frontend_keys = set()
    for path in (ROOT / "frontend/src").rglob("*.tsx"):
        frontend_keys.update(re.findall(r"\buseTrack\(\s*['\"]([^'\"]+)['\"]", path.read_text(encoding="utf-8")))
    assert frontend_keys, "Клиентские действия должны проходить через useTrack"
    assert frontend_keys <= set(CLIENT_ACTIONS), frontend_keys - set(CLIENT_ACTIONS)
    server_keys = set()
    for path in (ROOT / "backend").rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts or ".venv" in path.parts:
            continue
        server_keys.update(
            re.findall(r"\busage\.track\(\s*\w+,\s*['\"]([^'\"]+)['\"]", path.read_text(encoding="utf-8"))
        )
    allowed_server = {action.key for action in ACTIONS if action.source == "server"}
    assert server_keys == allowed_server, server_keys ^ allowed_server
