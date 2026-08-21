"""Вторая дверь: вход по личной почте с одноразовой ссылкой.

Для выпускников, у которых школьный аккаунт Entra уже отключён.
Токен подписывается ключом Django, живёт ограниченное время и сгорает
после первого использования — отметка о сгорании хранится в `MagicLinkToken`.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from accounts.models import Identity, IdentityProvider, MagicLinkToken, User


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(email: str) -> str | None:
    """Выпустить ссылку, если такая почта известна системе.

    Возвращает токен (для тестов и отправки письма) либо None, если почты
    нет. Наружу разницы быть не должно — иначе форма превращается
    в проверку «есть ли такой человек».
    """
    email = email.strip().lower()
    known = Identity.objects.filter(email=email).exists() or User.objects.filter(email=email).exists()
    if not known:
        return None

    token = secrets.token_urlsafe(32)
    MagicLinkToken.objects.create(
        email=email,
        token_hash=_hash(token),
        expires_at=timezone.now() + timedelta(minutes=settings.MAGIC_LINK_TTL_MINUTES),
    )
    link = f"{settings.FRONTEND_BASE_URL}/login/link?token={token}"
    send_mail(
        subject="Вход в платформу школы",
        message=f"Ссылка для входа действует {settings.MAGIC_LINK_TTL_MINUTES} минут:\n\n{link}\n",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=True,
    )
    return token


def redeem(token: str) -> User | None:
    """Погасить токен и вернуть пользователя. Повторное гашение не проходит."""
    record = MagicLinkToken.objects.filter(token_hash=_hash(token)).first()
    if record is None or not record.is_usable:
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
