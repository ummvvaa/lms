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

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

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
        return (
            "Отправка писем не настроена: приглашения и ссылки на смену пароля "
            "никуда не уходят, они пишутся в журнал сервера. Новый человек войти "
            "не сможет. Задайте EMAIL_HOST и остальные параметры почты "
            "(см. docs/DEPLOY.md, раздел «Почта»)"
        )
    host = (getattr(settings, "EMAIL_HOST", "") or "").lower()
    if any(host == known or host.endswith(f".{known}") for known in MICROSOFT_HOSTS):
        return (
            "Почта настроена на SMTP Microsoft с логином и паролем ящика. "
            "Microsoft отключает такую аутентификацию, и в один день приглашения "
            "перестанут уходить без предупреждения. Переведите отправку "
            "на сервис рассылок (см. docs/DEPLOY.md, раздел «Почта»)"
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
        "detail": note or f"Письма уходят через {settings.EMAIL_HOST} от имени {settings.DEFAULT_FROM_EMAIL}",
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


def send(*, to: str, subject: str, text: str, html: str = "") -> bool:
    """Отправить одно письмо. Возвращает, ушло ли оно.

    Ошибка отправки не роняет запрос: человек не должен видеть трассировку
    из-за недоступного почтового сервера. Но и молчать нельзя — пишем
    в журнал с адресом и темой, чтобы потом было что искать.
    """
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

    try:
        sent = message.send(fail_silently=False)
    except OSError as error:
        log.error("Письмо «%s» для %s не ушло: %s", subject, to, error)
        return False
    return bool(sent)


def send_test(to: str) -> dict:
    """Пробное письмо: проверить настройку, ничего не заводя.

    Отдельная функция, а не «пригласите себя и посмотрите»: приглашение
    заводит учётную запись, а проверка почты не должна ничего создавать.
    """
    school = settings.SCHOOL_NAME
    ok = send(
        to=to,
        subject="проверка отправки писем",
        text=(
            f"Это пробное письмо от платформы {school}.\n\n"
            f"Если вы его получили, приглашения и ссылки на смену пароля тоже дойдут.\n"
        ),
        html=(
            f"<p>Это пробное письмо от платформы <b>{school}</b>.</p>"
            f"<p>Если вы его получили, приглашения и ссылки на смену пароля тоже дойдут.</p>"
        ),
    )
    if not is_configured():
        # консольный бэкенд «отправляет» что угодно и возвращает успех —
        # написать здесь «письмо отправлено» значит соврать администратору
        return {
            "ok": False,
            "configured": False,
            "detail": (f"Письмо для {to} ушло только в журнал сервера: отправка не настроена. " + warning()),
        }
    return {
        "ok": ok,
        "configured": True,
        "detail": (
            f"Письмо отправлено на {to}. Если через пять минут его нет — проверьте спам "
            f"и раздел «Почта» в docs/DEPLOY.md"
            if ok
            else "Письмо не ушло. Проверьте EMAIL_HOST, порт, логин и пароль — подробности в журнале сервера"
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
        return False, f"Почтовый сервер не отвечает: {error}"
    return True, f"Соединение с {settings.EMAIL_HOST}:{settings.EMAIL_PORT} установлено"
