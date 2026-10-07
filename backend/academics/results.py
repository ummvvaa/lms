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
from django.utils.translation import gettext as _

from academics import cache
from academics.calendar import SchoolCalendar, today
from academics.cohorts import cohorts_of_student, member_ids
from academics.marks import ABSENT, EXCUSED, LATE, arrivals_map, grades_map, marks_map
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


# --- Посещаемость по минутам -----------------------------------------------------
#
# Одна формула на все экраны, выгрузки, отчёт родителям и помощника (решение
# владельца, 30.09.2026). Минуты урока — конец минус начало по звонкам группы
# урока (у подгруппы потока — групп потока); номера нет в сетке — длина урока
# по умолчанию из настроек школы. «Был» — все минуты, «опоздал» — от прихода
# до конца, опоздание без времени (до 30.09.2026) — все минуты, «не был» — 0.
# Уважительная — 0 минут и урок в знаменателе, если так решила школа
# («Пропуск по уважительной причине снижает процент»), иначе урок в процент
# не входит. Процент — минуты присутствия к минутам отмеченных уроков.
#
# Правило школы «Опоздание больше N минут считается пропуском» (05.10.2026,
# выключено нулём): такое опоздание читается как «н» уже в карте отметок
# (`marks.marks_map`), поэтому сюда приходит пропуском — 0 минут, в счёт «н»
# и в «день без причины»; в счёт опозданий не идёт. В базе отметка учителя
# остаётся опозданием со временем прихода.


