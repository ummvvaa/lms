"""Логин вместо почты и поиск учётной записи по тому, чем входят.

У 8–10 нет почты школы: их учётная запись получает логин «имя.фамилия»
латиницей, при совпадении — с цифрой («aliya.akhmetova2»). Латиница
паспортная (ICAO, как в казахстанском паспорте): қ → k, ә → a, ө → o,
ү и ұ → u, х → kh, й → i, ю → iu, я → ia — так ученик пишет своё имя
в документах и не гадает, как его набрать.

Форма входа принимает почту, логин или подтверждённую личную почту —
одно место, `find_user`, решает, чья это учётная запись.
"""

from __future__ import annotations

import re

#: паспортная латиница: русский алфавит и казахские буквы
PASSPORT_LATIN: dict[str, str] = {  # i18n-skip: таблица транслитерации, не текст интерфейса
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "iu",
    "я": "ia",
    "ә": "a",
    "ғ": "g",
    "қ": "k",
    "ң": "n",
    "ө": "o",
    "ұ": "u",
    "ү": "u",
    "һ": "h",
    "і": "i",
}

#: логин без почты — только строчная латиница, цифры, точка и дефис
LOGIN_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")


def latin(text: str) -> str:
    """Имя латиницей: «Әлия-Нұр» → «alia-nur». Пробел пропадает, дефис остаётся."""
    out = []
    for char in (text or "").strip().lower():
        if char in PASSPORT_LATIN:
            out.append(PASSPORT_LATIN[char])
        elif "a" <= char <= "z" or char.isdigit() or char == "-":
            out.append(char)
    return re.sub(r"-{2,}", "-", "".join(out)).strip("-")


def base_login(first_name: str, last_name: str) -> str:
    """«имя.фамилия» латиницей; без имени — одна фамилия, без обоих — «uchenik»."""
    parts = [part for part in (latin(first_name), latin(last_name)) if part]
    return ".".join(parts) or "uchenik"


def make_login(first_name: str, last_name: str, *, taken: set[str] | None = None) -> str:
    """Свободный логин: при совпадении — с цифрой, начиная с 2.

    `taken` — логины, уже выданные в этом же заходе, но ещё не сохранённые:
    два тёзки в одном списке не должны получить один логин.
    """
    from accounts.models import User

    base = base_login(first_name, last_name)
    taken = {value.lower() for value in (taken or set())}
    candidate, number = base, 1
    while candidate in taken or User.objects.filter(login__iexact=candidate).exists():
        number += 1
        candidate = f"{base}{number}"
    return candidate


def normalize(identifier: str) -> str:
    """Как набрали, но без пробелов по краям и в нижнем регистре."""
    return (identifier or "").strip().lower()


def find_user(identifier: str):
    """Учётная запись по почте, логину или подтверждённой личной почте; иначе None."""
    from accounts.models import Identity, IdentityProvider, User

    value = normalize(identifier)
    if not value:
        return None
    if "@" not in value:
        return User.objects.filter(login__iexact=value).first()
    user = User.objects.filter(email__iexact=value).first()
    if user is not None:
        return user
    identity = (
        Identity.objects.filter(provider=IdentityProvider.EMAIL_LINK, email__iexact=value, confirmed_at__isnull=False)
        .select_related("user")
        .first()
    )
    return identity.user if identity else None


def lock_key(identifier: str) -> str:
    """По чему считать неудачи входа: одна серия на учётную запись.

    Иначе пять попыток по логину и пять по почте того же человека дали бы
    десять. Неизвестный идентификатор считается как набранный.
    """
    user = find_user(identifier)
    return user.handle.lower() if user is not None else normalize(identifier)


def address_of(user) -> str:
    """Куда можно написать человеку: почта школы или подтверждённая личная; иначе пусто."""
    from accounts.models import IdentityProvider

    if user.email:
        return user.email
    identity = (
        user.identities.filter(provider=IdentityProvider.EMAIL_LINK, confirmed_at__isnull=False)
        .order_by("-confirmed_at")
        .first()
    )
    return identity.email if identity else ""


def student_archived(user) -> bool:
    """Ученик в архиве — выпуск или удаление: вход ему закрыт, данные остаются."""
    student = getattr(user, "student", None) if getattr(user, "role", "") == "student" else None
    return student is not None and student.archived_at is not None
