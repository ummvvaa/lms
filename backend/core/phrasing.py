"""Текст с числами, который собирает сервер, — на языке ответа.

Дайджест и сообщения отдаются фронту готовыми строками, поэтому формы слова
при числе и перечисления живут здесь, а не в компоненте. «У 1 учеников
обновился балл» читается как сбой перевода, а таких чисел в сводке много.

Формы — одной строкой перевода через черту, как на фронте:
`tn(n, "{n} урок|{n} урока|{n} уроков")`. Русских форм три (1, 2, 5),
в переводе на казахский одна («{n} сабақ»: после числа существительное
не меняется), на английский две (one|other). Форму выбирает язык ответа.
"""

from __future__ import annotations

from collections.abc import Sequence

from django.utils import translation
from django.utils.translation import gettext


def _form(number: int, forms: str) -> str:
    """Форма из «один|два|пять» (или перевода) для числа на активном языке."""
    parts = forms.split("|")
    if len(parts) == 1:
        return parts[0]
    lang = (translation.get_language() or "ru").split("-")[0]
    n = abs(int(number))
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            index = 0
        elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            index = 1
        else:
            index = 2
    else:
        index = 0 if n == 1 else 1
    return parts[min(index, len(parts) - 1)]


def _joined(forms: str | Sequence[str]) -> str:
    return forms if isinstance(forms, str) else "|".join(forms)


def plural(number: int, forms: str | Sequence[str]) -> str:
    """Слово в нужной форме без числа: `plural(n, "ученик|ученика|учеников")`."""
    return _form(number, gettext(_joined(forms)))


def counted(number: int, forms: str | Sequence[str]) -> str:
    """«3 ученика» — число вместе со словом в нужной форме."""
    return f"{number} {plural(number, forms)}"


def tn(number: int, forms: str, **params: object) -> str:
    """Фраза с числом: `tn(n, "{n} урок|{n} урока|{n} уроков")`; `{n}` — само число."""
    return _form(number, gettext(forms)).format(n=number, **params)


def people(number: int) -> str:
    """«трое учеников» для маленьких чисел по-русски, «7 учеников» для больших."""
    lang = (translation.get_language() or "ru").split("-")[0]
    collective = {
        1: "один ученик",
        2: "двое учеников",
        3: "трое учеников",
        4: "четверо учеников",
    }  # i18n-skip: только русский
    if lang == "ru" and number in collective:
        return collective[number]
    return tn(number, "{n} ученик|{n} ученика|{n} учеников")


def listing(parts: Sequence[str], *, last: str | None = None) -> str:
    """«а, б и в» — перечисление с союзом языка перед последним."""
    items = [str(p) for p in parts if p]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    conjunction = last if last is not None else gettext("и")
    return ", ".join(items[:-1]) + f" {conjunction} " + items[-1]


def days_left(number: int) -> str:
    """«через 5 дней», «завтра», «сегодня», «просрочен на 2 дня»."""
    if number < 0:
        return tn(-number, "просрочен на {n} день|просрочен на {n} дня|просрочен на {n} дней")
    if number == 0:
        return gettext("сегодня")
    if number == 1:
        return gettext("завтра")
    return tn(number, "через {n} день|через {n} дня|через {n} дней")


def until(moment) -> str:
    """«13.09.2026, 11:00» — срок, когда он у человека перед глазами.

    С фазы 69 сроки пишутся датой, а не длительностью: «действует 2880
    минут» человек в уме не переводит, а «до 13 сентября, 11:00» видит
    сразу. Время — местное: сервер живёт по Алматы, и получатель тоже.
    """
    from django.utils import timezone

    if not moment:
        return ""
    if isinstance(moment, str):
        # из браузера срок возвращается строкой: выгрузка собирается
        # из тех же строк, что экран показал после выдачи
        from django.utils.dateparse import parse_datetime

        moment = parse_datetime(moment)
        if moment is None:
            return ""
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)
    # по-английски день отделяется косой чертой, как в `en-GB` на фронте
    pattern = "%d/%m/%Y, %H:%M" if (translation.get_language() or "ru").startswith("en") else "%d.%m.%Y, %H:%M"
    return timezone.localtime(moment).strftime(pattern)