def _minutes_between(starts: dt.time, ends: dt.time) -> int:
    day = dt.date(2000, 1, 1)
    return max(0, int((dt.datetime.combine(day, ends) - dt.datetime.combine(day, starts)).total_seconds() // 60))


@dataclass(frozen=True)
class MinuteRules:
    """Что нужно формуле: звонки года и правила школы."""

    calendar: SchoolCalendar
    excused_lowers: bool
    default_minutes: int
    #: опоздание дольше стольких минут читается как пропуск; 0 — правило выключено
    late_absent_after: int = 0

    def span(self, lesson: Lesson) -> tuple[dt.time, dt.time] | None:
        from academics.calendar import lesson_groups

        return self.calendar.bell(lesson.slot, lesson_groups(lesson))

    def minutes(self, lesson: Lesson) -> int:
        span = self.span(lesson)
        return _minutes_between(*span) if span else self.default_minutes


def minute_rules() -> MinuteRules:
    """Правила формулы — один раз за запрос, если он открыт (`academics.cache`)."""
    from academics import calendar as school_calendar
    from core import school_rules

    store = cache.current()
    if store is not None and "minute_rules" in store.memo:
        return store.memo["minute_rules"]
    values = school_rules.values()
    rules = MinuteRules(
        calendar=school_calendar.load(),
        excused_lowers=bool(values[school_rules.EXCUSED_LOWERS_ATTENDANCE]),
        default_minutes=values[school_rules.LESSON_MINUTES_DEFAULT],
        late_absent_after=int(values[school_rules.LATE_AS_ABSENT_MINUTES]),
    )
    if store is not None:
        store.memo["minute_rules"] = rules
    return rules


def late_by(lesson: Lesson, arrived: dt.time | None, rules: MinuteRules | None = None) -> int | None:
    """На сколько минут опоздал: от начала урока до прихода; времени нет — None."""
    if arrived is None:
        return None
    span = (rules or minute_rules()).span(lesson)
    if span is None:
        return None
    return _minutes_between(span[0], arrived)


def late_counts_absent(lesson: Lesson, arrived: dt.time | None, rules: MinuteRules | None = None) -> bool:
    """Опоздание дольше правила школы читается как пропуск.

    Времени прихода нет (опоздания до 30.09.2026) или у номера урока нет звонка —
    минуты посчитать не из чего, опоздание остаётся опозданием.
    """
    rules = rules or minute_rules()
    if not rules.late_absent_after or arrived is None:
        return False
    minutes = late_by(lesson, arrived, rules)
    return minutes is not None and minutes > rules.late_absent_after


def late_fields(lesson: Lesson, mark: str | None, arrived: dt.time | None) -> dict:
    """Для экрана: во сколько пришёл и на сколько опоздал; у старых опозданий — пусто.

    `late_as_absent` — опоздание по правилу школы считается пропуском: в картах
    отметок оно уже «н» (или «у» внутри уважительного периода), время прихода
    при нём остаётся, чтобы экран сказал, откуда взялась «н».
    """
    as_absent = mark in (LATE, ABSENT, EXCUSED) and late_counts_absent(lesson, arrived)
    if mark != LATE and not as_absent:
        return {"arrived": None, "late_by": None, "late_as_absent": False}
    return {
        "arrived": f"{arrived:%H:%M}" if arrived else None,
        "late_by": late_by(lesson, arrived),
        "late_as_absent": as_absent,
    }


@dataclass
class Presence:
    """Счёт посещаемости: уроки по отметкам и минуты присутствия."""

    total: int = 0
    absent: int = 0
    excused: int = 0
    late: int = 0
    #: сумма минут опозданий, где время прихода известно
    late_minutes: int = 0
    #: опоздания без времени — до 30.09.2026 время не записывалось
    late_unknown: int = 0
    minutes_total: int = 0
    minutes_present: int = 0

    def count(self, lesson: Lesson, mark: str, arrived: dt.time | None, rules: MinuteRules) -> None:
        """Добавить отмеченный урок ученика в счёт."""
        self.total += 1
        minutes = rules.minutes(lesson)
        if mark == ABSENT:
            self.absent += 1
            self.minutes_total += minutes
            return
        if mark == EXCUSED:
            self.excused += 1
            if rules.excused_lowers:
                self.minutes_total += minutes
            return
        self.minutes_total += minutes
        if mark == LATE:
            self.late += 1
            span = rules.span(lesson)
            if arrived is not None and span is not None:
                self.late_minutes += _minutes_between(span[0], arrived)
                self.minutes_present += min(minutes, _minutes_between(arrived, span[1]))
                return
            if arrived is None:
                self.late_unknown += 1
        self.minutes_present += minutes

    @property
    def pct(self) -> int | None:
        if not self.minutes_total:
            return None
        return round(self.minutes_present * 100 / self.minutes_total)


@dataclass
class CourseStats(Presence):
    """Строка ученика в журнале за период."""

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
    #: оценки за ДЗ — в среднюю ФО идут, только когда так решила школа
    #: («Оценки за ДЗ входят в четвертную», `core.school_rules`), с весом к одной ФО
    hw: list[int] = field(default_factory=list)
    hw_weight: float = 0.0

    @property
    def attendance_pct(self) -> int | None:
        return self.pct

    @property
    def fo_avg(self) -> float | None:
        weight = self.hw_weight if self.hw else 0.0
        count = len(self.fo) + weight * len(self.hw)
        if not count:
            return None
        return round((sum(self.fo) + weight * sum(self.hw)) / count, 1)

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
            "late_minutes": self.late_minutes,
            "late_unknown": self.late_unknown,
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
    arrivals: dict = field(default_factory=dict)
    #: оценки за ДЗ `(урок, ученик)` и правило школы: входят ли в четвертную, вес
    homework: dict = field(default_factory=dict)
    homework_weight: float = 0.0

    def stats(self, student_id: int) -> CourseStats:
        out = CourseStats(scheme=self.course.subject.scheme, fo_max=self.scale.fo_max, _scale=self.scale)
        rules = minute_rules()
        if self.homework_weight:
            out.hw_weight = self.homework_weight
            out.hw = [
                self.homework[(lesson.pk, student_id)]
                for lesson in self.lessons
                if (lesson.pk, student_id) in self.homework
            ]
        for lesson in self.lessons:
            mark = self.marks.get((lesson.pk, student_id))
            if mark is None:
                continue
            out.count(lesson, mark, self.arrivals.get((lesson.pk, student_id)), rules)
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
        "course", "course__subject", "course__cohort", "course__cohort__group", "teacher", "substitute"
    )
    if live_only:
        rows = rows.exclude(status=LessonStatus.CANCELLED)
    return list(rows.order_by("date", "slot", "id"))


def prime_lessons(start: dt.date, end: dt.date) -> None:
    """Прочитать уроки школы за период в кэш запроса один раз — перед циклом по всем курсам."""
    store = cache.current()
    if store is not None:
        store.live_lessons(start, end)


def course_context(
    course: Course, start: dt.date, end: dt.date, scale, *, quarter: Quarter | None = None
) -> CourseContext:
    """Собрать контекст журнала: ученики состава плюс те, у кого есть строки за период."""
    store = cache.current()
    key = (course.pk, start, end, quarter.pk if quarter is not None else None)
    if store is not None and key in store.contexts:
        return store.contexts[key]
    # уроки школы за период читаются целиком только там, где их спросили сами
    # (успеваемость школы, посещаемость): журнал одного курса на этом читал
    # все 28 тысяч строк года ради своих сорока (D75, 06.10.2026)
    if store is not None and store.has_lessons(start, end):
        lessons = [lesson for lesson in store.live_lessons(start, end) if lesson.course_id == course.pk]
    else:
        lessons = course_lessons(course, start, end)
    ids = member_ids(course.cohort, min(end, today()))
    extra = set()
    if lessons:
        pks = {lesson.pk for lesson in lessons}
        if store is not None:
            # отметки и оценки периода уже в кэше запроса — ещё два запроса на курс не нужны
            extra |= {sid for lesson_id, sid in store.attendance_rows(start, end) if lesson_id in pks}
            extra |= {sid for lesson_id, sid in store.grade_rows(start, end) if lesson_id in pks}
        else:
            from academics.models import Attendance, Grade

            extra |= set(Attendance.objects.filter(lesson_id__in=pks).values_list("student_id", flat=True))
            extra |= set(Grade.objects.filter(lesson_id__in=pks).values_list("student_id", flat=True))
    for sid in sorted(extra):
        if sid not in ids:
            ids.append(sid)
    finals = {}
    if quarter is not None:
        finals = {row.student_id: row for row in QuarterResult.objects.filter(course=course, quarter=quarter)}
    from homework import services as homework

    # правило ДЗ — одно на запрос, а не запрос к правилам на каждый курс школы
    if store is not None and "quarter_rule" in store.memo:
        included, weight = store.memo["quarter_rule"]
    else:
        included, weight = homework.quarter_rule()
        if store is not None:
            store.memo["quarter_rule"] = (included, weight)
    context = CourseContext(
        course=course,
        lessons=lessons,
        student_ids=ids,
        marks=marks_map(lessons, ids),
        grades=grades_map(lessons, ids),
        scale=scale,
        finals=finals,
        arrivals=arrivals_map(lessons, ids),
        homework=homework.graded_map([lesson.pk for lesson in lessons], ids) if lessons else {},
        homework_weight=weight if included else 0.0,
    )
    if store is not None:
        store.contexts[key] = context
    return context


# --- Ученик по всем предметам ---------------------------------------------------


def student_courses(student_id: int, on: dt.date | None = None) -> list[Course]:
    """Журналы, где ученик состоит на дату — по порядку предметов.

    Только предметы, которые ведутся в LMS: оценки, успеваемость и отчёты
    по «только расписание» не считаются (решение владельца, 07.10.2026).
    """
    cohorts = cohorts_of_student(student_id, on)
    return list(
        Course.objects.filter(cohort_id__in=cohorts, subject__in_lms=True)
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
class AttendanceTotals(Presence):
    """Посещаемость ученика за период по всем урокам, с разбивкой по дням."""

    days: dict = field(default_factory=dict)
    #: все отметки по дням, включая «был» — учебные дни отчёта по шаблону школы
    marked: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "absent": self.absent,
            "excused": self.excused,
            "late": self.late,
            "late_minutes": self.late_minutes,
            "late_unknown": self.late_unknown,
            "pct": self.pct,
        }


def student_attendance(student_id: int, start: dt.date, end: dt.date) -> AttendanceTotals:
    """Посещаемость ученика по всем урокам за период, с разбивкой по дням."""
    from academics.schedule import for_student, live_lessons, student_lessons

    store = cache.current()
    if store is not None and store.has_lessons(start, end):
        lessons = for_student(live_lessons(start, end), student_id)
    else:
        lessons = student_lessons(student_id, start, end)
    marks = marks_map(lessons, [student_id])
    arrivals = arrivals_map(lessons, [student_id])
    rules = minute_rules()
    out = AttendanceTotals()
    for lesson in lessons:
        mark = marks.get((lesson.pk, student_id))
        if mark is None:
            continue
        out.count(lesson, mark, arrivals.get((lesson.pk, student_id)), rules)
        out.marked.setdefault(lesson.date, []).append(mark)
        if mark != "present":
            out.days.setdefault(lesson.date, []).append((lesson, mark))
    return out


def attendance_by_students(student_ids: list[int], start: dt.date, end: dt.date) -> dict[int, AttendanceTotals]:
    """Посещаемость многих учеников за период — без запроса на каждого.

    Считается по отметкам: урок без отметки в счёт не идёт (как и в
    `student_attendance`), поэтому обходить составы не нужно — живые уроки
    периода читаются один раз, отметки — одной картой.
    """
    from academics.cohorts import member_ids
    from academics.schedule import live_lessons

    lessons = live_lessons(start, end)
    marks = marks_map(lessons, student_ids)
    arrivals = arrivals_map(lessons, student_ids)
    rules = minute_rules()
    by_id = {lesson.pk: lesson for lesson in lessons}
    # карта отметок ставит «был» всем запрошенным по отмеченному уроку —
    # состав урока проверяется отдельно, по членству на дату
    members: dict[tuple[int, dt.date], set[int]] = {}
    out: dict[int, AttendanceTotals] = {sid: AttendanceTotals() for sid in student_ids}
    for (lesson_id, student_id), mark in marks.items():
        totals = out.get(student_id)
        lesson = by_id.get(lesson_id)
        if totals is None or lesson is None:
            continue
        key = (lesson.course.cohort_id, lesson.date)
        if key not in members:
            members[key] = set(member_ids(lesson.course.cohort, lesson.date))
        if student_id not in members[key]:
            continue
        totals.count(lesson, mark, arrivals.get((lesson_id, student_id)), rules)
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
        words = ", ".join(f"{lesson.course.subject.short} — {MARK_WORDS.get(mark, mark)}" for lesson, mark in items)
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
        # опоздания за те же дни — число в карточке ученика; опоздание, которое
        # по правилу школы считается пропуском, сюда не входит: оно в «н»
        "late": totals.late,
        "window_days": days,
        "days": rows,
        "unexcused_days": unexcused_days(student_id, start, end, totals),
    }


