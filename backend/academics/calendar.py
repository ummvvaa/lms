"""Календарь учебного года: учебные дни, четверти, звонки, «сейчас».

Все даты — по Алматы (`timezone.localdate()`), никакого `date.today()`:
после полуночи по UTC школа ещё живёт вчерашним днём, и урок в 8:30
не должен считаться «вчерашним».
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.utils import timezone

from academics.models import AcademicYear, Break, GradingScale, Quarter, ReportSettings

#: Уроков в дне по умолчанию — для звонков посева и пустого года
DEFAULT_BELLS: tuple[tuple[int, str, str], ...] = (
    (1, "08:30", "09:15"),
    (2, "09:25", "10:10"),
    (3, "10:25", "11:10"),
    (4, "11:25", "12:10"),
    (5, "12:20", "13:05"),
    (6, "13:15", "14:00"),
    (7, "14:10", "14:55"),
    (8, "15:05", "15:50"),
)

WEEKDAYS_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
WEEKDAYS_FULL = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
MONTHS_NOMINATIVE = (
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)


def today() -> dt.date:
    """Сегодня по Алматы — единственное место, откуда берётся «сегодня»."""
    return timezone.localdate()


def now_local() -> dt.datetime:
    return timezone.localtime()


def week_start(day: dt.date) -> dt.date:
    """Понедельник недели, в которую входит день."""
    return day - dt.timedelta(days=day.weekday())


def days_between(start: dt.date, end: dt.date) -> list[dt.date]:
    """Все дни от `start` до `end` включительно."""
    if end < start:
        return []
    return [start + dt.timedelta(days=offset) for offset in range((end - start).days + 1)]


def date_words(day: dt.date) -> str:
    """«25 сентября» — как человек называет день."""
    return f"{day.day} {MONTHS_GENITIVE[day.month - 1]}"


def date_with_weekday(day: dt.date) -> str:
    """«пт, 25 сентября»."""
    return f"{WEEKDAYS_SHORT[day.weekday()]}, {date_words(day)}"


def month_title(day: dt.date) -> str:
    """«сентябрь 2026» — название месяца для отчёта и файла."""
    return f"{MONTHS_NOMINATIVE[day.month - 1]} {day.year}"


def current_year() -> AcademicYear | None:
    """Текущий учебный год; нет помеченного — тот, в который попадает сегодня."""
    year = AcademicYear.objects.filter(is_current=True).first()
    if year is not None:
        return year
    day = today()
    return AcademicYear.objects.filter(starts__lte=day, ends__gte=day).first()


def scale_of(year: AcademicYear | None) -> GradingScale:
    """Шкала года; без записи — умолчания модели, чтобы расчёт не падал."""
    if year is None:
        return GradingScale()
    scale, _ = GradingScale.objects.get_or_create(year=year)
    return scale


def report_settings_of(year: AcademicYear | None) -> ReportSettings:
    if year is None:
        return ReportSettings()
    row, _ = ReportSettings.objects.get_or_create(year=year)
    return row


@dataclass(frozen=True)
class SchoolCalendar:
    """Год целиком в памяти: учебные дни считаются без запросов в цикле."""

    year: AcademicYear | None
    quarters: tuple[Quarter, ...]
    breaks: tuple[Break, ...]
    holidays: frozenset[dt.date]
    bells: dict[int, tuple[dt.time, dt.time]]

    def is_school_day(self, day: dt.date) -> bool:
        """Учебный день: будни внутри четверти, не каникулы и не праздник."""
        if day.weekday() >= 5 or day in self.holidays:
            return False
        if any(b.starts <= day <= b.ends for b in self.breaks):
            return False
        return any(q.starts <= day <= q.ends for q in self.quarters)

    def quarter_of(self, day: dt.date) -> Quarter | None:
        for quarter in self.quarters:
            if quarter.starts <= day <= quarter.ends:
                return quarter
        return None

    def current_quarter(self) -> Quarter | None:
        """Четверть, которая идёт сегодня, иначе ближайшая следующая, иначе последняя."""
        day = today()
        found = self.quarter_of(day)
        if found is not None:
            return found
        ahead = [q for q in self.quarters if q.starts > day]
        if ahead:
            return ahead[0]
        return self.quarters[-1] if self.quarters else None

    def bell(self, slot: int) -> tuple[dt.time, dt.time] | None:
        return self.bells.get(slot)

    def slot_state(self, day: dt.date, slot: int, at: dt.datetime | None = None) -> str:
        """`past`, `now` или `future` для урока в этот день и номер."""
        moment = at or now_local()
        if day < moment.date():
            return "past"
        if day > moment.date():
            return "future"
        bell = self.bell(slot)
        if bell is None:
            return "future"
        if moment.time() >= bell[1]:
            return "past"
        if moment.time() >= bell[0]:
            return "now"
        return "future"

    def current_slot(self, at: dt.datetime | None = None) -> int | None:
        moment = at or now_local()
        for slot, (starts, ends) in sorted(self.bells.items()):
            if starts <= moment.time() < ends:
                return slot
        return None

    def lesson_started(self, day: dt.date, slot: int) -> bool:
        return self.slot_state(day, slot) != "future"

    def lesson_finished(self, day: dt.date, slot: int) -> bool:
        return self.slot_state(day, slot) == "past"

    @property
    def slots(self) -> list[int]:
        return sorted(self.bells) or [n for n, _s, _e in DEFAULT_BELLS]


def load(year: AcademicYear | None = None) -> SchoolCalendar:
    """Собрать календарь года одним набором запросов."""
    year = year or current_year()
    if year is None:
        bells = {n: (dt.time.fromisoformat(s), dt.time.fromisoformat(e)) for n, s, e in DEFAULT_BELLS}
        return SchoolCalendar(year=None, quarters=(), breaks=(), holidays=frozenset(), bells=bells)
    bells = {b.number: (b.starts, b.ends) for b in year.bells.all()}
    if not bells:
        bells = {n: (dt.time.fromisoformat(s), dt.time.fromisoformat(e)) for n, s, e in DEFAULT_BELLS}
    return SchoolCalendar(
        year=year,
        quarters=tuple(year.quarters.order_by("number")),
        breaks=tuple(year.breaks.all()),
        holidays=frozenset(year.holidays.values_list("date", flat=True)),
        bells=bells,
    )


def bell_text(calendar: SchoolCalendar, slot: int) -> str:
    bell = calendar.bell(slot)
    return f"{bell[0]:%H:%M}–{bell[1]:%H:%M}" if bell else ""


def period_bounds(calendar: SchoolCalendar, code: str) -> tuple[dt.date, dt.date, str]:
    """Границы периода по коду: `week`, `month`, `q<N>` или `ГГГГ-ММ`.

    Возвращает начало, конец и название словами. Неизвестный код — текущий месяц.
    """
    day = today()
    if code == "week":
        start = week_start(day)
        return start, start + dt.timedelta(days=6), "эта неделя"
    if code.startswith("q") and code[1:].isdigit():
        number = int(code[1:])
        for quarter in calendar.quarters:
            if quarter.number == number:
                return quarter.starts, quarter.ends, quarter.title
    if len(code) == 7 and code[4] == "-" and code[:4].isdigit() and code[5:].isdigit():
        first = dt.date(int(code[:4]), int(code[5:]), 1)
        last = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        return first, last, month_title(first)
    first = day.replace(day=1)
    last = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return first, last, month_title(first)


def period_choices(calendar: SchoolCalendar) -> list[dict]:
    """Периоды для переключателей: неделя, текущий месяц, четверти года."""
    day = today()
    out = [
        {"code": "week", "title": "Неделя"},
        {"code": f"{day.year}-{day.month:02d}", "title": MONTHS_NOMINATIVE[day.month - 1].capitalize()},
    ]
    for quarter in calendar.quarters:
        out.append({"code": f"q{quarter.number}", "title": quarter.title})
    return out
