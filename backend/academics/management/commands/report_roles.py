"""Раздел отчёта родителям у журналов предмета по учителю.

SAT — один предмет, а Verbal и Math ведут разные учителя: раздел ставится
журналу. Имён сотрудников в репозитории нет — команда берёт их из
аргументов (порядок для школы — `docs/DEPLOY.md`):

    manage.py report_roles sat_verbal "Фамилия1" "Фамилия2" --subject SAT
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from academics.models import Course, ReportRole


class Command(BaseCommand):
    help = "Поставить раздел отчёта родителям журналам учителей (по фамилии в ФИО)"

    def add_arguments(self, parser):
        parser.add_argument("role", choices=[value for value in ReportRole.values if value])
        parser.add_argument("teachers", nargs="+", help="фамилии или часть ФИО учителей")
        parser.add_argument("--subject", default="SAT", help="название предмета, по умолчанию SAT")

    def handle(self, *args, role: str, teachers: list[str], subject: str, **options):
        wanted = Q()
        for name in teachers:
            if not name.strip():
                raise CommandError("Пустая фамилия")
            wanted |= Q(teacher__full_name__icontains=name.strip())
        rows = Course.objects.filter(subject__title__iexact=subject.strip()).filter(wanted)
        changed = rows.exclude(report_role=role).update(report_role=role)
        label = ReportRole(role).label
        self.stdout.write(f"{subject}: журналов с разделом «{label}» — {rows.count()}, изменено {changed}")
