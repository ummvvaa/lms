"""Оставить в LMS предметы, которых нет в Kundelik; остальные — только расписание.

Сначала посмотреть, что изменится (ничего не пишет):

    manage.py keep_subjects --dry-run

Затем записать тот же план:

    manage.py keep_subjects --apply

Предмет, который в LMS называется иначе, добавляется `--title "Название"`.
Порядок на проде (бэкап → dry-run → apply) — `docs/DEPLOY.md`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from academics import keep_subjects
from academics.models import Scheme


class Command(BaseCommand):
    help = "Ведутся в LMS только EEP, GE, SAT, Creative Writing, Профориентация; остальные — только расписание"

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true", help="показать план и ничего не менять")
        mode.add_argument("--apply", action="store_true", help="записать план")
        parser.add_argument("--title", action="append", default=[], help="ещё один предмет, который ведётся в LMS")

    def handle(self, *args, dry_run: bool = False, apply: bool = False, title: list[str], **options):
        result = keep_subjects.plan(title)
        self._print(result)
        if result.missing:
            raise CommandError(
                "Не найдены в LMS: " + ", ".join(result.missing) + ". Уточните название через --title и повторите."
            )
        if dry_run:
            self.stdout.write("Сухой прогон — ничего не изменено.")
            return
        counts = keep_subjects.apply(result)
        self.stdout.write(
            self.style.SUCCESS(
                "Записано: ведутся — {kept}, только расписание — {schedule_only}, "
                "«Только ФО из 10» — {rescheme}, учителей отключено — {disabled}.".format(**counts)
            )
        )

    def _print(self, result: keep_subjects.Plan) -> None:
        out = self.stdout.write
        out("Что искали → что нашлось:")
        for label, hits in result.found:
            names = ", ".join(f"«{s.title}» ({s.code})" for s in hits) or "НЕ НАЙДЕНО"
            out(f"  {label}: {names}")
        out("")
        out(f"Ведутся в LMS ({len(result.keep)}):")
        for row in result.keep:
            now = "" if row.subject.in_lms else "  ← сейчас «только расписание»"
            out(
                f"  {row.subject.title}: журналов {row.courses}, уроков в неделю {row.weekly}, "
                f"учителей {row.teachers}{now}"
            )
        if result.rescheme:
            out("")
            out(f"Схема станет «{Scheme.FO.label}» ({len(result.rescheme)}):")
            for row in result.rescheme:
                out(
                    f"  {row.subject.title}: сейчас «{row.subject.get_scheme_display()}»; "
                    f"уроков СОР/СОЧ {row.sor_soch_lessons}, оценок за них {row.sor_soch_grades} — "
                    "остаются в базе, в средний и итог не идут"
                )
        out("")
        out(f"Только расписание ({len(result.schedule_only)}):")
        for row in result.schedule_only:
            now = "" if not row.subject.in_lms else "  ← сейчас ведётся"
            out(f"  {row.subject.title}: журналов {row.courses}, уроков в неделю {row.weekly}{now}")
        out("")
        out(f"Отключатся учителя ({len(result.disable)}) — запись и уроки в расписании остаются:")
        for row in result.disable:
            out(f"  {row.user.full_name or row.user.email}: {', '.join(row.subjects) or 'журналов нет'}")
        if result.mixed:
            out("")
            out(f"Входят, но видят только ведущиеся предметы ({len(result.mixed)}):")
            for row in result.mixed:
                out(f"  {row.user.full_name or row.user.email}: {', '.join(row.subjects)}")
        out("")
