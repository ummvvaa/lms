"""Правила паролей и ограничение попыток входа.

Требования к паролю сознательно скромные и понятные: длина, отсутствие
в списке распространённых и несовпадение с почтой. Проверки, которые
человек не может объяснить себе сам, приводят к паролю на стикере.

Блокировка считается по журналу `LoginAttempt`, а не по счётчику в кэше:
после перезапуска контейнера перебор не должен начинаться с чистого листа.
"""

from __future__ import annotations

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
FAILURES_BEFORE_LOCK = 5

#: Для адреса порог выше: за одним школьным IP сидит вся школа, и один
#: человек, забывший пароль, не должен запирать дверь остальным.
FAILURES_BEFORE_ADDRESS_LOCK = 15

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


@dataclass(frozen=True)
class Lock:
    """Блокировка: сколько ждать и из-за чего."""

    seconds: int
    scope: str  # "account" | "address"

    @property
    def message(self) -> str:
        minutes = max(1, round(self.seconds / 60))
        where = "этой учётной записи" if self.scope == "account" else "этого адреса"
        return f"Слишком много неудачных попыток для {where}. Попробуйте через {minutes} мин."


def _lock_for(failures: int, threshold: int = FAILURES_BEFORE_LOCK) -> timedelta | None:
    """Задержка после N неудач подряд: до порога можно, дальше удвоение."""
    if failures < threshold:
        return None
    steps = failures - threshold
    delay = FIRST_LOCK * (2**steps)
    return min(delay, MAX_LOCK)


def _recent_failures(**filters) -> list[LoginAttempt]:
    """Неудачи подряд: серия обрывается на первом удачном входе."""
    since = timezone.now() - WINDOW
    attempts = list(LoginAttempt.objects.filter(created_at__gte=since, **filters).order_by("-created_at")[:50])
    series: list[LoginAttempt] = []
    for attempt in attempts:
        if attempt.successful:
            break
        series.append(attempt)
    return series


def check_lock(*, email: str, ip: str | None) -> Lock | None:
    """Не пора ли отказать, не проверяя пароль вовсе."""
    scopes = [("account", {"email": email.strip().lower()}, FAILURES_BEFORE_LOCK)]
    if ip:
        scopes.append(("address", {"ip": ip}, FAILURES_BEFORE_ADDRESS_LOCK))

    for scope, filters, threshold in scopes:
        series = _recent_failures(**filters)
        delay = _lock_for(len(series), threshold)
        if delay is None:
            continue
        unlock_at = series[0].created_at + delay
        remaining = (unlock_at - timezone.now()).total_seconds()
        if remaining > 0:
            return Lock(seconds=int(remaining), scope=scope)
    return None


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
