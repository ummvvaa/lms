"""Одноразовые ссылки: приглашение, сброс пароля и вход выпускника.

Токен случайный, в базе лежит только его хеш, живёт ограниченное время
и сгорает после первого использования. У каждой ссылки есть назначение:
ссылка на сброс пароля не должна работать как ссылка на вход.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from accounts.models import Identity, IdentityProvider, LinkPurpose, MagicLinkToken, User


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


#: Что человек увидит в письме и куда его ведёт ссылка.
#: Название школы подставляется из настроек — в коде его нет (фаза 23).
LETTERS = {
    LinkPurpose.LOGIN: ("вход в платформу", "Ссылка для входа", "/login/link"),
    LinkPurpose.INVITE: ("доступ в платформу", "Ссылка для установки пароля", "/set-password"),
    LinkPurpose.RESET: ("сброс пароля", "Ссылка для смены пароля", "/set-password"),
}

#: Ссылка на пароль живёт час — этого хватает и не оставляет её висеть сутки.
PASSWORD_LINK_TTL_MINUTES = 60


def _ttl_minutes(purpose: str) -> int:
    if purpose == LinkPurpose.LOGIN:
        return settings.MAGIC_LINK_TTL_MINUTES
    return int(getattr(settings, "PASSWORD_LINK_TTL_MINUTES", PASSWORD_LINK_TTL_MINUTES))


def issue(email: str, *, purpose: str = LinkPurpose.LOGIN) -> str | None:
    """Выпустить ссылку, если такая почта известна системе.

    Возвращает токен (для тестов и отправки письма) либо None, если почты
    нет. Наружу разницы быть не должно — иначе форма превращается
    в проверку «есть ли такой человек».
    """
    email = email.strip().lower()
    known = Identity.objects.filter(email=email).exists() or User.objects.filter(email=email).exists()
    if not known:
        return None

    minutes = _ttl_minutes(purpose)
    token = secrets.token_urlsafe(32)
    MagicLinkToken.objects.create(
        email=email,
        token_hash=_hash(token),
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=minutes),
    )
    if settings.DEBUG:
        # в контуре разработки почтового сервера нет: кладём токен в кэш,
        # чтобы `manage.py dev_link` мог его показать браузерным проверкам.
        # При DEBUG=0 этой ветки не существует
        from django.core.cache import cache

        cache.set(f"dev-link:{_hash(token)}", token, minutes * 60)

    about, lead, path = LETTERS.get(purpose, LETTERS[LinkPurpose.LOGIN])
    link = f"{settings.FRONTEND_BASE_URL}{path}?token={token}"
    school = settings.SCHOOL_NAME
    text = f"{lead} действует {minutes} минут:\n\n{link}\n\n{school}\n"
    # HTML-версия с логотипом; текстовая остаётся основной на случай
    # почтового клиента без картинок
    html = (
        f'<div style="font-family: sans-serif; max-width: 480px">'
        f'<img src="{settings.FRONTEND_BASE_URL}/brand/logo-email.png" alt="{school}" '
        f'width="120" style="display: block; margin-bottom: 16px" />'
        f"<p>{lead} действует {minutes} минут:</p>"
        f'<p><a href="{link}">{link}</a></p>'
        f'<p style="color: #777">{school}</p>'
        f"</div>"
    )
    message = EmailMultiAlternatives(
        subject=f"{school} — {about}",
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=True)
    return token


def redeem(token: str, *, purposes: tuple[str, ...] = (LinkPurpose.LOGIN,)) -> User | None:
    """Погасить токен и вернуть пользователя. Повторное гашение не проходит.

    Назначение сверяется: ссылкой на сброс пароля нельзя просто войти,
    а ссылкой на вход — сменить пароль.
    """
    record = MagicLinkToken.objects.filter(token_hash=_hash(token)).first()
    if record is None or not record.is_usable or record.purpose not in purposes:
        return None

    identity = Identity.objects.filter(email=record.email).select_related("user").first()
    user = identity.user if identity else User.objects.filter(email=record.email).first()
    if user is None or not user.is_active:
        return None

    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])

    if identity is None:
        Identity.objects.create(
            user=user,
            provider=IdentityProvider.EMAIL_LINK,
            email=record.email,
            is_primary=not user.identities.exists(),
        )
    else:
        identity.last_login_at = timezone.now()
        identity.save(update_fields=["last_login_at"])
    return user
