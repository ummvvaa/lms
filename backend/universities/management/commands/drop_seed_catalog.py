"""Убрать стартовый справочник целиком.

Удаляет ровно записи с источником `seed`. Вузы, заведённые школой,
остаются на месте — команда нужна как раз для того, чтобы заменить
заготовку файлом от директора по поступлению.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from universities.seed_catalog import SeedInUse, drop_seed


class Command(BaseCommand):
    help = "Удаляет стартовый справочник (записи с источником seed), не трогая заведённое школой"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Удалить, даже если программы стоят в списках учеников — вместе со связями",
        )

    def handle(self, *args, **options):
        # в бою заготовку убирает директор по поступлению кнопкой на экране
        # «Справочник» — с правами и подтверждением; команда из терминала
        # обходит и то, и другое, поэтому при DEBUG=0 не работает (фаза 56)
        if not settings.DEBUG:
            raise CommandError(
                "drop_seed_catalog работает только при DEBUG=1. В боевом контуре стартовый "
                "справочник убирается кнопкой «Удалить стартовый справочник» на экране «Справочник»"
            )
        try:
            stats = drop_seed(force=options["force"])
        except SeedInUse as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"Удалено: вузов {stats['universities']}, программ {stats['programs']}, "
                f"связей со списками учеников {stats['student_links']}"
            )
        )
        if stats["kept_universities"]:
            self.stdout.write(
                f"Оставлено вузов, под которыми школа завела свои программы: {stats['kept_universities']}"
            )
