"""Вход, выход, пароли, сведения о текущем пользователе и управление людьми.

Схема входа: почта и пароль проверяются здесь, сессия живёт в httpOnly
cookie. Внешнего провайдера сейчас нет, но модель `Identity` осталась —
вернуть его позже можно будет, не переделывая аутентификацию.

Регистрации самому себе нет: учётную запись заводит администратор либо
она появляется из массового приглашения.
"""

from __future__ import annotations

import logging

from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from accounts import magic_link, passwords
from accounts.models import LinkPurpose, Role, User
from accounts.permissions import IsAdmin
from accounts.serializers import (
    DetailSerializer,
    IdentitySerializer,
    InviteSerializer,
    LinkIdentitySerializer,
    LoginSerializer,
    MagicLinkRedeemSerializer,
    MagicLinkRequestSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    UserSerializer,
    UserWriteSerializer,
)
from accounts.services import create_user, deactivate, link_email_identity, touch_identity
from core.models import ArchiveEntry

log = logging.getLogger(__name__)

BACKEND = "django.contrib.auth.backends.ModelBackend"


class LoginThrottle(AnonRateThrottle):
    """Грубый потолок поверх адресной блокировки — против шумного перебора.

    Подбор пароля останавливает `accounts.passwords`, здесь только защита
    от шквала запросов. Потолок не слишком низкий: за одним школьным
    адресом сидит вся школа, и утренний вход не должен упираться в него.
    """

    scope = "login"


class LinkThrottle(AnonRateThrottle):
    """Выдача одноразовых ссылок — отдельный, более строгий предел.

    Каждый такой запрос отправляет письмо. Шестьдесят в минуту с одного
    адреса — это уже рассылка чужими руками, а не забывчивый директор.
    """

    scope = "password_link"


def _start_session(request, user):
    """Завести свою сессию и отдать состояние пользователя."""
    login(request, user, backend=BACKEND)
    get_token(request)
    touch_identity(user, user.email)
    return Response(MeSerializer(user).data)


