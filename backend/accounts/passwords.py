"""Правила паролей и ограничение попыток входа.

Требования к паролю сознательно скромные и понятные: длина, отсутствие
в списке распространённых и несовпадение с почтой. Проверки, которые
человек не может объяснить себе сам, приводят к паролю на стикере.

Блокировка считается по журналу `LoginAttempt`, а не по счётчику в кэше:
после перезапуска контейнера перебор не должен начинаться с чистого листа.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import LoginAttempt

#: Минимальная длина. В настройках — чтобы школа могла поднять планку без выката.
MIN_LENGTH = 10


def min_length() -> int:
    return int(getattr(settings, "PASSWORD_MIN_LENGTH", MIN_LENGTH))


#: Сколько неудач подряд можно допустить до первой блокировки учётной записи.
#: Намеренно не в настройках: перебор по конкретному человеку должен
#: ловиться одинаково в любой школе (фаза 36 порог по записи не смягчает).
FAILURES_BEFORE_LOCK = 5

#: Для адреса порог выше и живёт в настройках: за одним школьным IP сидит
#: вся школа. Умолчание — 100 за час — из расчёта на 250 человек за одним
#: адресом: утренний вход с опечатками у трети из них даёт около сотни
#: неудач, а перебор с одного внешнего адреса всё равно упирается
#: в порог по записи (5), а не в этот.
DEFAULT_ADDRESS_FAILURES = 100


def address_threshold() -> int:
    return int(getattr(settings, "LOGIN_IP_FAILURES", DEFAULT_ADDRESS_FAILURES))


def trusted_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Адреса и подсети, для которых блокировка по адресу не действует.

    Школьный адрес попадает сюда, и один забывчивый ученик перестаёт
    запирать остальных. Порог по учётной записи для них действует как
    обычно. Кривая запись в настройке пропускается, а не роняет вход.
    """
    out = []
    for raw in getattr(settings, "LOGIN_TRUSTED_NETWORKS", []) or []:
        try:
            out.append(ipaddress.ip_network(str(raw).strip(), strict=False))
        except ValueError:
            continue
    return out


def is_trusted(ip: str | None) -> bool:
    """Адрес из доверенной сети: блокировка по адресу к нему не применяется."""
    if not ip:
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in trusted_networks())


#: Нарастающая задержка: 6-я неудача — минута, дальше удвоение до потолка.
FIRST_LOCK = timedelta(minutes=1)
MAX_LOCK = timedelta(minutes=60)

#: За какое окно считаем неудачи. Старше — уже не серия, а забытый пароль.
WINDOW = timedelta(hours=1)


class PasswordRejected(ValueError):
    """Пароль не принят. Текст пригоден для показа человеку."""


def validate_password(password: str, *, email: str = "") -> None:
    """Проверить пароль по правилам школы. Молчит, если всё в порядке."""
    limit = min_length()
    if len(password) < limit:
        raise PasswordRejected(f"Пароль должен быть не короче {limit} символов")

    local_part = email.split("@")[0].strip().lower()
    lowered = password.strip().lower()
    if email and (lowered == email.strip().lower() or (local_part and lowered == local_part)):
        raise PasswordRejected("Пароль не должен совпадать с почтой")

    try:
        CommonPasswordValidator().validate(password)
    except ValidationError as error:
        raise PasswordRejected("Такой пароль слишком распространён — придумайте другой") from error


