"""Показать токен последней одноразовой ссылки. Только при DEBUG.

В контуре разработки почтового сервера нет: письма уходят в консоль.
Браузерным проверкам нужно пройти путь «пригласили → поставил пароль»
целиком, и токен они берут отсюда, а не из служебной ручки в API —
лишней двери в аутентификации быть не должно.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import MagicLinkToken, User


class Command(BaseCommand):
    help = "Печатает токен последней ссылки для почты (только при DEBUG)"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument(
            "--require-password-change",
            action="store_true",
            help="Вместо токена: пометить, что пользователю надо сменить пароль",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("dev_link работает только при DEBUG=1")

        email = options["email"].strip().lower()

        if options["require_password_change"]:
            updated = User.objects.filter(email__iexact=email).update(must_change_password=True)
            if not updated:
                raise CommandError(f"Пользователь {email} не найден")
            self.stdout.write("ok")
            return

        record = MagicLinkToken.objects.filter(email=email, used_at__isnull=True).order_by("-created_at").first()
        if record is None:
            raise CommandError(f"Действующих ссылок для {email} нет")

        # сам токен в базе не хранится — только хеш; для отладки держим
        # соответствие в кэше на время жизни ссылки
        from django.core.cache import cache

        token = cache.get(f"dev-link:{record.token_hash}")
        if not token:
            raise CommandError("Токен не найден в кэше отладки — ссылка выпущена не этим процессом")
        self.stdout.write(token)