def day_rules() -> tuple[int, float]:
    """Пороги «дня без причины» — настройки школы: сколько «н» и какая доля уроков дня."""
    from core import school_rules

    values = school_rules.values()
    return int(values[school_rules.DAY_ABSENT_MIN]), values[school_rules.DAY_ABSENT_SHARE] / 100


def unexcused_days(
    student_id: int,
    start: dt.date,
    end: dt.date,
    totals: AttendanceTotals | None = None,
    rules: tuple[int, float] | None = None,
) -> list[dt.date]:
    """Дни без причины: «н» за день не меньше порога и не меньше доли уроков дня ученика.

    Пороги — настройки школы (`core.school_rules`; по умолчанию 2 «н» и 60 % —
    решение владельца 25.09.2026). Считаются только «н»: «у» уже оформлены
    и в риск не входят. Список учеников передаёт пороги сам (`rules`), чтобы
    не читать их на каждого.
    """
    min_absent, share = rules or day_rules()
    totals = totals or student_attendance(student_id, start, end)
    from academics.schedule import for_student, live_lessons

    out = []
    for day, rows in sorted(totals.days.items()):
        absent = sum(1 for _l, mark in rows if mark == ABSENT)
        if absent < min_absent:
            continue
        day_lessons = for_student(
            [lesson for lesson in live_lessons(start, end) if lesson.date == day and lesson.in_lms], student_id
        )
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
        raise ResultRefused(_("Приём итогов закрыт: изменить итог может только Кымбат или администратор"))
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
            raise ResultRefused(_("Итог — от 2 до 5"))
        if computed is not None and grade != computed and not reason:
            raise ResultRefused(_("Итог отличается от расчёта: напишите причину"))
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
