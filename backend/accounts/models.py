"""Пользователи, роли и способы входа."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from core.domains import ROLE_CURATOR, ROLE_TITLES


class Role(models.TextChoices):
    """Роли системы. Домены берутся из реестра `core.domains`."""

    STUDENT = "student", ROLE_TITLES["student"]
    DIRECTOR_BEHAVIOR = "director_behavior", ROLE_TITLES["director_behavior"]
    DIRECTOR_ADMISSION = "director_admission", ROLE_TITLES["director_admission"]
    DIRECTOR_EXAM = "director_exam", ROLE_TITLES["director_exam"]
    DIRECTOR_TALENT = "director_talent", ROLE_TITLES["director_talent"]
    DIRECTOR_SPORT = "director_sport", ROLE_TITLES["director_sport"]
    #: куратор (фаза 60): подтверждает данные учеников своих групп,
    #: доменом не владеет; группы назначает администратор
    CURATOR = ROLE_CURATOR, ROLE_TITLES[ROLE_CURATOR]
    ADMIN = "admin", ROLE_TITLES["admin"]


class Theme(models.TextChoices):
    """Тема интерфейса. По умолчанию — как в системе пользователя."""

    LIGHT = "light", "Светлая"
    DARK = "dark", "Тёмная"
    SYSTEM = "system", "Как в системе"


class Language(models.TextChoices):
    """Язык интерфейса и писем. Русский основной."""

    RU = "ru", "Русский"
    KK = "kk", "Қазақша"
    EN = "en", "English"


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
    #: до какого момента действует выданный временный пароль. Пусто —
    #: пароль человек придумал себе сам, срока у него нет
    temp_password_expires_at = models.DateTimeField("Временный пароль действует до", null=True, blank=True)
    password_changed_at = models.DateTimeField("Пароль сменён", null=True, blank=True)
    #: «видит всю школу»: читает все домены и сводный вид, пишет только свой.
    #: Так у Салтанат нет второй роли `admin` — роль остаётся одна (см. решения)
    sees_whole_school = models.BooleanField("Видит всю школу", default=False)
    #: предпочтения интерфейса живут на сервере, а не в localStorage:
    #: они должны пережить смену устройства и очистку браузера
    sidebar_collapsed = models.BooleanField("Сайдбар свёрнут", default=False)
    theme = models.CharField("Тема", max_length=8, choices=Theme.choices, default=Theme.SYSTEM)
    language = models.CharField("Язык", max_length=2, choices=Language.choices, default=Language.RU)
    #: ученик нажал «Позже» на предложении привязать личную почту (фаза 75):
    #: закрыл на телефоне — не должен увидеть снова на компьютере, поэтому
    #: признак живёт здесь, а не в localStorage одного браузера
    link_identity_dismissed = models.BooleanField("Предложение о личной почте закрыто", default=False)

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
    def is_probe(self) -> bool:
        """Одноразовая запись браузерного прогона: живёт до уборки, в бою не входит."""
        from accounts.probe import is_probe_email

        return is_probe_email(self.email)

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


class CuratorAssignment(models.Model):
    """Назначение куратора на учебную группу (фаза 60).

    У группы в каждый момент один действующий куратор, у куратора групп
    несколько. История не удаляется: смена куратора посреди года закрывает
    старую запись датой `until` и открывает новую с `since`. Пустое
    `until` — назначение действует. `until` не входит в срок: в день
    смены группу ведёт уже новый куратор.

    Текстовое поле `StudyGroup.curator` удалено в фазе 61: источником
    права стало назначение. Назначения миграцией не создаются —
    сопоставить имя из старой записи с учётной записью мог только
    владелец руками, до удаления поля.
    """

    curator = models.ForeignKey(
        "accounts.User",
        verbose_name="Куратор",
        related_name="curator_assignments",
        on_delete=models.CASCADE,
    )
    group = models.ForeignKey(
        "students.StudyGroup",
        verbose_name="Группа",
        related_name="curator_assignments",
        on_delete=models.CASCADE,
    )
    since = models.DateField("Действует с")
    until = models.DateField("Действует до", null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        verbose_name="Кто назначил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Назначение куратора"
        verbose_name_plural = "Назначения кураторов"
        ordering = ("-since", "-id")
        constraints = [
            # одна открытая запись на группу — правило держит база, а не код
            models.UniqueConstraint(
                fields=("group",),
                condition=models.Q(until__isnull=True),
                name="one_open_curator_per_group",
            ),
            models.CheckConstraint(
                condition=models.Q(until__isnull=True) | models.Q(until__gt=models.F("since")),
                name="curator_until_after_since",
            ),
        ]
        indexes = [models.Index(fields=("curator", "until"))]

    def __str__(self) -> str:
        return f"{self.curator} → {self.group} с {self.since}"

    @property
    def is_active(self) -> bool:
        today = timezone.localdate()
        return self.since <= today and (self.until is None or self.until > today)


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
    #: администратор снял блокировку: попытка остаётся в журнале, но
    #: в серию неудач больше не входит (фаза 36). Удалять строки нельзя —
    #: по ним потом разбираются, кто и когда ломился
    cleared_at = models.DateTimeField("Снята", null=True, blank=True)
    cleared_by = models.ForeignKey(
        "accounts.User",
        verbose_name="Кто снял",
        related_name="cleared_login_attempts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

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
