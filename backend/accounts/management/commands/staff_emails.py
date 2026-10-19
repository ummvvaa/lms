"""Почты сотрудников из файла школы «№, ФИО, Почта».

Сначала посмотреть, что изменится (ничего не пишет):

    manage.py staff_emails /path/Почты.xlsx

Затем записать тот же план:

    manage.py staff_emails /path/Почты.xlsx --apply

Четыре списка: впишется почта, уже есть, заведётся, не уверен / конфликт.
Писем команда не шлёт — приглашения уходят кнопкой «Выслать письма».
Порядок на проде (файл на сервер → план → --apply) — `docs/DEPLOY.md`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from accounts import staff_emails


class Command(BaseCommand):
    help = "Вписать почты сотрудников из файла школы; новых завести учителями без пароля"

    def add_arguments(self, parser):
        parser.add_argument("path", help="книга xlsx с колонками «ФИО» и «Почта»")
        parser.add_argument("--apply", action="store_true", help="записать план; без ключа — только показать")

    def handle(self, *args, path: str, apply: bool = False, **options):
        try:
            rows, errors = staff_emails.read(path)
        except OSError as error:
            raise CommandError(f"Файл не читается: {error}") from error
        if errors:
            raise CommandError("; ".join(errors))
        result = staff_emails.plan(rows)
        self._print(result)
        if not apply:
            self.stdout.write("Сухой прогон — ничего не изменено.")
            return
        counts = staff_emails.apply(result)
        self.stdout.write(
            self.style.SUCCESS("Записано: почт вписано — {filled}, заведено учителей — {created}.".format(**counts))
        )

    def _print(self, result: staff_emails.Plan) -> None:
        out = self.stdout.write

        def who(user) -> str:
            name = user.full_name or user.handle
            handle = f" ({user.handle})" if user.handle and user.handle != name else ""
            off = "" if user.is_active else "  ← доступ отключён"
            return f"{name}{handle}{off}"

        out(f"Впишется почта ({len(result.fill)}):")
        for item in result.fill:
            out(f"  {item.row.full_name} → {who(item.user)}: {item.row.email}")
        out("")
        out(f"Уже есть ({len(result.same)}):")
        for item in result.same:
            out(f"  {item.row.full_name} → {who(item.user)}")
        out("")
        out(f"Заведётся ({len(result.create)}) — учитель, без пароля, вход по приглашению:")
        for item in result.create:
            out(f"  {item.row.full_name}: {item.row.email}")
        out("")
        out(f"Не уверен / конфликт ({len(result.unsure)}) — не применяется:")
        for item in result.unsure:
            found = ", ".join(f"«{c.user.full_name or c.user.handle}» ({c.score:.2f})" for c in item.candidates)
            tail = f"; кандидаты: {found}" if found else ""
            out(f"  строка {item.row.number} «{item.row.full_name}» ({item.row.email}): {item.why}{tail}")
        out("")
