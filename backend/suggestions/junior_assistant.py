"""Помощник ученика 8–10: только учёба.

Четыре кнопки — неделя, как подтянуть предмет, как считается итог
четверти, план подготовки к СОЧ. Операций поступления у 8–10 нет вовсе:
кнопок вузов, готовности и задач плана им не показывают и не выполняют,
а в модель не уходит ничего о поступлении.

Модели передаются только свои оценки и комментарии учителя по предмету —
без имён учителей и без средних по группе (инвариант №7). Факты собирают
правила; без модели ответ — те же факты с пометкой упрощённого режима.
"""

from __future__ import annotations

import datetime as dt

from academics import calendar as school_calendar
from academics import schedule
from academics.calendar import date_with_weekday, scale_of, today
from academics.models import Grade, Lesson, LessonKind, LessonStatus
from academics.payloads import kind_label
from academics.results import student_summary
from core.phrasing import counted
from students.models import Activity, Competition, Student

#: сколько тем четверти назвать в плане подготовки к СОЧ
TOPICS_IN_PLAN = 8

VOICE_RULES = """Ты помощник по учёбе ученика 8–10 класса школьной платформы.

Тебе передают готовые факты из системы: его уроки, оценки, темы и даты
работ. Твоя работа — коротко и по-русски сказать, что это значит и что
делать дальше.

Правила, нарушать нельзя:
- опирайся ТОЛЬКО на переданные факты, ничего не добавляй от себя;
- не ставь оценок и не обещай их — только советуй, как готовиться;
- не упоминай поступление, вузы, экзамены IELTS и SAT — у ученика их нет;
- не сравнивай ученика с классом и не называй средних по группе;
- три-шесть предложений или короткий список, без вступлений."""

CHAT_RULES = (
    "Ты помощник по учёбе ученика 8–10 класса. Отвечай коротко и по-русски. "
    "Помогай разобраться в предмете и спланировать подготовку, но не решай "
    "контрольные за ученика и не ставь оценок. Не говори о поступлении, вузах "
    "и экзаменах IELTS и SAT — у ученика их нет. Не сравнивай его с классом."
)


def _quarter(calendar):
    quarter = calendar.current_quarter()
    current = today()
    if quarter is None:
        return None, current.replace(day=1), current
    return quarter, quarter.starts, min(quarter.ends, current)


def _subjects(student: Student) -> list[dict]:
    """Предметы четверти со своими баллами: процент выходит, ФО, СОР, СОЧ."""
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    quarter, start, end = _quarter(calendar)
    rows = []
    for item in student_summary(student.pk, start, max(start, end), scale, quarter=quarter):
        course, stats = item["course"], item["stats"]
        rows.append({"course": course, "stats": stats, "pct": stats.quarter_pct})
    return rows


def weakest_subject(student: Student) -> dict | None:
    """Предмет, где итог четверти выходит ниже всего; без оценок — None."""
    graded = [row for row in _subjects(student) if row["pct"] is not None]
    return min(graded, key=lambda row: row["pct"]) if graded else None


def nearest_soch(student: Student) -> Lesson | None:
    current = today()
    lessons = (
        schedule.lessons_between(current, current + dt.timedelta(days=120))
        .filter(kind=LessonKind.SOCH)
        .exclude(status=LessonStatus.CANCELLED)
    )
    found = sorted(
        (lesson for lesson in schedule.for_student(list(lessons), student.pk) if lesson.is_live),
        key=lambda lesson: (lesson.date, lesson.slot),
    )
    return found[0] if found else None


def hints(student: Student) -> dict[str, str]:
    """Подписи кнопок с предметом: «Казахский язык — ниже всего в четверти»."""
    weakest = weakest_subject(student)
    soch = nearest_soch(student)
    return {
        "improve_subject": (
            f"{weakest['course'].subject.title} — ниже всего в четверти" if weakest else "Когда появятся оценки"
        ),
        "soch_plan": (
            f"{soch.course.subject.title}, {date_with_weekday(soch.date)}" if soch else "Ближайшего СОЧ пока нет"
        ),
    }


def _reply(text: str, lines: list[str] | None = None) -> dict:
    from suggestions.assistant import _reply as base

    return base(text, lines=lines or [])


def week(*, student: Student, **_kwargs) -> dict:
    """Уроки недели по дням, работы СОР и СОЧ, олимпиады и соревнования."""
    current = today()
    monday = current - dt.timedelta(days=current.weekday())
    sunday = monday + dt.timedelta(days=6)
    lessons = [
        lesson
        for lesson in schedule.for_student(list(schedule.lessons_between(monday, sunday)), student.pk)
        if lesson.is_live
    ]
    lines = []
    by_day: dict[dt.date, int] = {}
    for lesson in lessons:
        by_day[lesson.date] = by_day.get(lesson.date, 0) + 1
    for day in sorted(by_day):
        lines.append(f"{date_with_weekday(day)}: {counted(by_day[day], ('урок', 'урока', 'уроков'))}")
    for lesson in sorted(lessons, key=lambda row: (row.date, row.slot)):
        if lesson.kind != LessonKind.FO:
            lines.append(f"{kind_label(lesson)} — {lesson.course.subject.title}, {date_with_weekday(lesson.date)}")
    for row in Activity.objects.filter(student=student, category="olympiad", date__gte=monday, date__lte=sunday):
        lines.append(f"Олимпиада: {row.title}, {date_with_weekday(row.date)}")
    for row in Competition.objects.filter(student=student, date__gte=monday, date__lte=sunday):
        lines.append(f"Соревнование: {row.name}, {date_with_weekday(row.date)}")
    if not lines:
        return _reply("На этой неделе уроков в расписании нет.")
    return _reply("Ваша неделя:", lines)


