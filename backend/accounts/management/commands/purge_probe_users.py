"""Убрать одноразовые записи прогона насовсем.

Работает в любом режиме: уборка должна быть возможна всегда, даже если
прогон упал, а контур с тех пор переключили. Удаляет записи `*@probe.local`
вместе с сессиями, попытками входа и ссылками; журнал правок остаётся
с подписью-снимком автора.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from accounts import probe


class Command(BaseCommand):
    help = "Удаляет одноразовые записи прогона вместе с сессиями; журнал остаётся"

    def handle(self, *args, **options):
        counts = probe.purge_all()
        if not counts["users"]:
            self.stdout.write("Одноразовых записей нет — убирать нечего")
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Удалено записей: {counts['users']}, сессий: {counts['sessions']}, "
                f"попыток входа: {counts['attempts']}, ссылок: {counts['links']}; "
                f"строк журнала подписано: {counts['signed']}"
            )
        )
