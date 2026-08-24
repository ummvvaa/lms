"""Русский текст, который собирает сервер.

Дайджест и сообщения отдаются фронту готовыми строками, поэтому склонения
числительных и перечисления живут здесь, а не в компоненте. «У 1 учеников
обновился балл» читается как сбой перевода, а таких чисел в сводке много.
"""

from __future__ import annotations

from collections.abc import Sequence

#: «двое», «трое» — про людей это читается живее, чем «2 ученика»
_PEOPLE = {1: "один ученик", 2: "двое учеников", 3: "трое учеников", 4: "четверо учеников"}


def plural(number: int, forms: Sequence[str]) -> str:
    """Форма слова под число: `forms = (ученик, ученика, учеников)`."""
    n = abs(int(number)) % 100
    if 11 <= n <= 14:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def counted(number: int, forms: Sequence[str]) -> str:
    """«3 ученика» — число вместе со склонённым словом."""
    return f"{number} {plural(number, forms)}"


def people(number: int) -> str:
    """«трое учеников» для маленьких чисел, «7 учеников» для больших."""
    if number in _PEOPLE:
        return _PEOPLE[number]
    return counted(number, ("ученик", "ученика", "учеников"))


def listing(parts: Sequence[str], *, last: str = "и") -> str:
    """«а, б и в» — перечисление с человеческим союзом перед последним."""
    items = [p for p in parts if p]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" {last} " + items[-1]


def days_left(number: int) -> str:
    """«через 5 дней», «завтра», «сегодня», «просрочен на 2 дня»."""
    if number < 0:
        return f"просрочен на {counted(-number, ('день', 'дня', 'дней'))}"
    if number == 0:
        return "сегодня"
    if number == 1:
        return "завтра"
    return f"через {counted(number, ('день', 'дня', 'дней'))}"