def improve_subject(*, student: Student, **_kwargs) -> dict:
    """Предмет, где итог ниже всего: свои оценки и комментарии учителя, без имён."""
    weakest = weakest_subject(student)
    if weakest is None:
        return _reply("Оценок за четверть пока нет — подсказать, что подтянуть, не по чему.")
    course, stats = weakest["course"], weakest["stats"]
    subject = course.subject.title
    lines = [f"Сейчас выходит: {round(weakest['pct'])}%"]
    if stats.fo:
        lines.append(f"ФО: {', '.join(str(value) for value in stats.fo)} (из {stats.fo_max})")
    if stats.sor_max:
        lines.append(f"СОР: {stats.sor_got} из {stats.sor_max}")
    else:
        lines.append("СОР за четверть ещё не было")
    if stats.soch_max:
        lines.append(f"СОЧ: {stats.soch_got} из {stats.soch_max}")
    _quarter_row, start, end = _quarter(school_calendar.load())
    comments = (
        Grade.objects.filter(student=student, lesson__course=course, lesson__date__gte=start, lesson__date__lte=end)
        .exclude(comment="")
        .order_by("-lesson__date")
        .values_list("comment", flat=True)[:3]
    )
    lines += [f"Комментарий учителя: {comment}" for comment in comments]
    parts = {"ФО": stats.fo_pct, "СОР": stats.sor_pct, "СОЧ": stats.soch_pct}
    known = {name: value for name, value in parts.items() if value is not None}
    if known:
        lowest = min(known, key=known.get)
        lines.append(f"Слабее всего — {lowest}: {round(known[lowest])}%")
    return _reply(f"Ниже всего в четверти — {subject}.", lines)


def quarter_formula(*, student: Student, **_kwargs) -> dict:
    """Как считается итог четверти — из шкалы школы, а не из памяти модели."""
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    lines = [
        f"ФО — средняя оценка из {scale.fo_max}, её вес {scale.weight_fo}%",
        f"СОР — сумма баллов к сумме максимумов, вес {scale.weight_sor}%",
        f"СОЧ — баллы к максимуму, вес {scale.weight_soch}%",
        "Пока какой-то части нет, её вес делится между остальными",
        f"Оценка по порогам: от {scale.threshold_5}% — 5, от {scale.threshold_4}% — 4, от {scale.threshold_3}% — 3",
        "«Сейчас выходит» на экране «Оценки» считается по той же формуле",
    ]
    return _reply("Итог четверти считается по шкале школы:", lines)


def soch_plan(*, student: Student, **_kwargs) -> dict:
    """План подготовки к ближайшему СОЧ: дата, свои баллы по предмету, темы четверти."""
    soch = nearest_soch(student)
    if soch is None:
        return _reply("Ближайшего СОЧ в расписании нет — план строить не к чему.")
    current = today()
    days = (soch.date - current).days
    subject = soch.course.subject.title
    lines = [f"{subject}: СОЧ {date_with_weekday(soch.date)}, осталось {counted(days, ('день', 'дня', 'дней'))}"]
    for row in _subjects(student):
        if row["course"].pk == soch.course_id:
            stats = row["stats"]
            if stats.sor_max:
                lines.append(f"СОР по предмету: {stats.sor_got} из {stats.sor_max}")
            if stats.fo:
                lines.append(f"ФО: {', '.join(str(value) for value in stats.fo)}")
    _quarter_row, start, _end = _quarter(school_calendar.load())
    topics = list(
        Lesson.objects.filter(course=soch.course, date__gte=start, date__lt=soch.date)
        .exclude(topic="")
        .order_by("date")
        .values_list("topic", flat=True)
    )
    unique = list(dict.fromkeys(topics))[-TOPICS_IN_PLAN:]
    if unique:
        lines.append("Темы четверти: " + "; ".join(unique))
    weeks = max(1, days // 7)
    lines.append(
        f"Разбейте темы на {counted(weeks, ('неделю', 'недели', 'недель'))}: "
        "повторение, задания как в СОР, пробная работа за день-два до СОЧ"
    )
    return _reply(f"План подготовки к СОЧ по предмету «{subject}»:", lines)


HANDLERS = {
    "week": week,
    "improve_subject": improve_subject,
    "quarter_formula": quarter_formula,
    "soch_plan": soch_plan,
}
