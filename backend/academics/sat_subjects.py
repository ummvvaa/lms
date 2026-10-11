# i18n-skip-file: план для владельца в терминале (`manage.py sat_subjects`) и названия предметов школы
"""SAT: один предмет с разделами отчёта или два предмета — SAT Math и SAT Verbal.

Школа ведёт SAT одним предметом, а Math и Verbal — разделы отчёта у журналов
(решение владельца, 30.09.2026). С 11.10.2026 это выбор: правило школы
«SAT: два предмета» (`core.school_rules.SAT_TWO_SUBJECTS`) хранит целевой
режим, а журналы разносит и сводит обратно эта команда — не на лету, с сухим
прогоном. Оценки и уроки привязаны к журналу, поэтому журнал просто
переводится на другой предмет, и ни одна оценка не двигается.

* разнести: каждый SAT-журнал уходит на SAT Math или SAT Verbal по своему
  разделу отчёта; журнал без раздела — отказ, пока Кымбат не проставит
  раздел (решение владельца); предмет SAT прячется из списков;
* свести: журналы SAT Math и SAT Verbal возвращаются на SAT, раздел отчёта
  ставится по предмету; два предмета прячутся.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from academics.keep_subjects import _key
from academics.models import Course, ReportRole, Scheme, Subject
from core import school_rules

#: как предметы называются в LMS и в книге школы (без регистра)
MERGED_NAMES = ("sat",)
MATH_NAMES = ("sat math",)
VERBAL_NAMES = ("sat verbal",)
#: названия, с которыми заводятся недостающие предметы
MATH_TITLE, VERBAL_TITLE, MERGED_TITLE = "SAT Math", "SAT Verbal", "SAT"  # i18n-skip: названия предметов школы

ROLE_OF = {MATH_NAMES: ReportRole.SAT_MATH, VERBAL_NAMES: ReportRole.SAT_VERBAL}


def two_subjects() -> bool:
    """Целевой режим по правилу школы."""
    return bool(school_rules.value(school_rules.SAT_TWO_SUBJECTS))


def _find(names) -> Subject | None:
    """Предмет по названию или коду, предпочтительно показываемый в списках."""
    rows = [
        s
        for s in Subject.objects.order_by("-is_active", "order", "pk")
        if _key(s.title) in names or _key(s.code) in names
    ]
    return rows[0] if rows else None


def sat_kind(subject: Subject) -> str:
    """`merged`, `math`, `verbal` или пусто — к SAT предмет не относится."""
    key = _key(subject.title)
    if key in MERGED_NAMES or _key(subject.code) in MERGED_NAMES:
        return "merged"
    if key in MATH_NAMES:
        return "math"
    if key in VERBAL_NAMES:
        return "verbal"
    return ""


@dataclass
class Plan:
    #: `split` или `merge`
    mode: str
    merged: Subject | None = None
    math: Subject | None = None
    verbal: Subject | None = None
    #: журналы, которые переедут: (журнал, куда)
    moves: list[tuple[Course, str]] = field(default_factory=list)
    #: журналы SAT без раздела отчёта — разнести нельзя
    without_role: list[Course] = field(default_factory=list)
    #: предметы, которые заведутся
    create: list[str] = field(default_factory=list)
    #: предметы, которые спрячутся из списков
    hide: list[Subject] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def changes(self) -> bool:
        return bool(self.moves or self.create or self.hide)


def _live_courses(subject: Subject | None):
    if subject is None:
        return []
    return list(Course.objects.filter(subject=subject, archived_at__isnull=True).select_related("cohort", "teacher"))


def plan(mode: str) -> Plan:
    out = Plan(mode=mode, merged=_find(MERGED_NAMES), math=_find(MATH_NAMES), verbal=_find(VERBAL_NAMES))
    if mode == "split":
        if out.merged is None and out.math is None and out.verbal is None:
            out.errors.append("предмета SAT в LMS нет — разносить нечего")
            return out
        if out.math is None:
            out.create.append(MATH_TITLE)
        if out.verbal is None:
            out.create.append(VERBAL_TITLE)
        for course in _live_courses(out.merged):
            if course.report_role == ReportRole.SAT_MATH:
                out.moves.append((course, "math"))
            elif course.report_role == ReportRole.SAT_VERBAL:
                out.moves.append((course, "verbal"))
            else:
                out.without_role.append(course)
        if out.without_role:
            out.errors.append(
                "у журналов SAT не проставлен раздел отчёта (SAT Math или SAT Verbal) — проставьте в «Учителях»"
            )
        if out.merged is not None and out.merged.is_active:
            out.hide.append(out.merged)
        for subject in (out.math, out.verbal):
            if subject is not None and not (subject.is_active and subject.in_lms):
                out.create.append(f"{subject.title} — включить")
        return out
    # merge
    if out.math is None and out.verbal is None:
        out.errors.append("предметов SAT Math и SAT Verbal в LMS нет — сводить нечего")
        return out
    if out.merged is None:
        out.create.append(MERGED_TITLE)
    for course in _live_courses(out.math):
        out.moves.append((course, "merged"))
    for course in _live_courses(out.verbal):
        out.moves.append((course, "merged"))
    for subject in (out.math, out.verbal):
        if subject is not None and subject.is_active:
            out.hide.append(subject)
    if out.merged is not None and not (out.merged.is_active and out.merged.in_lms):
        out.create.append(f"{out.merged.title} — включить")
    return out


def _ensure(subject: Subject | None, title: str, code: str, *, order: int, actor) -> Subject:
    from core.audit import apply_changes

    if subject is None:
        base, number, candidate = code, 1, code
        while Subject.objects.filter(code=candidate).exists():
            number += 1
            candidate = f"{base}-{number}"
        return Subject.objects.create(
            code=candidate, title=title, short_title=title[:32], scheme=Scheme.FO, order=order, in_lms=True
        )
    changes = {}
    if not subject.is_active:
        changes["is_active"] = True
    if not subject.in_lms:
        changes["in_lms"] = True
    if subject.scheme != Scheme.FO:
        changes["scheme"] = Scheme.FO
    if changes:
        apply_changes(subject, changes, actor=actor)
    return subject


@transaction.atomic
def apply(result: Plan, *, actor=None) -> dict:
    """Записать план и выставить правило школы под режим. Повторный запуск ничего не меняет."""
    from core.audit import apply_changes

    if result.errors:
        raise ValueError("; ".join(result.errors))
    counts = {"moved": 0, "created": 0, "hidden": 0}
    if result.mode == "split":
        order = result.merged.order if result.merged is not None else 100
        targets = {
            "math": _ensure(result.math, MATH_TITLE, "sat-math", order=order, actor=actor),
            "verbal": _ensure(result.verbal, VERBAL_TITLE, "sat-verbal", order=order + 1, actor=actor),
        }
        counts["created"] = sum(1 for key in ("math", "verbal") if getattr(result, key) is None)
    else:
        order = (result.math or result.verbal).order
        targets = {"merged": _ensure(result.merged, MERGED_TITLE, "sat", order=order, actor=actor)}
        counts["created"] = int(result.merged is None)
    for course, where in result.moves:
        changes = {"subject": targets[where]}
        if where == "merged":
            # раздел отчёта — по прежнему предмету: отзывы SAT Verbal и SAT Math в отчёте остаются
            changes["report_role"] = (
                ReportRole.SAT_MATH if sat_kind(course.subject) == "math" else ReportRole.SAT_VERBAL
            )
        apply_changes(course, changes, actor=actor)
        counts["moved"] += 1
    for subject in result.hide:
        apply_changes(subject, {"is_active": False, "in_lms": False}, actor=actor)
        counts["hidden"] += 1
    school_rules.set_value(school_rules.SAT_TWO_SUBJECTS, 1 if result.mode == "split" else 0, actor=actor)
    return counts


def state() -> dict:
    """Строка для экрана предметов: режим по правилу и расходится ли с ним база."""
    two = two_subjects()
    merged, math, verbal = _find(MERGED_NAMES), _find(MATH_NAMES), _find(VERBAL_NAMES)
    merged_live = bool(_live_courses(merged)) if merged is not None and merged.is_active else False
    parts_live = any(bool(_live_courses(s)) for s in (math, verbal) if s is not None and s.is_active)
    pending = (merged_live and two) or (parts_live and not two)
    return {"two": two, "pending": pending}
