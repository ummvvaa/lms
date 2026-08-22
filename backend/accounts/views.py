"""Вход, выход и сведения о текущем пользователе.

Схема входа: фронт получает id_token у Microsoft, отдаёт его сюда один раз,
бэкенд проверяет и заводит **свою** сессию в httpOnly cookie. Токен Microsoft
дальше нигде не используется и в localStorage не попадает.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import Http404
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from accounts import magic_link
from accounts.entra import EntraError, verify_id_token
from accounts.serializers import (
    DetailSerializer,
    EntraLoginSerializer,
    IdentitySerializer,
    LinkIdentitySerializer,
    LocalLoginSerializer,
    MagicLinkRedeemSerializer,
    MagicLinkRequestSerializer,
    MeSerializer,
)
from accounts.services import link_email_identity, upsert_from_entra

log = logging.getLogger(__name__)

BACKEND = "django.contrib.auth.backends.ModelBackend"


class LoginThrottle(AnonRateThrottle):
    """Ограничение на попытки входа — одноразовые ссылки не перебирают."""

    rate = "20/min"


@extend_schema(request=EntraLoginSerializer, responses=MeSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
def entra_login(request):
    """Вход через Microsoft Entra ID."""
    serializer = EntraLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        claims = verify_id_token(serializer.validated_data["id_token"])
    except EntraError as exc:
        log.warning("Вход через Entra отклонён: %s", exc)
        return Response({"detail": "Токен не принят"}, status=status.HTTP_401_UNAUTHORIZED)

    user, _identity = upsert_from_entra(claims)
    if not user.is_active:
        return Response({"detail": "Учётная запись отключена"}, status=status.HTTP_403_FORBIDDEN)

    login(request, user, backend=BACKEND)
    get_token(request)
    return Response(MeSerializer(user).data)


@extend_schema(request=LocalLoginSerializer, responses=MeSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def local_login(request):
    """Вход по email и паролю для локальной ручной проверки.

    Маршрут намеренно не существует в production: боевой вход остаётся через
    Microsoft Entra и одноразовые ссылки.
    """
    if not settings.DEBUG:
        raise Http404

    serializer = LocalLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = authenticate(
        request,
        username=serializer.validated_data["email"],
        password=serializer.validated_data["password"],
    )
    if user is None:
        return Response({"detail": "Неверная почта или пароль"}, status=status.HTTP_401_UNAUTHORIZED)

    login(request, user, backend=BACKEND)
    get_token(request)
    return Response(MeSerializer(user).data)


@extend_schema(request=MagicLinkRequestSerializer, responses=DetailSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def magic_link_request(request):
    """Запрос одноразовой ссылки на личную почту (вторая дверь)."""
    serializer = MagicLinkRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    token = magic_link.issue(serializer.validated_data["email"])
    # Ответ одинаков и когда почта известна, и когда нет — форма не должна
    # превращаться в проверку «есть ли такой человек».
    payload = {"detail": "Если такая почта известна системе, ссылка отправлена"}
    if token and settings.MAGIC_LINK_RETURN_TOKEN:
        # только для разработки: письма локально никуда не уходят
        payload["token"] = token
    return Response(payload)


@extend_schema(request=MagicLinkRedeemSerializer, responses=MeSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def magic_link_redeem(request):
    """Погашение одноразовой ссылки — выдаём сессию."""
    serializer = MagicLinkRedeemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = magic_link.redeem(serializer.validated_data["token"])
    if user is None:
        return Response({"detail": "Ссылка недействительна или уже использована"}, status=status.HTTP_401_UNAUTHORIZED)
    login(request, user, backend=BACKEND)
    get_token(request)
    return Response(MeSerializer(user).data)


@extend_schema(responses=MeSerializer)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """Текущий пользователь. Фронт зовёт при загрузке — сессия переживает F5."""
    get_token(request)
    return Response(MeSerializer(request.user).data)


@extend_schema(request=None, responses=DetailSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """Выход: сессия гасится на сервере."""
    logout(request)
    return Response({"detail": "Вы вышли"})


@extend_schema(request=LinkIdentitySerializer, responses=IdentitySerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def link_identity(request):
    """Привязать личную почту второй идентичностью — из кабинета."""
    serializer = LinkIdentitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        identity = link_email_identity(request.user, serializer.validated_data["email"])
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(IdentitySerializer(identity).data, status=status.HTTP_201_CREATED)
