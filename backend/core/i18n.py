"""Перевод серверных текстов: письма и уведомления.

Язык живёт в профиле получателя (`User.language`), русский — исходный.
Ключ словаря — русский текст как он написан в коде; подстановки вида
`{title}` остаются в шаблоне и заполняются после перевода. Нет перевода —
уходит русский текст, система не падает.

Казахский — черновик, не вычитан носителем языка (см. docs/I18N.md).
"""

from __future__ import annotations

#: Переводы серверных шаблонов. Термины (IELTS, Common App) не переводятся.
SERVER_TEXTS: dict[str, dict[str, str]] = {
    "kk": {
        # письма одноразовых ссылок
        "вход в платформу": "платформаға кіру",
        "доступ в платформу": "платформаға қолжетімділік",
        "сброс пароля": "құпиясөзді қалпына келтіру",
        "Ссылка для входа действует {minutes} минут:": "Кіру сілтемесі {minutes} минут жарамды:",
        "Ссылка для установки пароля действует {minutes} минут:": (
            "Құпиясөзді орнату сілтемесі {minutes} минут жарамды:"
        ),
        "Ссылка для смены пароля действует {minutes} минут:": ("Құпиясөзді өзгерту сілтемесі {minutes} минут жарамды:"),
        # уведомления
        "{who} загрузил материал «{title}» — ждёт проверки": ("{who} «{title}» материалын жүктеді — тексеруді күтуде"),
        "Ваш материал «{title}» одобрен и появился в библиотеке": (
            "Сіздің «{title}» материалыңыз мақұлданып, кітапханада пайда болды"
        ),
        "По вашему запросу «{topic}» появился материал «{title}»": (
            "Сіздің «{topic}» сұранысыңыз бойынша «{title}» материалы пайда болды"
        ),
        "Материал «{title}» не прошёл проверку: {reason}": ("«{title}» материалы тексеруден өтпеді: {reason}"),
        "{who} оставил вопрос под вашим материалом «{title}»": (
            "{who} сіздің «{title}» материалыңыздың астына сұрақ қалдырды"
        ),
        "{who} оставил вопрос под материалом «{title}»": ("{who} «{title}» материалының астына сұрақ қалдырды"),
        "Жалоба на {what} под «{title}»: {reason}": "«{title}» астындағы {what} туралы шағым: {reason}",
        "комментарий": "пікірге",
        "материал": "материалға",
    },
    "en": {
        "вход в платформу": "platform sign-in",
        "доступ в платформу": "platform access",
        "сброс пароля": "password reset",
        "Ссылка для входа действует {minutes} минут:": "The sign-in link is valid for {minutes} minutes:",
        "Ссылка для установки пароля действует {minutes} минут:": (
            "The password setup link is valid for {minutes} minutes:"
        ),
        "Ссылка для смены пароля действует {minutes} минут:": (
            "The password change link is valid for {minutes} minutes:"
        ),
        "{who} загрузил материал «{title}» — ждёт проверки": (
            "{who} uploaded the material “{title}” — awaiting review"
        ),
        "Ваш материал «{title}» одобрен и появился в библиотеке": (
            "Your material “{title}” was approved and appeared in the library"
        ),
        "По вашему запросу «{topic}» появился материал «{title}»": ("Your request “{topic}” got a material: “{title}”"),
        "Материал «{title}» не прошёл проверку: {reason}": ("The material “{title}” did not pass review: {reason}"),
        "{who} оставил вопрос под вашим материалом «{title}»": ("{who} left a question under your material “{title}”"),
        "{who} оставил вопрос под материалом «{title}»": ("{who} left a question under the material “{title}”"),
        "Жалоба на {what} под «{title}»: {reason}": "A complaint about a {what} under “{title}”: {reason}",
        "комментарий": "comment",
        "материал": "material",
    },
}


def translate(lang: str, text: str) -> str:
    """Перевод по исходному русскому тексту. Нет перевода — исходный текст."""
    return SERVER_TEXTS.get(lang, {}).get(text, text)


def render(lang: str, template: str, **params: object) -> str:
    """Перевести шаблон и подставить значения."""
    text = translate(lang, template)
    if params:
        text = text.format(**params)
    return text
