"""Стартовый справочник: 20 вузов с программами, требованиями и раундами.

Все записи получают `data_source=seed` и `is_verified=False`: это
заготовка, а не проверенные данные (инвариант №14). Плашку снимает
директор по поступлению, сверившись с сайтом вуза.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from universities.seed_catalog import create_seed, seed_stats


class Command(BaseCommand):
    help = "Заводит стартовый справочник из 20 вузов, помеченных «не подтверждено»"

    def handle(self, *args, **options):
        created = create_seed()
        stats = seed_stats()
        self.stdout.write(
            self.style.SUCCESS(
                "Заведено: вузов {universities}, программ {programs}, "
                "требований {requirements}, раундов {rounds}".format(**created)
            )
        )
        self.stdout.write(
            f"Всего в стартовом справочнике: {stats['universities']} вузов, "
            f"из них без подтверждения — {stats['unverified']}"
        )
        self.stdout.write("Каждая запись помечена «Данные не подтверждены, проверьте на сайте вуза».")
