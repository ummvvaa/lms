"""Healthcheck-эндпойнты для боевого контура.

`/healthz` — процесс жив, отвечает быстро и без похода в базу.
`/readyz`  — готов обслуживать: база и Redis доступны.
"""

from __future__ import annotations

from django.db import connection
from django.http import JsonResponse


def healthz(request):
    """Живость процесса. Балансировщик дёргает часто — ничего тяжёлого."""
    return JsonResponse({"status": "ok"})


def readyz(request):
    """Готовность: проверяем базу и Redis."""
    checks: dict[str, str] = {}
    ok = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        ok = False

    try:
        import redis
        from django.conf import settings

        redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        ok = False

    return JsonResponse({"status": "ok" if ok else "degraded", "checks": checks}, status=200 if ok else 503)
