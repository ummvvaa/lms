"""`makemessages` проекта: свои слова перевода и без тестов с миграциями.

    python manage.py makemessages -l kk -l en

Строки писем и уведомлений переводятся по языку получателя через
`core.i18n.render(lang, "Шаблон {имя}", …)` и `translate(lang, "…")` — их
второй аргумент тоже строка перевода. Тесты и миграции строк интерфейса
не содержат: их русский текст — проверки и история, не перевод.
"""

from __future__ import annotations

from django.core.management.commands import makemessages

IGNORED = ["*/tests/*", "*/migrations/*", "conftest.py", "staticfiles/*", "media/*", "private/*"]


class Command(makemessages.Command):
    xgettext_options = [
        *makemessages.Command.xgettext_options,
        "--keyword=render:2",
        "--keyword=translate:2",
        "--keyword=tn:2",
        "--keyword=plural:2",
        "--keyword=counted:2",
    ]

    def handle(self, *args, **options):
        options["ignore_patterns"] = list(options.get("ignore_patterns") or []) + IGNORED
        super().handle(*args, **options)
