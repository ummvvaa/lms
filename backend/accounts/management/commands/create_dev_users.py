"""Разработческие учётные записи всех ролей.

Пароли берутся из переменных окружения и в репозиторий не попадают:
файла со списком паролей у проекта нет.

Команда работает только при `DEBUG=True` и отказывается запускаться
в боевом контуре — без исключений и без флага «всё равно запустить».
Учётные записи школы заводит администратор через интерфейс, и пароль
владелец задаёт себе сам по одноразовой ссылке.

Отключённую запись команда не включает обратно: если администратор
убрал разработческие записи в архив, повторный запуск (по привычке,
из скрипта, из документации) не должен молча открыть им дверь. Вернуть
их можно только явным ключом `--force`.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Identity, IdentityProvider, Role, User
from accounts.naming import NameRejected, check_full_name
from accounts.passwords import PasswordRejected, set_password

#: Роль → переменная окружения с паролем. Имена без пометок вроде
#: «(тест)» и «(разработка)»: такое имя видно в шапке, в журнале правок
#: и в письмах, а отличить эти записи от настоящих потом нечем. Контур
#: разработки отличается доменом почты `@dev.local`, а не именем.
ACCOUNTS: tuple[tuple[str, str, str, str], ...] = (
    ("student@dev.local", Role.STUDENT, "DEV_STUDENT_PASSWORD", "Ученик"),
    ("behavior@dev.local", Role.DIRECTOR_BEHAVIOR, "DEV_BEHAVIOR_PASSWORD", "Салтанат"),
    ("admission@dev.local", Role.DIRECTOR_ADMISSION, "DEV_ADMISSION_PASSWORD", "Асем"),
    ("exam@dev.local", Role.DIRECTOR_EXAM, "DEV_EXAM_PASSWORD", "Кымбат"),
    ("talent@dev.local", Role.DIRECTOR_TALENT, "DEV_TALENT_PASSWORD", "Арман"),
    ("sport@dev.local", Role.DIRECTOR_SPORT, "DEV_SPORT_PASSWORD", "Нурлыбек"),
    ("admin@dev.local", Role.ADMIN, "DEV_ADMIN_PASSWORD", "Администратор"),
)


class Command(BaseCommand):
    help = "Создаёт учётные записи всех ролей с паролями из окружения (только при DEBUG)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Включить обратно разработческие записи, которые были отключены и убраны в архив",
        )

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

        skipped: list[str] = []
        for email, role, var, full_name in ACCOUNTS:
            # пометка «тест» в имени запрещена и здесь: команда заводит
            # такие же учётные записи, как интерфейс администратора
            try:
                check_full_name(full_name)
            except NameRejected as error:
                raise CommandError(f"{email}: {error}") from error
            password = os.environ[var]
            user, created = User.objects.get_or_create(email=email, defaults={"role": role, "full_name": full_name})
            if not created and not user.is_active and not options["force"]:
                # запись отключили намеренно — включать её обратно без
                # явного ключа нельзя, иначе архив держится до первого
                # запуска команды по привычке
                skipped.append(email)
                self.stdout.write(f"  пропущен: {email} · отключён, без --force не включается")
                continue
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

        done = len(ACCOUNTS) - len(skipped)
        self.stdout.write(self.style.SUCCESS(f"Готово: {done} учётных записей"))
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"Отключённых записей не тронуто: {len(skipped)}. "
                    "Чтобы вернуть их, запустите команду с ключом --force"
                )
            )
