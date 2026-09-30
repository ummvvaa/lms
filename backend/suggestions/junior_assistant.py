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

from django.utils.translation import gettext as _

from academics import calendar as school_calendar
from academics import schedule
from academics.calendar import date_with_weekday, scale_of, today
from academics.models import Grade, Lesson, LessonKind, LessonStatus
from academics.payloads import kind_label
from academics.results import student_summary
from core.phrasing import tn
from students.models import Activity, Competition, Student

#: сколько тем четверти назвать в плане подготовки к СОЧ
TOPICS_IN_PLAN = 8

VOICE_RULES = (  # i18n-skip: промпт модели
    """Ты помощник по учёбе ученика 8–10 класса школьной платформы.

Тебе передают готовые факты из системы: его уроки, оценки, темы и даты
работ. Твоя работа — коротко и по-русски сказать, что это значит и что
делать дальше.

Правила, нарушать нельзя:
- опирайся ТОЛЬКО на переданные факты, ничего не добавляй от себя;
- не ставь оценок и не обещай их — только советуй, как готовиться;
- не упоминай поступление, вузы, экзамены IELTS и SAT — у ученика их нет;
- не сравнивай ученика с классом и не называй средних по группе;
- три-шесть предложений или короткий список, без вступлений."""
)  # fmt: skip

