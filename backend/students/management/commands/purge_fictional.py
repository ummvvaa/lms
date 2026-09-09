"""Вычистить вымышленных учеников и одноразовые записи прогона.

Единственное место, где ученик удаляется физически, — поэтому две
предохранительные скобы: `--yes` всегда, а на бою (DEBUG выключен)
ещё `--production`. `--dry-run` печатает, что уйдёт, и ничего не трогает.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from students import fictional


class Command(BaseCommand):
    help = (
        "Удаляет вымышленных учеников со всем, что на них ссылается, и probe-аккаунты (--yes; на бою ещё --production)"
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Показать, что удалится, и выйти")
        parser.add_argument("--yes", action="store_true", help="Подтвердить удаление")
        parser.add_argument(
            "--production",
            action="store_true",
            help="Второе подтверждение при выключенном DEBUG: удаление на бою",
        )

    def handle(self, *args, **options):
        outcome = fictional.plan()
        self.stdout.write("Уйдёт насовсем:")
        for line in outcome.lines():
            self.stdout.write(f"  {line}")
        if outcome.names:
            self.stdout.write("  Почты (первые 50): " + ", ".join(outcome.names))

        if options["dry_run"]:
            self.stdout.write("Сухой прогон — ничего не удалено")
            return
        if not options["yes"]:
            raise CommandError("Удаление требует --yes (сначала посмотрите --dry-run)")
        if not settings.DEBUG and not options["production"]:
            raise CommandError("DEBUG выключен: это бой. Удаление на бою требует ещё --production")

        fictional.purge()
        self.stdout.write(
            self.style.SUCCESS(f"Удалено учеников: {outcome.students}, записей прогона: {outcome.probe_accounts}")
        )
