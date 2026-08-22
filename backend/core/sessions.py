"""Сессии, переживающие вторую вкладку.

`SESSION_SAVE_EVERY_REQUEST` продлевает сессию при каждом обращении — так
человек не вылетает посреди рабочего дня. Но если параллельный запрос
успел сессию убить (вышел во второй вкладке, сменил пароль, истёк срок),
Django отвечает пятисоткой: `SessionInterrupted`.

Для API это неправильный ответ. Сессии нет — значит 401, и фронт спокойно
уводит на экран входа вместо страницы с трассировкой.
"""

from __future__ import annotations

from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import JsonResponse


class ResilientSessionMiddleware(SessionMiddleware):
    """То же, что стандартная сессия, но без 500 на исчезнувшей сессии."""

    def process_response(self, request, response):
        try:
            return super().process_response(request, response)
        except SessionInterrupted:
            if request.path.startswith("/api/"):
                return JsonResponse({"detail": "Сессия завершена, войдите заново"}, status=401)
            raise
