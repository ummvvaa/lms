"""Текущий пользователь для сигнального аудита.

`core.audit.apply_changes` знает актора: его передаёт вызывающий код.
А правка из админки или из shell идёт мимо и до сигналов доходит без автора —
в журнале оставался «—», и было не понять, кто менял поле.

Здесь актор кладётся в контекст запроса и оттуда читается сигналом.
Контекстная переменная, а не глобальная: под gunicorn с потоками
и под асинхронным стеком глобальная переменная течёт между запросами.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_current_actor: ContextVar[object | None] = ContextVar("current_actor", default=None)


def get_actor():
    """Кто сейчас правит. None — правка не из запроса (shell, Celery)."""
    return _current_actor.get()


@contextmanager
def acting_as(user):
    """Явно назначить актора на время блока — для команд и фоновых задач."""
    token = _current_actor.set(user)
    try:
        yield
    finally:
        _current_actor.reset(token)


class CurrentActorMiddleware:
    """Кладёт пользователя запроса в контекст на время его обработки."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        token = _current_actor.set(user if user is not None and user.is_authenticated else None)
        try:
            return self.get_response(request)
        finally:
            _current_actor.reset(token)
