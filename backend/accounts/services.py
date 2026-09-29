"""Пользователи и идентичности: заведение, приглашение, привязка почты."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from accounts.models import Identity, IdentityProvider, Role, User
from accounts.naming import check_full_name


@transaction.atomic
def create_user(*, email: str, full_name: str = "", role: str = Role.STUDENT, sees_whole_school: bool = False) -> User:
    """Завести учётную запись. Пароль ставит сам человек по ссылке-приглашению.

    Регистрации самому себе в системе нет: аккаунт создаёт администратор
    либо он появляется из массового приглашения.
    """
    email = email.strip().lower()
    # имя с пометкой «тест» отсюда попадёт в журнал и в письма навсегда
    full_name = check_full_name(full_name)
    user = User.objects.create_user(email=email, password=None, full_name=full_name, role=role)
    user.set_unusable_password()
    user.must_change_password = True
    user.sees_whole_school = sees_whole_school
    user.save(update_fields=["password", "must_change_password", "sees_whole_school"])

    Identity.objects.get_or_create(
        provider=IdentityProvider.PASSWORD,
        email=email,
        defaults={"user": user, "is_primary": True, "confirmed_at": timezone.now()},
    )

    # карточку ученика могли завести раньше учётной записи: связываем по
    # почте, иначе человек войдёт и не увидит собственных данных
    from students.linking import link_user

    link_user(user)
    return user


def touch_identity(user: User, email: str | None, provider: str = IdentityProvider.PASSWORD) -> Identity | None:
    """Отметить вход по этой идентичности, заведя её при необходимости.

    У входящего по логину почты нет — и отмечать нечего.
    """
    if not email:
        return None
    email = email.strip().lower()
    identity = Identity.objects.filter(provider=provider, email=email).first()
    if identity is None:
        identity = Identity.objects.create(
            user=user,
            provider=provider,
            email=email,
            is_primary=not user.identities.exists(),
            confirmed_at=timezone.now(),
        )
    identity.last_login_at = timezone.now()
    identity.save(update_fields=["last_login_at"])
    return identity


def link_email_identity(user: User, email: str) -> Identity:
    """Привязать личную почту — после подтверждения письмом.

    До подтверждения адрес не вход и не адрес сброса пароля: иначе чужая
    почта, набранная с опечаткой, становилась дверью в учётную запись.
    Неподтверждённый адрес, который кто-то привязал раньше, не держит
    почту за ним — он ничего не доказал.
    """
    from accounts import magic_link

    email = email.strip().lower()
    if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
        raise ValueError("Эта почта уже привязана к другому пользователю")
    identity = Identity.objects.filter(provider=IdentityProvider.EMAIL_LINK, email__iexact=email).first()
    if identity is not None and identity.user_id != user.pk:
        if identity.confirmed_at is not None:
            raise ValueError("Эта почта уже привязана к другому пользователю")
        identity.user = user
        identity.save(update_fields=["user"])
    if identity is None:
        identity = Identity.objects.create(
            user=user, provider=IdentityProvider.EMAIL_LINK, email=email, is_primary=False
        )
    if identity.confirmed_at is None:
        magic_link.issue_confirmation(user, email)
    return identity


def deactivate(user: User) -> User:
    """Отключить доступ, не удаляя запись: на пользователе висит аудит."""
    user.is_active = False
    user.save(update_fields=["is_active"])
    return user


def is_director(user: User) -> bool:
    return user.role.startswith("director_") or user.role == Role.ADMIN
