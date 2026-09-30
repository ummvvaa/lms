"""Найти строки сервера мимо перевода.

    python manage.py i18n_check                 # весь код приложений
    python manage.py i18n_check academics core  # только эти папки или файлы

Печатает «файл:строка: причина: «текст»» и число нарушений. Правила —
`core/i18n_guard.py`; ноль нарушений проверяет тест `test_server_i18n`.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand

from core import i18n_guard


class Command(BaseCommand):
    help = "Строки сервера мимо перевода"

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="*", help="папки или файлы относительно backend/")
        parser.add_argument("--summary", action="store_true", help="только число нарушений по файлам")

    def handle(self, *args, paths: list[str], summary: bool = False, **options):
        root = i18n_guard.backend_root()
        files = None
        if paths:
            files = []
            for item in paths:
                target = root / item
                files += (
                    [target] if target.is_file() else [p for p in i18n_guard.app_sources(root) if target in p.parents]
                )
        violations = i18n_guard.check_paths(files, root)
        if summary:
            for path, count in Counter(v.path for v in violations).most_common():
                self.stdout.write(f"{count:5} {path}")
        else:
            for violation in violations:
                self.stdout.write(str(violation))
        self.stdout.write(f"Нарушений: {len(violations)}")
