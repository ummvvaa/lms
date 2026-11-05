"""«Ученики секций» — рабочий список директора спорта и администратора (02.11.2026).

В списке только ученики хотя бы с одной действующей записью: убрали из всех
секций — ученик из списка уходит, история записей и отметок остаётся.
Фильтры собираются вместе и одним путём идут в список и в Excel: выгрузка —
ровно то, что на экране. Массовые действия сначала считают итог «сколько
пройдёт и почему нет», потом выполняются — по ученику в своей транзакции,
тем же путём, что запись по одному (`services.enroll`, `services.leave`).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.translation import gettext as _

from core.models import AuditLog
from sport import services
from sport.models import Section, SectionEnrollment, SectionMark, SectionSlot
from students.models import Student

#: массовые действия: назначить час (у кого его нет), перевести в час, убрать из секции
ASSIGN_HOUR = "assign_hour"
MOVE_HOUR = "move_hour"
REMOVE = "remove"
ACTIONS = (ASSIGN_HOUR, MOVE_HOUR, REMOVE)


def _flag(raw) -> bool:
    return str(raw or "").lower() in ("1", "true", "yes", "on")


def _number(raw) -> int | None:
    return int(raw) if str(raw if raw is not None else "").isdigit() else None


@dataclass(frozen=True)
class Filters:
    """Фильтры списка: всё вместе, пустое — не фильтрует."""

    q: str = ""
    group: int | None = None
    parallel: int | None = None
    section: int | None = None
    weekday: int | None = None
    hour: str = ""
    no_hour: bool = False
    below: bool = False
    several: bool = False
    never: bool = False
    month: str | None = None

    @classmethod
    def of(cls, params) -> Filters:
        hour = str(params.get("hour") or "").strip()[:5]
        return cls(
            q=str(params.get("q") or "").strip(),
            group=_number(params.get("group")),
            parallel=_number(params.get("parallel")),
            section=_number(params.get("section")),
            weekday=_number(params.get("weekday")),
            hour=hour if len(hour) == 5 and hour[2] == ":" else "",
            no_hour=_flag(params.get("no_hour")),
            below=_flag(params.get("below")),
            several=_flag(params.get("several")),
            never=_flag(params.get("never")),
            month=str(params.get("month") or "") or None,
        )

    def fits_enrollment(self, row: SectionEnrollment) -> bool:
        """Секция, день и час — у одной и той же записи ученика."""
        if self.section and row.section_id != self.section:
            return False
        if self.weekday is not None and (row.slot_id is None or row.slot.weekday != self.weekday):
            return False
        if self.hour and (row.slot_id is None or f"{row.slot.starts:%H:%M}" != self.hour):
            return False
        return True


def _enrollment_dict(row: SectionEnrollment, pct) -> dict:
    return {
        "id": row.pk,
        "section": row.section_id,
        "section_title": row.section.title,
        "slot": row.slot_id,
        "slot_title": services.slot_words(row.slot) if row.slot_id else "",
        "weekday": row.slot.weekday if row.slot_id else None,
        "starts": f"{row.slot.starts:%H:%M}" if row.slot_id else "",
        "percent": pct,
        "below": services.below_threshold(pct),
        "enrolled_at": timezone.localtime(row.enrolled_at).isoformat(),
        "source": row.source,
    }


def _brief(student) -> dict:
    return {
        "id": student.pk,
        "full_name": student.full_name,
        "short_name": f"{student.last_name} {student.first_name}".strip(),
        "group": student.group.code if student.group_id else "",
        "group_id": student.group_id,
        "parallel": services.student_parallel(student),
    }


def _matches_name(student, words: list[str]) -> bool:
    name = f"{student.last_name} {student.first_name} {getattr(student, 'middle_name', '') or ''}".lower()
    return all(word in name for word in words)


def roster(filters: Filters, students=None) -> tuple[list[dict], int]:
    """Строки списка по фильтрам и сколько всего учеников с записями.

    `students` — граница видимости (`core.scope.visible_students`).
    """
    query = services.active_enrollments().select_related("student", "student__group", "section", "slot")
    if students is not None:
        query = query.filter(student__in=students)
    enrollments = list(query.order_by("enrolled_at", "id"))
    by_student: dict[int, list[SectionEnrollment]] = {}
    for row in enrollments:
        by_student.setdefault(row.student_id, []).append(row)
    total = len(by_student)
    pct = services.month_percents(enrollments, filters.month)
    first, last = services.month_bounds(filters.month)
    ids = list(by_student)
    came = set(
        SectionMark.objects.counted()
        .filter(student_id__in=ids, date__gte=first, date__lte=last, is_guest=False)
        .values_list("student_id", flat=True)
    )
    guests = dict(
        SectionMark.objects.counted()
        .filter(student_id__in=ids, date__gte=first, date__lte=last, is_guest=True)
        .values("student_id")
        .annotate(n=Count("id"))
        .values_list("student_id", "n")
    )
    latest: dict[int, dict] = {}
    for mark in (
        SectionMark.objects.counted()
        .filter(student_id__in=ids, is_guest=False)
        .order_by("student_id", "-date", "-marked_at")
        .distinct("student_id")
        .values("student_id", "date", "slot__section__title")
    ):
        latest[mark["student_id"]] = {"date": mark["date"].isoformat(), "section": mark["slot__section__title"]}
    words = [word.lower() for word in filters.q.split()[:4]]
    out = []
    for student_id, rows in by_student.items():
        student = rows[0].student
        if words and not _matches_name(student, words):
            continue
        if filters.group and student.group_id != filters.group:
            continue
        if filters.parallel and services.student_parallel(student) != filters.parallel:
            continue
        if (filters.section or filters.weekday is not None or filters.hour) and not any(
            filters.fits_enrollment(r) for r in rows
        ):
            continue
        if filters.no_hour and all(r.slot_id for r in rows):
            continue
        values = [pct.get(r.pk) for r in rows]
        if filters.below and not any(services.below_threshold(v) for v in values):
            continue
        if filters.several and len(rows) < 2:
            continue
        held = any(v is not None for v in values)
        if filters.never and not (held and student_id not in came):
            continue
        known = [v for v in values if v is not None]
        out.append(
            {
                "student": _brief(student),
                "enrollments": [_enrollment_dict(r, pct.get(r.pk)) for r in rows],
                "last_mark": latest.get(student_id),
                "guest_visits": guests.get(student_id, 0),
                "worst": min(known) if known else None,
            }
        )
    out.sort(key=lambda r: r["student"]["full_name"])
    return out, total


def facets(students=None) -> dict:
    """Что предложить в фильтрах: группы учеников списка, секции с часами, часы начала."""
    query = services.active_enrollments()
    if students is not None:
        query = query.filter(student__in=students)
    groups = (
        query.exclude(student__group__isnull=True)
        .values_list("student__group_id", "student__group__code")
        .distinct()
        .order_by("student__group__code")
    )
    slots = SectionSlot.objects.filter(section__archived_at__isnull=True).select_related("section")
    return {
        "groups": [{"id": pk, "code": code} for pk, code in groups],
        "hours": sorted({f"{slot.starts:%H:%M}" for slot in slots}),
        "weekdays": sorted({slot.weekday for slot in slots}),
    }


# --- История ученика ------------------------------------------------------------------------


def _who(user) -> str:
    return (getattr(user, "full_name", "") or getattr(user, "email", "") or "") if user else ""


def history(student) -> dict:
    """Панель истории: записи (и закрытые) — когда и кем, события журнала, последние отметки и гостевые визиты."""
    enrollments = (
        SectionEnrollment.objects.filter(student=student)
        .select_related("section", "slot", "created_by", "slot_set_by", "ended_by")
        .order_by("-enrolled_at", "-id")
    )
    events = (
        AuditLog.objects.filter(student_id=student.pk, field_name=services.EVENT)
        .select_related("actor")
        .order_by("-created_at", "-id")[:40]
    )
    marks = (
        SectionMark.objects.counted().filter(student=student).select_related("slot", "slot__section").order_by("-date")
    )
    return {
        "student": _brief(student),
        "enrollments": [
            {
                "id": row.pk,
                "section_title": row.section.title,
                "slot_title": services.slot_words(row.slot) if row.slot_id else "",
                "enrolled_at": timezone.localtime(row.enrolled_at).isoformat(),
                "source": row.source,
                "source_title": row.get_source_display(),
                "created_by": _who(row.created_by),
                "slot_set_by": _who(row.slot_set_by),
                "ended_at": timezone.localtime(row.ended_at).isoformat() if row.ended_at else None,
                "ended_by": _who(row.ended_by),
            }
            for row in enrollments
        ],
        "events": [
            {
                "id": event.pk,
                "at": timezone.localtime(event.created_at).isoformat(),
                "text": event.new_value,
                "author": _who(event.actor) or event.actor_title,
            }
            for event in events
        ],
        "marks": [
            {
                "date": mark.date.isoformat(),
                "section": mark.slot.section.title,
                "slot": services.slot_words(mark.slot),
                "method": mark.method,
                "guest": mark.is_guest,
            }
            for mark in marks.filter(is_guest=False)[:10]
        ],
        "guests": [
            {"date": mark.date.isoformat(), "section": mark.slot.section.title, "slot": services.slot_words(mark.slot)}
            for mark in marks.filter(is_guest=True)[:10]
        ],
    }


# --- Массовые действия ----------------------------------------------------------------------


def bulk(*, action: str, students, section: Section | None, slot: SectionSlot | None, actor, apply: bool) -> dict:
    """Итог массового действия по ученикам: кто пройдёт, кто нет и почему; `apply` — выполнить.

    Лимит часа в итоге считается нарастающим: десятерых на час с тремя
    свободными местами — предупреждение у восьмого. Предупреждения директору
    не мешают: итог он уже видел. Каждый ученик — своя транзакция: отказ
    у одного не откатывает остальных.
    """
    if action not in ACTIONS:
        raise services.Refused(_("Неизвестное действие"))
    if action in (ASSIGN_HOUR, MOVE_HOUR):
        if slot is None:
            raise services.Refused(_("Выберите час занятия"))
        section = slot.section
    if section is None:
        raise services.Refused(_("Выберите секцию"))
    planned = 0
    rows = []
    for student in sorted(students, key=lambda s: (s.last_name, s.first_name)):
        row = services.active_in(student, section)
        reason = ""
        warnings: list[str] = []
        if row is None:
            reason = _("Не записан в секцию «{title}»").format(title=section.title)
        elif action == ASSIGN_HOUR and row.slot_id:
            reason = _("Час уже назначен: {slot}").format(slot=services.slot_words(row.slot))
        elif action == MOVE_HOUR and row.slot_id == slot.pk:
            reason = _("Уже на этом часе")
        elif action in (ASSIGN_HOUR, MOVE_HOUR):
            refusals, warnings = services.check(student=student, slot=slot, by_director=True, planned=planned)
            reason = refusals[0] if refusals else ""
        if apply and not reason:
            try:
                with transaction.atomic():
                    if action == REMOVE:
                        services.leave(student=student, section=section, actor=actor, by_director=True)
                    else:
                        services.enroll(student=student, slot=slot, actor=actor, by_director=True, force=True)
            except services.Refused as error:
                reason = str(error)
        if not reason and action in (ASSIGN_HOUR, MOVE_HOUR) and not apply:
            planned += 1
        rows.append({"student": _brief(student), "ok": not reason, "reason": reason, "warnings": warnings})
    return {
        "action": action,
        "applied": apply,
        "ok": sum(1 for r in rows if r["ok"]),
        "failed": sum(1 for r in rows if not r["ok"]),
        "rows": rows,
    }


def students_of(ids, visible) -> list[Student]:
    """Отмеченные ученики в границе видимости: чужой id молча не попадает в действие."""
    return list(visible.filter(pk__in=[i for i in ids if str(i).isdigit()]).select_related("group"))
