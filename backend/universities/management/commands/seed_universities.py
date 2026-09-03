"""Стартовый справочник: 20 вузов с программами, требованиями и раундами.

Все записи получают `data_source=seed` и `is_verified=False`: это
заготовка, а не проверенные данные (инвариант №14). Плашку снимает
директор по поступлению, сверившись с сайтом вуза.

Команда открыта в бою намеренно: каталог вузов нужен боевому контуру
с первого дня, и запрета по `DEBUG` у неё нет. Но на непустом
справочнике она в бою останавливается: на вузах висят дедлайны
(инвариант №4), и задвоенный вуз разъехался бы дедлайнами у всех
учеников сразу. Осознанный повтор — флагом `--force`.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from universities.models import University
from universities.seed_catalog import create_seed, seed_stats


class Command(BaseCommand):
    help = "Заводит стартовый справочник из 20 вузов, помеченных «не подтверждено»"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Завести заготовку даже в бою на непустом справочнике",
        )

    def handle(self, *args, **options):
        existing = University.objects.count()
        if existing and not settings.DEBUG and not options["force"]:
            raise CommandError(
                f"В справочнике уже {existing} вузов — в боевом контуре команда на этом "
                "останавливается. На вузах висят дедлайны раундов, и лишняя запись "
                "разъедет сроки сразу у всех учеников. Если заготовку правда нужно "
                "досеять поверх — запустите с флагом --force."
            )

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
