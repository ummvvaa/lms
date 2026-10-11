"""SAT: разнести на SAT Math и SAT Verbal или свести обратно в один предмет.

Сначала посмотреть план (ничего не пишет):

    manage.py sat_subjects --split --dry-run
    manage.py sat_subjects --merge --dry-run

Затем записать тот же план:

    manage.py sat_subjects --split --apply

Команда переводит журналы на другой предмет: оценки и уроки остаются при
журнале. Правило школы «SAT: два предмета» выставляется под режим.
Порядок на проде (бэкап → dry-run → apply) — `docs/DEPLOY.md`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from academics import sat_subjects


class Command(BaseCommand):
    help = "SAT: один предмет с разделами отчёта или два предмета (SAT Math и SAT Verbal)"

    def add_arguments(self, parser):
        what = parser.add_mutually_exclusive_group(required=True)
        what.add_argument("--split", action="store_true", help="разнести SAT на SAT Math и SAT Verbal")
        what.add_argument("--merge", action="store_true", help="свести SAT Math и SAT Verbal в SAT")
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true", help="показать план и ничего не менять")
        mode.add_argument("--apply", action="store_true", help="записать план")

    def handle(self, *args, split: bool = False, dry_run: bool = False, apply: bool = False, **options):
        result = sat_subjects.plan("split" if split else "merge")
        self._print(result)
        if result.errors:
            raise CommandError("Нельзя: " + "; ".join(result.errors))
        if dry_run:
            self.stdout.write("Сухой прогон — ничего не изменено.")
            return
        counts = sat_subjects.apply(result)
        self.stdout.write(
            f"Готово: журналов переведено {counts['moved']}, предметов заведено {counts['created']}, "
            f"спрятано {counts['hidden']}; правило «SAT: два предмета» — {'да' if split else 'нет'}."
        )

    def _print(self, result: sat_subjects.Plan) -> None:
        self.stdout.write(
            "Режим: " + ("разнести SAT на SAT Math и SAT Verbal" if result.mode == "split" else "свести в SAT")
        )
        for label, subject in (("SAT", result.merged), ("SAT Math", result.math), ("SAT Verbal", result.verbal)):
            if subject is None:
                self.stdout.write(f"  {label}: в LMS нет")
            else:
                state = "в списках" if subject.is_active else "скрыт"
                self.stdout.write(
                    f"  {label}: «{subject.title}» ({subject.code}), {state}, журналов {len(_live(subject))}"
                )
        for title in result.create:
            self.stdout.write(f"  заведётся или включится: {title}")
        for course, where in result.moves:
            target = {"math": "SAT Math", "verbal": "SAT Verbal", "merged": "SAT"}[where]
            teacher = course.teacher.full_name if course.teacher_id else "учитель не назначен"
            self.stdout.write(f"  журнал {course.cohort.name} · {teacher} → {target}")
        for course in result.without_role:
            teacher = course.teacher.full_name if course.teacher_id else "учитель не назначен"
            self.stdout.write(f"  БЕЗ РАЗДЕЛА ОТЧЁТА: {course.cohort.name} · {teacher}")
        for subject in result.hide:
            self.stdout.write(f"  спрячется из списков: {subject.title}")
        if not result.changes and not result.errors:
            self.stdout.write("  менять нечего")


def _live(subject):
    return sat_subjects._live_courses(subject)
