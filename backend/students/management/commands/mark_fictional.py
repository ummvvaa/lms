"""Пометить учеников вымышленными — по списку почт или по домену.

Для пилотных карточек на проде: владелец передаёт почты, команда ставит
признак `is_fictional`, по которому потом работают `preflight`
и `purge_fictional`. Без `--yes` только показывает, кого нашла.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from students import fictional


class Command(BaseCommand):
    help = "Помечает учеников вымышленными по почтам (--emails, --file) или домену (--domain); без --yes — сухой прогон"

    def add_arguments(self, parser):
        parser.add_argument("--emails", default="", help="Почты через запятую")
        parser.add_argument("--file", default="", help="Файл с почтами, по одной в строке")
        parser.add_argument("--domain", default="", help="Все ученики с почтой в этом домене, например probe.local")
        parser.add_argument("--yes", action="store_true", help="Поставить признак; без флага — только показать")

    def handle(self, *args, **options):
        emails = [e for e in options["emails"].split(",") if e.strip()]
        if options["file"]:
            path = Path(options["file"])
            if not path.exists():
                raise CommandError(f"Файла {path} нет")
            emails += [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        domain = options["domain"].strip()
        if not emails and not domain:
            raise CommandError("Укажите --emails, --file или --domain")

        if not options["yes"]:
            from students.models import Student

            rows = Student.all_objects.none()
            if emails:
                rows = rows | Student.all_objects.filter(email__in=[e.strip().lower() for e in emails])
            if domain:
                rows = rows | Student.all_objects.filter(email__iendswith=f"@{domain.lstrip('@')}")
            found = list(rows.distinct().order_by("email"))
            self.stdout.write(f"Сухой прогон: нашлось {len(found)}, пометить с --yes")
            for row in found:
                mark = "уже помечен" if row.is_fictional else "будет помечен"
                self.stdout.write(f"  {row.email} · {row.full_name} · {mark}")
            missing = sorted({e.strip().lower() for e in emails} - {r.email.lower() for r in found})
            for email in missing:
                self.stdout.write(self.style.WARNING(f"  {email} · не найден"))
            return

        found = fictional.mark(emails=emails, domain=domain)
        self.stdout.write(self.style.SUCCESS(f"Помечено вымышленными: {len(found)}"))
