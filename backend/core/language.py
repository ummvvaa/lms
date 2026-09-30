"""Язык ответа на запрос: язык профиля вошедшего, без входа — язык браузера.

Ошибки API, подписи вариантов, фразы кабинетов и выгрузки собираются на этом
языке. Вошедшему — `User.language` (его выбор в профиле), иначе
`Accept-Language`: фронт присылает в нём язык экрана входа. Стоит сразу после
`AuthenticationMiddleware`: и ворота прав ниже по списку отвечают уже на языке
человека.
"""

from __future__ import annotations

from django.utils import translation

from core.i18n import INTERFACE_LANGUAGES, language_of


def request_language(request) -> str:
    """Язык ответа на этот запрос."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return language_of(user)
    lang = translation.get_language_from_request(request)
    lang = (lang or "ru").split("-")[0]
    return lang if lang in INTERFACE_LANGUAGES else "ru"


class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = request_language(request)
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
        try:
            response = self.get_response(request)
        finally:
            translation.deactivate()
        response.headers.setdefault("Content-Language", lang)
        return response