def _wait_phrase(seconds: int) -> str:
    """«через 3 мин», «через 1 ч 12 мин» — по-человечески, без секунд."""
    minutes = max(1, -(-seconds // 60))
    if minutes < 60:
        return f"через {minutes} мин"
    hours, rest = divmod(minutes, 60)
    return f"через {hours} ч {rest} мин" if rest else f"через {hours} ч"


@dataclass(frozen=True)
class Lock:
    """Блокировка: сколько ждать, из-за чего и кто в ней."""

    seconds: int
    scope: str  # "account" | "address"
    #: почта или адрес, по которым она считается
    value: str = ""
    failures: int = 0

    @property
    def message(self) -> str:
        """Отказ объясняет, что случилось, когда откроется и к кому идти.

        Раньше человек видел «попробуйте через 37 мин» и не знал, что делать;
        снять блокировку может администратор школы, и об этом сказано прямо.
        """
        wait = _wait_phrase(self.seconds)
        if self.scope == "account":
            return (
                f"Слишком много попыток входа в эту учётную запись. Вход откроется {wait}. "
                "Если это были не вы — обратитесь к администратору школы"
            )
        return (
            f"Слишком много попыток входа с этого адреса. Вход откроется {wait} — "
            "обратитесь к администратору школы, он снимает блокировку сразу"
        )

    def as_dict(self) -> dict:
        return {
            "scope": self.scope,
            "value": self.value,
            "failures": self.failures,
            "seconds": self.seconds,
            "unlock_at": (timezone.now() + timedelta(seconds=self.seconds)).isoformat(),
            "message": self.message,
        }


def _lock_for(failures: int, threshold: int = FAILURES_BEFORE_LOCK) -> timedelta | None:
    """Задержка после N неудач подряд: до порога можно, дальше удвоение."""
    if failures < threshold:
        return None
    steps = failures - threshold
    delay = FIRST_LOCK * (2**steps)
    return min(delay, MAX_LOCK)


def _recent_failures(**filters) -> list[LoginAttempt]:
    """Неудачи подряд: серия обрывается на первом удачном входе.

    Снятые администратором попытки (`cleared_at`) в серию не входят:
    так снятие блокировки и работает — журнал остаётся, счёт обнуляется.
    """
    since = timezone.now() - WINDOW
    attempts = list(
        LoginAttempt.objects.filter(created_at__gte=since, cleared_at__isnull=True, **filters).order_by("-created_at")[
            :500
        ]
    )
    series: list[LoginAttempt] = []
    for attempt in attempts:
        if attempt.successful:
            break
        series.append(attempt)
    return series


def _lock_of(scope: str, value: str, series: list[LoginAttempt], threshold: int) -> Lock | None:
    delay = _lock_for(len(series), threshold)
    if delay is None:
        return None
    unlock_at = series[0].created_at + delay
    remaining = (unlock_at - timezone.now()).total_seconds()
    if remaining <= 0:
        return None
    return Lock(seconds=int(remaining), scope=scope, value=value, failures=len(series))


def check_lock(*, email: str, ip: str | None) -> Lock | None:
    """Не пора ли отказать, не проверяя пароль вовсе.

    Адрес из доверенной сети по адресу не блокируется — только по записи.
    """
    email = email.strip().lower()
    lock = _lock_of("account", email, _recent_failures(email=email), FAILURES_BEFORE_LOCK)
    if lock is not None:
        return lock
    if ip and not is_trusted(ip):
        return _lock_of("address", ip, _recent_failures(ip=ip), address_threshold())
    return None


def current_locks() -> list[Lock]:
    """Все действующие блокировки — для экрана администратора.

    Считаются тем же кодом, что и отказ на входе: список не может
    разойтись с тем, что видит человек на форме.
    """
    since = timezone.now() - WINDOW
    # `order_by()` обязателен: с `ordering = -created_at` из Meta `distinct()`
    # на `values_list` включает время в SELECT DISTINCT, и одна запись
    # приходит столько раз, сколько у неё неудач — браузер это и поймал
    recent = LoginAttempt.objects.filter(created_at__gte=since, successful=False, cleared_at__isnull=True).order_by()
    locks: list[Lock] = []
    for email in recent.exclude(email="").values_list("email", flat=True).distinct()[:200]:
        lock = _lock_of("account", email, _recent_failures(email=email), FAILURES_BEFORE_LOCK)
        if lock is not None:
            locks.append(lock)
    for ip in recent.exclude(ip__isnull=True).values_list("ip", flat=True).distinct()[:200]:
        if is_trusted(ip):
            continue
        lock = _lock_of("address", ip, _recent_failures(ip=ip), address_threshold())
        if lock is not None:
            locks.append(lock)
    return sorted(locks, key=lambda lock: -lock.seconds)


def unlock(*, scope: str, value: str, actor=None) -> int:
    """Снять блокировку: пометить неудачи серии снятыми, журнал оставить.

    Удалять строки нельзя — по ним потом разбираются, кто и когда ломился.
    Возвращает, сколько попыток снято.
    """
    since = timezone.now() - WINDOW
    filters = {"email": value.strip().lower()} if scope == "account" else {"ip": value}
    return LoginAttempt.objects.filter(
        created_at__gte=since, successful=False, cleared_at__isnull=True, **filters
    ).update(cleared_at=timezone.now(), cleared_by=actor)


def record_attempt(*, email: str, ip: str | None, successful: bool, reason: str = "", user_agent: str = "") -> None:
    """Записать попытку входа. Пишем и удачные — по ним обрывается серия."""
    LoginAttempt.objects.create(
        email=email.strip().lower(),
        ip=ip,
        successful=successful,
        reason=reason[:64],
        user_agent=(user_agent or "")[:250],
    )


def client_ip(request) -> str | None:
    """Адрес клиента с учётом прокси перед приложением."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def set_password(user, raw_password: str, *, validate: bool = True) -> None:
    """Установить пароль, снять требование его сменить и срок временного.

    Срок снимается здесь же: пароль, который человек придумал себе сам,
    временным больше не считается, и просрочиться ему нечем. Старый
    пароль после этого не работает — хеш перезаписан.
    """
    if validate:
        validate_password(raw_password, email=user.email)
    user.set_password(raw_password)
    user.must_change_password = False
    user.password_changed_at = timezone.now()
    user.temp_password_expires_at = None
    user.save(update_fields=["password", "must_change_password", "password_changed_at", "temp_password_expires_at"])
