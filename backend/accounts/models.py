"""Пользователи, роли и способы входа."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from core.domains import ROLE_TITLES


class Role(models.TextChoices):
    """Роли системы. Домены берутся из реестра `core.domains`."""

    STUDENT = "student", ROLE_TITLES["student"]
    DIRECTOR_BEHAVIOR = "director_behavior", ROLE_TITLES["director_behavior"]
    DIRECTOR_ADMISSION = "director_admission", ROLE_TITLES["director_admission"]
    DIRECTOR_EXAM = "director_exam", ROLE_TITLES["director_exam"]
    DIRECTOR_TALENT = "director_talent", ROLE_TITLES["director_talent"]
    DIRECTOR_SPORT = "director_sport", ROLE_TITLES["director_sport"]
    ADMIN = "admin", ROLE_TITLES["admin"]


class UserManager(BaseUserManager):
    """Менеджер пользователей: логин — email."""

    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra):
        if not email:
            raise ValueError("Email обязателен")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", Role.ADMIN)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Пользователь платформы. Роль одна, домен выводится из роли."""

    email = models.EmailField("Email", unique=True)
    full_name = models.CharField("ФИО", max_length=200, blank=True)
    role = models.CharField("Роль", max_length=32, choices=Role.choices, default=Role.STUDENT)
    is_active = models.BooleanField("Активен", default=True)
    is_staff = models.BooleanField("Доступ в админку", default=False)
    date_joined = models.DateTimeField("Создан", auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ("email",)

    def __str__(self) -> str:
        return self.full_name or self.email

    @property
    def domain_code(self) -> str | None:
        """Код домена, которым владеет роль пользователя."""
        from core.domains import domain_of_role

        d = domain_of_role(self.role)
        return d.code if d else None


class IdentityProvider(models.TextChoices):
    """Откуда пришёл вход."""

    ENTRA = "entra", "Microsoft Entra ID"
    EMAIL_LINK = "email_link", "Одноразовая ссылка на почту"
    LOCAL = "local", "Локальный пароль"


class Identity(models.Model):
    """Способ входа. У одного пользователя их может быть несколько.

    Школьный Entra и личная почта выпускника — две разные идентичности
    одного и того же `User`.
    """

    user = models.ForeignKey(User, verbose_name="Пользователь", related_name="identities", on_delete=models.CASCADE)
    provider = models.CharField("Провайдер", max_length=32, choices=IdentityProvider.choices)
    external_id = models.CharField("Внешний идентификатор", max_length=255, blank=True)
    email = models.EmailField("Email")
    is_primary = models.BooleanField("Основная", default=False)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    last_login_at = models.DateTimeField("Последний вход", null=True, blank=True)

    class Meta:
        verbose_name = "Идентичность"
        verbose_name_plural = "Идентичности"
        constraints = [
            models.UniqueConstraint(fields=("provider", "email"), name="uniq_identity_provider_email"),
            models.UniqueConstraint(
                fields=("provider", "external_id"),
                condition=~models.Q(external_id=""),
                name="uniq_identity_provider_external_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_provider_display()}: {self.email}"


class MagicLinkToken(models.Model):
    """Одноразовая ссылка. В базе — только хеш, сам токен уходит в письмо."""

    email = models.EmailField("Email", db_index=True)
    token_hash = models.CharField("Хеш токена", max_length=64, unique=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    expires_at = models.DateTimeField("Истекает")
    used_at = models.DateTimeField("Использован", null=True, blank=True)

    class Meta:
        verbose_name = "Одноразовая ссылка"
        verbose_name_plural = "Одноразовые ссылки"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.email} до {self.expires_at:%Y-%m-%d %H:%M}"

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()
