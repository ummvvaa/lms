"""Пользователи и идентичности: поиск, создание, маппинг ролей."""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.entra import EntraClaims
from accounts.models import Identity, IdentityProvider, Role, User


def role_from_groups(groups: tuple[str, ...] | list[str]) -> str | None:
    """Роль по группам Entra. Маппинг задаётся настройкой, не кодом.

    Если пользователь в нескольких группах — берём первую по порядку
    приоритета из настроек, чтобы результат не зависел от порядка групп
    в токене.
    """
    mapping: dict[str, str] = settings.ENTRA_GROUP_ROLE_MAP
    incoming = {str(g) for g in groups}
    for group_id, role in mapping.items():
        if group_id in incoming:
            return role
    return None


@transaction.atomic
def upsert_from_entra(claims: EntraClaims) -> tuple[User, Identity]:
    """Найти или создать пользователя по данным Entra и обновить роль.

    Сначала ищем по внешнему идентификатору, потом по email — выпускник
    мог сначала войти по личной почте, и вторая идентичность должна лечь
    на того же `User`, а не создать нового.
    """
    identity = Identity.objects.filter(provider=IdentityProvider.ENTRA, external_id=claims.subject).first()
    if identity is None:
        identity = Identity.objects.filter(provider=IdentityProvider.ENTRA, email=claims.email).first()

    user = identity.user if identity else User.objects.filter(email=claims.email).first()
    created = user is None
    if created:
        user = User.objects.create_user(email=claims.email, password=None, full_name=claims.full_name)
        user.set_unusable_password()
        user.save(update_fields=["password"])

    role = role_from_groups(claims.groups)
    updates: list[str] = []
    if role and user.role != role:
        user.role = role
        updates.append("role")
    elif created and role is None:
        user.role = settings.ENTRA_DEFAULT_ROLE
        updates.append("role")
    if claims.full_name and user.full_name != claims.full_name:
        user.full_name = claims.full_name
        updates.append("full_name")
    if updates:
        user.save(update_fields=updates)

    if identity is None:
        identity = Identity.objects.create(
            user=user,
            provider=IdentityProvider.ENTRA,
            external_id=claims.subject,
            email=claims.email,
            is_primary=not user.identities.exists(),
        )
    else:
        changed = []
        if identity.external_id != claims.subject:
            identity.external_id = claims.subject
            changed.append("external_id")
        if identity.email != claims.email:
            identity.email = claims.email
            changed.append("email")
        if changed:
            identity.save(update_fields=changed)

    identity.last_login_at = timezone.now()
    identity.save(update_fields=["last_login_at"])
    return user, identity


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


def is_director(user: User) -> bool:
    return user.role.startswith("director_") or user.role == Role.ADMIN
