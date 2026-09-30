"""Перевод школы на следующий учебный год.

8→9, 9→10, 10→11: группа остаётся той же (город тот же), растёт её
параллель; у тех, кто перешёл в 11, само включается поступление — разделы
считает реестр параллелей. 11 — выпуск: ученики и группа уходят в архив
(мягко, с возвратом), учётные записи отключаются, назначения кураторов
закрываются, данные остаются.

Сначала предпросмотр — что куда переходит и сколько учеников; потом
подтверждение числом, как у раздачи паролей. Одна запись на учебный год
(`YearTransfer.school_year` уникален): второй перевод в том же году —
отказ. Учебный год — по дате Алматы, сентябрь–август. Год выпуска
учеников не меняется: параллель растёт, выпуск остаётся тем же.
Расписание и журналы перевод не трогает — новый год строит учебная часть,
прошлые оценки остаются со своими датами.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from core.parallels import ADMISSION_PARALLEL, PARALLELS
from students.models import Student, StudyGroup, YearTransfer


class TransferRefused(Exception):
    """Перевод не выполнен: причина — для человека."""


def school_year(today: dt.date | None = None) -> str:
    """«2026/2027» — учебный год по дате Алматы: с сентября по август."""
    today = today or timezone.localdate()
    start = today.year if today.month >= 9 else today.year - 1
    return f"{start}/{start + 1}"


@dataclass
class Step:
    group: StudyGroup
    students: int

    @property
    def graduates(self) -> bool:
        return self.group.parallel == ADMISSION_PARALLEL


def _steps() -> list[Step]:
    groups = StudyGroup.objects.filter(parallel__in=PARALLELS).order_by("-parallel", "code")
    return [Step(group=group, students=Student.objects.filter(group=group).count()) for group in groups]


def preview() -> dict:
    """Что куда перейдёт и сколько учеников — до подтверждения."""
    year = school_year()
    done = YearTransfer.objects.filter(school_year=year).first()
    steps = _steps()
    moves = [
        {
            "group": step.group.code,
            "group_id": step.group.pk,
            "from": step.group.parallel,
            "to": None if step.graduates else step.group.parallel + 1,
            "students": step.students,
            "title": (
                _("{group}: выпуск, {count} уч. — в архив, вход закрыт").format(
                    group=step.group.code, count=step.students
                )
                if step.graduates
                else _("{group}: {parallel} → {next_parallel}, {count} уч.").format(
                    group=step.group.code,
                    parallel=step.group.parallel,
                    next_parallel=step.group.parallel + 1,
                    count=step.students,
                )
            ),
        }
        for step in steps
    ]
    moved = sum(step.students for step in steps if not step.graduates)
    graduated = sum(step.students for step in steps if step.graduates)
    without_group = Student.objects.filter(group__isnull=True).count()
    return {
        "school_year": year,
        "done": (
            {
                "at": done.done_at,
                "by": done.actor_title,
                "detail": _("Перевод за {year} уже выполнен {date} — повторить его нельзя").format(
                    year=year, date=f"{done.done_at:%d.%m.%Y}"
                ),
            }
            if done
            else None
        ),
        "moves": moves,
        "students_moved": moved,
        "students_graduated": graduated,
        "groups_moved": sum(1 for step in steps if not step.graduates),
        "groups_graduated": sum(1 for step in steps if step.graduates),
        "without_group": without_group,
        # подтверждение осмысленным вводом: набрать число затронутых — значит прочитать его
        "confirm": str(moved + graduated),
        "detail": (
            _("Перевод за {year}: переходят {moved} уч., выпускаются {graduated} уч.").format(
                year=year, moved=moved, graduated=graduated
            )
            + (
                " " + _("Учеников без группы — {count}: перевод их не трогает.").format(count=without_group)
                if without_group
                else ""
            )
        ),
    }


@transaction.atomic
def run(*, actor, confirm: str) -> dict:
    """Перевести школу: выпуск 11, затем 10→11, 9→10, 8→9. Одна запись на год."""
    from accounts.models import CuratorAssignment
    from core.archive import archive
    from core.audit import record_event
    from core.models import AuditLog

    plan = preview()
    if plan["done"]:
        raise TransferRefused(plan["done"]["detail"])
    if str(confirm or "").strip() != plan["confirm"]:
        raise TransferRefused(
            _("Наберите число затронутых учеников — {count}, — чтобы подтвердить перевод").format(count=plan["confirm"])
        )

    year = plan["school_year"]
    try:
        with transaction.atomic():
            record = YearTransfer.objects.create(
                school_year=year,
                actor=actor,
                actor_title=getattr(actor, "full_name", "") or getattr(actor, "handle", ""),
            )
    except IntegrityError as error:
        raise TransferRefused(_("Перевод за {year} уже выполнен — повторить его нельзя").format(year=year)) from error

    today = timezone.localdate()
    steps = _steps()
    graduated_students = graduated_groups = moved_students = moved_groups = 0

    # сначала выпуск: иначе 10, ставшие 11, выпустились бы в тот же заход
    for step in (step for step in steps if step.graduates):
        group = step.group
        for student in Student.objects.filter(group=group).select_related("user"):
            record_event(
                student=student,
                code="year_transfer",
                text=_("выпуск {year}: в архиве, вход закрыт").format(year=year),
                actor=actor,
            )
            if student.user_id:
                type(student.user).objects.filter(pk=student.user_id).update(is_active=False)
            archive(student, actor=actor)
            graduated_students += 1
        # кураторы выпускной группы её больше не ведут; история назначений остаётся
        for row in CuratorAssignment.objects.filter(group=group, until__isnull=True):
            row.until = max(today, row.since + dt.timedelta(days=1))
            row.save(update_fields=["until"])
        archive(group, actor=actor)
        graduated_groups += 1

    for parallel in sorted((p for p in PARALLELS if p != ADMISSION_PARALLEL), reverse=True):
        groups = [step.group for step in steps if step.group.parallel == parallel]
        for group in groups:
            for student in Student.objects.filter(group=group):
                record_event(
                    student=student,
                    code="year_transfer",
                    text=_("перевод {year}: {parallel} → {next_parallel} параллель").format(
                        year=year, parallel=parallel, next_parallel=parallel + 1
                    ),
                    actor=actor,
                )
                moved_students += 1
        StudyGroup.objects.filter(pk__in=[group.pk for group in groups]).update(parallel=parallel + 1)
        moved_groups += len(groups)

    record.groups_moved = moved_groups
    record.students_moved = moved_students
    record.groups_graduated = graduated_groups
    record.students_graduated = graduated_students
    record.save(update_fields=["groups_moved", "students_moved", "groups_graduated", "students_graduated"])

    AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_role=getattr(actor, "role", "") or "",
        model_label="students.StudyGroup",
        object_id="",
        field_name="year_transfer",
        old_value="",
        new_value=(
            _(
                "перевод на следующий год ({year}): переведено групп {groups_moved}, учеников {students_moved}; "
                "выпущено групп {groups_graduated}, учеников {students_graduated}"
            ).format(
                year=year,
                groups_moved=moved_groups,
                students_moved=moved_students,
                groups_graduated=graduated_groups,
                students_graduated=graduated_students,
            )
        ),
    )
    return {
        "school_year": year,
        "groups_moved": moved_groups,
        "students_moved": moved_students,
        "groups_graduated": graduated_groups,
        "students_graduated": graduated_students,
        "detail": (
            _(
                "Школа переведена на следующий год: переведено учеников {moved}, "
                "выпущено {graduated}. Выпускники в архиве, их вход закрыт"
            ).format(moved=moved_students, graduated=graduated_students)
        ),
    }
