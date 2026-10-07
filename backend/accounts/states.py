"""Состояние пароля учётной записи: одно место на весь экран (фаза 69).

В день раздачи паролей администратор смотрит на двести строк и хочет
знать про каждую одно: человек уже может войти или нет. Ответ склеен
из трёх разных вещей — есть ли пароль, ждёт ли он смены, не сгорела ли
ссылка-приглашение, — и раскладывать эту логику по экрану и по запросу
нельзя: чипы, счётчики и массовая выдача обязаны понимать её одинаково.

Пять состояний, и они не пересекаются:

* **не выдавали** — пароля нет, живых или просроченных приглашений тоже;
* **ссылка выдана** — пароля нет, есть живая ссылка; письмо могло не отправляться;
* **ждёт смены** — выдан временный пароль, человек им ещё не вошёл;
* **срок истёк** — войти нечем: временный пароль просрочен либо
  приглашение сгорело неиспользованным. Таким нужен новый пароль;
* **задан** — человек придумал свой пароль и работает.

Порядок важен: «срок истёк» проверяется раньше «ждёт смены», иначе
просроченные утонули бы среди ждущих и в день раздачи их бы пропустили.
"""

from __future__ import annotations

from django.db.models import Count, Exists, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone
from django.utils.translation import gettext_lazy

from accounts.models import InviteMail, LinkPurpose, MagicLinkToken, User

NO_PASSWORD = "no_password"
INVITE_ISSUED = "invite_issued"
WAITING = "waiting"
EXPIRED = "expired"
READY = "ready"

#: Подписи чипов — те же слова, что человек читает в строке таблицы
TITLES: dict[str, object] = {
    NO_PASSWORD: gettext_lazy("Не выдавали"),
    INVITE_ISSUED: gettext_lazy("Ссылка выдана"),
    WAITING: gettext_lazy("Ждёт смены пароля"),
    EXPIRED: gettext_lazy("Срок истёк"),
    READY: gettext_lazy("Пароль задан"),
}

#: Порядок чипов на экране: от «ничего нет» к «всё хорошо»
ORDER: tuple[str, ...] = (NO_PASSWORD, INVITE_ISSUED, WAITING, EXPIRED, READY)

#: Кому массовая выдача сбросит уже работающий пароль. Держится здесь,
#: рядом с состояниями: модалка и сервер должны считать одинаково
RESETS_A_WORKING_PASSWORD: tuple[str, ...] = (READY,)


def _has_usable_password() -> Q:
    """Пароль задан. В базе непригодный хеш начинается с «!» (так делает Django)."""
    return ~Q(password__startswith="!") & ~Q(password="")


def password_is_set(user: User) -> bool:
    """Пустой хеш тоже означает отсутствие пароля, как в условии выборки."""
    return bool(user.password) and user.has_usable_password()


def _live_invite() -> Exists:
    """Живая неиспользованная ссылка-приглашение этой учётной записи."""
    return Exists(
        MagicLinkToken.objects.filter(
            user=OuterRef("pk"),
            purpose=LinkPurpose.INVITE,
            used_at__isnull=True,
            expires_at__gte=timezone.now(),
        )
    )


def _dead_invite() -> Exists:
    """Приглашение выпускали, но оно сгорело неиспользованным."""
    return Exists(
        MagicLinkToken.objects.filter(
            user=OuterRef("pk"),
            purpose=LinkPurpose.INVITE,
            used_at__isnull=True,
            expires_at__lt=timezone.now(),
        )
    )


def annotate(queryset: QuerySet[User]) -> QuerySet[User]:
    """Добавить признаки, по которым считается состояние. Один запрос на всех."""
    latest_mail = InviteMail.objects.filter(user=OuterRef("pk"), status=InviteMail.Status.SENT).order_by(
        "-sent_at", "-pk"
    )
    return queryset.annotate(
        has_live_invite=_live_invite(),
        has_dead_invite=_dead_invite(),
        last_mail_sent_at=Subquery(latest_mail.values("sent_at")[:1]),
    )


def condition(code: str) -> Q:
    """Условие выборки для одного состояния. Неизвестный код — пусто."""
    now = timezone.now()
    has_password = _has_usable_password()
    expired_temp = Q(must_change_password=True, temp_password_expires_at__lt=now)

    # сгоревшее приглашение перестаёт что-либо значить, как только
    # выслали новое: у человека на руках живая ссылка, и место ему
    # среди «ссылка выдана», а не среди тех, кому войти нечем
    burnt = Q(has_dead_invite=True) & ~Q(has_live_invite=True)

    if code == NO_PASSWORD:
        return ~has_password & Q(has_live_invite=False, has_dead_invite=False)
    if code == INVITE_ISSUED:
        return ~has_password & Q(has_live_invite=True)
    if code == WAITING:
        return has_password & Q(must_change_password=True) & ~expired_temp
    if code == EXPIRED:
        # войти нечем: временный пароль просрочен либо приглашение сгорело
        return (has_password & expired_temp) | (~has_password & burnt)
    if code == READY:
        return has_password & Q(must_change_password=False)
    return Q()


def apply(queryset: QuerySet[User], code: str) -> QuerySet[User]:
    """Сузить выборку до одного состояния. Пустой или чужой код — как есть.

    Признаки навешиваются всегда, даже когда сужать не по чему: строку
    списка сериализует `state_of`, и без них он пошёл бы в базу за каждым
    человеком отдельно — двести строк превратились бы в сотни запросов.
    """
    rows = annotate(queryset)
    if code not in ORDER:
        return rows
    return rows.filter(condition(code))


def counts(queryset: QuerySet[User]) -> dict[str, int]:
    """Сколько записей в каждом состоянии. Считается по той же выборке, что и список."""
    rows = annotate(queryset)
    return rows.aggregate(**{code: Count("pk", filter=condition(code)) for code in ORDER})


def state_of(user: User) -> str:
    """Состояние одной записи — теми же правилами, что и выборка.

    Нужен сериализатору строки: человек должен видеть в строке ровно то,
    по чему он её отфильтровал.
    """
    now = timezone.now()
    if not password_is_set(user):
        # в списке признаки посчитаны одним запросом на всех (`annotate`);
        # поодиночке — например, письмом или карточкой — спрашиваем базу
        dead = getattr(user, "has_dead_invite", None)
        live = getattr(user, "has_live_invite", None)
        if dead is None or live is None:
            dead = MagicLinkToken.objects.filter(
                user=user,
                purpose=LinkPurpose.INVITE,
                used_at__isnull=True,
                expires_at__lt=now,
            ).exists()
            live = MagicLinkToken.objects.filter(
                user=user,
                purpose=LinkPurpose.INVITE,
                used_at__isnull=True,
                expires_at__gte=now,
            ).exists()
        if live:
            return INVITE_ISSUED
        return EXPIRED if dead else NO_PASSWORD
    if user.must_change_password:
        if user.temp_password_expires_at is not None and user.temp_password_expires_at < now:
            return EXPIRED
        return WAITING
    return READY
