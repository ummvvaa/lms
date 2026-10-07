"""Отправка писем: настройки, состояние и общий шаблон.

Без работающей отправки нельзя пригласить 250 учеников: администратору
пришлось бы придумывать и передавать пароль каждому лично, а пароль,
который знает кто-то ещё, — это не пароль.

Отправляем через обычный SMTP сервиса рассылок. На логин и пароль
почтового ящика Microsoft не завязываемся: базовую аутентификацию SMTP
Microsoft отключает, и настройка перестанет работать в тот день, когда
это дойдёт до нашего арендатора.

Если параметры не заданы, письма не пропадают: Django пишет их в лог,
а у администратора висит заметное предупреждение, что приглашения
не уходят. Молчаливая потеря письма выглядит как «ссылка не пришла,
наверное, спам» — и разбираться с этим будет школа, а не мы.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.translation import gettext as _

log = logging.getLogger("mail")

#: Хосты, за которыми стоит базовая аутентификация Microsoft. Работать
#: она может и сегодня, но перестанет без предупреждения с нашей стороны.
MICROSOFT_HOSTS = ("smtp.office365.com", "smtp.outlook.com", "smtp-mail.outlook.com", "smtp.live.com")


#: Бэкенды, которые ничего не отправляют: письма уходят в вывод или в файл.
LOG_ONLY_BACKENDS = ("console", "dummy", "filebased")


def is_configured() -> bool:
    """Настроена ли отправка наружу.

    Консольный, файловый и пустой бэкенды — это «письма в лог», а не
    отправка. SMTP без хоста тоже никуда не уйдёт. Любой другой бэкенд
    (например, подставленный на время проверок) считаем работающим.
    """
    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    if not backend or any(name in backend for name in LOG_ONLY_BACKENDS):
        return False
    if "smtp" in backend:
        return bool(getattr(settings, "EMAIL_HOST", ""))
    return True


def warning() -> str:
    """Что показать администратору. Пустая строка — всё в порядке."""
    if not is_configured():
        return _(
            "Отправка писем не настроена: приглашения и ссылки на смену пароля "
            "никуда не уходят, они пишутся в журнал сервера. Новый человек войти "
            "не сможет. Задайте EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD "
            "и DEFAULT_FROM_EMAIL в deploy/.env.prod и перезапустите сервер"
        )
    host = (getattr(settings, "EMAIL_HOST", "") or "").lower()
    if any(host == known or host.endswith(f".{known}") for known in MICROSOFT_HOSTS):
        return _(
            "Почта настроена на SMTP Microsoft с логином и паролем ящика. "
            "Microsoft отключает такую аутентификацию, и в один день приглашения "
            "перестанут уходить без предупреждения. Переведите отправку "
            "на сервис рассылок: SMTP с ключом API, а не с паролем ящика"
        )
    return ""


def status() -> dict:
    """Состояние отправки для экрана администратора."""
    note = warning()
    return {
        "configured": is_configured(),
        "host": getattr(settings, "EMAIL_HOST", "") or "",
        "port": getattr(settings, "EMAIL_PORT", 0),
        "from_email": getattr(settings, "DEFAULT_FROM_EMAIL", ""),
        "backend": getattr(settings, "EMAIL_BACKEND", ""),
        "warning": note,
        "detail": note
        or _("Письма уходят через {host} от имени {sender}").format(
            host=settings.EMAIL_HOST, sender=settings.DEFAULT_FROM_EMAIL
        ),
    }


def wrap(body_html: str) -> str:
    """Обёртка письма: логотип школы, название и одинаковые поля.

    Цвета здесь заданы числами намеренно: почтовый клиент наших токенов
    не знает, а тему письма выбирает сам.
    """
    school = settings.SCHOOL_NAME
    logo = f"{settings.FRONTEND_BASE_URL}/brand/logo-email.png"
    return (
        '<div style="font-family: -apple-system, Segoe UI, Arial, sans-serif; max-width: 480px; '
        'font-size: 15px; line-height: 1.5">'
        f'<img src="{logo}" alt="{school}" width="120" style="display: block; margin-bottom: 16px" />'
        f"{body_html}"
        f'<p style="color: #767676; font-size: 13px; margin-top: 24px">{school}</p>'
        "</div>"
    )


@dataclass(frozen=True)
class SendResult:
    """Ответ транспорта без тела письма и секретов."""

    sent: bool
    error: str = ""
    uncertain: bool = False


def safe_error(error, *, secrets=()) -> str:
    """Убрать секреты и ссылки даже из ответа SMTP, процитировавшего письмо."""
    value = str(error)
    for secret in (*secrets, getattr(settings, "EMAIL_HOST_PASSWORD", "")):
        if secret:
            value = value.replace(str(secret), _("[скрыто]"))
    value = re.sub(r"https?://\S+", _("[ссылка скрыта]"), value)
    value = re.sub(r"[A-Za-z0-9_-]{32,}", _("[скрыто]"), value)
    return " ".join(value.split())[:500]


def send(*, to: str, subject: str, text: str, html: str = "") -> bool:
    """Совместимый короткий ответ для существующих отправителей."""
    return send_result(to=to, subject=subject, text=text, html=html).sent


def send_result(*, to: str, subject: str, text: str, html: str = "", secrets=()) -> SendResult:
    """Отправить одно письмо. Возвращает, ушло ли оно.

    Ошибка отправки не роняет запрос: человек не должен видеть трассировку
    из-за недоступного почтового сервера. Но и молчать нельзя — пишем
    в журнал с адресом и темой, чтобы потом было что искать.
    """
    try:
        school = settings.SCHOOL_NAME
        message = EmailMultiAlternatives(
            subject=f"{school} — {subject}",
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to],
        )
        if html:
            message.attach_alternative(wrap(html), "text/html")
        if not is_configured():
            log.warning("Отправка писем не настроена — письмо «%s» для %s ушло только в журнал", subject, to)
        sent = message.send(fail_silently=False)
    except Exception as error:
        detail = safe_error(error, secrets=secrets)
        log.error("Письмо «%s» для %s не ушло: %s", subject, to, detail)
        # Ответ SMTP с кодом — отказ; обрыв соединения мог случиться уже
        # после приёма письма. Такой случай до конца суток занимает бюджет.
        return SendResult(False, detail, uncertain=not hasattr(error, "smtp_code"))
    if not is_configured():
        return SendResult(False, _("Отправка писем не настроена"))
    return SendResult(bool(sent), "" if sent else _("Почтовый сервер не принял письмо"))


def send_test(to: str) -> dict:
    """Пробное письмо: проверить настройку, ничего не заводя.

    Отдельная функция, а не «пригласите себя и посмотрите»: приглашение
    заводит учётную запись, а проверка почты не должна ничего создавать.
    """
    # письмо уходит на адрес, который набрал администратор (обычно свой), —
    # поэтому на языке того, кто проверяет почту
    school = settings.SCHOOL_NAME
    greeting = _("Это пробное письмо от платформы {school}.")
    promise = _("Если вы его получили, приглашения и ссылки на смену пароля тоже дойдут.")
    ok = send(
        to=to,
        subject=_("проверка отправки писем"),
        text=f"{greeting.format(school=school)}\n\n{promise}\n",
        html=f"<p>{greeting.format(school=f'<b>{school}</b>')}</p><p>{promise}</p>",
    )
    if not is_configured():
        # консольный бэкенд «отправляет» что угодно и возвращает успех —
        # написать здесь «письмо отправлено» значит соврать администратору
        return {
            "ok": False,
            "configured": False,
            "detail": _("Письмо для {to} ушло только в журнал сервера: отправка не настроена. {warning}").format(
                to=to, warning=warning()
            ),
        }
    return {
        "ok": ok,
        "configured": True,
        "detail": (
            _(
                "Письмо отправлено на {to}. Если через пять минут его нет — проверьте спам "
                "и записи SPF, DKIM и DMARC у домена отправителя"
            ).format(to=to)
            if ok
            else _("Письмо не ушло. Проверьте EMAIL_HOST, порт, логин и пароль — подробности в журнале сервера")
        ),
    }


def connection_check() -> tuple[bool, str]:
    """Достучаться до почтового сервера, ничего не отправляя."""
    if not is_configured():
        return False, warning()
    try:
        connection = get_connection(fail_silently=False)
        connection.open()
        connection.close()
    except Exception as error:  # почтовый сервер отвечает как умеет
        return False, _("Почтовый сервер не отвечает: {error}").format(error=error)
    return True, _("Соединение с {host}:{port} установлено").format(host=settings.EMAIL_HOST, port=settings.EMAIL_PORT)
