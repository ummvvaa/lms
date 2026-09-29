"""Ученик по почте или логину — ключ строки в файлах импорта.

У 8–10 почты нет, и строку файла с ними связывает логин учётной записи
(«aigerim.serikova»). Почта и логин равноправны: колонка может называться
«почта ученика» или «логин», значение ищется в обоих.
"""

from __future__ import annotations

from students.models import Student


def key_map() -> dict[str, tuple[int, str]]:
    """Почта и логин (в нижнем регистре) → (id ученика, «Фамилия Имя»)."""
    out: dict[str, tuple[int, str]] = {}
    for pk, email, login, last, first in Student.objects.values_list(
        "pk", "email", "user__login", "last_name", "first_name"
    ):
        name = f"{last} {first}".strip()
        for key in (email, login):
            if key:
                out[key.lower()] = (pk, name)
    return out


def resolve(value: str) -> Student | None:
    """Ученик по почте или логину; не нашёлся — None."""
    from django.db.models import Q

    value = (value or "").strip().lower()
    if not value:
        return None
    return Student.objects.filter(Q(email__iexact=value) | Q(user__login__iexact=value)).first()
