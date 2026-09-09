"""Предполётная проверка перед живыми учениками (фаза 64).

Печатает список «ок / не ок» и ничего не меняет. Каждая строка — то,
что после запуска исправлять поздно: выключенный DEBUG, чужой SECRET_KEY,
почта, бэкапы, остатки посева, группы без куратора. Выход 1, если хоть
одно «не ок»: скрипт запуска может на неё опереться.

Пробное письмо уходит только с `--mail-to`: без адреса проверяется одно
соединение с сервером, и строка помечается предупреждением.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


@dataclass
class Check:
    title: str
    ok: bool
    detail: str = ""
    #: предупреждение — не «не ок», но и не молчание
    warn: bool = False


def _settings_checks() -> list[Check]:
    out = [Check("DEBUG выключен", not settings.DEBUG, "DJANGO_DEBUG=1 — на бою так нельзя" if settings.DEBUG else "")]
    key = settings.SECRET_KEY
    weak = key.startswith("dev-insecure") or len(key) < 32
    out.append(Check("SECRET_KEY свой", not weak, "ключ из примера или короче 32 символов" if weak else ""))
    hosts = settings.ALLOWED_HOSTS
    star = "*" in hosts
    out.append(Check("ALLOWED_HOSTS без «*»", not star and bool(hosts), ", ".join(hosts)))
    nets = getattr(settings, "LOGIN_TRUSTED_NETWORKS", []) or []
    out.append(
        Check(
            "LOGIN_TRUSTED_NETWORKS задан",
            bool(nets),
            ", ".join(nets) if nets else "пусто: блокировка по адресу действует на всех, впишите сеть школы",
        )
    )
    return out


def _mail_checks(mail_to: str) -> list[Check]:
    from core import mail

    ok, detail = mail.connection_check()
    out = [Check("Почта: сервер отвечает", ok, detail)]
    if mail_to:
        result = mail.send_test(mail_to)
        out.append(Check(f"Почта: пробное письмо на {mail_to}", bool(result.get("ok")), str(result.get("detail", ""))))
    else:
        out.append(Check("Почта: пробное письмо", False, "не отправлялось — укажите --mail-to", warn=True))
    return out


def _backup_checks() -> list[Check]:
    bucket = os.environ.get("BACKUP_REMOTE_BUCKET", "")
    endpoint = os.environ.get("BACKUP_REMOTE_ENDPOINT", "")
    keys = os.environ.get("BACKUP_REMOTE_ACCESS_KEY", "") and os.environ.get("BACKUP_REMOTE_SECRET_KEY", "")
    out = [
        Check(
            "Бэкап: переменные бакета заданы",
            bool(bucket and endpoint and keys),
            "заполните BACKUP_REMOTE_* в .env.prod" if not (bucket and endpoint and keys) else f"{endpoint}/{bucket}",
        )
    ]
    folder = Path(os.environ.get("BACKUP_DIR", "/backups"))
    dumps = sorted(folder.glob("lms-*.dump"), key=lambda p: p.stat().st_mtime) if folder.exists() else []
    if not dumps:
        out.append(Check("Бэкап: последний дамп не старше суток", False, f"в {folder} дампов нет"))
    else:
        age_h = (time.time() - dumps[-1].stat().st_mtime) / 3600
        out.append(
            Check(
                "Бэкап: последний дамп не старше суток",
                age_h <= 24,
                f"{dumps[-1].name}, {age_h:.1f} ч назад",
            )
        )
    return out


def _data_checks() -> list[Check]:
    from accounts.curators import active_assignments
    from accounts.probe import probe_users
    from directories.models import ExamKind
    from students.models import Student, StudyGroup

    out = []
    probes = probe_users().filter(is_active=True).count()
    out.append(Check("Probe-аккаунты: ни одного активного", probes == 0, f"активных {probes}" if probes else ""))

    fictional = Student.all_objects.filter(is_fictional=True).count()
    out.append(
        Check(
            "Вымышленных учеников нет",
            fictional == 0,
            f"помечено {fictional} — вычистите purge_fictional" if fictional else "",
        )
    )

    from accounts.models import User

    orphans_users = User.objects.filter(role="student", is_active=True, student__isnull=True).count()
    out.append(
        Check(
            "Учётные записи учеников без карточки",
            orphans_users == 0,
            f"{orphans_users} — приглашённые без карточки или остатки посева" if orphans_users else "",
            warn=True,
        )
    )

    groups = list(StudyGroup.objects.filter(is_active=True))
    led = set(active_assignments().values_list("group_id", flat=True))
    orphans = [g.code for g in groups if g.pk not in led]
    out.append(
        Check(
            "У всех групп есть куратор",
            not orphans and bool(groups),
            (
                ("без куратора: " + ", ".join(orphans))
                if orphans
                else ("групп нет" if not groups else f"групп {len(groups)}")
            ),
        )
    )

    visible = set(ExamKind.objects.filter(is_active=True).values_list("name", flat=True))
    ent_live = ExamKind.objects.filter(name__iexact="ЕНТ").exists()
    out.append(
        Check(
            "Экзамены: ЕНТ в архиве, IELTS и SAT показываются",
            not ent_live and {"IELTS", "SAT"} <= visible,
            f"показываются: {', '.join(sorted(visible))}" + (" · ЕНТ живой" if ent_live else ""),
        )
    )
    return out


def _system_checks() -> list[Check]:
    from io import StringIO

    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    out = [Check("Миграции применены", not pending, f"не применено: {len(pending)}" if pending else "")]

    buffer = StringIO()
    try:
        call_command("check", "--deploy", "--fail-level", "ERROR", stdout=buffer, stderr=buffer)
        text = buffer.getvalue()
        warnings = text.count("(W0") + text.count(".W0")
        out.append(
            Check(
                "check --deploy без ошибок",
                True,
                f"предупреждений: {warnings}, ошибок нет" if warnings else "чисто",
            )
        )
    except SystemExit:
        out.append(Check("check --deploy без ошибок", False, buffer.getvalue().strip()[-400:]))
    except Exception as error:
        out.append(Check("check --deploy без ошибок", False, str(error)[-400:]))
    return out


class Command(BaseCommand):
    help = "Предполётная проверка перед живыми учениками: печатает «ок / не ок», ничего не меняет"

    def add_arguments(self, parser):
        parser.add_argument("--mail-to", default="", help="Куда отправить пробное письмо")

    def handle(self, *args, **options):
        checks = _settings_checks() + _mail_checks(options["mail_to"]) + _backup_checks() + _data_checks()
        checks += _system_checks()
        failed = 0
        for check in checks:
            if check.ok:
                mark = self.style.SUCCESS("ок    ")
            elif check.warn:
                mark = self.style.WARNING("внимание")
            else:
                mark = self.style.ERROR("НЕ ОК ")
                failed += 1
            line = f"[{mark}] {check.title}"
            if check.detail:
                line += f" — {check.detail}"
            self.stdout.write(line)
        self.stdout.write("")
        if failed:
            self.stdout.write(self.style.ERROR(f"Не ок: {failed}. К живым ученикам не готово"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("Всё ок — можно открывать доступ"))
