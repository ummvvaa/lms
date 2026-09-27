"""Учебная часть для браузерного прогона — только структура, без учеников.

Учебный год с четвертями и звонками, предметы, профиль учителя прогона
(`teacher@probe.local`), составы «вся группа» для групп, которые завёл посев
прогона через API, и недельное расписание: три предмета на группу, один из них
у учителя прогона. Отметки и оценки ставит сам сценарий через API — как учитель.
Только при `DEBUG=1`; все записи `is_fictional`, второй учитель — тоже на
домене прогона и уходит вместе с остальными записями `purge_probe_users`.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from academics import seed


class Command(BaseCommand):
    help = "Учебная часть для прогона: год, предметы, составы и расписание учителя прогона (только при DEBUG)"

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_probe_academics работает только при DEBUG=1")
        try:
            outcome = seed.seed_probe()
        except seed.SeedRefused as error:
            raise CommandError(str(error)) from error
        for key, value in outcome.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write(self.style.SUCCESS("Готово: учебная часть прогона посеяна"))
