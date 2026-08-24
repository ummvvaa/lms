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
from django.utils import timezone

from accounts.models import Identity, IdentityProvider, LinkPurpose, MagicLinkToken, User
from core import mail
from core.i18n import render, translate


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


#: Что человек увидит в письме и куда его ведёт ссылка. Тексты — русские
#: шаблоны, перевод по языку получателя делает `core.i18n` (фаза 24).
#: Название школы подставляется из настроек — в коде его нет (фаза 23).
LETTERS = {
    LinkPurpose.LOGIN: ("вход в платформу", "Ссылка для входа действует {minutes} минут:", "/login/link"),
    LinkPurpose.INVITE: (
        "доступ в платформу",
        "Ссылка для установки пароля действует {minutes} минут:",
        "/set-password",
    ),
    LinkPurpose.RESET: (
        "сброс пароля",
        "Ссылка для смены пароля действует {minutes} минут:",
        "/set-password",
    ),
}

#: Ссылка на пароль живёт час — этого хватает и не оставляет её висеть сутки.
PASSWORD_LINK_TTL_MINUTES = 60


def ttl_minutes(purpose: str) -> int:
    """Сколько живёт ссылка этого назначения — в минутах."""
    return _ttl_minutes(purpose)


def _ttl_minutes(purpose: str) -> int:
    if purpose == LinkPurpose.LOGIN:
        return settings.MAGIC_LINK_TTL_MINUTES
    return int(getattr(settings, "PASSWORD_LINK_TTL_MINUTES", PASSWORD_LINK_TTL_MINUTES))


def link_for(purpose: str, token: str) -> str:
    """Полный адрес, по которому человек откроет ссылку.

    Собирается из `FRONTEND_BASE_URL`: письмо и ссылка, скопированная
    администратором, ведут в одно и то же место — иначе одна из них
    однажды поведёт не туда.
    """
    _about, _lead, path = LETTERS.get(purpose, LETTERS[LinkPurpose.LOGIN])
    return f"{settings.FRONTEND_BASE_URL}{path}?token={token}"


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

    about, lead, _path = LETTERS.get(purpose, LETTERS[LinkPurpose.LOGIN])
    # ссылка нужна и отдельно от письма: пока почта не настроена,
    # администратор раздаёт её руками, иначе завести человека нечем
    link = link_for(purpose, token)
    # письмо уходит на языке получателя; неизвестной почте не пишем вовсе,
    # так что владелец у адреса есть всегда, но подстрахуемся русским
    owner = User.objects.filter(email__iexact=email).first()
    if owner is None:
        identity = Identity.objects.filter(email__iexact=email).select_related("user").first()
        owner = identity.user if identity else None
    lang = getattr(owner, "language", "ru")
    about = translate(lang, about)
    lead = render(lang, lead, minutes=minutes)
    school = settings.SCHOOL_NAME
    text = f"{lead}\n\n{link}\n\n{school}\n"
    # HTML-версия с логотипом и названием школы собирается общей обёрткой
    # (`core.mail.wrap`), текстовая остаётся основной на случай почтового
    # клиента без картинок
    mail.send(
        to=email,
        subject=about,
        text=text,
        html=f'<p>{lead}</p><p><a href="{link}">{link}</a></p>',
    )
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
