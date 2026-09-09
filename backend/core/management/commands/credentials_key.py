"""Ключ шифрования паролей учеников: контрольная запись и проверка (фаза 65)."""

from django.core.management.base import BaseCommand

from core import secrets


class Command(BaseCommand):
    help = "Контрольная запись ключа CREDENTIALS_KEY: создать (--init) или проверить"

    def add_arguments(self, parser):
        parser.add_argument(
            "--init",
            action="store_true",
            help="создать контрольную запись текущим ключом, если её ещё нет",
        )

    def handle(self, *args, **options):
        if options["init"]:
            if not secrets.key_ready():
                self.stderr.write(self.style.ERROR("CREDENTIALS_KEY пуст или не похож на ключ Fernet"))
                raise SystemExit(1)
            row = secrets.ensure_key_check()
            self.stdout.write(self.style.SUCCESS(f"Контрольная запись на месте (от {row.created_at:%d.%m.%Y})"))
        ok, detail = secrets.verify_key()
        if ok:
            self.stdout.write(self.style.SUCCESS(f"Ключ расшифровывает контрольную запись: {detail}"))
            return
        self.stderr.write(self.style.ERROR(f"Ключ не проверен: {detail}"))
        raise SystemExit(1)
