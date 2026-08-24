"""Разработческие учётные записи всех ролей.

Пароли берутся из переменных окружения и в репозиторий не попадают:
файла со списком паролей у проекта нет.

Команда работает только при `DEBUG=True` и отказывается запускаться
в боевом контуре — без исключений и без флага «всё равно запустить».
Учётные записи школы заводит администратор через интерфейс, и пароль
владелец задаёт себе сам по одноразовой ссылке.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Identity, IdentityProvider, Role, User
from accounts.passwords import PasswordRejected, set_password

#: Роль → переменная окружения с паролем.
ACCOUNTS: tuple[tuple[str, str, str, str], ...] = (
    ("student@dev.local", Role.STUDENT, "DEV_STUDENT_PASSWORD", "Ученик (разработка)"),
    ("behavior@dev.local", Role.DIRECTOR_BEHAVIOR, "DEV_BEHAVIOR_PASSWORD", "Салтанат (разработка)"),
    ("admission@dev.local", Role.DIRECTOR_ADMISSION, "DEV_ADMISSION_PASSWORD", "Асем (разработка)"),
    ("exam@dev.local", Role.DIRECTOR_EXAM, "DEV_EXAM_PASSWORD", "Кымбат (разработка)"),
    ("talent@dev.local", Role.DIRECTOR_TALENT, "DEV_TALENT_PASSWORD", "Арман (разработка)"),
    ("sport@dev.local", Role.DIRECTOR_SPORT, "DEV_SPORT_PASSWORD", "Нурлыбек (разработка)"),
    ("admin@dev.local", Role.ADMIN, "DEV_ADMIN_PASSWORD", "Администратор (разработка)"),
)


class Command(BaseCommand):
    help = "Создаёт учётные записи всех ролей с паролями из окружения (только при DEBUG)"

    @transaction.atomic
    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.DEBUG:
            raise CommandError(
                "create_dev_users работает только при DEBUG=1. В боевом контуре учётные записи "
                "заводит администратор на экране «Пользователи»: он создаёт запись и отправляет "
                "ссылку, а пароль владелец задаёт себе сам"
            )

        missing = [var for _, _, var, _ in ACCOUNTS if not os.environ.get(var)]
        if missing:
            raise CommandError(
                "Не заданы переменные с паролями: " + ", ".join(missing) + "\n"
                "Задайте их в deploy/.env — в репозитории паролей нет и быть не должно."
            )

        for email, role, var, full_name in ACCOUNTS:
            password = os.environ[var]
            user, created = User.objects.get_or_create(email=email, defaults={"role": role, "full_name": full_name})
            user.role = role
            user.full_name = full_name
            user.is_active = True
            # у Салтанат нет второй роли: вместо неё флаг «видит всю школу»
            user.sees_whole_school = role == Role.DIRECTOR_BEHAVIOR
            user.is_staff = role == Role.ADMIN
            user.is_superuser = role == Role.ADMIN
            user.save()

            try:
                set_password(user, password)
            except PasswordRejected as error:
                raise CommandError(f"{email}: {error}") from error

            Identity.objects.get_or_create(
                provider=IdentityProvider.PASSWORD,
                email=email,
                defaults={"user": user, "is_primary": True},
            )
            self.stdout.write(f"  {'создан' if created else 'обновлён'}: {email} · {role}")

        self.stdout.write(self.style.SUCCESS(f"Готово: {len(ACCOUNTS)} учётных записей"))
