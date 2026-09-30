"""Язык сервера: чей язык и как перевести строку на язык получателя.

Переводы — Django gettext: исходная строка в коде русская, переводы
`locale/kk` и `locale/en` (`makemessages` → `.po` → `compilemessages` → `.mo`).
Язык ответа на запрос включает `core.language.LanguageMiddleware`; письма и
уведомления переводятся на язык получателя (`language_of(user)`) через
`render`/`translate`. Подстановки `{title}` остаются в шаблоне и заполняются
после перевода. Нет перевода — уходит русский текст, система не падает.

Три языка открыты (решение владельца, 30.09.2026); казахский вычитывает
человек по выгрузке `manage.py i18n_export`.

Язык писем и уведомлений — язык интерфейса получателя. Список языков в выборе —
`INTERFACE_LANGUAGES`, один на сервер и интерфейс: фронт получает его в `/auth/me/`.
"""

from __future__ import annotations

import re

from django.utils import translation

#: Языки, которые предлагаются в выборе: добавить язык сюда — значит включить
#: его и в интерфейсе, и в письмах
INTERFACE_LANGUAGES: tuple[str, ...] = ("ru", "kk", "en")


def language_of(user) -> str:
    """Язык писем и уведомлений человека: его язык, если он предлагается; иначе русский."""
    saved = getattr(user, "language", "") or "ru"
    return saved if saved in INTERFACE_LANGUAGES else "ru"


def offered_languages() -> list[dict]:
    """Языки выбора с подписями: каждый подписан сам собой."""
    from accounts.models import Language

    labels = dict(Language.choices)
    return [{"value": code, "label": labels.get(code, code)} for code in INTERFACE_LANGUAGES]


def translate(lang: str, text: str) -> str:
    """Перевод по исходному русскому тексту на язык `lang`. Нет перевода — исходный текст.

    Письмо и уведомление переводятся на языке получателя, а не того, кто
    сделал запрос: поэтому язык передаётся явно, а не берётся активным.
    """
    with translation.override(lang):
        return translation.gettext(text)


def render(lang: str, template: str, **params: object) -> str:
    """Перевести шаблон на язык `lang` и подставить значения `{имя}`.

    Шаблон с формами числа через черту («… {n} день|… {n} дня|… {n} дней»)
    выбирает форму по `n` — по правилам языка получателя.
    """
    text = translate(lang, template)
    if "|" in text and "n" in params:
        from core.phrasing import _form

        with translation.override(lang):
            text = _form(int(params["n"]), text)
    if params:
        text = text.format(**params)
    return text


#: Язык ответа модели ИИ: строка в системный промпт (`suggestions.llm.complete(language=…)`).
#: Инструкция модели, а не текст интерфейса — поэтому на русском, как весь промпт.
ANSWER_LANGUAGE: dict[str, str] = {  # i18n-skip: инструкция модели ИИ, людям не показывается
    "ru": "Отвечай на русском языке.",
    "kk": (
        "Отвечай на казахском языке: литературный казахский, обращение на «Сіз». "
        "IELTS, SAT, GPA, Mock Test, названия вузов и программ не переводи."
    ),
    "en": (
        "Answer in English: plain British school English. "
        "Keep IELTS, SAT, GPA, Mock Test and university and programme names as they are."
    ),
}


def answer_rule(lang: str) -> str:
    """Строка о языке ответа для модели ИИ на языке `lang`."""
    return ANSWER_LANGUAGE.get(lang, ANSWER_LANGUAGE["ru"])


def active_language() -> str:
    """Язык ответа на текущий запрос или язык `override` в фоновой задаче."""
    lang = (translation.get_language() or "ru").split("-")[0]
    return lang if lang in INTERFACE_LANGUAGES else "ru"


#: Процент соответствия — не шанс поступления (инвариант №11) ни на одном языке:
#: фильтр ответа модели ловит запретные слова и по-казахски, и по-английски
BANNED_ADMISSION_WORDS = re.compile(  # i18n-skip: регулярка по ответу модели
    r"шанс|вероятност|прогноз|мүмкіндіг|ықтималдығ|болжам|chance|probabilit|likelihood|predict|forecast",
    re.IGNORECASE,
)
