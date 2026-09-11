"""Состояние пароля учётной записи: одно место на весь экран (фаза 69).

В день раздачи паролей администратор смотрит на двести строк и хочет
знать про каждую одно: человек уже может войти или нет. Ответ склеен
из трёх разных вещей — есть ли пароль, ждёт ли он смены, не сгорела ли
ссылка-приглашение, — и раскладывать эту логику по экрану и по запросу
нельзя: чипы, счётчики и массовая выдача обязаны понимать её одинаково.

Четыре состояния, и они не пересекаются:

* **не задан** — пароля нет и ссылка ещё жива (или её не выпускали);
* **ждёт смены** — выдан временный пароль, человек им ещё не вошёл;
* **срок истёк** — войти нечем: временный пароль просрочен либо
  приглашение сгорело неиспользованным. Таким нужен новый пароль;
* **задан** — человек придумал свой пароль и работает.

Порядок важен: «срок истёк» проверяется раньше «ждёт смены», иначе
просроченные утонули бы среди ждущих и в день раздачи их бы пропустили.
"""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils import timezone

from accounts.models import LinkPurpose, MagicLinkToken, User

NO_PASSWORD = "no_password"
WAITING = "waiting"
EXPIRED = "expired"
READY = "ready"

#: Подписи чипов — те же слова, что человек читает в строке таблицы
TITLES: dict[str, str] = {
    NO_PASSWORD: "Пароль не задан",
    WAITING: "Ждёт смены пароля",
    EXPIRED: "Срок истёк",
    READY: "Пароль задан",
}

#: Порядок чипов на экране: от «ничего нет» к «всё хорошо»
ORDER: tuple[str, ...] = (NO_PASSWORD, WAITING, EXPIRED, READY)

#: Кому массовая выдача сбросит уже работающий пароль. Держится здесь,
#: рядом с состояниями: модалка и сервер должны считать одинаково
RESETS_A_WORKING_PASSWORD: tuple[str, ...] = (READY,)


def _has_usable_password() -> Q:
    """Пароль задан. В базе непригодный хеш начинается с «!» (так делает Django)."""
    return ~Q(password__startswith="!") & ~Q(password="")


def _live_invite() -> Exists:
    """Живая неиспользованная ссылка-приглашение на эту почту."""
    return Exists(
        MagicLinkToken.objects.filter(
            email=OuterRef("email"),
            purpose=LinkPurpose.INVITE,
            used_at__isnull=True,
            expires_at__gte=timezone.now(),
        )
    )


def _dead_invite() -> Exists:
    """Приглашение выпускали, но оно сгорело неиспользованным."""
    return Exists(
        MagicLinkToken.objects.filter(
            email=OuterRef("email"),
            purpose=LinkPurpose.INVITE,
            used_at__isnull=True,
            expires_at__lt=timezone.now(),
        )
    )


def annotate(queryset: QuerySet[User]) -> QuerySet[User]:
    """Добавить признаки, по которым считается состояние. Один запрос на всех."""
    return queryset.annotate(has_live_invite=_live_invite(), has_dead_invite=_dead_invite())


def condition(code: str) -> Q:
    """Условие выборки для одного состояния. Неизвестный код — пусто."""
    now = timezone.now()
    has_password = _has_usable_password()
    expired_temp = Q(must_change_password=True, temp_password_expires_at__lt=now)

    # сгоревшее приглашение перестаёт что-либо значить, как только
    # выслали новое: у человека на руках живая ссылка, и место ему
    # среди «пароль не задан», а не среди тех, кому войти нечем
    burnt = Q(has_dead_invite=True) & ~Q(has_live_invite=True)

    if code == NO_PASSWORD:
        # пароля нет, и войти ещё будет чем: ссылка жива или её не выпускали
        return ~has_password & ~burnt
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
    return {code: rows.filter(condition(code)).count() for code in ORDER}


def state_of(user: User) -> str:
    """Состояние одной записи — теми же правилами, что и выборка.

    Нужен сериализатору строки: человек должен видеть в строке ровно то,
    по чему он её отфильтровал.
    """
    now = timezone.now()
    if not user.has_usable_password():
        # в списке признаки посчитаны одним запросом на всех (`annotate`);
        # поодиночке — например, письмом или карточкой — спрашиваем базу
        dead = getattr(user, "has_dead_invite", None)
        live = getattr(user, "has_live_invite", None)
        if dead is None or live is None:
            dead = MagicLinkToken.objects.filter(
                email=user.email,
                purpose=LinkPurpose.INVITE,
                used_at__isnull=True,
                expires_at__lt=now,
            ).exists()
            live = MagicLinkToken.objects.filter(
                email=user.email,
                purpose=LinkPurpose.INVITE,
                used_at__isnull=True,
                expires_at__gte=now,
            ).exists()
        return EXPIRED if dead and not live else NO_PASSWORD
    if user.must_change_password:
        if user.temp_password_expires_at is not None and user.temp_password_expires_at < now:
            return EXPIRED
        return WAITING
    return READY
