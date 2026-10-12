"""Учебная часть для браузерного прогона — только структура, без учеников.

Учебный год с четвертями и звонками, предметы, профиль учителя прогона
(`teacher@probe.local`), составы «вся группа» для групп, которые завёл посев
прогона через API, и недельное расписание: три предмета на группу, один из них
у учителя прогона. Отметки и оценки ставит сам сценарий через API — как учитель.
Сверх общих предметов — «Профориентация» (ведётся в LMS, без оценок) у третьего
учителя прогона `career@probe.local` с паролем из `PROBE_PASSWORD` и физкультура
«только расписание» у четвёртого (`schedule@probe.local`) — он один во вкладке
«Только расписание» экрана «Учителя». Только при `DEBUG=1`; все записи `is_fictional`,
второй и третий учителя — тоже на домене прогона и уходят вместе с остальными
записями `purge_probe_users`.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from academics import seed


class Command(BaseCommand):
    help = "Учебная часть для прогона: год, предметы, составы и расписание учителя прогона (только при DEBUG)"

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_probe_academics работает только при DEBUG=1")
        try:
            outcome = seed.seed_probe(password=os.environ.get("PROBE_PASSWORD", ""))
        except seed.SeedRefused as error:
            raise CommandError(str(error)) from error
        for key, value in outcome.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write(self.style.SUCCESS("Готово: учебная часть прогона посеяна"))
