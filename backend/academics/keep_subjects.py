# i18n-skip-file: план для владельца в терминале (`manage.py keep_subjects`) и названия предметов школы
"""Какие предметы ведутся в LMS, а какие — только расписание.

Основной журнал школа ведёт в Kundelik; в LMS остаются предметы, которых
там нет (решение владельца, 07.10.2026): EEP, GE, SAT (Math и Verbal —
разделы отчёта у журналов одного предмета), Creative Writing,
Профориентация. Остальные предметы остаются в расписании без журнала,
оценок и ДЗ. Их оценивание — только ФО из 10.

Учителя, которые не ведут ни одного такого предмета, отключаются: запись,
её уроки в расписании и фамилия в них остаются. Сначала — план без записи
(`plan`), потом то же одним махом (`apply`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Q

from academics.calendar import today
from academics.models import Course, Grade, Lesson, LessonKind, LessonSeries, Scheme, Subject
from accounts.models import Role, User

#: предмет школы → как он может называться в LMS (без регистра и лишних пробелов)
KEPT: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("EEP — English Exam Preparation", ("английский язык (eep)", "eep", "english exam preparation")),
    ("GE — General English", ("английский язык (ge)", "ge", "general english")),
    ("SAT — Math и Verbal", ("sat", "sat math", "sat verbal")),
    ("Creative Writing", ("creative writing",)),
    ("Профориентация", ("профориентация",)),
)


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().casefold()


#: по этому слову в названии предмет считается профориентацией
CAREER_KEY = "профориентац"


@dataclass
class SubjectRow:
    subject: Subject
    courses: int
    weekly: int
    teachers: int
    #: уроков СОР и СОЧ и оценок за них — после перехода на «Только ФО» в расчёт не идут
    sor_soch_lessons: int = 0
    sor_soch_grades: int = 0


@dataclass
class TeacherRow:
    user: User
    subjects: list[str]


@dataclass
class Plan:
    #: что искали → какие предметы нашлись
    found: list[tuple[str, list[Subject]]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    keep: list[SubjectRow] = field(default_factory=list)
    schedule_only: list[SubjectRow] = field(default_factory=list)
    #: ведутся, но схема станет «Только ФО»
    rescheme: list[SubjectRow] = field(default_factory=list)
    disable: list[TeacherRow] = field(default_factory=list)
    #: ведут и те и другие: входят, видят только ведущиеся
    mixed: list[TeacherRow] = field(default_factory=list)

    @property
    def changes(self) -> bool:
        return bool(
            [r for r in self.keep if not r.subject.in_lms]
            or [r for r in self.schedule_only if r.subject.in_lms]
            or self.rescheme
            or self.disable
        )


def _row(subject: Subject) -> SubjectRow:
    courses = Course.objects.filter(subject=subject, archived_at__isnull=True)
    return SubjectRow(
        subject=subject,
        courses=courses.count(),
        weekly=LessonSeries.objects.filter(course__subject=subject, ends__gte=today()).count(),
        teachers=courses.exclude(teacher__isnull=True).values("teacher").distinct().count(),
    )


def is_kept_title(title: str) -> bool:
    """Предмет школы, который ведётся в LMS: по названию из файла или экрана."""
    return any(_key(title) in names for _label, names in KEPT)


def kept_subjects(extra_titles: list[str] | None = None) -> tuple[list[tuple[str, list[Subject]]], list[str]]:
    """Шесть предметов школы в базе: что нашлось и чего нет."""
    subjects = list(Subject.objects.all())
    found: list[tuple[str, list[Subject]]] = []
    missing: list[str] = []
    wanted = list(KEPT) + [(title, (_key(title),)) for title in extra_titles or []]
    for label, names in wanted:
        hits = [s for s in subjects if _key(s.title) in names or _key(s.code) in names]
        found.append((label, hits))
        if not hits:
            missing.append(label)
    return found, missing


def plan(extra_titles: list[str] | None = None) -> Plan:
    out = Plan()
    out.found, out.missing = kept_subjects(extra_titles)
    keep_ids = {s.pk for _label, hits in out.found for s in hits}
    for subject in Subject.objects.order_by("order", "title"):
        row = _row(subject)
        if subject.pk in keep_ids:
            out.keep.append(row)
            if subject.scheme != Scheme.FO:
                assessed = Lesson.objects.filter(course__subject=subject, kind__in=(LessonKind.SOR, LessonKind.SOCH))
                row.sor_soch_lessons = assessed.count()
                row.sor_soch_grades = Grade.objects.filter(lesson__in=assessed).count()
                out.rescheme.append(row)
        else:
            out.schedule_only.append(row)
    keeps = Q(subject_id__in=keep_ids)
    teachers = User.objects.filter(role=Role.TEACHER, is_active=True).order_by("full_name", "email")
    for user in teachers:
        own = Course.objects.filter(teacher=user, archived_at__isnull=True).select_related("subject")
        titles = sorted({c.subject.title for c in own})
        kept = (
            own.filter(keeps).exists()
            or Lesson.objects.filter(substitute=user, date__gte=today(), course__subject_id__in=keep_ids).exists()
        )
        if not kept:
            out.disable.append(TeacherRow(user=user, subjects=titles))
        elif own.exclude(keeps).exists():
            out.mixed.append(TeacherRow(user=user, subjects=titles))
    return out


@transaction.atomic
def apply(result: Plan, *, actor=None) -> dict:
    """Записать план: признак и схема предметов, отключение учителей — с журналом."""
    from accounts.services import deactivate
    from core.audit import apply_changes

    if result.missing:
        raise ValueError("не найдены: " + ", ".join(result.missing))
    counts = {"kept": 0, "schedule_only": 0, "rescheme": 0, "disabled": 0}
    rescheme = {row.subject.pk for row in result.rescheme}
    for row in result.keep:
        changes = {"in_lms": True}
        if row.subject.pk in rescheme:
            changes["scheme"] = Scheme.FO
        # профориентация: её учителю открыт раздел «Профтест» (`career.rights`)
        if CAREER_KEY in _key(row.subject.title):
            changes["is_career"] = True
        if apply_changes(row.subject, changes, actor=actor):
            counts["kept"] += 1
        counts["rescheme"] += int(row.subject.pk in rescheme)
    for row in result.schedule_only:
        if apply_changes(row.subject, {"in_lms": False}, actor=actor):
            counts["schedule_only"] += 1
    for row in result.disable:
        apply_changes(row.user, {"is_active": False}, actor=actor)
        deactivate(row.user)
        counts["disabled"] += 1
    return counts
