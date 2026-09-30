"""Помощник учителя: только чтение и только свои ученики.

Пять кнопок — уроки сегодня и на неделю, неотмеченные уроки, кто отстаёт
по моему предмету, у кого нет оценок, ближайшие СОР и СОЧ — и свободный
вопрос. Граница одна с экранами учителя (`core.scope`): ученики его
составов из расписания и состав урока на замене — в день урока. Уроки
замены на неделе видны, но без состава.

Писать помощник не может ничего: ни оценок, ни отметок, ни предложений.
Пороги «отстаёт» и окно «нет оценок» — настройки администратора
(`core.school_rules`), а не числа в коде.
"""

from __future__ import annotations

import datetime as dt

from django.utils.translation import gettext as _

from academics import calendar as school_calendar
from academics import teachers
from academics.calendar import WEEKDAYS_SHORT, by_time, date_with_weekday, lesson_groups, scale_of, today, week_start
from academics.models import Course, LessonKind, Scheme
from academics.payloads import kind_label
from academics.results import course_context
from core import school_rules
from core.phrasing import tn
from core.scope import visible_ids
from students.models import Student

VOICE_RULES = (  # i18n-skip: промпт модели
    """Ты помощник учителя школьной платформы.

Тебе передают готовые факты из системы: уроки учителя, отметки и оценки
его учеников. Твоя работа — коротко и по-русски сказать, что это значит
и что сделать дальше.

Правила, нарушать нельзя:
- опирайся ТОЛЬКО на переданные факты, ничего не добавляй от себя;
- говори только об учениках из фактов: о других данных нет;
- не ставь и не меняй оценок, не обещай внести что-то за учителя;
- учеников называй ровно так, как они названы в фактах («ученик 3»):
  имена подставит система;
- три-пять предложений или короткий список, без вступлений."""
)  # fmt: skip

CHAT_RULES = (  # i18n-skip: промпт модели
    "Ты помощник учителя школьной платформы. Отвечай коротко и по-русски. "
    "Ниже — факты из журналов учителя: только его ученики и его уроки. Отвечай "
    "только по этим фактам; об учениках, которых в фактах нет, скажи прямо, что "
    "данных о них у тебя нет. Не ставь и не меняй оценок, не обещай внести что-то "
    "в журнал — это делает учитель сам. Учеников в фактах называй так, как они "
    "названы («ученик 3»): имена подставит система."
)

#: сколько строк-фактов уходит в модель на свободный вопрос
MAX_FACTS = 150

#: за сколько дней вперёд искать СОР и СОЧ — как на экране «Сегодня»
ASSESSMENTS_AHEAD = 30


def _reply(text: str, lines: list[str] | None = None) -> dict:
    from suggestions.assistant import _reply as base

    return base(text, lines=lines or [])


def _name(student: Student) -> str:
    return f"{student.last_name} {student.first_name}".strip()


def _lessons(number: int) -> str:
    """«3 урока» — число уроков словом на языке ответа."""
    return tn(number, "{n} урок|{n} урока|{n} уроков")


def _swap(lesson, user) -> str:
    """Пометка замены после названия урока."""
    return " " + _("(замена)") if lesson.substitute_id == user.pk else ""


def _lesson_line(lesson, user, calendar=None) -> str:
    """«10:15, 1 урок — английский BOSTON, СОР 1 (замена)»: время — по звонкам группы урока."""
    calendar = calendar or school_calendar.load()
    bell = calendar.bell(lesson.slot, lesson_groups(lesson))
    at = f"{bell[0]:%H:%M}, " if bell else ""
    kind = f", {kind_label(lesson)}" if lesson.kind != LessonKind.FO else ""
    course = f"{lesson.course.subject.short_title.lower()} {lesson.course.cohort.name}"
    return at + _("{slot} урок — {course}").format(slot=lesson.slot, course=course) + kind + _swap(lesson, user)


def _quarter(calendar):
    quarter = calendar.current_quarter()
    current = today()
    if quarter is None:
        return None, current.replace(day=1), current
    return quarter, quarter.starts, max(quarter.starts, min(quarter.ends, current))


def own_courses(user) -> list[Course]:
    """Свои журналы: по ним «отстаёт» и «нет оценок». Замена журнала не даёт."""
    return list(
        Course.objects.filter(teacher=user, archived_at__isnull=True)
        .select_related("subject", "cohort", "cohort__group")
        .order_by("subject__order", "cohort__name")
    )


def people_of(user, student_ids=None) -> dict[int, Student]:
    """Ученики, о которых учителю можно спрашивать: его составы и только они."""
    ids = visible_ids(user, student_ids)
    return {s.pk: s for s in Student.objects.filter(pk__in=ids)}


# --- Кнопки ------------------------------------------------------------------


