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
from django.utils import timezone, translation
from django.utils.translation import gettext_noop

from accounts.models import Identity, IdentityProvider, LinkPurpose, MagicLinkToken, User
from core import mail, phrasing
from core.i18n import language_of, render, translate


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


#: Что человек увидит в письме и куда его ведёт ссылка. Тексты — русские
#: шаблоны (`gettext_noop`), перевод по языку получателя делает `core.i18n` (фаза 24).
#: Название школы подставляется из настроек — в коде его нет (фаза 23).
LETTERS = {
    LinkPurpose.LOGIN: (
        gettext_noop("вход в платформу"),
        gettext_noop("Ссылка для входа действует до {until}:"),
        "/login/link",
    ),
    LinkPurpose.INVITE: (
        gettext_noop("доступ в платформу"),
        gettext_noop("Ссылка для установки пароля действует до {until}:"),
        "/set-password",
    ),
    LinkPurpose.RESET: (
        gettext_noop("сброс пароля"),
        gettext_noop("Ссылка для смены пароля действует до {until}:"),
        "/set-password",
    ),
    LinkPurpose.CONFIRM: (
        gettext_noop("подтверждение почты"),
        gettext_noop("Подтвердите, что это ваша почта. Ссылка действует до {until}:"),
        "/confirm-email",
    ),
}

#: Ссылка на пароль живёт двое суток (фаза 69): пароли раздают списком,
#: и часа не хватало, чтобы передать двести ссылок до того, как они сгорят
PASSWORD_LINK_TTL_MINUTES = 2880


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


def issue(email: str, *, purpose: str = LinkPurpose.LOGIN, actor=None) -> str | None:
    """Выпустить ссылку по адресу, если он известен системе, и отправить письмо.

    Адрес известен, если это почта учётной записи или подтверждённая
    личная почта (`accounts.logins.find_user`). Возвращает токен (для
    тестов) либо None — наружу разницы быть не должно, иначе форма
    превращается в проверку «есть ли такой человек».
    """
    from accounts.logins import find_user

    email = email.strip().lower()
    if "@" not in email:
        return None
    user = find_user(email)
    if user is None:
        return None
    return _issue(user, purpose, address=email, actor=actor)[0]


def issue_for(user: User, *, purpose: str, send: bool = True, actor=None, mail_entry=None) -> tuple[str, str]:
    """Выпустить ссылку учётной записи — её показывают на экране.

    Так выдаёт ссылку куратор или администратор: у 8–10 почты нет,
    и ссылка живёт на экране и в файле выдачи. Письмо уходит, только
    если человеку есть куда писать. Возвращает токен и адрес письма
    (пусто — письма не было).
    """
    from accounts.logins import address_of

    address = address_of(user) if send else ""
    return _issue(user, purpose, address=address, actor=actor, mail_entry=mail_entry)


def _issue(user: User, purpose: str, *, address: str, actor=None, mail_entry=None) -> tuple[str, str]:
    minutes = _ttl_minutes(purpose)
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(minutes=minutes)
    record = MagicLinkToken.objects.create(
        email=address,
        user=user,
        token_hash=_hash(token),
        purpose=purpose,
        expires_at=expires_at,
    )
    if settings.DEBUG:
        # в контуре разработки почтового сервера нет: кладём токен в кэш,
        # чтобы `manage.py dev_link` мог его показать браузерным проверкам.
        # При DEBUG=0 этой ветки не существует
        from django.core.cache import cache

        cache.set(f"dev-link:{_hash(token)}", token, minutes * 60)
    sent = bool(address) and _send(
        address,
        purpose,
        token,
        expires_at,
        lang=language_of(user),
        user=user,
        actor=actor,
        entry=mail_entry,
        record=record,
    )
    return token, address if sent else ""


def _send(
    address: str, purpose: str, token: str, expires_at, *, lang: str, user, actor=None, entry=None, record=None
) -> bool:
    from accounts import mailing

    about, lead, _path = LETTERS.get(purpose, LETTERS[LinkPurpose.LOGIN])
    # ссылка нужна и отдельно от письма: пока почта не настроена,
    # администратор раздаёт её руками, иначе завести человека нечем
    link = link_for(purpose, token)
    about = translate(lang, about)
    # срок — датой, а не длительностью (фаза 69): «до 13.09.2026, 11:00»
    # человек понимает сразу, «2880 минут» — нет
    # и дата — по правилам языка получателя: по-английски «13/09/2026»
    with translation.override(lang):
        until = phrasing.until(expires_at)
    lead = render(lang, lead, until=until)
    school = settings.SCHOOL_NAME
    text = f"{lead}\n\n{link}\n\n{school}\n"
    # HTML-версия с логотипом и названием школы собирается общей обёрткой
    # (`core.mail.wrap`), текстовая остаётся основной на случай почтового
    # клиента без картинок
    return mailing.deliver(
        user=user,
        address=address,
        purpose=purpose,
        actor=actor,
        entry=entry,
        token=record,
        secrets=(token,),
        sender=lambda: mail.send_result(
            to=address,
            subject=about,
            text=text,
            html=f'<p>{lead}</p><p><a href="{link}">{link}</a></p>',
            secrets=(token,),
        ),
    )


def issue_confirmation(user: User, email: str, *, actor=None) -> str:
    """Письмо на личную почту: подтвердите, что адрес ваш."""
    email = email.strip().lower()
    return _issue(user, LinkPurpose.CONFIRM, address=email, actor=actor or user)[0]


def confirm(token: str) -> Identity | None:
    """Погасить ссылку подтверждения: личная почта становится входом и адресом сброса."""
    record = MagicLinkToken.objects.filter(token_hash=_hash(token), purpose=LinkPurpose.CONFIRM).first()
    if record is None or not record.is_usable or record.user_id is None:
        return None
    identity = Identity.objects.filter(
        provider=IdentityProvider.EMAIL_LINK, email__iexact=record.email, user_id=record.user_id
    ).first()
    if identity is None:
        return None
    now = timezone.now()
    record.used_at = now
    record.save(update_fields=["used_at"])
    identity.confirmed_at = now
    identity.save(update_fields=["confirmed_at"])
    return identity


def redeem(token: str, *, purposes: tuple[str, ...] = (LinkPurpose.LOGIN,)) -> User | None:
    """Погасить токен и вернуть пользователя. Повторное гашение не проходит.

    Назначение сверяется: ссылкой на сброс пароля нельзя просто войти,
    а ссылкой на вход — сменить пароль. Неподтверждённая личная почта
    ссылку не гасит: она ещё не вход.
    """
    from accounts.logins import find_user

    record = MagicLinkToken.objects.filter(token_hash=_hash(token)).first()
    if record is None or not record.is_usable or record.purpose not in purposes:
        return None

    user = record.user if record.user_id else find_user(record.email)
    if user is None or not user.is_active:
        return None

    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])

    if record.email:
        identity = Identity.objects.filter(email__iexact=record.email, user=user).first()
        if identity is None:
            Identity.objects.create(
                user=user,
                provider=IdentityProvider.EMAIL_LINK,
                email=record.email,
                is_primary=not user.identities.exists(),
                confirmed_at=timezone.now(),
            )
        else:
            identity.last_login_at = timezone.now()
            identity.save(update_fields=["last_login_at"])
    return user
