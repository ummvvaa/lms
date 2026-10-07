"""Вход, выход, пароли, сведения о текущем пользователе и управление людьми.

Схема входа: почта и пароль проверяются здесь, сессия живёт в httpOnly
cookie. Внешнего провайдера сейчас нет, но модель `Identity` осталась —
вернуть его позже можно будет, не переделывая аутентификацию.

Регистрации самому себе нет: учётную запись заводит администратор либо
она появляется из массового приглашения.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from accounts import magic_link, passwords, temporary
from accounts.models import LinkPurpose, Role, User
from accounts.permissions import IsAdmin
from accounts.serializers import (
    BulkUsersSerializer,
    CredentialsExportSerializer,
    DetailSerializer,
    HandoutSerializer,
    IdentitySerializer,
    InviteSerializer,
    LinkIdentitySerializer,
    LoginSerializer,
    MagicLinkRedeemSerializer,
    MagicLinkRequestSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PreferencesSerializer,
    UserSerializer,
    UserWriteSerializer,
)
from accounts.services import create_user, deactivate, link_email_identity, touch_identity
from core import usage
from core.models import ArchiveEntry
from core.phrasing import tn

log = logging.getLogger(__name__)

BACKEND = "accounts.backends.LoginBackend"


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
    from django.conf import settings

    # одноразовая запись прогона живёт только в контуре разработки: даже
    # если её забыли убрать, в бою она не откроет дверь ни паролем, ни ссылкой
    from accounts.logins import student_archived

    if student_archived(user):
        return Response({"detail": _("Учётная запись в архиве — вход закрыт")}, status=status.HTTP_403_FORBIDDEN)
    if user.is_probe and not settings.DEBUG:
        return Response(
            {"detail": _("Одноразовая запись прогона работает только в контуре разработки")},
            status=status.HTTP_403_FORBIDDEN,
        )
    login(request, user, backend=BACKEND)
    get_token(request)
    # вошёл по логину — почты у него может не быть вовсе
    touch_identity(user, user.email)
    usage.track(request, "auth.login")
    return Response(MeSerializer(user).data)


@extend_schema(request=LoginSerializer, responses=MeSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login_view(request):
    """Вход по почте, логину или подтверждённой личной почте и паролю."""
    from accounts.logins import lock_key

    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    identifier = serializer.validated_data["identifier"]
    # серия неудач — одна на учётную запись, чем бы ни входили
    email = lock_key(identifier)
    ip = passwords.client_ip(request)
    agent = request.META.get("HTTP_USER_AGENT", "")

    lock = passwords.check_lock(email=email, ip=ip)
    if lock is not None:
        passwords.record_attempt(email=email, ip=ip, successful=False, reason="locked", user_agent=agent)
        # кроме текста — когда откроется и по чему считается: экран может
        # показать обратный отсчёт, а администратор — найти блокировку в списке
        return Response(
            {
                "detail": lock.message,
                "scope": lock.scope,
                "unlock_in": lock.seconds,
                "unlock_at": lock.as_dict()["unlock_at"],
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    user = authenticate(request, username=identifier, password=serializer.validated_data["password"])
    if user is None:
        passwords.record_attempt(email=email, ip=ip, successful=False, reason="bad_credentials", user_agent=agent)
        # одинаковый ответ на неизвестную почту и неверный пароль:
        # форма входа не должна работать как проверка «есть ли такой человек»
        return Response({"detail": _("Неверная почта, логин или пароль")}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        passwords.record_attempt(email=email, ip=ip, successful=False, reason="inactive", user_agent=agent)
        return Response({"detail": _("Учётная запись отключена")}, status=status.HTTP_403_FORBIDDEN)

    # временный пароль живёт ограниченное время: письмо с ним остаётся
    # в ящике навсегда, и бессрочный пароль оттуда — открытая дверь
    if temporary.is_expired(user):
        passwords.record_attempt(email=email, ip=ip, successful=False, reason="temp_expired", user_agent=agent)
        return Response(
            {"detail": temporary.expired_message(user), "code": "temp_password_expired"},
            status=status.HTTP_403_FORBIDDEN,
        )

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
        return Response({"detail": _("Текущий пароль неверен")}, status=status.HTTP_400_BAD_REQUEST)

    try:
        passwords.set_password(user, serializer.validated_data["new_password"])
    except passwords.PasswordRejected as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

    # Ключ сессии намеренно НЕ вращаем (фаза 36, D1). `update_session_auth_hash`
    # делает `cycle_key()`: старая сессия удаляется, в cookie уезжает новый ключ —
    # и любой запрос, ушедший параллельно со старым ключом, ответив позже,
    # перетирал cookie уже мёртвым ключом. Человек после смены пароля
    # оказывался на экране входа. Ключ выдан при входе и своё уже отработал;
    # здесь достаточно обновить отпечаток пароля в сессии — остальные сессии
    # этого человека (на других устройствах) по нему и закроются.
    from django.contrib.auth import HASH_SESSION_KEY

    request.session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    return Response(MeSerializer(user).data)


# --- Блокировки входа (фаза 36) --------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAdmin])
def login_locks(request):
    """Действующие блокировки входа: кто, сколько неудач, когда снимется.

    Считаются тем же кодом, что и отказ на форме входа, поэтому список
    не расходится с тем, что видит человек. Рядом — доверенные сети
    и пороги, чтобы администратор понимал, почему школьный адрес не заперт.
    """
    from django.conf import settings

    return Response(
        {
            "locks": [lock.as_dict() for lock in passwords.current_locks()],
            "trusted_networks": [str(n) for n in passwords.trusted_networks()],
            "account_threshold": passwords.FAILURES_BEFORE_LOCK,
            "address_threshold": passwords.address_threshold(),
            "window_minutes": int(passwords.WINDOW.total_seconds() // 60),
            "settings_note": (
                _(
                    "Порог по адресу — переменная LOGIN_IP_FAILURES, доверенные сети — "
                    "LOGIN_TRUSTED_NETWORKS в настройках контура"
                )
            ),
            "debug": bool(settings.DEBUG),
        }
    )


@extend_schema(request=None, responses={200: DetailSerializer})
@api_view(["POST"])
@permission_classes([IsAdmin])
def login_unlock(request):
    """Снять блокировку: попытки остаются в журнале, но серия обнуляется."""
    scope = str(request.data.get("scope") or "")
    value = str(request.data.get("value") or "").strip()
    if scope not in ("account", "address") or not value:
        return Response(
            {"detail": _("Укажите, что снимать: учётную запись (account) или адрес (address), и её значение")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    cleared = passwords.unlock(scope=scope, value=value, actor=request.user)
    log.info("Блокировку входа (%s %s) снял %s: %d попыток", scope, value, request.user.handle, cleared)
    text = (
        _("Блокировка учётной записи {value} снята. Попыток в серии было: {count}")
        if scope == "account"
        else _("Блокировка адреса {value} снята. Попыток в серии было: {count}")
    )
    return Response({"detail": text.format(value=value, count=cleared), "cleared": cleared})


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
    return Response({"detail": _("Если такая почта известна системе, ссылка отправлена")})


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
        return Response(
            {"detail": _("Ссылка недействительна или уже использована")}, status=status.HTTP_400_BAD_REQUEST
        )

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
    return Response({"detail": _("Если такая почта известна системе, ссылка отправлена")})


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
        return Response(
            {"detail": _("Ссылка недействительна или уже использована")}, status=status.HTTP_400_BAD_REQUEST
        )
    return _start_session(request, user)


@extend_schema(request=None, responses=DetailSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """Выход: сессия убивается на сервере."""
    logout(request)
    return Response({"detail": _("Вы вышли")})


@extend_schema(responses=MeSerializer)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """Кто я, какая роль, какой домен веду."""
    get_token(request)
    return Response(MeSerializer(request.user).data)


@extend_schema(request=PreferencesSerializer, responses=MeSerializer)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def preferences(request):
    """Предпочтения интерфейса: сайдбар, тема, язык.

    Живут на сервере, а не в localStorage — чтобы пережить смену
    устройства и очистку браузера.
    """
    serializer = PreferencesSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    changed = dict(serializer.validated_data)
    # сменил язык сам — уведомление о языке, выбранном школой, больше не нужно
    if "language" in changed and request.user.language_notice:
        changed["language_notice"] = False
    for field, value in changed.items():
        setattr(request.user, field, value)
    if changed:
        request.user.save(update_fields=list(changed))
    return Response(MeSerializer(request.user).data)


@extend_schema(request=LinkIdentitySerializer, responses=IdentitySerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def link_identity(request):
    """Привязать личную почту: письмо со ссылкой подтверждения уходит на неё."""
    serializer = LinkIdentitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        identity = link_email_identity(request.user, serializer.validated_data["email"])
    except ValueError as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    payload = IdentitySerializer(identity).data
    payload["detail"] = (
        _("Почта уже подтверждена")
        if identity.confirmed_at
        else _("На {email} ушло письмо — откройте ссылку, чтобы подтвердить почту").format(email=identity.email)
    )
    return Response(payload, status=status.HTTP_201_CREATED)


@extend_schema(request=MagicLinkRedeemSerializer, responses=DetailSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def confirm_identity(request):
    """Подтверждение личной почты по ссылке из письма."""
    serializer = MagicLinkRedeemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    identity = magic_link.confirm(serializer.validated_data["token"])
    if identity is None:
        return Response(
            {"detail": _("Ссылка недействительна или уже использована")}, status=status.HTTP_400_BAD_REQUEST
        )
    return Response(
        {
            "detail": _("Почта {email} подтверждена: по ней можно войти и восстановить пароль").format(
                email=identity.email
            ),
            "email": identity.email,
        }
    )


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
            return Response({"detail": _("Такая почта уже заведена")}, status=status.HTTP_400_BAD_REQUEST)

        user = create_user(
            email=data["email"],
            full_name=data.get("full_name", ""),
            role=data.get("role", Role.STUDENT),
            sees_whole_school=data.get("sees_whole_school", False),
        )
        token, sent_to = magic_link.issue_for(user, purpose=LinkPurpose.INVITE, actor=request.user)
        # ссылку отдаём сразу: пока почта не настроена, письмо уходит
        # в журнал, и без ссылки на экране завести человека нечем
        payload = UserSerializer(user).data
        payload["invite"] = _invite_payload(user, token, sent_to)
        if token:
            usage.track(request, "access.link.issue")
        return Response(payload, status=status.HTTP_201_CREATED)

    from accounts import states

    base = _filter_users(request.query_params)
    # сколько отключённых прячет переключатель — считается до сужения
    # по доступу, иначе его собственный счётчик всегда показывал бы ноль
    inactive = base.filter(is_active=False).count()

    active = request.query_params.get("is_active", "").strip()
    queryset = base.filter(is_active=active == "true") if active in ("true", "false") else base

    # счётчики чипов считаются до сужения по состоянию: человек должен
    # видеть, сколько записей в каждом состоянии, стоя на любом чипе
    payload_counts = states.counts(queryset)
    rows = states.apply(queryset, request.query_params.get("state", "").strip())

    return Response(
        {
            "results": UserSerializer(rows.order_by("email", "login"), many=True).data,
            "counts": {"all": queryset.count(), "inactive": inactive, **payload_counts},
            "states": [{"code": code, "title": states.TITLES[code]} for code in states.ORDER],
            "groups": _group_codes(),
        }
    )


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAdmin])
def users_export(request):
    """Пользователи книгой XLSX — по тому же фильтру, что стоит на экране.

    Список учётных записей, а не выдача доступа: паролей, ссылок-приглашений
    и токенов в нём нет и быть не может — только состояние пароля словами.
    С `?preview=1` отвечает таблицей для экрана (`core/exports.py`).
    """
    from accounts import states
    from core.domains import ROLE_TITLES
    from core.exports import Column, workbook_response

    queryset = _filter_users(request.query_params)
    active = request.query_params.get("is_active", "").strip()
    if active in ("true", "false"):
        queryset = queryset.filter(is_active=active == "true")
    rows = states.apply(queryset, request.query_params.get("state", "").strip()).order_by("role", "full_name", "email")

    def group_of(user: User) -> str:
        student = getattr(user, "student", None)
        return student.group.code if student is not None and student.group_id else ""

    columns = (
        Column(_("ФИО"), lambda user: user.full_name, 32),
        Column(_("Почта"), lambda user: user.email or "", 34),
        Column(_("Логин"), lambda user: user.login or "", 24),
        Column(_("Роль"), lambda user: str(ROLE_TITLES.get(user.role, user.role)), 34),
        Column(_("Группа"), group_of, 12),
        Column(_("Состояние пароля"), lambda user: str(states.TITLES[states.state_of(user)]), 24),
        Column(_("Активен"), lambda user: user.is_active, 10),
    )
    stamp = timezone.localdate().strftime("%Y-%m-%d")
    return workbook_response(
        filename=_("пользователи-{date}.xlsx").format(date=stamp),
        sheet=_("Пользователи"),
        columns=columns,
        rows=rows,
        request=request,
    )


def _filter_users(params) -> QuerySet[User]:
    """Сузить список по фильтрам экрана: поиск, роль, группа, параллель.

    Одно место на список и на раздачу паролей (фаза 69): числа в модалке
    обязаны совпадать с тем, что человек видит в таблице, а два похожих
    набора условий расходятся на первой же правке. Состояние пароля сюда
    не входит — по нему считаются счётчики чипов; доступ тоже: списку он
    нужен переключателем, выдаче — всегда только живые записи.
    """
    queryset = User.objects.select_related("student__group").all()
    search = (params.get("search") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(email__icontains=search) | Q(login__icontains=search) | Q(full_name__icontains=search)
        )
    role = (params.get("role") or "").strip()
    if role:
        queryset = queryset.filter(role=role)
    group = (params.get("group") or "").strip()
    if group:
        queryset = queryset.filter(student__group__code__iexact=group)
    parallel = (params.get("parallel") or "").strip()
    if parallel:
        # параллель — только у учеников: сотрудник в фильтр не попадает
        from core.parallels import in_parallel

        queryset = in_parallel(queryset.filter(role=Role.STUDENT, student__isnull=False), parallel, prefix="student__")
    if str(params.get("never_logged_in", "")).lower() in ("true", "1"):
        queryset = queryset.filter(last_login__isnull=True)
    return queryset


def _group_codes() -> list[str]:
    """Группы школы для фильтра — по ним отбирают учеников в день раздачи."""
    from students.models import StudyGroup

    return list(StudyGroup.objects.filter(is_active=True).order_by("code").values_list("code", flat=True))


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
        return Response({"detail": _("Пользователь не найден")}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        if request.user.pk == user.pk:
            return Response({"detail": _("Нельзя удалить самого себя")}, status=status.HTTP_400_BAD_REQUEST)
        if not user.is_active:
            return Response({"detail": _("Эта учётная запись уже отключена")}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=["is_active"])
        deactivate(user)
        entry = ArchiveEntry.objects.create(  # i18n-skip: запись архива хранится в базе как данные
            model_label="accounts.User",
            object_id=str(user.pk),
            title=user.full_name or user.handle,
            kind_title="Учётная запись",
            summary="Доступ отключён, записи журнала остались на месте",
            actor=request.user,
        )
        return Response(
            {
                "archived": entry.pk,
                "detail": _(
                    "Доступ для {login} отключён. Правки этого человека остались "
                    "в журнале, а саму запись можно вернуть из архива"
                ).format(login=user.handle),
            }
        )

    serializer = UserWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    if request.user.pk == user.pk and data.get("is_active") is False:
        return Response({"detail": _("Нельзя отключить самого себя")}, status=status.HTTP_400_BAD_REQUEST)
    # роль себе не меняют (фаза 67): администратор, понизивший себя по ошибке,
    # не сможет вернуть роль обратно — некому
    if request.user.pk == user.pk and "role" in data and data["role"] != user.role:
        return Response(
            {"detail": _("Свою роль сменить нельзя: попросите другого администратора")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = (data.get("email") or "").strip().lower()
    if email and email != (user.email or "").lower():
        # почта — это логин: занятую отдаём отказом словами, а не 500 из базы
        if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            return Response(
                {"detail": _("Почта {email} уже занята другой учётной записью").format(email=email)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data["email"] = email
    else:
        data.pop("email", None)

    login_changed = "email" in data
    was_email = user.email

    # правка идёт общим журналом (`apply_changes`): учётной записи нет
    # в реестре доменов, и сигнал аудита её не пишет — а видеть, кто и что
    # поменял человеку в карточке, надо ровно так же, как у ученика
    from core.audit import apply_changes

    changes = {
        field: data[field]
        for field in ("email", "full_name", "role", "sees_whole_school", "is_active")
        if field in data
    }
    if changes:
        apply_changes(user, changes, actor=request.user)
    if data.get("is_active") is False:
        deactivate(user)

    payload = UserSerializer(user).data
    if login_changed:
        # ссылка на прежнюю почту больше не придёт — сказать об этом прямо
        payload["login_changed"] = {
            "was": was_email,
            "now": user.email,
            "detail": _(
                "Вход теперь по почте {email}. Прежняя ссылка уходила на {old_email} "
                "и больше не придёт — вышлите приглашение заново"
            ).format(email=user.email, old_email=was_email),
        }
    return Response(payload)


def _invite_payload(user, token: str | None, sent_to: str = "") -> dict:
    """Ссылка-приглашение для показа администратору.

    Отдаётся только по явному действию и только администратору: ссылка
    равна паролю до первого использования, и в общем списке ей не место —
    оттуда она уедет в скриншот и в журнал прокси.
    """
    minutes = magic_link.ttl_minutes(LinkPurpose.INVITE)
    if not token:
        return {"link": "", "detail": _("Ссылку выпустить не удалось: такой почты система не знает")}
    return {
        "link": magic_link.link_for(LinkPurpose.INVITE, token),
        "email": user.email,
        "login": user.handle,
        "sent_to": sent_to,
        "minutes": minutes,
        "detail": (
            tn(
                minutes,
                "Ссылка действует {n} минуту и гаснет после первого использования. "
                "Передайте её лично — по ней {login} задаст себе пароль|"
                "Ссылка действует {n} минуты и гаснет после первого использования. "
                "Передайте её лично — по ней {login} задаст себе пароль|"
                "Ссылка действует {n} минут и гаснет после первого использования. "
                "Передайте её лично — по ней {login} задаст себе пароль",
                login=user.handle,
            )
            + (_(". Копия ушла письмом на {email}").format(email=sent_to) if sent_to else "")
        ),
    }


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAdmin])
def user_invite_link(request, pk: int):
    """Выпустить свежую ссылку-приглашение и показать её администратору.

    Нужна, когда почта не настроена или письмо не дошло: без ссылки
    новый человек не может задать пароль и войти вообще никак.
    """
    user = User.objects.filter(pk=pk).first()
    if user is None:
        return Response({"detail": _("Пользователь не найден")}, status=status.HTTP_404_NOT_FOUND)
    if not user.is_active:
        return Response(
            {"detail": _("Учётная запись отключена — сначала включите её")}, status=status.HTTP_400_BAD_REQUEST
        )

    token, sent_to = magic_link.issue_for(user, purpose=LinkPurpose.INVITE, actor=request.user)
    log.info("Ссылка-приглашение для %s выпущена администратором %s", user.handle, request.user.handle)
    if token:
        usage.track(request, "access.link.issue")
    return Response(_invite_payload(user, token, sent_to))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_password_link(request, pk: int):
    """Ссылка на пароль ученику — куратор своей группы или администратор.

    У 8–10 почты нет: ссылку показывают на экране, и куратор передаёт её
    лично. Письмо уходит, только если у ученика есть почта. Живёт 48 часов,
    как всякая ссылка на пароль; выдача — событие журнала ученика.
    """
    from core.audit import record_event
    from core.domains import ROLE_ADMIN, ROLE_CURATOR
    from core.phrasing import until
    from core.scope import sees_student
    from students.models import Student

    if request.user.role not in (ROLE_ADMIN, ROLE_CURATOR):
        return Response(
            {"detail": _("Ссылку на пароль ученику выдают куратор его группы и администратор")},
            status=status.HTTP_403_FORBIDDEN,
        )
    student = Student.objects.select_related("user", "group").filter(pk=pk).first()
    if student is None or not sees_student(request.user, student.pk):
        return Response({"detail": _("Ученик не найден")}, status=status.HTTP_404_NOT_FOUND)
    user = student.user
    if user is None:
        return Response({"detail": _("У ученика нет учётной записи")}, status=status.HTTP_400_BAD_REQUEST)
    if not user.is_active:
        return Response({"detail": _("Доступ ученика отключён")}, status=status.HTTP_400_BAD_REQUEST)

    token, sent_to = magic_link.issue_for(user, purpose=LinkPurpose.RESET, actor=request.user)
    expires = timezone.now() + timedelta(minutes=magic_link.ttl_minutes(LinkPurpose.RESET))
    moment = until(expires)
    record_event(  # i18n-skip: значение записи журнала хранится в базе как данные
        student=student,
        code="password_link",
        text=f"ссылка на пароль до {moment}" + (f", копия письмом на {sent_to}" if sent_to else ""),
        actor=request.user,
    )
    if token:
        usage.track(request, "access.student_link.issue")
    return Response(
        {
            "link": magic_link.link_for(LinkPurpose.RESET, token),
            "login": user.handle,
            "until": moment,
            "sent_to": sent_to,
            "detail": (
                _(
                    "Ссылка действует до {moment} и гаснет после первого использования. "
                    "Передайте её лично — по ней {login} задаст себе пароль"
                ).format(moment=moment, login=user.handle)
                + (
                    _(". Копия ушла письмом на {email}").format(email=sent_to)
                    if sent_to
                    else _(". Письмо не отправлено — передайте ссылку лично")
                )
            ),
        }
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAdmin])
def user_temp_password(request, pk: int):
    """Выпустить новый временный пароль и показать его администратору.

    Открытым текстом пароль возвращается ровно один раз — тому, кто нажал
    кнопку. В базе остаётся хеш, восстановить пароль нельзя.
    """
    user = User.objects.filter(pk=pk).first()
    if user is None:
        return Response({"detail": _("Пользователь не найден")}, status=status.HTTP_404_NOT_FOUND)
    if not user.is_active:
        return Response(
            {"detail": _("Учётная запись отключена — сначала включите её")}, status=status.HTTP_400_BAD_REQUEST
        )

    password = temporary.issue(user)
    sent = temporary.send_letter(user, password, actor=request.user)
    log.info("Временный пароль для %s выпустил %s", user.handle, request.user.handle)
    return Response(
        {
            "email": user.email,
            "login": user.handle,
            "full_name": user.full_name,
            "password": password,
            "hours": temporary.ttl_hours(),
            "sent": sent,
            "detail": (
                _("Новый временный пароль для {login} выпущен и отправлен письмом").format(login=user.handle)
                if sent
                else _("Новый временный пароль для {login} выпущен. Письмо не ушло — передайте пароль лично").format(
                    login=user.handle
                )
            ),
        }
    )


@extend_schema(request=BulkUsersSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAdmin])
def users_bulk(request):
    """Одно действие сразу над несколькими учётными записями.

    Список отмеченных строк приходит с экрана. Действия ровно три: выслать
    письма заново, выпустить новые временные пароли, отключить доступ.
    Удаления здесь нет намеренно: пачкой такое не делают.
    """
    payload = BulkUsersSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    action = payload.validated_data["action"]
    people = list(User.objects.filter(pk__in=payload.validated_data["users"]))

    if action == "invite":
        from accounts import mailing

        result = mailing.bulk_invite(people, actor=request.user, force=payload.validated_data["force"])
        if result["sent"] + result["queued"]:
            usage.track(request, "access.invite.bulk")
        return Response({**_mailing_result(result), "done": result["sent"], "issued": []})

    done, skipped, issued = 0, [], []
    for user in people:
        if user.pk == request.user.pk and action == "deactivate":
            skipped.append({"email": user.handle, "reason": _("нельзя отключить самого себя")})
            continue
        if not user.is_active and action != "deactivate":
            skipped.append({"email": user.handle, "reason": _("учётная запись отключена")})
            continue

        if action == "temp_password":
            password = temporary.issue(user)
            temporary.send_letter(user, password, actor=request.user)
            issued.append(
                {"full_name": user.full_name, "email": user.email, "login": user.handle, "password": password}
            )
        elif action == "deactivate":
            if not user.is_active:
                skipped.append({"email": user.handle, "reason": _("уже отключена")})
                continue
            user.is_active = False
            user.save(update_fields=["is_active"])
            deactivate(user)
        done += 1

    titles = {
        "temp_password": _("Новые временные пароли выпущены: {done}"),
        "deactivate": _("Доступ отключён: {done}"),
    }
    return Response(
        {
            "done": done,
            "skipped": skipped,
            # пароли открытым текстом — только в этом ответе, чтобы
            # администратор мог их скачать; на сервере они не хранятся
            "issued": issued,
            "detail": titles[action].format(done=done)
            + (_(", пропущено: {count}").format(count=len(skipped)) if skipped else ""),
        }
    )


def _mailing_result(result: dict) -> dict:
    """Одинаковый итог для обоих способов массового приглашения."""
    detail = _("Отправлено {sent}, в очереди {queued}, пропущено {skipped}").format(
        sent=result["sent"], queued=result["queued"], skipped=len(result["skipped"])
    )
    if result["failed"]:
        detail += _(", ошибок отправки {failed}").format(failed=result["failed"])
    return {**result, "detail": detail}


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAdmin])
def mail_queue(request):
    """Ожидающие письма и ближайший срок начала отправки."""
    from accounts import mailing

    return Response(mailing.queue_summary(), headers={"Cache-Control": "private, no-store"})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAdmin])
def mail_queue_cancel(request):
    """Отмена ещё не начатой отправки, история писем сохраняется."""
    from accounts import mailing

    result = mailing.cancel_queue(actor=request.user)
    return Response({**result, "detail": _("Отменено писем: {count}").format(count=result["cancelled"])})


@extend_schema(responses={200: list})
@api_view(["GET"])
@permission_classes([IsAdmin])
def user_mail_history(request, pk: int):
    """Последние письма пользователю: без ссылок, токенов и паролей."""
    from accounts import mailing

    user = User.objects.filter(pk=pk).first()
    if user is None:
        return Response({"detail": _("Пользователь не найден")}, status=status.HTTP_404_NOT_FOUND)
    return Response({"rows": mailing.history(user)}, headers={"Cache-Control": "private, no-store"})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAdmin])
def passwords_handout(request):
    """Раздача паролей списком: предпросмотр и сама выдача (фаза 69).

    Работает либо по отмеченным строкам, либо по текущему фильтру —
    что именно, решает экран и пишет словами в модалке. Ошибиться здесь
    дорого: выдача сбрасывает уже заданный пароль, поэтому таких людей
    по умолчанию нет в списке, а подтверждение — набранное число.
    """
    from accounts import handout, states

    payload = HandoutSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    data = payload.validated_data
    include_ready = data.get("include_ready", False)

    if data.get("users"):
        queryset = User.objects.select_related("student__group").filter(pk__in=data["users"])
        scope = _("по отмеченным строкам: {count}").format(count=len(data["users"]))
    else:
        # тот же набор фильтров, что у списка, и тем же кодом: человек
        # видит на экране ровно то, что уйдёт в выдачу
        queryset = states.apply(_filter_users(data), data.get("state", ""))
        scope = _("по текущему фильтру")

    plan = handout.plan(queryset, include_ready=include_ready)
    plan["scope"] = scope

    if data.get("confirm") is None:
        return Response(plan)

    if str(data["confirm"]).strip() != plan["confirm"]:
        return Response(
            {
                "detail": _("Наберите число затронутых — {number}, — чтобы подтвердить выдачу").format(
                    number=plan["confirm"]
                ),
                **plan,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    outcome = handout.issue(queryset, actor=request.user, include_ready=include_ready)
    return Response({**plan, **outcome})


@extend_schema(request=None, responses={200: None})
@api_view(["POST"])
@permission_classes([IsAdmin])
def passwords_handout_export(request):
    """Выданные пароли книгой XLSX. Собирается по запросу, на сервере не лежит."""
    from accounts import handout

    payload = CredentialsExportSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    return handout.export(payload.validated_data["rows"], request=request, kind=payload.validated_data["kind"])


@extend_schema(request=CredentialsExportSerializer, responses={200: str})
@api_view(["POST"])
@permission_classes([IsAdmin])
def credentials_export(request):
    """Выгрузка списка «ФИО, логин, временный пароль» файлом.

    Файл собирается по запросу и на сервере не хранится: список паролей
    открытым текстом не должен лежать нигде дольше, чем нужно, чтобы его
    скачать. Пароли приходят с экрана — те, что были показаны при выдаче.
    """
    from django.http import HttpResponse

    payload = CredentialsExportSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    body = temporary.export_csv(payload.validated_data["rows"])

    response = HttpResponse(body, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="uchetnye-zapisi.csv"'
    usage.track(request, "export.download")
    return response


@extend_schema(request=InviteSerializer, responses=DetailSerializer)
@api_view(["POST"])
@permission_classes([IsAdmin])
def invite(request):
    """Массовое приглашение: список почт, каждому — ссылка на установку пароля."""
    serializer = InviteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    role = serializer.validated_data.get("role", Role.STUDENT)

    from accounts import mailing

    created, people = 0, []
    emails = dict.fromkeys(email.strip().lower() for email in serializer.validated_data["emails"])
    for email in emails:
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            try:
                with transaction.atomic():
                    user = create_user(email=email, role=role)
                created += 1
            except IntegrityError:
                # Два одновременных приглашения одного адреса используют
                # одну учётную запись и общую защиту от повторной отправки.
                user = User.objects.filter(email__iexact=email).first()
                if user is None:
                    raise
        people.append(user)
    result = mailing.bulk_invite(people, actor=request.user, force=serializer.validated_data["force"])
    if result["sent"] + result["queued"]:
        usage.track(request, "access.invite.bulk")
    payload = _mailing_result(result)
    if created:
        payload["detail"] = _("Заведено учётных записей: {created}. {result}").format(
            created=created, result=payload["detail"]
        )
    return Response({**payload, "created": created, "invited": result["sent"]})