CHAT_RULES = (  # i18n-skip: промпт модели
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
            _("{subject} — ниже всего в четверти").format(subject=weakest["course"].subject.title)
            if weakest
            else _("Когда появятся оценки")
        ),
        "soch_plan": (
            f"{soch.course.subject.title}, {date_with_weekday(soch.date)}" if soch else _("Ближайшего СОЧ пока нет")
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
        lessons_count = tn(by_day[day], "{n} урок|{n} урока|{n} уроков")
        lines.append(f"{date_with_weekday(day)}: {lessons_count}")
    for lesson in sorted(lessons, key=lambda row: (row.date, row.slot)):
        if lesson.kind != LessonKind.FO:
            lines.append(f"{kind_label(lesson)} — {lesson.course.subject.title}, {date_with_weekday(lesson.date)}")
    for row in Activity.objects.filter(student=student, category="olympiad", date__gte=monday, date__lte=sunday):
        lines.append(_("Олимпиада: {title}, {date}").format(title=row.title, date=date_with_weekday(row.date)))
    for row in Competition.objects.filter(student=student, date__gte=monday, date__lte=sunday):
        lines.append(_("Соревнование: {title}, {date}").format(title=row.name, date=date_with_weekday(row.date)))
    if not lines:
        return _reply(_("На этой неделе уроков в расписании нет."))
    return _reply(_("Ваша неделя:"), lines)


def improve_subject(*, student: Student, **_kwargs) -> dict:
    """Предмет, где итог ниже всего: свои оценки и комментарии учителя, без имён."""
    weakest = weakest_subject(student)
    if weakest is None:
        return _reply(_("Оценок за четверть пока нет — подсказать, что подтянуть, не по чему."))
    course, stats = weakest["course"], weakest["stats"]
    subject = course.subject.title
    lines = [_("Сейчас выходит: {percent}%").format(percent=round(weakest["pct"]))]
    if stats.fo:
        lines.append(
            _("ФО: {grades} (из {maximum})").format(
                grades=", ".join(str(value) for value in stats.fo), maximum=stats.fo_max
            )
        )
    if stats.sor_max:
        lines.append(_("СОР: {got} из {maximum}").format(got=stats.sor_got, maximum=stats.sor_max))
    else:
        lines.append(_("СОР за четверть ещё не было"))
    if stats.soch_max:
        lines.append(_("СОЧ: {got} из {maximum}").format(got=stats.soch_got, maximum=stats.soch_max))
    _quarter_row, start, end = _quarter(school_calendar.load())
    comments = (
        Grade.objects.filter(student=student, lesson__course=course, lesson__date__gte=start, lesson__date__lte=end)
        .exclude(comment="")
        .order_by("-lesson__date")
        .values_list("comment", flat=True)[:3]
    )
    lines += [_("Комментарий учителя: {comment}").format(comment=comment) for comment in comments]
    parts = {_("ФО"): stats.fo_pct, _("СОР"): stats.sor_pct, _("СОЧ"): stats.soch_pct}
    known = {name: value for name, value in parts.items() if value is not None}
    if known:
        lowest = min(known, key=known.get)
        lines.append(_("Слабее всего — {part}: {percent}%").format(part=lowest, percent=round(known[lowest])))
    return _reply(_("Ниже всего в четверти — {subject}.").format(subject=subject), lines)


def quarter_formula(*, student: Student, **_kwargs) -> dict:
    """Как считается итог четверти — из шкалы школы, а не из памяти модели."""
    calendar = school_calendar.load()
    scale = scale_of(calendar.year)
    lines = [
        _("ФО — средняя оценка из {maximum}, её вес {weight}%").format(maximum=scale.fo_max, weight=scale.weight_fo),
        _("СОР — сумма баллов к сумме максимумов, вес {weight}%").format(weight=scale.weight_sor),
        _("СОЧ — баллы к максимуму, вес {weight}%").format(weight=scale.weight_soch),
        _("Пока какой-то части нет, её вес делится между остальными"),
        _("Оценка по порогам: от {five}% — 5, от {four}% — 4, от {three}% — 3").format(
            five=scale.threshold_5, four=scale.threshold_4, three=scale.threshold_3
        ),
        _("«Сейчас выходит» на экране «Оценки» считается по той же формуле"),
    ]
    return _reply(_("Итог четверти считается по шкале школы:"), lines)


def soch_plan(*, student: Student, **_kwargs) -> dict:
    """План подготовки к ближайшему СОЧ: дата, свои баллы по предмету, темы четверти."""
    soch = nearest_soch(student)
    if soch is None:
        return _reply(_("Ближайшего СОЧ в расписании нет — план строить не к чему."))
    current = today()
    days = (soch.date - current).days
    subject = soch.course.subject.title
    lines = [
        tn(
            days,
            "{subject}: СОЧ {date}, остался {n} день|{subject}: СОЧ {date}, осталось {n} дня|"
            "{subject}: СОЧ {date}, осталось {n} дней",
            subject=subject,
            date=date_with_weekday(soch.date),
        )
    ]
    for row in _subjects(student):
        if row["course"].pk == soch.course_id:
            stats = row["stats"]
            if stats.sor_max:
                lines.append(_("СОР по предмету: {got} из {maximum}").format(got=stats.sor_got, maximum=stats.sor_max))
            if stats.fo:
                lines.append(_("ФО: {grades}").format(grades=", ".join(str(value) for value in stats.fo)))
    _quarter_row, start, _end = _quarter(school_calendar.load())
    topics = list(
        Lesson.objects.filter(course=soch.course, date__gte=start, date__lt=soch.date)
        .exclude(topic="")
        .order_by("date")
        .values_list("topic", flat=True)
    )
    unique = list(dict.fromkeys(topics))[-TOPICS_IN_PLAN:]
    if unique:
        lines.append(_("Темы четверти: {topics}").format(topics="; ".join(unique)))
    weeks = max(1, days // 7)
    lines.append(
        tn(
            weeks,
            "Разбейте темы на {n} неделю: повторение, задания как в СОР, пробная работа за день-два до СОЧ|"
            "Разбейте темы на {n} недели: повторение, задания как в СОР, пробная работа за день-два до СОЧ|"
            "Разбейте темы на {n} недель: повторение, задания как в СОР, пробная работа за день-два до СОЧ",
        )
    )
    return _reply(_("План подготовки к СОЧ по предмету «{subject}»:").format(subject=subject), lines)


HANDLERS = {
    "week": week,
    "improve_subject": improve_subject,
    "quarter_formula": quarter_formula,
    "soch_plan": soch_plan,
}