@extend_schema(request=LoginSerializer, responses=MeSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login_view(request):
    """Вход по почте и паролю."""
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"].strip().lower()
    ip = passwords.client_ip(request)
    agent = request.META.get("HTTP_USER_AGENT", "")

    lock = passwords.check_lock(email=email, ip=ip)
    if lock is not None:
        passwords.record_attempt(email=email, ip=ip, successful=False, reason="locked", user_agent=agent)
        return Response({"detail": lock.message}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    user = authenticate(request, username=email, password=serializer.validated_data["password"])
    if user is None:
        passwords.record_attempt(email=email, ip=ip, successful=False, reason="bad_credentials", user_agent=agent)
        # одинаковый ответ на неизвестную почту и неверный пароль:
        # форма входа не должна работать как проверка «есть ли такой человек»
        return Response({"detail": "Неверная почта или пароль"}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        passwords.record_attempt(email=email, ip=ip, successful=False, reason="inactive", user_agent=agent)
        return Response({"detail": "Учётная запись отключена"}, status=status.HTTP_403_FORBIDDEN)

    passwords.record_attempt(email=email, ip=ip, successful=True, user_agent=agent)
    return _start_session(request, user)


@extend_schema(request=PasswordChangeSerializer, responses=MeSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def password_change(request):
    """Смена пароля. Обязательна при первом входе."""
    serializer = PasswordChangeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = request.user

    if not user.check_password(serializer.validated_data["current_password"]):
        return Response({"detail": "Текущий пароль неверен"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        passwords.set_password(user, serializer.validated_data["new_password"])
    except passwords.PasswordRejected as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

    # смена пароля вращает ключ сессии — иначе текущая сессия выпадет
    from django.contrib.auth import update_session_auth_hash

    update_session_auth_hash(request, user)
    return Response(MeSerializer(user).data)


@extend_schema(request=MagicLinkRequestSerializer, responses=DetailSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LinkThrottle])
def password_reset_request(request):
    """Запрос ссылки на сброс пароля."""
    serializer = MagicLinkRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    magic_link.issue(serializer.validated_data["email"], purpose=LinkPurpose.RESET)
    # ответ одинаков для известной и неизвестной почты
    return Response({"detail": "Если такая почта известна системе, ссылка отправлена"})


@extend_schema(request=PasswordResetConfirmSerializer, responses=MeSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def password_reset_confirm(request):
    """Установка пароля по одноразовой ссылке: сброс или приглашение."""
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = magic_link.redeem(serializer.validated_data["token"], purposes=(LinkPurpose.RESET, LinkPurpose.INVITE))
    if user is None:
        return Response({"detail": "Ссылка недействительна или уже использована"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        passwords.set_password(user, serializer.validated_data["new_password"])
    except passwords.PasswordRejected as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

    return _start_session(request, user)


@extend_schema(request=MagicLinkRequestSerializer, responses=DetailSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LinkThrottle])
def magic_link_request(request):
    """Ссылка на вход для выпускника, у которого пароля нет."""
    serializer = MagicLinkRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    magic_link.issue(serializer.validated_data["email"], purpose=LinkPurpose.LOGIN)
    return Response({"detail": "Если такая почта известна системе, ссылка отправлена"})


@extend_schema(request=MagicLinkRedeemSerializer, responses=MeSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def magic_link_redeem(request):
    """Погашение ссылки на вход."""
    serializer = MagicLinkRedeemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = magic_link.redeem(serializer.validated_data["token"], purposes=(LinkPurpose.LOGIN,))
    if user is None:
        return Response({"detail": "Ссылка недействительна или уже использована"}, status=status.HTTP_400_BAD_REQUEST)
    return _start_session(request, user)


@extend_schema(request=None, responses=DetailSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """Выход: сессия убивается на сервере."""
    logout(request)
    return Response({"detail": "Вы вышли"})


@extend_schema(responses=MeSerializer)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """Кто я, какая роль, какой домен веду."""
    get_token(request)
    return Response(MeSerializer(request.user).data)


@extend_schema(request=LinkIdentitySerializer, responses=IdentitySerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def link_identity(request):
    """Привязать личную почту второй идентичностью."""
    serializer = LinkIdentitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        identity = link_email_identity(request.user, serializer.validated_data["email"])
    except ValueError as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(IdentitySerializer(identity).data, status=status.HTTP_201_CREATED)


# --- Управление пользователями: только роль `admin` ----------------------


@extend_schema(request=UserWriteSerializer, responses=UserSerializer(many=True))
@api_view(["GET", "POST"])
@permission_classes([IsAdmin])
def users(request):
    """Список с поиском и заведение новой учётной записи."""
    if request.method == "POST":
        serializer = UserWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if User.objects.filter(email__iexact=data["email"]).exists():
            return Response({"detail": "Такая почта уже заведена"}, status=status.HTTP_400_BAD_REQUEST)

        user = create_user(
            email=data["email"],
            full_name=data.get("full_name", ""),
            role=data.get("role", Role.STUDENT),
            sees_whole_school=data.get("sees_whole_school", False),
        )
        magic_link.issue(user.email, purpose=LinkPurpose.INVITE)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    queryset = User.objects.all()
    search = request.query_params.get("search", "").strip()
    if search:
        queryset = queryset.filter(Q(email__icontains=search) | Q(full_name__icontains=search))
    role = request.query_params.get("role", "").strip()
    if role:
        queryset = queryset.filter(role=role)
    active = request.query_params.get("is_active", "").strip()
    if active in ("true", "false"):
        queryset = queryset.filter(is_active=active == "true")

    return Response(UserSerializer(queryset.order_by("email"), many=True).data)


@extend_schema(request=UserWriteSerializer, responses=UserSerializer)
@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdmin])
def user_detail(request, pk: int):
    """Смена роли, флага «видит всю школу» и отключение доступа.

    Физического удаления нет и не будет: на пользователе висят записи
    аудита, и удаление развалило бы историю правок (инвариант №13).
    DELETE отключает доступ и кладёт запись в архив, откуда её можно
    вернуть — снаружи это выглядит как обычное удаление.
    """
    user = User.objects.filter(pk=pk).first()
    if user is None:
        return Response({"detail": "Пользователь не найден"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        if request.user.pk == user.pk:
            return Response({"detail": "Нельзя удалить самого себя"}, status=status.HTTP_400_BAD_REQUEST)
        if not user.is_active:
            return Response({"detail": "Эта учётная запись уже отключена"}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=["is_active"])
        deactivate(user)
        entry = ArchiveEntry.objects.create(
            model_label="accounts.User",
            object_id=str(user.pk),
            title=user.full_name or user.email,
            kind_title="Учётная запись",
            summary="Доступ отключён, записи журнала остались на месте",
            actor=request.user,
        )
        return Response(
            {
                "archived": entry.pk,
                "detail": (
                    f"Доступ для {user.email} отключён. Правки этого человека остались "
                    "в журнале, а саму запись можно вернуть из архива"
                ),
            }
        )

    serializer = UserWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    if request.user.pk == user.pk and data.get("is_active") is False:
        return Response({"detail": "Нельзя отключить самого себя"}, status=status.HTTP_400_BAD_REQUEST)

    updates: list[str] = []
    for field in ("full_name", "role", "sees_whole_school", "is_active"):
        if field in data:
            setattr(user, field, data[field])
            updates.append(field)
    if updates:
        user.save(update_fields=updates)
    if data.get("is_active") is False:
        deactivate(user)
    return Response(UserSerializer(user).data)


@extend_schema(request=InviteSerializer, responses=DetailSerializer)
@api_view(["POST"])
@permission_classes([IsAdmin])
def invite(request):
    """Массовое приглашение: список почт, каждому — ссылка на установку пароля."""
    serializer = InviteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    role = serializer.validated_data.get("role", Role.STUDENT)

    created, invited, skipped = 0, 0, []
    for email in serializer.validated_data["emails"]:
        email = email.strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = create_user(email=email, role=role)
            created += 1
        elif not user.is_active:
            skipped.append({"email": email, "reason": "учётная запись отключена"})
            continue
        magic_link.issue(user.email, purpose=LinkPurpose.INVITE)
        invited += 1

    return Response({"created": created, "invited": invited, "skipped": skipped})
