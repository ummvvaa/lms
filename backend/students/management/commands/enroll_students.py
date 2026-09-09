"""Завести учеников списком из файла — тем же путём, что экран «Пользователи».

Файл с онбординга (ФИО, почта, класс, группа) проходит через тот же
`students.enrollment`: разбор, предпросмотр, заведение карточки, учётной
записи и временного пароля. Команда ничего не делает по-своему — иначе
экран и терминал разошлись бы в первый же учебный год.

Пароли выдаются один раз: файлом `--out` (CSV: ФИО, почта, пароль),
как на экране их показывают один раз. На сервере они не хранятся.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from students.enrollment import build_preview, enroll
from students.import_service import read_table


class Command(BaseCommand):
    help = "Заводит учеников из CSV/XLSX через `students.enrollment`; пароли — в файл --out"

    def add_arguments(self, parser):
        parser.add_argument("path", help="CSV или XLSX: ФИО, почта, класс, группа")
        parser.add_argument("--out", default="", help="Куда сложить временные пароли (CSV)")
        parser.add_argument("--dry-run", action="store_true", help="Только предпросмотр")
        parser.add_argument("--no-mail", action="store_true", help="Не отправлять письма с паролями")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"Файла {path} нет")
        # `read_table` смотрит на расширение, поэтому файл читается в память
        # под своим именем — как загруженный с экрана
        buffer = io.BytesIO(path.read_bytes())
        buffer.name = path.name
        header, rows = read_table(buffer)
        preview = build_preview(header=header, rows=rows)

        self.stdout.write(preview.detail())
        for row in preview.broken:
            self.stdout.write(self.style.WARNING(f"  строка {row.number}: {row.reason}"))
        for row in preview.existing:
            self.stdout.write(f"  строка {row.number}: {row.email} — уже заведён, пропущен")
        if options["dry_run"]:
            self.stdout.write("Сухой прогон — ничего не заведено")
            return
        if not preview.ready:
            self.stdout.write("Заводить нечего")
            return

        with transaction.atomic():
            outcome = enroll(
                rows=[row.as_dict() for row in preview.ready],
                actor=None,
                send_mail=not options["no_mail"],
            )
        self.stdout.write(self.style.SUCCESS(outcome["detail"]))

        if options["out"] and outcome["rows"]:
            out = Path(options["out"])
            with out.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["ФИО", "Почта", "Временный пароль"])
                for row in outcome["rows"]:
                    writer.writerow([row["full_name"], row["email"], row["password"]])
            self.stdout.write(f"Пароли сложены в {out} — выдайте и удалите файл")
