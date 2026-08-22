"""Разработческие учётные записи всех ролей.

Пароли берутся из переменных окружения и в репозиторий не попадают:
файла со списком паролей у проекта больше нет. Команда работает только
при DEBUG — в боевом контуре учётные записи заводит администратор.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Identity, IdentityProvider, Role, User
from accounts.passwords import PasswordRejected, set_password

#: Роль → переменная окружения с паролем.
ACCOUNTS: tuple[tuple[str, str, str, str], ...] = (
    ("test.student@lms.local", Role.STUDENT, "DEV_STUDENT_PASSWORD", "Тестовый Ученик"),
    ("test.behavior@lms.local", Role.DIRECTOR_BEHAVIOR, "DEV_BEHAVIOR_PASSWORD", "Салтанат (тест)"),
    ("test.admission@lms.local", Role.DIRECTOR_ADMISSION, "DEV_ADMISSION_PASSWORD", "Асем (тест)"),
    ("test.exam@lms.local", Role.DIRECTOR_EXAM, "DEV_EXAM_PASSWORD", "Кымбат (тест)"),
    ("test.talent@lms.local", Role.DIRECTOR_TALENT, "DEV_TALENT_PASSWORD", "Арман (тест)"),
    ("test.sport@lms.local", Role.DIRECTOR_SPORT, "DEV_SPORT_PASSWORD", "Нурлыбек (тест)"),
    ("test.admin@lms.local", Role.ADMIN, "DEV_ADMIN_PASSWORD", "Администратор (тест)"),
)


class Command(BaseCommand):
    help = "Создаёт учётные записи всех ролей с паролями из окружения (только при DEBUG)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-production",
            action="store_true",
            help="Разрешить запуск при DEBUG=0 — только осознанно и на закрытом стенде",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.DEBUG and not options["allow_production"]:
            raise CommandError("create_dev_users работает только при DEBUG=1")

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
