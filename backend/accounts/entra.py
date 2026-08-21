"""Проверка токена Microsoft Entra ID.

Фронт получает id_token через MSAL.js и один раз отдаёт его сюда.
Бэкенд проверяет подпись по JWKS, сверяет issuer, audience и срок,
после чего выдаёт **свою** сессию. Токен Microsoft дальше не используется
и на фронте не хранится.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import jwt
import requests
from django.conf import settings
from jwt import PyJWKClient

#: Кэш JWKS-клиентов по URL — ключи Microsoft меняются редко.
_jwk_clients: dict[str, PyJWKClient] = {}
_jwk_lock = threading.Lock()


class EntraError(Exception):
    """Токен не прошёл проверку."""


@dataclass(frozen=True)
class EntraClaims:
    """Что мы забираем из проверенного токена."""

    subject: str
    email: str
    full_name: str
    groups: tuple[str, ...]


def _jwks_client(url: str) -> PyJWKClient:
    with _jwk_lock:
        client = _jwk_clients.get(url)
        if client is None:
            client = PyJWKClient(url, cache_keys=True, lifespan=3600)
            _jwk_clients[url] = client
        return client


def verify_id_token(token: str) -> EntraClaims:
    """Проверить id_token и вернуть заявленные данные.

    Проверяются подпись по JWKS, issuer, audience и срок действия.
    Любая осечка — `EntraError`, наружу деталей не отдаём.
    """
    cfg = settings.ENTRA
    if not cfg.get("CLIENT_ID") or not cfg.get("TENANT_ID"):
        raise EntraError("Вход через Microsoft не настроен")

    try:
        signing_key = _jwks_client(cfg["JWKS_URL"]).get_signing_key_from_jwt(token)
        payload: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=cfg["CLIENT_ID"],
            issuer=cfg["ISSUER"],
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
            leeway=cfg.get("LEEWAY_SECONDS", 60),
        )
    except Exception as exc:
        raise EntraError(f"Токен не прошёл проверку: {exc}") from exc

    email = (payload.get("preferred_username") or payload.get("email") or payload.get("upn") or "").strip().lower()
    if not email:
        raise EntraError("В токене нет email")

    groups = payload.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]

    return EntraClaims(
        subject=str(payload["sub"]),
        email=email,
        full_name=(payload.get("name") or "").strip(),
        groups=tuple(str(g) for g in groups),
    )


def fetch_openid_config(tenant_id: str) -> dict[str, Any]:
    """Служебное: подтянуть метаданные тенанта (issuer, jwks_uri)."""
    url = f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def now() -> int:
    return int(time.time())
