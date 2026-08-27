"""Сессии, переживающие вторую вкладку и смену пароля.

Продление при активности раньше делал `SESSION_SAVE_EVERY_REQUEST`: каждый
ответ пересохранял сессию и переписывал cookie. Из-за этого после смены
пароля запрос, ушедший параллельно, ответив позже, затирал и cookie,
и новый отпечаток пароля в данных сессии — человек оказывался на экране
входа (фаза 36, D1). Теперь сессия продлевается здесь: обновлением срока
в базе, без записи данных, и не чаще раза в `SESSION_TOUCH_MINUTES`.
Cookie при этом переставляется с тем же ключом — ключ сессии после входа
не меняется, и «перетереть» его нечем.

Если параллельный запрос успел сессию убить (вышел во второй вкладке,
истёк срок), Django отвечает пятисоткой `SessionInterrupted`. Для API это
неправильный ответ: сессии нет — значит 401, и фронт уводит на вход.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date


def _touch_key(session_key: str) -> str:
    return f"session-touch:{session_key}"


class ResilientSessionMiddleware(SessionMiddleware):
    """То же, что стандартная сессия, но продление без записи данных и без 500."""

    def process_response(self, request, response):
        try:
            response = super().process_response(request, response)
        except SessionInterrupted:
            if request.path.startswith("/api/"):
                return JsonResponse({"detail": "Сессия завершена, войдите заново"}, status=401)
            raise
        self._touch(request, response)
        return response

    def _touch(self, request, response) -> None:
        """Продлить срок живой сессии, если с прошлого продления прошло достаточно.

        Данные сессии не пишутся: обновляется только `expire_date` строки —
        чтобы ответ, ушедший параллельно со сменой пароля, не вернул старый
        отпечаток. Cookie переставляется с тем же ключом и новым сроком.
        """
        session = getattr(request, "session", None)
        if (
            session is None
            or session.is_empty()
            or session.modified
            or getattr(session, "_session_cache", None) is None
        ):
            # изменённую сессию Django уже сохранил и cookie выставил сам;
            # пустую или не читавшуюся продлевать нечего
            return
        key = session.session_key
        if not key:
            return
        interval = int(getattr(settings, "SESSION_TOUCH_MINUTES", 15)) * 60
        # `add` срабатывает один раз за интервал: остальные запросы в него
        # не попадают и в базу не ходят
        if not cache.add(_touch_key(key), 1, timeout=interval):
            return
        age = session.get_expiry_age()
        expire_date = timezone.now() + timezone.timedelta(seconds=age)
        model = getattr(session, "model", None)
        if model is None:
            return
        updated = model.objects.filter(session_key=key).update(expire_date=expire_date)
        if not updated:
            # сессии уже нет (вышли в другой вкладке): cookie не трогаем,
            # следующий запрос получит 401 и уведёт на вход
            cache.delete(_touch_key(key))
            return
        patch_vary_headers(response, ("Cookie",))
        response.set_cookie(
            settings.SESSION_COOKIE_NAME,
            key,
            max_age=age,
            expires=http_date(expire_date.timestamp()),
            domain=settings.SESSION_COOKIE_DOMAIN,
            path=settings.SESSION_COOKIE_PATH,
            secure=settings.SESSION_COOKIE_SECURE or None,
            httponly=settings.SESSION_COOKIE_HTTPONLY or None,
            samesite=settings.SESSION_COOKIE_SAMESITE,
        )
