"""Пользователи, роли и способы входа."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy, pgettext_lazy

from core.domains import ROLE_CURATOR, ROLE_TEACHER, ROLE_TITLES


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
    #: учитель: отдельная учётка, видит только свои уроки и учеников
    #: своих составов; профиль (предметы, кабинет) — `academics.TeacherProfile`
    TEACHER = ROLE_TEACHER, ROLE_TITLES[ROLE_TEACHER]
    ADMIN = "admin", ROLE_TITLES["admin"]


class Theme(models.TextChoices):
    """Тема интерфейса. По умолчанию — как в системе пользователя."""

    LIGHT = "light", gettext_lazy("Светлая")
    DARK = "dark", gettext_lazy("Тёмная")
    SYSTEM = "system", gettext_lazy("Как в системе")


class Language(models.TextChoices):
    """Язык интерфейса и писем. Русский основной."""

    RU = "ru", "Русский"  # i18n-skip: самоназвание языка в выборе
    KK = "kk", "Қазақша"  # i18n-skip: самоназвание языка в выборе
    EN = "en", "English"


class UserManager(BaseUserManager):
    """Менеджер пользователей: вход по почте или по логину.

    У сотрудников и 11 — почта; у 8–10 почты школы нет, у них логин
    «имя.фамилия» (`accounts.logins`). Без того и другого войти нечем.
    """

    use_in_migrations = True

    def create_user(self, email: str | None = None, password: str | None = None, **extra):
        email = self.normalize_email(email).lower() if email else None
        if not email and not extra.get("login"):
            raise ValueError(gettext("Нужна почта или логин"))
        user = self.model(email=email, **extra)
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

    #: почта необязательна: у 8–10 её нет — они входят по логину
    email = models.EmailField("Email", unique=True, null=True, blank=True)
    #: логин вместо почты — «имя.фамилия» латиницей, при совпадении с цифрой.
    #: Заводится только тем, у кого почты нет (`accounts.logins.make_login`)
    login = models.CharField(gettext_lazy("Логин"), max_length=64, unique=True, null=True, blank=True)
    full_name = models.CharField(gettext_lazy("ФИО"), max_length=200, blank=True)
    #: телефон сотрудника «+7XXXXXXXXXX» — по нему импорт расписания узнаёт
    #: уже заведённого человека (`academics.schedule_import`)
    phone = models.CharField(gettext_lazy("Телефон"), max_length=20, blank=True)
    role = models.CharField(gettext_lazy("Роль"), max_length=32, choices=Role.choices, default=Role.STUDENT)
    is_active = models.BooleanField(gettext_lazy("Активен"), default=True)
    is_staff = models.BooleanField(gettext_lazy("Доступ в админку"), default=False)
    date_joined = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)
    #: пароль выдан администратором или ссылкой-приглашением — до смены
    #: пользователя дальше экрана смены пароля не пускаем
    must_change_password = models.BooleanField(gettext_lazy("Требуется сменить пароль"), default=True)
    #: до какого момента действует выданный временный пароль. Пусто —
    #: пароль человек придумал себе сам, срока у него нет
    temp_password_expires_at = models.DateTimeField(
        gettext_lazy("Временный пароль действует до"), null=True, blank=True
    )
    password_changed_at = models.DateTimeField(gettext_lazy("Пароль сменён"), null=True, blank=True)
    #: «видит всю школу»: читает все домены и сводный вид, пишет только свой.
    #: Так у Салтанат нет второй роли `admin` — роль остаётся одна (см. решения)
    sees_whole_school = models.BooleanField(gettext_lazy("Видит всю школу"), default=False)
    #: предпочтения интерфейса живут на сервере, а не в localStorage:
    #: они должны пережить смену устройства и очистку браузера
    sidebar_collapsed = models.BooleanField(gettext_lazy("Сайдбар свёрнут"), default=False)
    theme = models.CharField(
        pgettext_lazy("appearance", "Тема"), max_length=8, choices=Theme.choices, default=Theme.SYSTEM
    )
    language = models.CharField(gettext_lazy("Язык"), max_length=2, choices=Language.choices, default=Language.RU)
    #: язык поменяла школа, а не сам человек (ученику проставлен язык группы):
    #: при следующем входе один раз показывается, что интерфейс теперь на этом
    #: языке и где его сменить. Снимается кнопкой в уведомлении или сменой языка
    language_notice = models.BooleanField(gettext_lazy("Показать уведомление о языке"), default=False)
    #: ученик нажал «Позже» на предложении привязать личную почту (фаза 75):
    #: закрыл на телефоне — не должен увидеть снова на компьютере, поэтому
    #: признак живёт здесь, а не в localStorage одного браузера
    link_identity_dismissed = models.BooleanField(gettext_lazy("Предложение о личной почте закрыто"), default=False)
    #: вымышленная учётная запись посева учебной части (учителя): ставится
    #: только посевом при `DEBUG=1` и вычищается `purge_fictional` вместе
    #: с вымышленными учениками
    is_fictional = models.BooleanField(gettext_lazy("Вымышленный"), default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = gettext_lazy("Пользователь")
        verbose_name_plural = gettext_lazy("Пользователи")
        ordering = ("email",)

    def __str__(self) -> str:
        return self.full_name or self.handle

    @property
    def handle(self) -> str:
        """Чем человек входит: почта, а у кого её нет — логин."""
        return self.email or self.login or ""

    @property
    def is_probe(self) -> bool:
        """Одноразовая запись браузерного прогона: живёт до уборки, в бою не входит."""
        from accounts.probe import is_probe_email, is_probe_login

        return is_probe_email(self.email or "") or is_probe_login(self.login)

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
        verbose_name=gettext_lazy("Куратор"),
        related_name="curator_assignments",
        on_delete=models.CASCADE,
    )
    group = models.ForeignKey(
        "students.StudyGroup",
        verbose_name=gettext_lazy("Группа"),
        related_name="curator_assignments",
        on_delete=models.CASCADE,
    )
    since = models.DateField(gettext_lazy("Действует с"))
    until = models.DateField(gettext_lazy("Действует до"), null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        verbose_name=gettext_lazy("Кто назначил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Создано"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Назначение куратора")
        verbose_name_plural = gettext_lazy("Назначения кураторов")
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
        return gettext("{curator} → {group} с {since}").format(curator=self.curator, group=self.group, since=self.since)

    @property
    def is_active(self) -> bool:
        today = timezone.localdate()
        return self.since <= today and (self.until is None or self.until > today)


class IdentityProvider(models.TextChoices):
    """Откуда пришёл вход.

    Модель идентичностей остаётся, хотя внешнего провайдера сейчас нет:
    вернуть внешний вход позже можно будет, не переделывая аутентификацию.
    """

    PASSWORD = "password", gettext_lazy("Почта и пароль")
    EMAIL_LINK = "email_link", gettext_lazy("Одноразовая ссылка на почту")


class Identity(models.Model):
    """Способ входа. У одного пользователя их может быть несколько.

    Школьная почта с паролем и личная почта выпускника — две разные
    идентичности одного и того же `User`. Внешнего провайдера сейчас нет,
    но таблица осталась: вернуть его можно будет, не переделывая вход.
    """

    user = models.ForeignKey(
        User, verbose_name=gettext_lazy("Пользователь"), related_name="identities", on_delete=models.CASCADE
    )
    provider = models.CharField(gettext_lazy("Провайдер"), max_length=32, choices=IdentityProvider.choices)
    external_id = models.CharField(gettext_lazy("Внешний идентификатор"), max_length=255, blank=True)
    email = models.EmailField("Email")
    is_primary = models.BooleanField(gettext_lazy("Основная"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Создана"), auto_now_add=True)
    last_login_at = models.DateTimeField(gettext_lazy("Последний вход"), null=True, blank=True)
    #: личная почта работает для входа и сброса пароля только после
    #: подтверждения письмом: иначе чужой адрес, привязанный по ошибке,
    #: становился дверью в чужую учётную запись. Почта школы (`password`)
    #: подтверждена тем, что её выдала школа
    confirmed_at = models.DateTimeField(gettext_lazy("Подтверждена"), null=True, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Идентичность")
        verbose_name_plural = gettext_lazy("Идентичности")
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

    LOGIN = "login", gettext_lazy("Вход по ссылке")
    INVITE = "invite", gettext_lazy("Приглашение: установить пароль")
    RESET = "reset", gettext_lazy("Сброс пароля")
    CONFIRM = "confirm", gettext_lazy("Подтверждение личной почты")


class MagicLinkToken(models.Model):
    """Одноразовая ссылка. В базе — только хеш, сам токен уходит в письмо.

    Ссылку, которую выдаёт куратор или администратор, получает учётная
    запись (`user`), а не адрес: у 8–10 почты нет, ссылку им показывают
    на экране и кладут в файл выдачи. `email` — куда ушло письмо, если ушло.
    """

    email = models.EmailField("Email", db_index=True, blank=True)
    user = models.ForeignKey(
        User,
        verbose_name=gettext_lazy("Учётная запись"),
        related_name="link_tokens",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    token_hash = models.CharField(gettext_lazy("Хеш токена"), max_length=64, unique=True)
    purpose = models.CharField(
        gettext_lazy("Назначение"), max_length=16, choices=LinkPurpose.choices, default=LinkPurpose.LOGIN
    )
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)
    expires_at = models.DateTimeField(gettext_lazy("Истекает"))
    used_at = models.DateTimeField(gettext_lazy("Использован"), null=True, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Одноразовая ссылка")
        verbose_name_plural = gettext_lazy("Одноразовые ссылки")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return gettext("{email} до {moment}").format(email=self.email, moment=f"{self.expires_at:%Y-%m-%d %H:%M}")

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()


class LoginAttempt(models.Model):
    """Журнал попыток входа.

    Отдельная таблица, а не `AuditLog`: тот ведёт доменные поля учеников,
    и мешать в него события аутентификации значит засорять историю карточки.
    Здесь же считается блокировка — сколько неудач было за последнее время.
    """

    #: чем входили — почта или логин, как набрали, в нижнем регистре
    email = models.CharField(gettext_lazy("Почта или логин"), max_length=254, db_index=True)
    ip = models.GenericIPAddressField(gettext_lazy("Адрес"), null=True, blank=True, db_index=True)
    successful = models.BooleanField(gettext_lazy("Удачная"), default=False)
    reason = models.CharField(gettext_lazy("Причина отказа"), max_length=64, blank=True)
    user_agent = models.CharField(gettext_lazy("Клиент"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Когда"), auto_now_add=True, db_index=True)
    #: администратор снял блокировку: попытка остаётся в журнале, но
    #: в серию неудач больше не входит (фаза 36). Удалять строки нельзя —
    #: по ним потом разбираются, кто и когда ломился
    cleared_at = models.DateTimeField(gettext_lazy("Снята"), null=True, blank=True)
    cleared_by = models.ForeignKey(
        "accounts.User",
        verbose_name=gettext_lazy("Кто снял"),
        related_name="cleared_login_attempts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Попытка входа")
        verbose_name_plural = gettext_lazy("Попытки входа")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("email", "-created_at")),
            models.Index(fields=("ip", "-created_at")),
        ]

    def __str__(self) -> str:
        mark = gettext("успех") if self.successful else gettext("отказ ({reason})").format(reason=self.reason)
        return f"{self.email} · {mark} · {self.created_at:%Y-%m-%d %H:%M}"
