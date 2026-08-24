"""Кто что видит в разделе материалов.

Правило одно и живёт здесь: ученик вне олимпиадной группы раздела
не видит вовсе. Не «видит пустой список» и не «получает 403» — 404,
как будто адреса нет. По 403 понятно, что раздел существует и кого-то
туда пускают, а это уже сведения о других детях.

Право отбирать в группу берётся из реестра доменов, а не пишется здесь
второй раз (инвариант №2).
"""

from __future__ import annotations

from rest_framework.exceptions import NotFound

from core.domains import ROLE_STUDENT, can_write
from students.models import Student

#: поле-признак в реестре: им владеет домен `talent`
GROUP_FIELD = ("students.Student", "in_olympiad_group")


def keeps_the_group(user) -> bool:
    """Кто отбирает в олимпиадную группу и модерирует материалы."""
    return can_write(getattr(user, "role", ""), *GROUP_FIELD)


def student_of(user) -> Student | None:
    return getattr(user, "student", None)


def in_group(user) -> bool:
    """Ученик из олимпиадной группы."""
    student = student_of(user)
    return student is not None and student.in_olympiad_group


def has_access(user) -> bool:
    """Пускать ли в раздел вообще.

    С фазы 26 раздел видят двое: директор талантов — он его модерирует —
    и ученик, отобранный в олимпиадную группу. Остальным директорам
    и администратору там смотреть нечего: это разбор заданий олимпиад,
    а не сведения об учениках, и лишний зритель тут ничего не решает.
    """
    if getattr(user, "role", "") == ROLE_STUDENT:
        return in_group(user)
    return keeps_the_group(user)


def require_access(user) -> None:
    """404 вместо 403: раздела для этого человека просто нет."""
    if not has_access(user):
        raise NotFound("Страница не найдена")
