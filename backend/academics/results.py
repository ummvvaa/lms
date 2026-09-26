"""Расчёты: строка ученика в журнале, формула четверти, пороги, итоги, риски.

Итог четверти: `ФО% × вес + СОР% × вес + СОЧ% × вес`, где ФО% — средний ФО
из максимума, СОР% и СОЧ% — сумма баллов к сумме максимумов. Пока какой-то
части нет, её вес делится между остальными. Перевод в оценку — по порогам
шкалы года. «Сейчас выходит» — прогноз по той же формуле; итог выставляет
учитель кнопкой, после закрытия четверти его правят Кымбат и администратор.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from academics import cache
from academics.calendar import SchoolCalendar, today
from academics.cohorts import cohorts_of_student, member_ids
from academics.marks import ABSENT, EXCUSED, LATE, grades_map, marks_map
from academics.models import Course, Lesson, LessonKind, LessonStatus, Quarter, QuarterResult, Scheme
from core.audit import record_change


def grade_of(percent: float | None, scale) -> int | None:
    """Процент в оценку по порогам шкалы; нет процента — нет оценки."""
    if percent is None:
        return None
    if percent >= scale.threshold_5:
        return 5
    if percent >= scale.threshold_4:
        return 4
    if percent >= scale.threshold_3:
        return 3
    return 2


def quarter_percent(fo_pct: float | None, sor_pct: float | None, soch_pct: float | None, scale) -> float | None:
    """Взвешенный процент; вес отсутствующих частей делится между остальными."""
    parts = [
        (fo_pct, scale.weight_fo),
        (sor_pct, scale.weight_sor),
        (soch_pct, scale.weight_soch),
    ]
    present = [(value, weight) for value, weight in parts if value is not None]
    total = sum(weight for _v, weight in present)
    if not present or total == 0:
        return None
    return sum(value * weight for value, weight in present) / total


@dataclass
class CourseStats:
    """Строка ученика в журнале за период."""

    total: int = 0
    absent: int = 0
    excused: int = 0
    late: int = 0
    fo: list[int] = field(default_factory=list)
    sor_got: int = 0
    sor_max: int = 0
    soch_got: int = 0
    soch_max: int = 0
    sor_count: int = 0
    soch_count: int = 0
    scheme: str = Scheme.KZ
    final: int | None = None
    final_reason: str = ""
    fo_max: int = 10
    _scale: object = None

    @property
    def attendance_pct(self) -> int | None:
        if not self.total:
            return None
        return round((self.total - self.absent - self.excused) * 100 / self.total)

    @property
    def fo_avg(self) -> float | None:
        return round(sum(self.fo) / len(self.fo), 1) if self.fo else None

    @property
    def fo_pct(self) -> float | None:
        return self.fo_avg / self.fo_max * 100 if self.fo_avg is not None and self.fo_max else None

    @property
    def sor_pct(self) -> float | None:
        return self.sor_got / self.sor_max * 100 if self.sor_max else None

    @property
    def soch_pct(self) -> float | None:
        return self.soch_got / self.soch_max * 100 if self.soch_max else None

    @property
    def quarter_pct(self) -> float | None:
        if self.scheme != Scheme.KZ or self._scale is None:
            return None
        return quarter_percent(self.fo_pct, self.sor_pct, self.soch_pct, self._scale)

    @property
    def quarter_grade(self) -> int | None:
        return grade_of(self.quarter_pct, self._scale) if self._scale is not None else None

    def as_dict(self) -> dict:
        pct = self.quarter_pct
        return {
            "total": self.total,
            "absent": self.absent,
            "excused": self.excused,
            "late": self.late,
            "attendance_pct": self.attendance_pct,
            "fo_avg": self.fo_avg,
            "fo_count": len(self.fo),
            "sor_got": self.sor_got,
            "sor_max": self.sor_max,
            "sor_count": self.sor_count,
            "soch_got": self.soch_got,
            "soch_max": self.soch_max,
            "soch_count": self.soch_count,
            "quarter_pct": round(pct, 1) if pct is not None else None,
            "quarter_grade": self.quarter_grade,
            "final": self.final,
            "final_reason": self.final_reason,
        }


@dataclass
class CourseContext:
    """Уроки журнала за период с отметками и оценками — один набор запросов."""

    course: Course
    lessons: list[Lesson]
    student_ids: list[int]
    marks: dict
    grades: dict
    scale: object
    finals: dict[int, QuarterResult]

    def stats(self, student_id: int) -> CourseStats:
        out = CourseStats(scheme=self.course.subject.scheme, fo_max=self.scale.fo_max, _scale=self.scale)
        for lesson in self.lessons:
            mark = self.marks.get((lesson.pk, student_id))
            if mark is None:
                continue
            out.total += 1
            if mark == ABSENT:
                out.absent += 1
            elif mark == EXCUSED:
                out.excused += 1
            elif mark == LATE:
                out.late += 1
            grade = self.grades.get((lesson.pk, student_id))
            if lesson.kind == LessonKind.FO:
                if grade is not None:
                    out.fo.append(grade.value)
            elif lesson.kind == LessonKind.SOR:
                if grade is not None:
                    out.sor_got += grade.value
                    out.sor_max += lesson.max_score or 0
                    out.sor_count += 1
            elif grade is not None:
                out.soch_got += grade.value
                out.soch_max += lesson.max_score or 0
                out.soch_count += 1
        final = self.finals.get(student_id)
        if final is not None:
            out.final = final.grade
            out.final_reason = final.reason
        return out


def course_lessons(course: Course, start: dt.date, end: dt.date, *, live_only: bool = True) -> list[Lesson]:
    rows = Lesson.objects.filter(course=course, date__gte=start, date__lte=end).select_related(
        "course", "course__subject"
    )
    if live_only:
        rows = rows.exclude(status=LessonStatus.CANCELLED)
    return list(rows.order_by("date", "slot", "id"))


def course_context(
    course: Course, start: dt.date, end: dt.date, scale, *, quarter: Quarter | None = None
) -> CourseContext:
    """Собрать контекст журнала: ученики состава плюс те, у кого есть строки за период."""
    store = cache.current()
    key = (course.pk, start, end, quarter.pk if quarter is not None else None)
    if store is not None and key in store.contexts:
        return store.contexts[key]
    if store is not None:
        lessons = [lesson for lesson in store.live_lessons(start, end) if lesson.course_id == course.pk]
    else:
        lessons = course_lessons(course, start, end)
    ids = member_ids(course.cohort, min(end, today()))
    extra = set()
    if lessons:
        from academics.models import Attendance, Grade

        pks = [lesson.pk for lesson in lessons]
        extra |= set(Attendance.objects.filter(lesson_id__in=pks).values_list("student_id", flat=True))
        extra |= set(Grade.objects.filter(lesson_id__in=pks).values_list("student_id", flat=True))
    for sid in sorted(extra):
        if sid not in ids:
            ids.append(sid)
    finals = {}
    if quarter is not None:
        finals = {row.student_id: row for row in QuarterResult.objects.filter(course=course, quarter=quarter)}
    context = CourseContext(
        course=course,
        lessons=lessons,
        student_ids=ids,
        marks=marks_map(lessons, ids),
        grades=grades_map(lessons, ids),
        scale=scale,
        finals=finals,
    )
    if store is not None:
        store.contexts[key] = context
    return context


# --- Ученик по всем предметам ---------------------------------------------------


def student_courses(student_id: int, on: dt.date | None = None) -> list[Course]:
    """Журналы, где ученик состоит на дату — по порядку предметов."""
    cohorts = cohorts_of_student(student_id, on)
    return list(
        Course.objects.filter(cohort_id__in=cohorts)
        .select_related("subject", "cohort", "cohort__group", "teacher")
        .order_by("subject__order", "cohort__name")
    )


def student_summary(
    student_id: int, start: dt.date, end: dt.date, scale, *, quarter: Quarter | None = None
) -> list[dict]:
    """Строка на журнал: предмет, учитель, состав, статистика."""
    out = []
    for course in student_courses(student_id, min(end, today())):
        context = course_context(course, start, end, scale, quarter=quarter)
        stats = context.stats(student_id)
        out.append({"course": course, "stats": stats})
    return out


@dataclass
class AttendanceTotals:
    total: int = 0
    absent: int = 0
    excused: int = 0
    late: int = 0
    days: dict = field(default_factory=dict)

    @property
    def pct(self) -> int | None:
        if not self.total:
            return None
        return round((self.total - self.absent - self.excused) * 100 / self.total)

    def as_dict(self) -> dict:
        return {"total": self.total, "absent": self.absent, "excused": self.excused, "late": self.late, "pct": self.pct}


def student_attendance(student_id: int, start: dt.date, end: dt.date) -> AttendanceTotals:
    """Посещаемость ученика по всем урокам за период, с разбивкой по дням."""
    from academics.schedule import for_student, live_lessons, student_lessons

    store = cache.current()
    if store is not None and store.has_lessons(start, end):
        lessons = for_student(live_lessons(start, end), student_id)
    else:
        lessons = student_lessons(student_id, start, end)
    marks = marks_map(lessons, [student_id])
    out = AttendanceTotals()
    for lesson in lessons:
        mark = marks.get((lesson.pk, student_id))
        if mark is None:
            continue
        out.total += 1
        if mark == ABSENT:
            out.absent += 1
        elif mark == EXCUSED:
            out.excused += 1
        elif mark == LATE:
            out.late += 1
        if mark != "present":
            out.days.setdefault(lesson.date, []).append((lesson, mark))
    return out


def attendance_by_students(student_ids: list[int], start: dt.date, end: dt.date) -> dict[int, AttendanceTotals]:
    """Посещаемость многих учеников за период — без запроса на каждого.

    Считается по отметкам: урок без отметки в счёт не идёт (как и в
    `student_attendance`), поэтому обходить составы не нужно — живые уроки
    периода читаются один раз, отметки — одной картой.
    """
    from academics.schedule import live_lessons

    lessons = live_lessons(start, end)
    marks = marks_map(lessons, student_ids)
    by_id = {lesson.pk: lesson for lesson in lessons}
    out: dict[int, AttendanceTotals] = {sid: AttendanceTotals() for sid in student_ids}
    for (lesson_id, student_id), mark in marks.items():
        totals = out.get(student_id)
        lesson = by_id.get(lesson_id)
        if totals is None or lesson is None:
            continue
        totals.total += 1
        if mark == ABSENT:
            totals.absent += 1
        elif mark == EXCUSED:
            totals.excused += 1
        elif mark == LATE:
            totals.late += 1
        if mark != "present":
            totals.days.setdefault(lesson.date, []).append((lesson, mark))
    return out


def recent_absences(student_id: int, *, days: int = 30) -> dict:
    """Пропуски ученика за последние `days` дней — для карточки куратора.

    Процент — по урокам с отметкой, дни — те, где стояло «н», «у» или «оп»,
    подпись дня — предметы с отметкой словами. Дни без причины — по правилу
    `unexcused_days`; они же предлагаются к оформлению.
    """
    from academics.marks import MARK_WORDS

    end = today()
    start = end - dt.timedelta(days=days)
    totals = student_attendance(student_id, start, end)
    rows = []
    for day in sorted(totals.days, reverse=True):
        items = totals.days[day]
        words = ", ".join(
            f"{lesson.course.subject.short_title} — {MARK_WORDS.get(mark, mark)}" for lesson, mark in items
        )
        rows.append(
            {
                "date": day,
                "present": False,
                "reason": words,
                "absent": sum(1 for _l, mark in items if mark == ABSENT),
                "excused": sum(1 for _l, mark in items if mark == EXCUSED),
                "late": sum(1 for _l, mark in items if mark == LATE),
            }
        )
    return {
        "pct": totals.pct,
        "total": totals.total,
        "days": rows,
        "unexcused_days": unexcused_days(student_id, start, end, totals),
    }


def unexcused_days(
    student_id: int, start: dt.date, end: dt.date, totals: AttendanceTotals | None = None
) -> list[dt.date]:
    """Дни без причины: не меньше двух «н» и не меньше 60 % уроков дня ученика.

    Пороги — решение владельца (25.09.2026); считаются только «н», «у» уже
    оформлены и в риск не входят.
    """
    from django.conf import settings

    rules = getattr(settings, "ACADEMICS_RULES", {})
    min_absent = int(rules.get("DAY_MIN_ABSENT", 2))
    share = float(rules.get("DAY_SHARE", 0.6))
    totals = totals or student_attendance(student_id, start, end)
    from academics.schedule import for_student, live_lessons

    out = []
    for day, rows in sorted(totals.days.items()):
        absent = sum(1 for _l, mark in rows if mark == ABSENT)
        if absent < min_absent:
            continue
        day_lessons = for_student([lesson for lesson in live_lessons(start, end) if lesson.date == day], student_id)
        if day_lessons and absent >= max(min_absent, round(len(day_lessons) * share + 0.4999)):
            out.append(day)
    return out


# --- Итог четверти ---------------------------------------------------------------


class ResultRefused(ValueError):
    """Итог так не выставить — текст объясняет почему."""


@transaction.atomic
def set_finals(course: Course, quarter: Quarter, rows: list[dict], *, actor, scale) -> int:
    """Выставить итоги журнала за четверть. Отличие от расчёта требует причины."""
    from core.domains import ROLE_TEACHER

    role = getattr(actor, "role", "")
    if quarter.is_closed and role == ROLE_TEACHER:
        raise ResultRefused("Приём итогов закрыт: изменить итог может только Кымбат или администратор")
    context = course_context(course, quarter.starts, quarter.ends, scale, quarter=quarter)
    written = 0
    for raw in rows:
        try:
            sid = int(raw.get("student"))
            grade = int(raw.get("final")) if raw.get("final") not in (None, "") else None
        except (TypeError, ValueError):
            continue
        if sid not in context.student_ids:
            continue
        reason = str(raw.get("reason") or "").strip()[:200]
        stats = context.stats(sid)
        computed = stats.quarter_grade
        pct = stats.quarter_pct
        existing = context.finals.get(sid)
        if grade is None:
            if existing is not None:
                record_change(
                    instance=existing, field_name="grade", old_value=existing.grade, new_value="", actor=actor
                )
                existing.delete()
                written += 1
            continue
        if grade < 2 or grade > 5:
            raise ResultRefused("Итог — от 2 до 5")
        if computed is not None and grade != computed and not reason:
            raise ResultRefused("Итог отличается от расчёта: напишите причину")
        if existing is None:
            existing = QuarterResult.objects.create(
                course=course,
                student_id=sid,
                quarter=quarter,
                grade=grade,
                computed_percent=Decimal(str(round(pct, 1))) if pct is not None else None,
                reason=reason,
                set_by=actor if getattr(actor, "pk", None) else None,
            )
            record_change(instance=existing, field_name="grade", old_value="", new_value=grade, actor=actor)
            if reason:
                record_change(instance=existing, field_name="reason", old_value="", new_value=reason, actor=actor)
        else:
            if existing.grade != grade:
                record_change(
                    instance=existing, field_name="grade", old_value=existing.grade, new_value=grade, actor=actor
                )
            if existing.reason != reason:
                record_change(
                    instance=existing, field_name="reason", old_value=existing.reason, new_value=reason, actor=actor
                )
            existing.grade = grade
            existing.reason = reason
            existing.computed_percent = Decimal(str(round(pct, 1))) if pct is not None else None
            existing.set_by = actor if getattr(actor, "pk", None) else None
            existing.save()
        written += 1
    return written


@transaction.atomic
def close_quarter(quarter: Quarter, *, actor) -> Quarter:
    """Закрыть приём итогов: учителя больше не меняют оценки и итоги."""
    from django.utils import timezone

    quarter.closed_at = timezone.now()
    quarter.closed_by = actor if getattr(actor, "pk", None) else None
    quarter.save(update_fields=["closed_at", "closed_by"])
    return quarter


@transaction.atomic
def open_quarter(quarter: Quarter, *, actor) -> Quarter:
    quarter.closed_at = None
    quarter.closed_by = None
    quarter.save(update_fields=["closed_at", "closed_by"])
    return quarter


def calendar_period(calendar: SchoolCalendar, code: str):
    """Границы периода и четверть, если период — четверть."""
    from academics.calendar import period_bounds

    start, end, title = period_bounds(calendar, code)
    quarter = None
    if code.startswith("q") and code[1:].isdigit():
        for row in calendar.quarters:
            if row.number == int(code[1:]):
                quarter = row
    return start, end, title, quarter
