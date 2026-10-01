"""Календарь учебного года: учебные дни, четверти, звонки, «сейчас».

Все даты — по Алматы (`timezone.localdate()`), никакого `date.today()`:
после полуночи по UTC школа ещё живёт вчерашним днём, и урок в 8:30
не должен считаться «вчерашним».
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from django.utils import timezone
from django.utils.translation import gettext, gettext_noop

from academics.models import AcademicYear, Bell, BellSchedule, Break, GradingScale, Quarter, ReportSettings
from core import stored_text

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


class Words(tuple):
    """Слова на язык ответа: `WEEKDAYS_SHORT[4]` — «пт», «жм» или «Fri».

    В таблице лежат исходные русские слова (`gettext_noop` — только пометка
    для каталога), перевод берётся при обращении: таблица живёт на уровне
    модуля, а язык у каждого запроса свой. Отдаётся обычная строка — годится
    и для ответа, и для книги Excel. В фоновой задаче языка нет — русский.
    """

    def __getitem__(self, index):
        found = super().__getitem__(index)
        if isinstance(index, slice):
            return tuple(gettext(word) for word in found)
        return gettext(found)

    def __iter__(self):
        return (gettext(word) for word in super().__iter__())


WEEKDAYS_SHORT = Words(
    (
        gettext_noop("пн"),
        gettext_noop("вт"),
        gettext_noop("ср"),
        gettext_noop("чт"),
        gettext_noop("пт"),
        gettext_noop("сб"),
        gettext_noop("вс"),
    )
)
WEEKDAYS_FULL = Words(
    (
        gettext_noop("понедельник"),
        gettext_noop("вторник"),
        gettext_noop("среда"),
        gettext_noop("четверг"),
        gettext_noop("пятница"),
        gettext_noop("суббота"),
        gettext_noop("воскресенье"),
    )
)
#: «25 сентября» — месяц при числе
MONTHS_GENITIVE = Words(
    (
        gettext_noop("января"),
        gettext_noop("февраля"),
        gettext_noop("марта"),
        gettext_noop("апреля"),
        gettext_noop("мая"),
        gettext_noop("июня"),
        gettext_noop("июля"),
        gettext_noop("августа"),
        gettext_noop("сентября"),
        gettext_noop("октября"),
        gettext_noop("ноября"),
        gettext_noop("декабря"),
    )
)
#: «сентябрь 2026» — месяц сам по себе
MONTHS_NOMINATIVE = Words(
    (
        gettext_noop("январь"),
        gettext_noop("февраль"),
        gettext_noop("март"),
        gettext_noop("апрель"),
        gettext_noop("май"),
        gettext_noop("июнь"),
        gettext_noop("июль"),
        gettext_noop("август"),
        gettext_noop("сентябрь"),
        gettext_noop("октябрь"),
        gettext_noop("ноябрь"),
        gettext_noop("декабрь"),
    )
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


Bells = dict[int, tuple[dt.time, dt.time]]


def _default_bells() -> Bells:
    return {n: (dt.time.fromisoformat(s), dt.time.fromisoformat(e)) for n, s, e in DEFAULT_BELLS}


@dataclass(frozen=True)
class SchoolCalendar:
    """Год целиком в памяти: учебные дни считаются без запросов в цикле.

    Звонков у школы несколько (решение владельца, 27.09.2026): `bells` —
    общее расписание, `schedules` — все по номеру, `group_schedule` — какое
    расписание у группы, если не общее. Время урока берётся из звонков его
    группы (`groups=`); без группы — общее.
    """

    year: AcademicYear | None
    quarters: tuple[Quarter, ...]
    breaks: tuple[Break, ...]
    holidays: frozenset[dt.date]
    bells: Bells
    schedules: dict[int, Bells] = field(default_factory=dict)
    schedule_titles: dict[int, str] = field(default_factory=dict)
    group_schedule: dict[int, int] = field(default_factory=dict)

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

    def schedule_ids_of(self, groups) -> set[int | None]:
        """Какие расписания звонков у групп: `None` — общее."""
        return {self.group_schedule.get(g) for g in (groups or [])} or {None}

    def schedule_of(self, groups=None) -> int | None:
        """Расписание звонков состава из этих групп: `None` — общее. То же правило, что `bells_of`."""
        ids = self.schedule_ids_of(groups)
        if len(ids) == 1:
            found = next(iter(ids))
            if found is not None and found in self.schedules:
                return found
        return None

    def bells_of(self, groups=None) -> Bells:
        """Звонки для состава из этих групп. Разные расписания — общее."""
        ids = self.schedule_ids_of(groups)
        if len(ids) == 1:
            found = next(iter(ids))
            if found is not None:
                return self.schedules.get(found, self.bells)
        return self.bells

    def bell(self, slot: int, groups=None) -> tuple[dt.time, dt.time] | None:
        return self.bells_of(groups).get(slot)

    def slot_state(self, day: dt.date, slot: int, at: dt.datetime | None = None, groups=None) -> str:
        """`past`, `now` или `future` для урока в этот день и номер."""
        moment = at or now_local()
        if day < moment.date():
            return "past"
        if day > moment.date():
            return "future"
        bell = self.bell(slot, groups)
        if bell is None:
            return "future"
        if moment.time() >= bell[1]:
            return "past"
        if moment.time() >= bell[0]:
            return "now"
        return "future"

    def current_slot(self, at: dt.datetime | None = None, groups=None) -> int | None:
        moment = at or now_local()
        for slot, (starts, ends) in sorted(self.bells_of(groups).items()):
            if starts <= moment.time() < ends:
                return slot
        return None

    def lesson_started(self, day: dt.date, slot: int, groups=None) -> bool:
        return self.slot_state(day, slot, groups=groups) != "future"

    def lesson_finished(self, day: dt.date, slot: int, groups=None) -> bool:
        return self.slot_state(day, slot, groups=groups) == "past"

    @property
    def slots(self) -> list[int]:
        numbers = set(self.bells)
        for rows in self.schedules.values():
            numbers.update(rows)
        return sorted(numbers) or [n for n, _s, _e in DEFAULT_BELLS]


def default_schedule(year: AcademicYear) -> BellSchedule:
    """Общее расписание звонков года — заводится при первом обращении."""
    found = year.bell_schedules.filter(is_default=True).first()
    if found is None:
        found = BellSchedule.objects.create(year=year, title="Общее", is_default=True)  # i18n-skip: данные в базе
        Bell.objects.filter(year=year, schedule__isnull=True).update(schedule=found)
    return found


def load(year: AcademicYear | None = None) -> SchoolCalendar:
    """Собрать календарь года одним набором запросов."""
    year = year or current_year()
    if year is None:
        return SchoolCalendar(year=None, quarters=(), breaks=(), holidays=frozenset(), bells=_default_bells())
    schedules: dict[int, Bells] = {}
    titles: dict[int, str] = {}
    default_id = None
    for row in year.bell_schedules.all():
        schedules[row.pk] = {}
        titles[row.pk] = row.title
        if row.is_default:
            default_id = row.pk
    for bell in year.bells.all():
        key = bell.schedule_id if bell.schedule_id in schedules else default_id
        if key is None:
            continue
        schedules[key][bell.number] = (bell.starts, bell.ends)
    bells = schedules.get(default_id) or _default_bells()
    if default_id is not None and not schedules.get(default_id):
        schedules[default_id] = bells
    group_schedule = {
        group_id: schedule_id
        for schedule_id, group_id in BellSchedule.groups.through.objects.filter(
            bellschedule__year=year, bellschedule__is_default=False
        ).values_list("bellschedule_id", "studygroup_id")
    }
    return SchoolCalendar(
        year=year,
        quarters=tuple(year.quarters.order_by("number")),
        breaks=tuple(year.breaks.all()),
        holidays=frozenset(year.holidays.values_list("date", flat=True)),
        bells=bells,
        schedules=schedules,
        schedule_titles=titles,
        group_schedule=group_schedule,
    )


def bell_text(calendar: SchoolCalendar, slot: int, groups=None) -> str:
    bell = calendar.bell(slot, groups)
    return f"{bell[0]:%H:%M}–{bell[1]:%H:%M}" if bell else ""


def lesson_groups(lesson) -> list[int]:
    """Группы состава урока — для звонков его группы."""
    from academics.cohorts import group_ids_of

    return group_ids_of(lesson.course.cohort)


def by_time(lessons, calendar: SchoolCalendar) -> list:
    """Уроки по дате и времени начала по звонкам их групп, а не по номеру урока.

    У учителя 1 урок 10 класса (10:15) идёт после 2 урока 8 класса (8:50):
    порядок по номеру поставил бы их наоборот.
    """

    def key(lesson):
        bell = calendar.bell(lesson.slot, lesson_groups(lesson))
        return (lesson.date, bell[0] if bell else dt.time.max, lesson.slot, lesson.pk)

    return sorted(lessons, key=key)


def period_bounds(calendar: SchoolCalendar, code: str) -> tuple[dt.date, dt.date, str]:
    """Границы периода по коду: `week`, `month`, `q<N>` или `ГГГГ-ММ`.

    Возвращает начало, конец и название словами. Неизвестный код — текущий месяц.
    """
    day = today()
    if code == "week":
        start = week_start(day)
        return start, start + dt.timedelta(days=6), gettext("эта неделя")
    if code.startswith("q") and code[1:].isdigit():
        number = int(code[1:])
        for quarter in calendar.quarters:
            if quarter.number == number:
                return quarter.starts, quarter.ends, stored_text.localize(quarter.title)
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
        {"code": "week", "title": gettext("Неделя")},
        {"code": f"{day.year}-{day.month:02d}", "title": MONTHS_NOMINATIVE[day.month - 1].capitalize()},
    ]
    for quarter in calendar.quarters:
        out.append({"code": f"q{quarter.number}", "title": stored_text.localize(quarter.title)})
    return out
