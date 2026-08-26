"""Завести одноразовые учётные записи для браузерного прогона.

Семь ролей на домене `probe.local`, пароль — из переменной окружения
`PROBE_PASSWORD`. Только при `DEBUG=1`: в боевом контуре команда
отказывается работать, флага «всё равно» нет и не будет.

Перед заведением убирает остатки прошлого прогона: если тот упал
посередине, записи и их сессии не должны доживать до следующего.
Разработческие записи `*@dev.local` команда не трогает никак.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts import probe
from accounts.passwords import PasswordRejected


class Command(BaseCommand):
    help = "Заводит одноразовые записи прогона (только при DEBUG, пароль из PROBE_PASSWORD)"

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "create_probe_users работает только при DEBUG=1: одноразовые записи прогона "
                "в боевом контуре не заводятся"
            )
        password = os.environ.get(probe.PASSWORD_VAR, "")
        if not password:
            raise CommandError(
                f"Не задана переменная {probe.PASSWORD_VAR}. Задайте её в e2e/.env "
                "(прогон передаёт её команде сам) — в репозитории паролей нет"
            )

        leftovers = probe.purge_all()
        if leftovers["users"]:
            self.stdout.write(f"  убраны остатки прошлого прогона: {leftovers['users']} записей")

        try:
            made = probe.create_all(password)
        except PasswordRejected as error:
            raise CommandError(f"{probe.PASSWORD_VAR}: {error}") from error

        for user in made:
            self.stdout.write(f"  заведён: {user.email} · {user.role}")
        self.stdout.write(self.style.SUCCESS(f"Готово: {len(made)} одноразовых записей"))
