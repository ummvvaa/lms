"""Завести учётную запись и отправить приглашение — из терминала.

Тот же путь, что и на экране «Пользователи»: запись создаётся без пароля,
человеку уходит одноразовая ссылка, пароль он задаёт себе сам. Пароль
не знает никто, включая того, кто запустил команду.

Нужна для первого администратора в новом контуре — дальше учётные записи
заводятся в интерфейсе. Работает и в бою: ничего лишнего она не даёт,
пароля в ней нет.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts import magic_link
from accounts.models import LinkPurpose, Role, User
from accounts.naming import NameRejected, check_full_name
from accounts.services import create_user


class Command(BaseCommand):
    help = "Заводит пользователя и отправляет ему приглашение установить пароль"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", default="", help="Имя и фамилия — как в школьных списках")
        parser.add_argument("--role", default=Role.STUDENT, choices=[value for value, _ in Role.choices])
        parser.add_argument(
            "--whole-school",
            action="store_true",
            help="Видит всю школу (читает все домены, пишет только свой)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f"Учётная запись {email} уже есть")

        try:
            name = check_full_name(options["name"])
        except NameRejected as error:
            raise CommandError(str(error)) from error

        user = create_user(
            email=email,
            full_name=name,
            role=options["role"],
            sees_whole_school=options["whole_school"],
        )
        magic_link.issue(user.email, purpose=LinkPurpose.INVITE)
        self.stdout.write(self.style.SUCCESS(f"Заведён {user.email} · {user.get_role_display()}"))
        self.stdout.write("Приглашение отправлено. Пароль человек задаёт себе сам по ссылке из письма.")
