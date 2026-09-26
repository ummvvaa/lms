"""Кэш на один запрос: составы, уроки, отметки и оценки читаются из базы один раз.

Экран посещаемости за месяц — это сотни уроков на два десятка учеников,
и без кэша каждый вызов `member_ids` и `marks_map` ходил в базу заново:
день группы собирался за десятки секунд. Кэш живёт ровно один запрос
(или одну фоновую задачу): между запросами ничего не хранится, поэтому
перевод ученика в другую подгруппу виден следующим же запросом.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import NamedTuple


class GradeRow(NamedTuple):
    """Оценка без модели: тысячи строк за период читаются кортежами, а не объектами."""

    lesson_id: int
    student_id: int
    value: int
    comment: str


def _covering(store: dict, start: dt.date, end: dt.date):
    """Уже загруженный период, накрывающий запрошенный, — чтобы не читать базу заново."""
    if (start, end) in store:
        return store[(start, end)]
    for (s, e), rows in store.items():
        if s <= start and e >= end:
            return rows
    return None


class Roster:
    """Составы в памяти: кто в какой группе, подгруппе и потоке на дату."""

    def __init__(self) -> None:
        from academics.models import Cohort, CohortMembership, StreamPart
        from students.models import Student

        self.students: dict[int, tuple[int | None, tuple]] = {}
        self.by_group: dict[int, list[int]] = {}
        for sid, group_id, last, first in (
            Student.objects.filter(is_active=True)
            .order_by("last_name", "first_name", "id")
            .values_list("pk", "group_id", "last_name", "first_name")
        ):
            self.students[sid] = (group_id, (last, first, sid))
            if group_id is not None:
                self.by_group.setdefault(group_id, []).append(sid)
        self.cohorts: dict[int, tuple[str, int | None]] = {
            pk: (kind, group_id) for pk, kind, group_id in Cohort.objects.values_list("pk", "kind", "group_id")
        }
        self.group_cohort: dict[int, int] = {
            group_id: pk for pk, (kind, group_id) in self.cohorts.items() if kind == "group" and group_id
        }
        self.memberships: dict[int, list[tuple[int, dt.date, dt.date | None]]] = {}
        for cohort_id, sid, since, until in CohortMembership.objects.values_list(
            "cohort_id", "student_id", "since", "until"
        ):
            self.memberships.setdefault(cohort_id, []).append((sid, since, until))
        self.parts: dict[int, list[int]] = {}
        for stream_id, part_id in StreamPart.objects.values_list("stream_id", "part_id"):
            self.parts.setdefault(stream_id, []).append(part_id)
        self._members: dict[tuple[int, dt.date], list[int]] = {}

    def _sorted(self, ids: Iterable[int]) -> list[int]:
        return sorted({sid for sid in ids if sid in self.students}, key=lambda sid: self.students[sid][1])

    def members(self, cohort_id: int, on: dt.date) -> list[int]:
        key = (cohort_id, on)
        found = self._members.get(key)
        if found is not None:
            return list(found)
        kind, group_id = self.cohorts.get(cohort_id, ("", None))
        if kind == "group":
            out = list(self.by_group.get(group_id, [])) if group_id else []
        elif kind == "subgroup":
            out = self._sorted(
                sid
                for sid, since, until in self.memberships.get(cohort_id, [])
                if since <= on and (until is None or until > on)
            )
        elif kind == "stream":
            seen: set[int] = set()
            for part in self.parts.get(cohort_id, []):
                seen.update(self.members(part, on))
            out = self._sorted(seen)
        else:
            out = []
        self._members[key] = out
        return list(out)

    def groups_of(self, cohort_id: int) -> list[int]:
        kind, group_id = self.cohorts.get(cohort_id, ("", None))
        if kind in ("group", "subgroup"):
            return [group_id] if group_id else []
        out: list[int] = []
        for part in self.parts.get(cohort_id, []):
            for gid in self.groups_of(part):
                if gid not in out:
                    out.append(gid)
        return out

    def cohorts_of_student(self, student_id: int, on: dt.date) -> list[int]:
        found = self.students.get(student_id)
        if found is None:
            return []
        ids: list[int] = []
        group_id = found[0]
        if group_id is not None and group_id in self.group_cohort:
            ids.append(self.group_cohort[group_id])
        for cohort_id, rows in self.memberships.items():
            if any(sid == student_id and since <= on and (until is None or until > on) for sid, since, until in rows):
                ids.append(cohort_id)
        for stream_id, parts in self.parts.items():
            if any(part in ids for part in parts):
                ids.append(stream_id)
        return list(dict.fromkeys(ids))


class RequestCache:
    """Всё, что читается много раз за один запрос."""

    def __init__(self) -> None:
        self._roster: Roster | None = None
        self.lessons: dict[tuple[dt.date, dt.date], list] = {}
        self.attendance: dict[tuple[dt.date, dt.date], dict[tuple[int, int], str]] = {}
        self.grades: dict[tuple[dt.date, dt.date], dict[tuple[int, int], object]] = {}
        self.excuses: dict[tuple[dt.date, dt.date], dict[int, list[tuple[dt.date, dt.date]]]] = {}
        self.contexts: dict[tuple, object] = {}

    @property
    def roster(self) -> Roster:
        if self._roster is None:
            self._roster = Roster()
        return self._roster

    def forget_roster(self) -> None:
        """Состав поменялся внутри запроса — следующий вызов перечитает."""
        self._roster = None

    def has_lessons(self, start: dt.date, end: dt.date) -> bool:
        return _covering(self.lessons, start, end) is not None

    def live_lessons(self, start: dt.date, end: dt.date) -> list:
        """Живые уроки периода с подгруженными связями — один запрос на период."""
        key = (start, end)
        found = _covering(self.lessons, start, end)
        if found is not None and key not in self.lessons:
            return [lesson for lesson in found if start <= lesson.date <= end]
        if key not in self.lessons:
            from academics.models import Lesson, LessonStatus

            self.lessons[key] = list(
                Lesson.objects.filter(date__gte=start, date__lte=end)
                .exclude(status=LessonStatus.CANCELLED)
                .select_related(
                    "course", "course__subject", "course__cohort", "course__cohort__group", "teacher", "substitute"
                )
                .order_by("date", "slot", "id")
            )
        return self.lessons[key]

    def attendance_rows(self, start: dt.date, end: dt.date) -> dict[tuple[int, int], str]:
        found = _covering(self.attendance, start, end)
        if found is not None:
            return found
        from academics.models import Attendance

        rows = {
            (lesson_id, sid): mark
            for lesson_id, sid, mark in Attendance.objects.filter(
                lesson__date__gte=start, lesson__date__lte=end
            ).values_list("lesson_id", "student_id", "mark")
        }
        self.attendance[(start, end)] = rows
        return rows

    def grade_rows(self, start: dt.date, end: dt.date) -> dict[tuple[int, int], GradeRow]:
        found = _covering(self.grades, start, end)
        if found is not None:
            return found
        from academics.models import Grade

        rows = {
            (lesson_id, sid): GradeRow(lesson_id, sid, value, comment)
            for lesson_id, sid, value, comment in Grade.objects.filter(
                lesson__date__gte=start, lesson__date__lte=end
            ).values_list("lesson_id", "student_id", "value", "comment")
        }
        self.grades[(start, end)] = rows
        return rows

    def excuse_rows(self, start: dt.date, end: dt.date) -> dict[int, list[tuple[dt.date, dt.date]]]:
        found = _covering(self.excuses, start, end)
        if found is not None:
            return found
        from academics.models import Excuse

        out: dict[int, list[tuple[dt.date, dt.date]]] = {}
        for sid, starts, ends in Excuse.objects.filter(starts__lte=end, ends__gte=start).values_list(
            "student_id", "starts", "ends"
        ):
            out.setdefault(sid, []).append((starts, ends))
        self.excuses[(start, end)] = out
        return out

    def forget_marks(self) -> None:
        """Отметки или оценки записаны — карты периода перечитываются."""
        self.attendance.clear()
        self.grades.clear()
        self.excuses.clear()
        self.contexts.clear()


_current: ContextVar[RequestCache | None] = ContextVar("academics_cache", default=None)


def current() -> RequestCache | None:
    return _current.get()


@contextmanager
def scope():
    """Открыть кэш на время блока: вьюха, задача, тест."""
    token = _current.set(RequestCache())
    try:
        yield _current.get()
    finally:
        _current.reset(token)


def cached(view):
    """Вьюха с кэшем на запрос."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        with scope():
            return view(*args, **kwargs)

    return wrapper


def invalidate() -> None:
    """После записи внутри кэшированного блока: карты перечитываются."""
    store = current()
    if store is not None:
        store.forget_marks()
        store.forget_roster()
