"""Дисциплина: посещаемость днями, замечания строками (фаза 66).

До фазы 66 дисциплина была тремя числами в профиле, и вносила их
Салтанат на всю школу. Числа отвечают на вопрос «сколько», но разговор
с родителем начинается с «когда» и «за что», а этого в числе нет.

Поэтому день и замечание стали строками (инвариант №5), а прежние поля
профиля остались и пересчитываются из строк. Так ничего не сломалось:
готовность, дашборды, правила обзвона и корзина «нужен контроль» читают
те же `attendance_percent` и `remarks_count`, что и раньше.

Прямой ввод чисел у Салтанат сохранён намеренно: за время до системы
строк в базе нет, и стирать историю ради стройности нельзя. Правило
простое — **есть строки, считаем по строкам; строк нет, число остаётся
таким, каким его внесли руками**.

Кто пишет: куратор — по своим группам, Салтанат — по всей школе
(`CURATOR_RIGHTS` в реестре, право «пишет»). Границу «своя группа»
держит общая выборка `core.scope`, второго списка групп здесь нет.

Отметка куратора утром (решение владельца, 19.10.2026): через несколько
минут после первого урока куратор отмечает по каждому ученику своих групп,
в школе он или нет, — строка `AttendanceDay` на ученика и день, только за
сегодня, в тот же день можно поправить. С отметками учителей она не связана:
процент, «Риски» и отчёты родителям считают по урокам (`academics.results`),
а старый процент профиля пересчитывается только из дат до `DAY_MARKS_UNTIL`.
По этим строкам — отчёт «Отсутствующие» для службы безопасности (`absences`).
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from core.audit import record_event
from core.domains import ROLE_CURATOR, ROLE_STUDENT, curator_writes
from core.scope import sees_student
from students.models import AttendanceDay, BehaviorProfile, BehaviorRemark, Student

#: Правка дня старше этого срока помечается в журнале отдельно: задним
#: числом посещаемость меняют редко, и такие правки должны быть заметны
LATE_EDIT_DAYS = 7


def may_write(user, student: Student) -> bool:
    """Вправе ли человек вести дисциплину этого ученика.

    Ученику — никогда, даже про себя: это не его данные о себе, а оценка
    школы (инвариант №7). Куратору — своих, директору школы — любых.
    """
    role = getattr(user, "role", "")
    if role == ROLE_STUDENT:
        return False
    if role == "director_behavior":
        return True
    if role == ROLE_CURATOR and curator_writes("behavior"):
        return sees_student(user, student.pk)
    from core.domains import ROLE_ADMIN

    return role == ROLE_ADMIN


# --- Посещаемость ------------------------------------------------------------


def day_marks_until() -> dt.date | None:
    """До какой даты считаются прежние отметки дня — день запуска уроков.

    После него посещаемость считается по урокам (`academics.results`), а строки
    дня остаются архивом на чтение; пусто в настройках — не считаются вовсе.
    """
    from django.conf import settings

    raw = str(settings.ACADEMICS_RULES.get("DAY_MARKS_UNTIL") or "").strip()
    return dt.date.fromisoformat(raw) if raw else None


def recount_attendance(student: Student) -> int | None:
    """Пересчитать прежний процент посещаемости из отметок дня до даты запуска.

    Строк в счёт нет — не трогать. Возвращает записанный процент или `None`,
    если считать не по чему. На экраны это число не идёт — его заменили уроки.
    """
    until = day_marks_until()
    if until is None:
        return None
    days = AttendanceDay.objects.filter(student=student, date__lte=until)
    total = days.count()
    if not total:
        return None
    present = days.exclude(mark=AttendanceDay.Mark.ABSENT).count()
    percent = round(present * 100 / total)
    profile, _created = BehaviorProfile.objects.get_or_create(student=student)
    if profile.attendance_percent != percent:
        BehaviorProfile.objects.filter(pk=profile.pk).update(attendance_percent=percent)
    return percent


MARKS = (AttendanceDay.Mark.PRESENT, AttendanceDay.Mark.ABSENT, AttendanceDay.Mark.LATE)


#: слова журнала: «был / не был / опоздал» — на экране отметка зовётся «в школе / нет / опоздал»
JOURNAL_WORDS = {
    AttendanceDay.Mark.PRESENT: gettext_noop("был"),
    AttendanceDay.Mark.ABSENT: gettext_noop("не был"),
    AttendanceDay.Mark.LATE: gettext_noop("опоздал"),
}


def mark_words(mark: str) -> str:
    """Отметка словом для журнала."""
    return _(JOURNAL_WORDS.get(mark, JOURNAL_WORDS[AttendanceDay.Mark.PRESENT]))


def mark_label(mark: str) -> str:
    """Отметка словом для экрана и файла: «в школе / нет / опоздал»."""
    return str(AttendanceDay.Mark(mark).label)


def _mark_of(raw) -> str:
    """Отметка из запроса: код или прежнее `present`; мусор — «в школе»."""
    if isinstance(raw, bool):
        return AttendanceDay.Mark.PRESENT if raw else AttendanceDay.Mark.ABSENT
    value = str(raw or "").strip().lower()
    return value if value in MARKS else AttendanceDay.Mark.PRESENT


@transaction.atomic
def mark_day(*, student: Student, date: dt.date, mark: str, reason: str = "", actor) -> AttendanceDay:
    """Отметить один день. Повторная отметка того же дня — правка, не дубль."""
    mark = _mark_of(mark)
    # комментарий есть только у «нет» и «опоздал»
    reason = reason[:200] if mark != AttendanceDay.Mark.PRESENT else ""
    row, created = AttendanceDay.objects.get_or_create(
        student=student,
        date=date,
        defaults={"mark": mark, "reason": reason, "noted_by": _actor(actor)},
    )
    if not created:
        changed = row.mark != mark or row.reason != reason
        row.mark = mark
        row.reason = reason
        row.noted_by = _actor(actor)
        row.save(update_fields=["mark", "reason", "noted_by", "updated_at"])
        if changed and _is_late(date):
            # правка задним числом — отдельной строкой журнала: по ней видно,
            # что посещаемость меняли не в тот день, когда она случилась
            record_event(
                student=student,
                code="attendance_late_edit",
                text=_("{date}: {mark}{reason} (правка спустя {days} дн.)").format(
                    date=f"{date:%d.%m.%Y}",
                    mark=mark_words(mark),
                    reason=f", {reason}" if reason else "",
                    days=(timezone.localdate() - date).days,
                ),
                actor=actor,
            )
    recount_attendance(student)
    return row


def _is_late(date: dt.date) -> bool:
    return (timezone.localdate() - date).days > LATE_EDIT_DAYS


def _actor(actor):
    return actor if getattr(actor, "pk", None) else None


def _journal_mark(student: Student, date: dt.date, was: str | None, now: str, actor) -> None:
    """В журнал — только «нет», «опоздал» и исправление прежней отметки (решение владельца, 19.10.2026)."""
    if was is None and now != AttendanceDay.Mark.PRESENT:
        record_event(
            student=student,
            code="attendance_day",
            text=_("{date}: {mark}").format(date=f"{date:%d.%m.%Y}", mark=mark_words(now)),
            actor=actor,
        )
    elif was is not None and was != now:
        record_event(
            student=student,
            code="attendance_day",
            text=_("{date}: {mark} (исправлено)").format(date=f"{date:%d.%m.%Y}", mark=mark_words(now)),
            actor=actor,
        )


def _row_dict(student: Student, row: AttendanceDay | None) -> dict:
    return {
        "student": student.pk,
        "full_name": student.full_name,
        "mark": row.mark if row else AttendanceDay.Mark.PRESENT,
        "reason": row.reason if row else "",
        "marked": row is not None,
    }


def _noted(marks: dict) -> dict | None:
    # кто и когда отмечал последним — подпись листа; имя автора берётся из его записи
    last = max(marks.values(), key=lambda row: row.updated_at, default=None)
    if last is None:
        return None
    return {"by": (last.noted_by.full_name or last.noted_by.handle) if last.noted_by else "", "at": last.updated_at}


def day_sheet(*, group, date: dt.date) -> dict:
    """Лист группы за день: все в школе, пока не отмечено иное.

    Пустой день — это «все в школе», а не «никого не отмечали»: куратору
    проще нажать трёх, чем двадцать. Что день уже отмечали, видно по `saved`.
    """
    from directors.services import release_label, released_map, released_on

    students = list(Student.objects.filter(group=group, is_active=True).order_by("last_name", "first_name"))
    marks = {
        row.student_id: row
        for row in AttendanceDay.objects.filter(student__in=students, date=date).select_related("noted_by")
    }
    # освобождённые от уроков (олимпиада, соревнование): у куратора — чип вместо трёх кнопок
    released = released_map([s.pk for s in students], date, date)

    def row_of(student: Student) -> dict:
        found = released_on(released, student.pk, date)
        return {
            **_row_dict(student, marks.get(student.pk)),
            "released": release_label(found) if found else "",
            "released_by": found.created_by_title if found else "",
        }

    return {
        "group": group.pk,
        "group_code": group.code,
        "date": date,
        "saved": bool(marks),
        "late": _is_late(date),
        "noted": _noted(marks),
        "rows": [row_of(s) for s in students],
        "absent": sum(1 for row in marks.values() if row.mark == AttendanceDay.Mark.ABSENT),
        "late_count": sum(1 for row in marks.values() if row.mark == AttendanceDay.Mark.LATE),
        "total": len(students),
    }


@transaction.atomic
def open_day(*, group, date: dt.date, actor) -> dict:
    """Открыть лист за сегодня: всем без отметки записать «в школе» (решение владельца, 19.10.2026).

    Так день считается отмеченным и без нажатий, а подпись «отметил … в …»
    появляется сразу; дальше куратор нажимает только тех, кого нет или кто опоздал.
    """
    students = Student.objects.filter(group=group, is_active=True)
    marked = set(AttendanceDay.objects.filter(student__in=students, date=date).values_list("student_id", flat=True))
    AttendanceDay.objects.bulk_create(
        [
            AttendanceDay(student=s, date=date, mark=AttendanceDay.Mark.PRESENT, noted_by=_actor(actor))
            for s in students
            if s.pk not in marked
        ]
    )
    return day_sheet(group=group, date=date)


@transaction.atomic
def mark_one(*, group, student: Student, date: dt.date, mark: str, reason: str, actor) -> dict:
    """Одна отметка — сразу при нажатии; возвращает строку и подпись листа."""
    before = AttendanceDay.objects.filter(student=student, date=date).first()
    was = before.mark if before else None
    row = mark_day(student=student, date=date, mark=mark, reason=reason, actor=actor)
    _journal_mark(student, date, was, row.mark, actor)
    sheet = day_sheet(group=group, date=date)
    return {
        "row": _row_dict(student, row),
        "noted": sheet["noted"],
        "absent": sheet["absent"],
        "late_count": sheet["late_count"],
    }


@transaction.atomic
def save_day(*, group, date: dt.date, rows: list[dict], actor) -> dict:
    """Сохранить лист за день целиком. Строки не про своих учеников отбрасываются."""
    allowed = {s.pk: s for s in Student.objects.filter(group=group, is_active=True).select_related("group")}
    before = {row.student_id: row.mark for row in AttendanceDay.objects.filter(student__in=allowed, date=date)}
    saved = 0
    for row in rows:
        try:
            student_id = int(row.get("student"))
        except (TypeError, ValueError):
            continue
        student = allowed.get(student_id)
        if student is None:
            continue
        mark = _mark_of(row["mark"] if "mark" in row else row.get("present", True))
        written = mark_day(
            student=student, date=date, mark=mark, reason=str(row.get("reason") or "").strip(), actor=actor
        )
        saved += 1
        _journal_mark(student, date, before.get(student_id), written.mark, actor)
    # `written` — сколько строк записали; `saved` в листе значит другое:
    # «этот день уже отмечали». Разные вещи, разные имена
    return {"written": saved, **day_sheet(group=group, date=date)}


#: исходные слова для каталога (`gettext_noop`); перевод — при сборке ответа
WEEKDAYS = (
    gettext_noop("пн"),
    gettext_noop("вт"),
    gettext_noop("ср"),
    gettext_noop("чт"),
    gettext_noop("пт"),
    gettext_noop("сб"),
    gettext_noop("вс"),
)

#: слова ячейки журнала — одни на экран и на файл; переводятся при сборке
CELL_WORDS = {
    "present": gettext_noop("был"),
    "absent": gettext_noop("не был"),
    "late": gettext_noop("опоздал"),
    "off": gettext_noop("выходной"),
    "unmarked": "—",
}


def month_journal(*, group, month: dt.date, absent_only: bool = False) -> dict:
    """Журнал посещаемости группы за месяц: строки — ученики, столбцы — дни.

    Календаря праздников нет, и выдумывать его не стали: выходной — день,
    в который по группе нет ни одной отметки. Итог ученика считается
    по дням, когда посещаемость вносили: «отсутствовал N из M». Ученик
    без отметки в учебный день (пришёл в группу позже) — прочерк,
    в M такой день у него не входит.
    """
    import calendar

    first = month.replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    students = list(Student.objects.filter(group=group, is_active=True).order_by("last_name", "first_name"))
    marks: dict[tuple[int, dt.date], AttendanceDay] = {
        (row.student_id, row.date): row
        for row in AttendanceDay.objects.filter(student__in=students, date__gte=first, date__lte=last)
    }
    school_days = {date for _student, date in marks}
    days = [first + dt.timedelta(days=offset) for offset in range((last - first).days + 1)]

    rows = []
    for student in students:
        cells, absent, marked = [], 0, 0
        for day in days:
            mark = marks.get((student.pk, day))
            if day not in school_days:
                cells.append("off")
            elif mark is None:
                cells.append("unmarked")
            else:
                marked += 1
                absent += 1 if mark.mark == AttendanceDay.Mark.ABSENT else 0
                cells.append(mark.mark)
        if absent_only and absent == 0:
            continue
        rows.append(
            {
                "student": student.pk,
                "full_name": student.full_name,
                "cells": cells,
                "absent": absent,
                "marked": marked,
                "summary": (
                    _("отсутствовал {absent} из {marked}").format(absent=absent, marked=marked)
                    if marked
                    else _("дни не отмечали")
                ),
            }
        )
    return {
        "group": group.pk,
        "group_code": group.code,
        "month": first.strftime("%Y-%m"),
        "days": [
            {"date": day, "day": day.day, "weekday": _(WEEKDAYS[day.weekday()]), "school_day": day in school_days}
            for day in days
        ],
        "school_days": len(school_days),
        "rows": rows,
        "words": {code: _(word) for code, word in CELL_WORDS.items()},
    }


def absences(*, groups, since: dt.date, until: dt.date) -> list[dict]:
    """Кого не было и кто опоздал по отметке куратора — по дням и группам, для службы безопасности.

    Строка — день одной группы; дни, когда никого не отмечали или все были
    в школе, в отчёт не попадают. У каждого — отметка и комментарий куратора.
    """
    rows = (
        AttendanceDay.objects.filter(
            date__gte=since, date__lte=until, student__group__in=groups, student__is_active=True
        )
        .exclude(mark=AttendanceDay.Mark.PRESENT)
        .select_related("student", "student__group")
        .order_by("-date", "student__group__code", "mark", "student__last_name", "student__first_name")
    )
    out: dict[tuple[dt.date, int], dict] = {}
    for row in rows:
        key = (row.date, row.student.group_id)
        bucket = out.setdefault(
            key,
            {
                "date": row.date,
                "weekday": _(WEEKDAYS[row.date.weekday()]),
                "group": row.student.group_id,
                "group_code": row.student.group.code,
                "students": [],
            },
        )
        bucket["students"].append(
            {"id": row.student_id, "full_name": row.student.full_name, "mark": row.mark, "reason": row.reason}
        )
    return [
        {
            **bucket,
            "count": sum(1 for s in bucket["students"] if s["mark"] == AttendanceDay.Mark.ABSENT),
            "late_count": sum(1 for s in bucket["students"] if s["mark"] == AttendanceDay.Mark.LATE),
        }
        for bucket in out.values()
    ]


def stats(*, groups, since: dt.date, until: dt.date) -> dict:
    """Аналитика по отметкам куратора за период: по ученикам и итого.

    День группы считается отмеченным, если в нём есть хоть одна строка
    (открытый лист пишет «в школе» всем). У ученика: дней — отмеченные дни
    его группы, не был и опоздал — его строки, был — остальное; процент —
    доля дней «был» и «опоздал» от отмеченных. Даты с комментарием — только
    у «нет» и «опоздал».
    """
    rows = list(
        AttendanceDay.objects.filter(
            date__gte=since, date__lte=until, student__group__in=groups, student__is_active=True
        )
        .select_related("student", "student__group")
        .order_by("date")
    )
    days_of_group: dict[int, set[dt.date]] = {}
    for row in rows:
        days_of_group.setdefault(row.student.group_id, set()).add(row.date)
    students = list(
        Student.objects.filter(group__in=groups, is_active=True)
        .select_related("group")
        .order_by("group__code", "last_name", "first_name")
    )
    by_student: dict[int, list[AttendanceDay]] = {}
    for row in rows:
        by_student.setdefault(row.student_id, []).append(row)
    out = []
    sum_days = sum_present = total_absent = total_late = 0
    for student in students:
        days = len(days_of_group.get(student.group_id, ()))
        mine = by_student.get(student.pk, [])
        absent = sum(1 for r in mine if r.mark == AttendanceDay.Mark.ABSENT)
        late = sum(1 for r in mine if r.mark == AttendanceDay.Mark.LATE)
        present = max(days - absent, 0)
        sum_days += days
        sum_present += present
        total_absent += absent
        total_late += late
        out.append(
            {
                "id": student.pk,
                "full_name": student.full_name,
                "group": student.group.code if student.group_id else "",
                "days": days,
                "present": present - late if present >= late else 0,
                "absent": absent,
                "late": late,
                "percent": round(present * 100 / days) if days else None,
                "dates": [
                    {"date": r.date, "mark": r.mark, "reason": r.reason}
                    for r in mine
                    if r.mark != AttendanceDay.Mark.PRESENT
                ],
            }
        )
    all_days = set().union(*days_of_group.values()) if days_of_group else set()
    return {
        "rows": out,
        "totals": {
            "days": len(all_days),
            "absent": total_absent,
            "late": total_late,
            "percent": round(sum_present * 100 / sum_days) if sum_days else None,
        },
    }


def attendance_history(student: Student, *, limit: int = 60) -> list[dict]:
    """Последние дни ученика — для карточки: когда именно не был."""
    return [
        {"date": row.date, "mark": row.mark, "reason": row.reason}
        for row in AttendanceDay.objects.filter(student=student).order_by("-date")[:limit]
    ]


# --- Замечания ---------------------------------------------------------------


def recount_remarks(student: Student) -> int:
    """Пересчитать счётчик замечаний из строк."""
    count = BehaviorRemark.objects.filter(student=student).count()
    profile, _created = BehaviorProfile.objects.get_or_create(student=student)
    if profile.remarks_count != count:
        BehaviorProfile.objects.filter(pk=profile.pk).update(remarks_count=count)
    return count


@transaction.atomic
def add_remark(*, student: Student, text: str, date: dt.date | None = None, actor) -> BehaviorRemark:
    """Записать замечание словами — и пересчитать счётчик профиля."""
    text = (text or "").strip()
    if not text:
        raise ValueError(_("Замечание без текста не записывается: через месяц никто не вспомнит, за что"))
    row = BehaviorRemark.objects.create(
        student=student,
        date=date or timezone.localdate(),
        text=text[:500],
        author=_actor(actor),
        author_role=getattr(actor, "role", "") or "",
    )
    recount_remarks(student)
    record_event(student=student, code="behavior_remark", text=text[:200], actor=actor)
    return row


@transaction.atomic
def drop_remark(row: BehaviorRemark, *, actor) -> None:
    """Убрать замечание в архив — и пересчитать счётчик.

    Физически замечание не удаляется (инвариант №13): написанное о ребёнке
    должно оставаться видимым в журнале, даже когда его сняли.
    """
    import uuid

    BehaviorRemark.all_objects.filter(pk=row.pk, archived_at__isnull=True).update(
        archived_at=timezone.now(), archive_batch=uuid.uuid4()
    )
    recount_remarks(row.student)
    record_event(student=row.student, code="behavior_remark_dropped", text=row.text[:200], actor=actor)


def remarks_of(student: Student) -> list[dict]:
    """Замечания ученика для карточки — словами, с автором и датой."""
    return [
        {
            "id": row.pk,
            "date": row.date,
            "text": row.text,
            "author": (row.author.full_name or row.author.email) if row.author_id else "",
            "author_role": row.author_role,
        }
        for row in BehaviorRemark.objects.filter(student=student).select_related("author")
    ]
