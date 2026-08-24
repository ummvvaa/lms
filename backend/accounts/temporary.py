"""Временный пароль: выдача, срок жизни, письмо и выгрузка списка.

Почему временный, а не постоянный. Письмо с паролем остаётся в ящике
навсегда: в поиске, в резервной копии почты, на общем компьютере, куда
ученик заходил один раз. Постоянный пароль в таком письме — открытая
дверь на годы. Временный с обязательной сменой закрывает её: он живёт
ограниченное время и перестаёт работать в тот момент, когда человек
придумал себе свой.

Пароль читаемый: его переписывают с экрана, диктуют по телефону и
набирают руками. Поэтому в алфавите нет символов, которые путают между
собой — единицы и латинской l, нуля и O, пятёрки и S.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from accounts.models import User
from accounts.passwords import set_password

#: Алфавит без похожих друг на друга символов. Здесь нет 0, O, o, 1, l, I,
#: 5, S, 2, Z, 8, B — всё, что путают при переписывании и по телефону.
SAFE_LETTERS = "abcdefghjkmnpqrstuvwxy"
SAFE_DIGITS = "346799"

#: Пароль из трёх групп по четыре: «kanp-4rtq-mwx7». Дефисы не входят
#: в длину для проверки, но помогают не потерять место при наборе.
GROUPS = 3
GROUP_SIZE = 4


def ttl_hours() -> int:
    """Сколько живёт временный пароль. Настраивается школой."""
    return int(getattr(settings, "TEMP_PASSWORD_TTL_HOURS", 72))


def generate() -> str:
    """Случайный читаемый пароль.

    Длина с дефисами — 14 символов, без них 12: обе больше минимальной
    планки школы, так что валидатор его примет при любых настройках.
    """
    alphabet = SAFE_LETTERS + SAFE_DIGITS
    groups = ["".join(secrets.choice(alphabet) for _ in range(GROUP_SIZE)) for _ in range(GROUPS)]
    return "-".join(groups)


def issue(user: User, *, password: str = "") -> str:
    """Выдать пользователю временный пароль и вернуть его открытым текстом.

    Открытый текст возвращается ровно один раз — тому, кто выдал. В базе
    остаётся только хеш: восстановить пароль потом нельзя, можно выпустить
    новый.
    """
    raw = password or generate()
    # `validate=False`: свой алфавит проверку на распространённые пароли
    # проходит всегда, а лишний прогон валидатора здесь ничего не добавит
    set_password(user, raw, validate=False)
    user.must_change_password = True
    user.temp_password_expires_at = timezone.now() + timedelta(hours=ttl_hours())
    user.save(update_fields=["must_change_password", "temp_password_expires_at"])
    return raw


def is_expired(user: User) -> bool:
    """Просрочен ли временный пароль.

    Пароль, который человек уже сменил, временным не считается: срок
    снимается при смене (`accounts.passwords.set_password`).
    """
    if not user.must_change_password or user.temp_password_expires_at is None:
        return False
    return user.temp_password_expires_at <= timezone.now()


def expired_message(user: User) -> str:
    """Что сказать человеку с просроченным паролем. Без подробностей о сроке."""
    return (
        "Временный пароль больше не действует — у него ограниченный срок. "
        "Попросите администратора школы выпустить новый: это одна кнопка"
    )


# --- Письмо ---------------------------------------------------------------


def letter(user: User, password: str) -> tuple[str, str, str]:
    """Тема, текст и HTML письма с временным паролем.

    В письме прямо сказано, что пароль временный и его надо сменить:
    человек, который этого не понял, оставит пароль из письма навсегда.
    """
    from core.i18n import translate

    lang = getattr(user, "language", "ru") or "ru"
    school = settings.SCHOOL_NAME
    address = settings.FRONTEND_BASE_URL
    hours = ttl_hours()

    subject = translate(lang, "доступ в платформу")
    lines = [
        translate(lang, "Вам открыт доступ в платформу школы."),
        "",
        f"{translate(lang, 'Адрес')}: {address}",
        f"{translate(lang, 'Логин')}: {user.email}",
        f"{translate(lang, 'Временный пароль')}: {password}",
        "",
        translate(lang, "При первом входе система попросит придумать свой пароль — это обязательно."),
        translate(lang, "После смены временный пароль перестанет работать.") + " " + render_ttl(lang, hours),
        "",
        school,
    ]
    text = "\n".join(lines) + "\n"

    html = (
        f"<p>{translate(lang, 'Вам открыт доступ в платформу школы.')}</p>"
        f"<p>{translate(lang, 'Адрес')}: <a href=\"{address}\">{address}</a><br />"
        f"{translate(lang, 'Логин')}: <b>{user.email}</b><br />"
        f"{translate(lang, 'Временный пароль')}: <b>{password}</b></p>"
        f"<p>{translate(lang, 'При первом входе система попросит придумать свой пароль — это обязательно.')} "
        f"{translate(lang, 'После смены временный пароль перестанет работать.')} {render_ttl(lang, hours)}</p>"
    )
    return subject, text, html


def render_ttl(lang: str, hours: int) -> str:
    """«Войти по нему нужно в течение 72 часов» — на языке получателя."""
    from core.i18n import render

    return render(lang, "Войти по нему нужно в течение {hours} часов.", hours=hours)


def send_letter(user: User, password: str) -> bool:
    """Отправить письмо с доступом. Возвращает, ушло ли оно."""
    from core import mail

    subject, text, html = letter(user, password)
    return mail.send(to=user.email, subject=subject, text=text, html=html)


# --- Выгрузка списка ------------------------------------------------------

#: Заголовок выгрузки. Порядок колонок из задания: ФИО, логин, пароль.
EXPORT_HEADER = ("ФИО", "Логин", "Временный пароль")


def export_csv(rows: list[dict]) -> str:
    """Список выданных паролей текстом CSV.

    Файл собирается по запросу и на сервере не хранится: список паролей
    в открытом виде не должен лежать нигде дольше, чем нужно, чтобы его
    скачать. Разделитель — точка с запятой: так Excel открывает CSV
    с кириллицей без танцев с мастером импорта.
    """
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(EXPORT_HEADER)
    for row in rows:
        writer.writerow([row.get("full_name", ""), row.get("email", ""), row.get("password", "")])
    # BOM: без него Excel читает файл в своей кодировке и рисует кракозябры
    return "﻿" + buffer.getvalue()
