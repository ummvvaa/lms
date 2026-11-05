"""Задать места секций разом из файла: `manage.py set_section_locations <csv> [--dry-run]`.

Строка файла — «название секции; широта; долгота; радиус». Радиус можно
не писать: тогда действует правило школы «Радиус отметки по геолокации».
Секция ищется по точному названию среди действующих; ненайденные выводятся
списком, новых секций команда не создаёт. Первая строка с заголовками
пропускается. Правка каждой секции — в журнал изменений с источником «импорт».
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.domains import Source
from sport import printed, services
from sport.models import Section


def _number(raw: str) -> Decimal:
    """Число из ячейки: Excel в русской раскладке пишет дробную часть через запятую."""
    return Decimal(raw.strip().replace(",", "."))


def _read(path: Path) -> list[list[str]]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise CommandError("Файл не читается: нужна кодировка UTF-8 или Windows-1251")
    return [[cell.strip() for cell in row] for row in csv.reader(text.splitlines(), delimiter=";") if any(row)]


class Command(BaseCommand):
    help = "Задать координаты и радиус секций из CSV «название; широта; долгота; радиус»"

    def add_arguments(self, parser):
        parser.add_argument("csv", help="путь к файлу CSV с разделителем «;»")
        parser.add_argument("--dry-run", action="store_true", help="только показать, что изменится")

    def handle(self, *args, **options):
        path = Path(options["csv"])
        if not path.is_file():
            raise CommandError(f"Файла нет: {path}")
        rows = _read(path)
        changed: list[str] = []
        same: list[str] = []
        missing: list[str] = []
        broken: list[str] = []
        with transaction.atomic():
            for number, row in enumerate(rows, start=1):
                if len(row) < 3:
                    broken.append(f"строка {number}: нужно «название; широта; долгота; радиус»")
                    continue
                title, latitude, longitude = row[0], row[1], row[2]
                radius = row[3] if len(row) > 3 else ""
                try:
                    point = printed.check_point(_number(latitude), _number(longitude))
                except InvalidOperation:
                    if number == 1:
                        continue  # строка заголовков
                    broken.append(f"строка {number}, «{title}»: широта и долгота — числа")
                    continue
                except services.Refused as error:
                    broken.append(f"строка {number}, «{title}»: {error}")
                    continue
                try:
                    radius_m = printed.check_radius(radius)
                except services.Refused as error:
                    broken.append(f"строка {number}, «{title}»: {error}")
                    continue
                found = list(Section.objects.filter(title=title)[:2])
                if not found:
                    missing.append(title)
                    continue
                if len(found) > 1:
                    broken.append(f"строка {number}, «{title}»: секций с таким названием несколько")
                    continue
                section = found[0]
                if printed.set_location(section, point=point, radius_m=radius_m, actor=None, source=Source.IMPORT):
                    radius_words = f"{radius_m} м" if radius_m else f"{printed.default_radius()} м по правилу школы"
                    changed.append(f"{title}: {printed.point_words(section)} · {radius_words}")
                else:
                    same.append(title)
            if options["dry_run"]:
                transaction.set_rollback(True)

        head = "Изменится" if options["dry_run"] else "Задано"
        self.stdout.write(f"{head}: {len(changed)}")
        for line in changed:
            self.stdout.write(f"  {line}")
        if same:
            self.stdout.write(f"Без изменений: {len(same)} — {', '.join(same)}")
        if missing:
            self.stdout.write(self.style.WARNING(f"Секции не найдены ({len(missing)}), ничего не создано:"))
            for title in missing:
                self.stdout.write(f"  {title}")
        if broken:
            self.stdout.write(self.style.ERROR(f"Строки с ошибками ({len(broken)}):"))
            for line in broken:
                self.stdout.write(f"  {line}")
        if options["dry_run"]:
            self.stdout.write("Проверка без записи: в базе ничего не изменено.")
