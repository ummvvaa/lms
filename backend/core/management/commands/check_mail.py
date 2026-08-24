"""Проверка отправки писем: настройки, соединение, пробное письмо.

Первое, что делают после выката: `check_mail --to me@school.kz`. Если
письмо не дошло, разбираться надо здесь, а не на живых приглашениях —
человек, которому приглашение не пришло, не сможет войти вовсе.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core import mail


class Command(BaseCommand):
    help = "Проверяет настройку почты и по желанию отправляет пробное письмо"

    def add_arguments(self, parser):
        parser.add_argument("--to", default="", help="Куда отправить пробное письмо")

    def handle(self, *args, **options):
        state = mail.status()
        self.stdout.write("Настройки почты:")
        self.stdout.write(f"  бэкенд: {state['backend']}")
        self.stdout.write(f"  сервер: {state['host'] or '(не задан)'}:{state['port']}")
        self.stdout.write(f"  отправитель: {state['from_email']}")

        if state["warning"]:
            self.stdout.write(self.style.WARNING(state["warning"]))
        else:
            self.stdout.write(self.style.SUCCESS("Отправка настроена"))

        ok, detail = mail.connection_check()
        self.stdout.write(("  " + detail) if ok else self.style.WARNING("  " + detail))

        to = options["to"].strip()
        if not to:
            self.stdout.write("Пробное письмо не отправлялось: укажите --to адрес")
            return

        result = mail.send_test(to)
        style = self.style.SUCCESS if result["ok"] else self.style.WARNING
        self.stdout.write(style(result["detail"]))