def _week(actor) -> tuple[str, list[str]]:
    """Уроки сегодня по звонкам, дальше — по дню на строку до конца недели."""
    day = today()
    end = week_start(day) + dt.timedelta(days=6)
    calendar = school_calendar.load()
    # по времени звонков, а не по номеру: 1 урок 10 класса идёт после 2 урока 8-го
    rows = [lesson for lesson in by_time(teachers.lessons_of(actor, day, end), calendar) if lesson.is_live]
    if not rows:
        return _("До конца недели уроков у вас нет."), []
    todays = [lesson for lesson in rows if lesson.date == day]
    lines = [_lesson_line(lesson, actor, calendar) for lesson in todays]
    later: dict[dt.date, list] = {}
    for lesson in rows:
        if lesson.date != day:
            later.setdefault(lesson.date, []).append(lesson)
    for date, lessons in sorted(later.items()):
        titles = ", ".join(
            f"{lesson.course.subject.short_title.lower()} {lesson.course.cohort.name}" + _swap(lesson, actor)
            for lesson in lessons
        )
        lines.append(f"{WEEKDAYS_SHORT[date.weekday()]} {date:%d.%m} — {_lessons(len(lessons))}: {titles}")
    head = (
        tn(len(todays), "Сегодня {n} урок|Сегодня {n} урока|Сегодня {n} уроков") if todays else _("Сегодня уроков нет")
    )
    total = tn(
        len(rows),
        "{today}, до конца недели всего {n} урок.|"
        "{today}, до конца недели всего {n} урока.|"
        "{today}, до конца недели всего {n} уроков.",
        today=head,
    )
    return total, lines


def lessons_week(*, actor, **_kwargs) -> dict:
    text, lines = _week(actor)
    return _reply(text, lines=lines)


def unmarked(*, actor, **_kwargs) -> dict:
    """Прошедшие уроки без сохранённой посещаемости — как на экране «Сегодня»."""
    calendar = school_calendar.load()
    rows = teachers.unmarked_lessons(actor, calendar)
    if not rows:
        return _reply(_("Все прошедшие уроки за неделю отмечены."))
    lines = [f"{date_with_weekday(lesson.date)}, {_lesson_line(lesson, actor)}" for lesson in rows]
    return _reply(
        _("Не отмечено уроков: {count}. Отметить можно в журнале или на экране урока.").format(count=len(rows)),
        lines=lines,
    )


def lagging(*, actor, student_ids=None, **_kwargs) -> dict:
    """Кто отстаёт по моему предмету: четвертная, ФО и посещаемость ниже порогов."""
    rules = school_rules.values()
    grade_below = rules[school_rules.QUARTER_GRADE_BELOW]
    fo_below = rules[school_rules.FO_ONLY_BELOW]
    attendance_below = rules[school_rules.ATTENDANCE_BELOW]
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    quarter, start, end = _quarter(calendar)
    people = people_of(actor, student_ids)
    lines: list[str] = []
    for course in own_courses(actor):
        context = course_context(course, start, end, scale, quarter=quarter)
        title = f"{course.subject.short_title.lower()} {course.cohort.name}"
        for sid in context.student_ids:
            student = people.get(sid)
            if student is None:
                continue
            stats = context.stats(sid)
            why: list[str] = []
            if course.subject.scheme == Scheme.FO:
                if stats.fo_pct is not None and stats.fo_pct < fo_below:
                    why.append(
                        _("средний ФО {average} из {maximum}").format(average=stats.fo_avg, maximum=stats.fo_max)
                    )
            else:
                grade = stats.final or stats.quarter_grade
                if grade is not None and grade < grade_below:
                    why.append(_("за четверть выходит {grade}").format(grade=grade))
            if stats.attendance_pct is not None and stats.attendance_pct < attendance_below:
                why.append(_("посещаемость {percent} %").format(percent=stats.attendance_pct))
            if why:
                lines.append(f"{_name(student)} — {title}: {', '.join(why)}")
    if not lines:
        return _reply(
            _(
                "Отстающих нет: четвертная не ниже {grade}, ФО не ниже {fo} %, посещаемость не ниже {attendance} %."
            ).format(grade=grade_below, fo=fo_below, attendance=attendance_below)
        )
    return _reply(_("Отстают по вашим предметам: {count}.").format(count=len(lines)), lines=lines)


