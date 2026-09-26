"""Посев учебной части для разработки — исключение по решению владельца.

Только при `DEBUG=1`; при настоящих учениках в базе отказывается; все
записи `is_fictional`, вычищает их `purge_fictional`. Пароль учителям
и кураторам посева — из `SEED_PASSWORD`, без него вход им закрыт.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from academics import seed


class Command(BaseCommand):
    help = "Сеет вымышленную школу для разработки учебной части (только при DEBUG, все записи is_fictional)"

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_academics работает только при DEBUG=1: в боевом контуре посева нет")
        try:
            outcome = seed.seed(password=os.environ.get("SEED_PASSWORD", ""))
        except seed.SeedRefused as error:
            raise CommandError(str(error)) from error
        for key, value in outcome.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write(self.style.SUCCESS("Готово: учебная часть посеяна"))
