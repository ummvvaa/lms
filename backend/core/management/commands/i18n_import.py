"""Загрузить вычитанные переводы из xlsx обратно в каталоги.

    python manage.py i18n_import translations.xlsx [--dry-run]

Берутся колонки «Ключ», «Қазақша» и «English» листов «Интерфейс» (словари
фронта) и «Сервер» (каталог Django gettext) таблицы, выгруженной `i18n_export`.
Перевод, у которого сломаны подстановки `{имя}` или формы числа, не
загружается — строка попадает в список отказов с причиной. Ключей, которых
нет в каталоге, команда не заводит: строку добавляет код, а не таблица.
После загрузки серверный каталог компилируется в `.mo`.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from openpyxl import load_workbook

from core import translations

COLUMNS = {"Ключ": "key", "Қазақша": "kk", "English": "en"}


def rows_of(sheet):
    """Строки листа как (номер строки, ключ, {язык: значение})."""
    rows = sheet.iter_rows(values_only=True)
    header = [str(cell or "").strip() for cell in next(rows, ())]
    where = {role: header.index(title) for title, role in COLUMNS.items() if title in header}
    if set(where) != set(COLUMNS.values()):
        raise CommandError("в таблице нет колонок «Ключ», «Қазақша» и «English» — это не выгрузка i18n_export")
    for number, row in enumerate(rows, start=2):
        key = str(row[where["key"]] or "")
        if key:
            yield number, key, {
                lang: "" if row[where[lang]] is None else str(row[where[lang]]) for lang in translations.LANGS
            }


class Command(BaseCommand):
    help = "Загрузить вычитанные переводы из xlsx в словари интерфейса и каталог сервера"

    def add_arguments(self, parser):
        parser.add_argument("file", help="таблица, выгруженная i18n_export")
        parser.add_argument("--dry-run", action="store_true", help="только показать, что изменится")
        parser.add_argument("--frontend-dir", help="папка словарей фронта (по умолчанию I18N_FRONTEND_DIR)")
        parser.add_argument("--locale-dir", help="папка переводов сервера (по умолчанию backend/locale)")

    def handle(self, *args, file: str, dry_run: bool = False, frontend_dir=None, locale_dir=None, **options):
        book = load_workbook(file, read_only=True)
        refused: list[str] = []
        unknown: list[str] = []
        changed = {("Интерфейс", lang): 0 for lang in translations.LANGS} | {
            ("Сервер", lang): 0 for lang in translations.LANGS
        }

        # интерфейс: словари фронта
        dictionaries = translations.read_dictionaries(Path(frontend_dir) if frontend_dir else None)
        plural = translations.plural_keys()
        sheet = book["Интерфейс"] if "Интерфейс" in book.sheetnames else book.worksheets[0]
        for number, key, values in rows_of(sheet):
            if key not in dictionaries["kk"].entries and key not in dictionaries["en"].entries:
                unknown.append(f"Интерфейс, строка {number}: «{key}»")
                continue
            for lang, value in values.items():
                if value == dictionaries[lang].entries.get(key):
                    continue
                problem = translations.check_translation(key, value, is_plural=key in plural)
                if problem:
                    refused.append(f"Интерфейс, строка {number}, {lang}: {problem} — «{value}»")
                    continue
                dictionaries[lang].entries[key] = value
                changed[("Интерфейс", lang)] += 1

        # сервер: каталог gettext
        locale = Path(locale_dir) if locale_dir else None
        catalogs = {}
        if "Сервер" in book.sheetnames:
            catalogs = {lang: translations.read_po(lang, locale) for lang in translations.LANGS}
            index = {
                lang: {entry.msgid: entry for entry in catalog if not entry.obsolete}
                for lang, catalog in catalogs.items()
            }
            for number, key, values in rows_of(book["Сервер"]):
                if key not in index["kk"]:
                    unknown.append(f"Сервер, строка {number}: «{key}»")
                    continue
                for lang, value in values.items():
                    entry = index[lang].get(key)
                    if entry is None or value == entry.msgstr:
                        continue
                    problem = translations.check_translation(key, value, is_plural="|" in key)
                    if problem:
                        refused.append(f"Сервер, строка {number}, {lang}: {problem} — «{value}»")
                        continue
                    entry.msgstr = value
                    if "fuzzy" in entry.flags:
                        entry.flags.remove("fuzzy")
                    changed[("Сервер", lang)] += 1

        if not dry_run:
            for lang in translations.LANGS:
                if changed[("Интерфейс", lang)]:
                    dictionaries[lang].write()
            if any(changed[("Сервер", lang)] for lang in translations.LANGS):
                for catalog in catalogs.values():
                    catalog.save()
                translations.compile_server(locale)
        verb = "Изменится" if dry_run else "Изменено"
        for part in ("Интерфейс", "Сервер"):
            self.stdout.write(f"{verb} ({part}): kk — {changed[(part, 'kk')]}, en — {changed[(part, 'en')]}")
        for line in refused:
            self.stdout.write(f"Не загружено: {line}")
        for line in unknown:
            self.stdout.write(f"Нет в каталоге: {line}")