def no_grades(*, actor, student_ids=None, **_kwargs) -> dict:
    """Были на уроках за окно, а оценок нет ни одной — по каждому журналу."""
    days = school_rules.value(school_rules.NO_GRADES_DAYS)
    end = today()
    start = end - dt.timedelta(days=days - 1)
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    people = people_of(actor, student_ids)
    lines: list[str] = []
    for course in own_courses(actor):
        context = course_context(course, start, end, scale)
        held = [lesson for lesson in context.lessons if lesson.is_marked]
        if not held:
            continue
        title = f"{course.subject.short_title.lower()} {course.cohort.name}"
        for sid in context.student_ids:
            student = people.get(sid)
            if student is None:
                continue
            present = [lesson for lesson in held if context.marks.get((lesson.pk, sid)) in ("present", "late")]
            if not present:
                continue
            if any((lesson.pk, sid) in context.grades for lesson in context.lessons):
                continue
            lines.append(
                tn(
                    len(present),
                    "{student} — {course}: {n} урок, оценок нет|"
                    "{student} — {course}: {n} урока, оценок нет|"
                    "{student} — {course}: {n} уроков, оценок нет",
                    student=_name(student),
                    course=title,
                )
            )
    if not lines:
        return _reply(
            tn(
                days,
                "За последние {n} день у всех, кто был на уроках, есть оценки.|"
                "За последние {n} дня у всех, кто был на уроках, есть оценки.|"
                "За последние {n} дней у всех, кто был на уроках, есть оценки.",
            )
        )
    return _reply(
        tn(
            days,
            "Без оценок за последние {n} день: {count}.|"
            "Без оценок за последние {n} дня: {count}.|"
            "Без оценок за последние {n} дней: {count}.",
            count=len(lines),
        ),
        lines=lines,
    )


def _assessments(actor) -> tuple[str, list[str]]:
    """Ближайшие СОР и СОЧ в моих составах — свои уроки и замены."""
    calendar = school_calendar.load()
    day = today()
    rows = [
        lesson
        for lesson in by_time(teachers.lessons_of(actor, day, day + dt.timedelta(days=ASSESSMENTS_AHEAD)), calendar)
        if lesson.is_live
        and lesson.kind != LessonKind.FO
        and not calendar.lesson_finished(lesson.date, lesson.slot, lesson_groups(lesson))
    ]
    if not rows:
        none_ahead = tn(
            ASSESSMENTS_AHEAD,
            "В ближайшие {n} день СОР и СОЧ у вас нет.|"
            "В ближайшие {n} дня СОР и СОЧ у вас нет.|"
            "В ближайшие {n} дней СОР и СОЧ у вас нет.",
        )
        return none_ahead, []
    lines = []
    for lesson in rows:
        template = (
            _("{date}, {slot} урок — {kind} · {course}, максимум {score}")
            if lesson.max_score
            else _("{date}, {slot} урок — {kind} · {course}")
        )
        lines.append(
            template.format(
                date=date_with_weekday(lesson.date),
                slot=lesson.slot,
                kind=kind_label(lesson),
                course=f"{lesson.course.subject.short_title.lower()} {lesson.course.cohort.name}",
                score=lesson.max_score,
            )
        )
    return _("Ближайшие СОР и СОЧ: {count}.").format(count=len(rows)), lines


def assessments(*, actor, **_kwargs) -> dict:
    text, lines = _assessments(actor)
    return _reply(text, lines=lines)


HANDLERS = {
    "lessons_week": lessons_week,
    "unmarked": unmarked,
    "lagging": lagging,
    "no_grades": no_grades,
    "assessments": assessments,
}


# --- Свободный вопрос ----------------------------------------------------------


def facts(actor, student_ids=None) -> tuple[list[str], list[Student]]:
    """Факты для свободного вопроса: уроки недели и строка на ученика в каждом журнале.

    Только ученики учителя (`core.scope`); выбор с экрана сужает список.
    Имена — как в журнале, обезличит их `assistant._hide_names`.
    """
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    quarter, start, end = _quarter(calendar)
    people = people_of(actor, student_ids)
    week, days = _week(actor)
    ahead, works = _assessments(actor)
    out = [week, *days, ahead, *works]
    seen: list[Student] = []
    # строки фактов уходят в модель, а не на экран
    for course in own_courses(actor):  # i18n-skip: факты для промпта модели
        context = course_context(course, start, end, scale, quarter=quarter)
        title = f"{course.subject.title} {course.cohort.name}"
        for sid in context.student_ids:
            student = people.get(sid)
            if student is None:
                continue
            stats = context.stats(sid)
            parts = []
            if course.subject.scheme == Scheme.FO:
                parts.append(f"средний ФО {stats.fo_avg}" if stats.fo_avg is not None else "оценок ФО нет")
            else:
                grade = stats.final or stats.quarter_grade
                parts.append(f"за четверть выходит {grade}" if grade is not None else "четвертная не выходит")
                if stats.fo_avg is not None:
                    parts.append(f"ФО {stats.fo_avg}")
                if stats.sor_max:
                    parts.append(f"СОР {stats.sor_got} из {stats.sor_max}")
                if stats.soch_max:
                    parts.append(f"СОЧ {stats.soch_got} из {stats.soch_max}")
            if stats.attendance_pct is not None:
                parts.append(f"посещаемость {stats.attendance_pct} %, не был {stats.absent + stats.excused}")
            out.append(f"{title} — {_name(student)}: {', '.join(parts)}")
            if student not in seen:
                seen.append(student)
            if len(out) >= MAX_FACTS:
                return out, seen
    return out, seen
