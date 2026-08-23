"""Пользователи и идентичности: заведение, приглашение, привязка почты."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from accounts.models import Identity, IdentityProvider, Role, User


@transaction.atomic
def create_user(*, email: str, full_name: str = "", role: str = Role.STUDENT, sees_whole_school: bool = False) -> User:
    """Завести учётную запись. Пароль ставит сам человек по ссылке-приглашению.

    Регистрации самому себе в системе нет: аккаунт создаёт администратор
    либо он появляется из массового приглашения.
    """
    email = email.strip().lower()
    user = User.objects.create_user(email=email, password=None, full_name=full_name, role=role)
    user.set_unusable_password()
    user.must_change_password = True
    user.sees_whole_school = sees_whole_school
    user.save(update_fields=["password", "must_change_password", "sees_whole_school"])

    Identity.objects.get_or_create(
        provider=IdentityProvider.PASSWORD,
        email=email,
        defaults={"user": user, "is_primary": True},
    )

    # карточку ученика могли завести раньше учётной записи: связываем по
    # почте, иначе человек войдёт и не увидит собственных данных
    from students.linking import link_user

    link_user(user)
    return user


def touch_identity(user: User, email: str, provider: str = IdentityProvider.PASSWORD) -> Identity:
    """Отметить вход по этой идентичности, заведя её при необходимости."""
    email = email.strip().lower()
    identity = Identity.objects.filter(provider=provider, email=email).first()
    if identity is None:
        identity = Identity.objects.create(
            user=user, provider=provider, email=email, is_primary=not user.identities.exists()
        )
    identity.last_login_at = timezone.now()
    identity.save(update_fields=["last_login_at"])
    return identity


def link_email_identity(user: User, email: str) -> Identity:
    """Привязать личную почту второй идентичностью к существующему `User`."""
    email = email.strip().lower()
    identity, _ = Identity.objects.get_or_create(
        provider=IdentityProvider.EMAIL_LINK,
        email=email,
        defaults={"user": user, "is_primary": False},
    )
    if identity.user_id != user.pk:
        raise ValueError("Эта почта уже привязана к другому пользователю")
    return identity


def deactivate(user: User) -> User:
    """Отключить доступ, не удаляя запись: на пользователе висит аудит."""
    user.is_active = False
    user.save(update_fields=["is_active"])
    return user


def is_director(user: User) -> bool:
    return user.role.startswith("director_") or user.role == Role.ADMIN
