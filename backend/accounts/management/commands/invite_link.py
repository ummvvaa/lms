"""Свежая ссылка-приглашение для одного человека — прямо в терминал.

Нужна, когда почта ещё не настроена или письмо не дошло, а интерфейс
недоступен. Ссылка равна паролю до первого использования: печатается
она только тому, у кого есть доступ к серверу, и живёт ограниченное время.

Работает и в бою: ничего лишнего команда не даёт — ровно то же самое
администратор видит на экране «Пользователи».
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from accounts import magic_link
from accounts.models import LinkPurpose, User


class Command(BaseCommand):
    help = "Печатает свежую ссылку на установку пароля для указанной почты"

    def add_arguments(self, parser):
        parser.add_argument("email", help="Почта человека, которому нужна ссылка")
        parser.add_argument(
            "--purpose",
            default=LinkPurpose.INVITE,
            choices=[value for value, _ in LinkPurpose.choices],
            help="Назначение ссылки: приглашение, сброс пароля или вход",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(
                f"Учётной записи {email} нет. Заведите её на экране «Пользователи» "
                f"или командой invite_user, а потом возвращайтесь за ссылкой"
            )
        if not user.is_active:
            raise CommandError(f"Учётная запись {email} отключена — сначала включите её")

        purpose = options["purpose"]
        token = magic_link.issue(email, purpose=purpose)
        if not token:
            raise CommandError(f"Ссылку для {email} выпустить не удалось")

        minutes = magic_link.ttl_minutes(purpose)
        self.stdout.write(magic_link.link_for(purpose, token))
        self.stdout.write(
            self.style.WARNING(
                f"Действует {minutes} минут и гаснет после первого использования. "
                f"Передайте её лично: до установки пароля она равна паролю"
            )
        )
