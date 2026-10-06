"""Ответы API не кэшируются браузером.

У ответов `/api/` не было `Cache-Control` вовсе: что с таким ответом делать,
решал браузер по своим эвристикам. Журнал после оценки должен приходить
свежим, а не из кэша Safari (D75, 06.10.2026). Выгрузки файлов ставят тот же
заголовок сами; страницу и куски сборки фронта отдаёт Caddy со своими
правилами, их это не касается.
"""

from __future__ import annotations

API_PREFIX = "/api/"
NO_STORE = "private, no-store"


class NoStoreApiMiddleware:
    """`Cache-Control: private, no-store` каждому ответу API, у которого его нет."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(API_PREFIX) and not response.has_header("Cache-Control"):
            response["Cache-Control"] = NO_STORE
        return response
