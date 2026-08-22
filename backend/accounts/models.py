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
    #: пароль выдан администратором или ссылкой-приглашением — до смены
    #: пользователя дальше экрана смены пароля не пускаем
    must_change_password = models.BooleanField("Требуется сменить пароль", default=True)
    password_changed_at = models.DateTimeField("Пароль сменён", null=True, blank=True)
    #: «видит всю школу»: читает все домены и сводный вид, пишет только свой.
    #: Так у Салтанат нет второй роли `admin` — роль остаётся одна (см. решения)
    sees_whole_school = models.BooleanField("Видит всю школу", default=False)

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
    def can_see_whole_school(self) -> bool:
        """Открыт ли сводный вид по всей школе. Право на чтение, не на запись."""
        return self.role == Role.ADMIN or self.sees_whole_school

    @property
    def domain_code(self) -> str | None:
        """Код домена, которым владеет роль пользователя."""
        from core.domains import domain_of_role

        d = domain_of_role(self.role)
        return d.code if d else None


class IdentityProvider(models.TextChoices):
    """Откуда пришёл вход.

    Модель идентичностей остаётся, хотя внешнего провайдера сейчас нет:
    вернуть внешний вход позже можно будет, не переделывая аутентификацию.
    """

    PASSWORD = "password", "Почта и пароль"
    EMAIL_LINK = "email_link", "Одноразовая ссылка на почту"


class Identity(models.Model):
    """Способ входа. У одного пользователя их может быть несколько.

    Школьная почта с паролем и личная почта выпускника — две разные
    идентичности одного и того же `User`. Внешнего провайдера сейчас нет,
    но таблица осталась: вернуть его можно будет, не переделывая вход.
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


class LinkPurpose(models.TextChoices):
    """Зачем выпущена одноразовая ссылка."""

    LOGIN = "login", "Вход по ссылке"
    INVITE = "invite", "Приглашение: установить пароль"
    RESET = "reset", "Сброс пароля"


class MagicLinkToken(models.Model):
    """Одноразовая ссылка. В базе — только хеш, сам токен уходит в письмо."""

    email = models.EmailField("Email", db_index=True)
    token_hash = models.CharField("Хеш токена", max_length=64, unique=True)
    purpose = models.CharField("Назначение", max_length=16, choices=LinkPurpose.choices, default=LinkPurpose.LOGIN)
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


class LoginAttempt(models.Model):
    """Журнал попыток входа.

    Отдельная таблица, а не `AuditLog`: тот ведёт доменные поля учеников,
    и мешать в него события аутентификации значит засорять историю карточки.
    Здесь же считается блокировка — сколько неудач было за последнее время.
    """

    email = models.EmailField("Email", db_index=True)
    ip = models.GenericIPAddressField("Адрес", null=True, blank=True, db_index=True)
    successful = models.BooleanField("Удачная", default=False)
    reason = models.CharField("Причина отказа", max_length=64, blank=True)
    user_agent = models.CharField("Клиент", max_length=250, blank=True)
    created_at = models.DateTimeField("Когда", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Попытка входа"
        verbose_name_plural = "Попытки входа"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("email", "-created_at")),
            models.Index(fields=("ip", "-created_at")),
        ]

    def __str__(self) -> str:
        mark = "успех" if self.successful else f"отказ ({self.reason})"
        return f"{self.email} · {mark} · {self.created_at:%Y-%m-%d %H:%M}"
