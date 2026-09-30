"""Отметки и оценки на уроке, уважительные причины за период.

Учитель отмечает только отсутствующих и опоздавших: присутствие — отсутствие
строки. «У» не хранится в отметке: её даёт уважительная причина куратора
за период, и на чтении «н» внутри периода читается как «у». Оценка ставится
только тому, кто был; поставили отсутствующему — он становится присутствующим.
Учитель правит свою оценку столько дней, сколько задано в шкале года.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone

from academics import cache
from academics.calendar import SchoolCalendar, lesson_groups, today
from academics.cohorts import member_ids
from academics.models import Attendance, Excuse, Grade, Lesson, LessonKind, Mark
from core.audit import record_change, record_event
from core.domains import ROLE_ADMIN, ROLE_TEACHER

#: Как отметка читается человеком — на экране, в файле и в отчёте
MARK_WORDS = {
    "present": "был",
    "absent": "не был",
    "late": "опоздал",
    "excused": "уважительная",
    "unmarked": "не отмечен",
}
MARK_SHORT = {"present": "", "absent": "н", "late": "оп", "excused": "у", "unmarked": ""}

PRESENT, ABSENT, LATE, EXCUSED = "present", "absent", "late", "excused"


class MarkRefused(ValueError):
    """Отметить или оценить так нельзя — текст объясняет почему."""


# --- Уважительные причины ---------------------------------------------------


def excuses_of(student_ids: Iterable[int], start: dt.date, end: dt.date) -> dict[int, list[tuple[dt.date, dt.date]]]:
    """Периоды уважительных причин учеников, пересекающие отрезок."""
    store = cache.current()
    if store is not None:
        rows = store.excuse_rows(start, end)
        wanted = set(student_ids)
        return {sid: periods for sid, periods in rows.items() if sid in wanted}
    out: dict[int, list[tuple[dt.date, dt.date]]] = {}
    for row in Excuse.objects.filter(student_id__in=list(student_ids), starts__lte=end, ends__gte=start):
        out.setdefault(row.student_id, []).append((row.starts, row.ends))
    return out


def is_excused(periods: dict[int, list[tuple[dt.date, dt.date]]], student_id: int, day: dt.date) -> bool:
    return any(starts <= day <= ends for starts, ends in periods.get(student_id, ()))


@transaction.atomic
def add_excuse(*, student, starts: dt.date, ends: dt.date, reason: str, document: str, file=None, actor=None) -> Excuse:
    """Оформить причину за период: пропуски «н» в эти дни станут «у» во всех журналах."""
    if ends < starts:
        raise MarkRefused("Дата «по» раньше даты «с»")
    if not reason.strip():
        raise MarkRefused("Напишите причину")
    row = Excuse.objects.create(
        student=student,
        starts=starts,
        ends=ends,
        reason=reason.strip()[:200],
        document=document or "other",
        file=file,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    cache.invalidate()
    record_event(
        student=student,
        code="excuse",
        text=f"{starts:%d.%m.%Y}–{ends:%d.%m.%Y}: {row.reason} ({row.get_document_display().lower()})",
        actor=actor,
    )
    return row


@transaction.atomic
def drop_excuse(row: Excuse, *, actor=None) -> None:
    """Снять причину: пропуски снова «н». Строка уходит в архив, а не стирается."""
    from core.archive import archive

    archive(row, actor=actor)
    cache.invalidate()
    record_event(
        student=row.student,
        code="excuse_dropped",
        text=f"{row.starts:%d.%m.%Y}–{row.ends:%d.%m.%Y}: {row.reason}",
        actor=actor,
    )


# --- Чтение отметок ------------------------------------------------------------


def marks_map(lessons: list[Lesson], student_ids: Iterable[int]) -> dict[tuple[int, int], str]:
    """`(урок, ученик)` → `present | absent | late | excused`; неотмеченный урок в карте не стоит.

    Присутствие пишется явно для отмеченных уроков, чтобы читающий код
    не различал «не был отмечен» и «был».
    """
    ids = list(student_ids)
    if not lessons or not ids:
        return {}
    start = min(lesson.date for lesson in lessons)
    end = max(lesson.date for lesson in lessons)
    periods = excuses_of(ids, start, end)
    store = cache.current()
    if store is not None:
        rows = store.attendance_rows(start, end)
    else:
        rows = {}
        for row in Attendance.objects.filter(lesson__in=[lesson.pk for lesson in lessons], student_id__in=ids):
            rows[(row.lesson_id, row.student_id)] = row.mark
    out: dict[tuple[int, int], str] = {}
    by_id = {lesson.pk: lesson for lesson in lessons}
    for lesson in lessons:
        if not lesson.is_marked:
            continue
        for sid in ids:
            mark = rows.get((lesson.pk, sid), PRESENT)
            if mark == Mark.ABSENT and is_excused(periods, sid, by_id[lesson.pk].date):
                mark = EXCUSED
            out[(lesson.pk, sid)] = mark
    return out


def arrivals_map(lessons: list[Lesson], student_ids: Iterable[int]) -> dict[tuple[int, int], dt.time]:
    """`(урок, ученик)` → во сколько пришёл опоздавший; опоздание без времени в карте не стоит."""
    ids = list(student_ids)
    if not lessons or not ids:
        return {}
    wanted = set(ids)
    pks = {lesson.pk for lesson in lessons}
    store = cache.current()
    if store is not None:
        start = min(lesson.date for lesson in lessons)
        end = max(lesson.date for lesson in lessons)
        rows = store.arrival_rows(start, end)
        return {key: at for key, at in rows.items() if key[0] in pks and key[1] in wanted}
    return {
        (lesson_id, sid): at
        for lesson_id, sid, at in Attendance.objects.filter(
            lesson__in=pks, student_id__in=ids, mark=Mark.LATE, arrived_at__isnull=False
        ).values_list("lesson_id", "student_id", "arrived_at")
    }


def grades_map(lessons: list[Lesson], student_ids: Iterable[int]) -> dict[tuple[int, int], Grade]:
    ids = list(student_ids)
    if not lessons or not ids:
        return {}
    store = cache.current()
    if store is not None:
        start = min(lesson.date for lesson in lessons)
        end = max(lesson.date for lesson in lessons)
        rows = store.grade_rows(start, end)
        pks = {lesson.pk for lesson in lessons}
        wanted = set(ids)
        return {key: row for key, row in rows.items() if key[0] in pks and key[1] in wanted}
    return {
        (row.lesson_id, row.student_id): row
        for row in Grade.objects.filter(lesson__in=[lesson.pk for lesson in lessons], student_id__in=ids)
    }


# --- Запись отметок -----------------------------------------------------------


@transaction.atomic
def save_attendance(
    lesson: Lesson, rows: list[dict], *, actor, calendar: SchoolCalendar, all_present: bool = False
) -> dict:
    """Сохранить отметки урока. Присутствие — отсутствие строки.

    `rows` — `[{"student": id, "mark": "present|absent|late", "arrived": "ЧЧ:ММ"}]`;
    строки не про учеников состава отбрасываются. `all_present` снимает все
    отметки. Время прихода проверяет `arrival_of`: у опоздавшего на прошедшем
    уроке оно обязательно, на идущем — без времени берётся «сейчас».
    """
    if not lesson.is_live:
        raise MarkRefused("Урок отменён: отмечать нечего")
    if not calendar.lesson_started(lesson.date, lesson.slot, lesson_groups(lesson)):
        raise MarkRefused("Урок ещё впереди: отметить можно со звонка")
    allowed = set(member_ids(lesson.course.cohort, lesson.date))
    current = {row.student_id: row for row in Attendance.objects.filter(lesson=lesson)}
    wanted: dict[int, str] = {}
    arrivals: dict[int, dt.time | None] = {}
    if not all_present:
        for raw in rows:
            try:
                sid = int(raw.get("student"))
            except (TypeError, ValueError):
                continue
            mark = str(raw.get("mark") or PRESENT)
            if sid in allowed and mark in (PRESENT, ABSENT, LATE):
                wanted[sid] = mark
                if mark == LATE:
                    row = current.get(sid)
                    kept = row.arrived_at if row is not None and row.mark == Mark.LATE else None
                    arrivals[sid] = arrival_of(
                        lesson,
                        raw.get("arrived"),
                        calendar=calendar,
                        kept=kept,
                        known=row is not None and row.mark == Mark.LATE,
                    )
    grades_dropped = 0
    written = 0
    # отметки, которых в запросе нет, остаются как были: экран шлёт всех,
    # клавиатура журнала — одного
    for sid, mark in wanted.items():
        row = current.get(sid)
        if mark == PRESENT:
            if row is not None:
                record_change(instance=row, field_name="mark", old_value=row.mark, new_value="", actor=actor)
                row.delete()
                written += 1
            continue
        arrived = arrivals.get(sid) if mark == LATE else None
        if row is None:
            row = Attendance.objects.create(
                lesson=lesson, student_id=sid, mark=mark, arrived_at=arrived, noted_by=_actor(actor)
            )
            record_change(instance=row, field_name="mark", old_value="", new_value=mark, actor=actor)
            if arrived is not None:
                record_change(
                    instance=row, field_name="arrived_at", old_value="", new_value=_hhmm(arrived), actor=actor
                )
            written += 1
        elif row.mark != mark or row.arrived_at != arrived:
            if row.mark != mark:
                record_change(instance=row, field_name="mark", old_value=row.mark, new_value=mark, actor=actor)
            if row.arrived_at != arrived:
                record_change(
                    instance=row,
                    field_name="arrived_at",
                    old_value=_hhmm(row.arrived_at),
                    new_value=_hhmm(arrived),
                    actor=actor,
                )
            row.mark = mark
            row.arrived_at = arrived
            row.noted_by = _actor(actor)
            row.save(update_fields=["mark", "arrived_at", "noted_by", "updated_at"])
            written += 1
        if mark == ABSENT:
            # оценка отсутствующему не живёт: его не было
            for grade in Grade.objects.filter(lesson=lesson, student_id=sid):
                record_change(instance=grade, field_name="value", old_value=grade.value, new_value="", actor=actor)
                grade.delete()
                grades_dropped += 1
    if all_present:
        for row in current.values():
            record_change(instance=row, field_name="mark", old_value=row.mark, new_value="", actor=actor)
            row.delete()
            written += 1
    if lesson.marked_at is None:
        record_change(instance=lesson, field_name="marked_at", old_value="", new_value="да", actor=actor)
    lesson.marked_at = timezone.now()
    lesson.marked_by = _actor(actor)
    lesson.save(update_fields=["marked_at", "marked_by", "updated_at"])
    cache.invalidate()
    return {"written": written, "grades_dropped": grades_dropped}


def _actor(actor):
    return actor if getattr(actor, "pk", None) else None


def _hhmm(value: dt.time | None) -> str:
    return f"{value:%H:%M}" if value is not None else ""


def _parse_time(raw) -> dt.time | None:
    """«8:12» или «08:12» → время; пусто — None; иначе — отказ словами."""
    text = str(raw or "").strip()
    if not text:
        return None
    found = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", text)
    if found is None or int(found.group(1)) > 23 or int(found.group(2)) > 59:
        raise MarkRefused("Время прихода — в виде ЧЧ:ММ, например 08:12")
    return dt.time(int(found.group(1)), int(found.group(2)))


def arrival_of(lesson: Lesson, raw, *, calendar: SchoolCalendar, kept=None, known: bool = False) -> dt.time | None:
    """Время прихода опоздавшего — проверенное по звонкам группы урока.

    Пришёл к началу урока — это «Был», после конца — «Не был»: такое время
    отклоняется с подсказкой. Времени в запросе нет: у опоздания, которое
    уже стояло, остаётся прежнее (у старых — пусто); на идущем уроке берётся
    «сейчас» по Алматы; на прошедшем — время обязательно. Урок без звонка
    в сетке группы — время принимается как есть.
    """
    from academics.calendar import now_local

    arrived = _parse_time(raw)
    span = calendar.bell(lesson.slot, lesson_groups(lesson))
    if arrived is None:
        if known:
            return kept
        if span is not None and calendar.slot_state(lesson.date, lesson.slot, groups=lesson_groups(lesson)) == "now":
            arrived = now_local().time().replace(second=0, microsecond=0)
        elif span is None:
            return None
        else:
            raise MarkRefused("Укажите, во сколько пришёл опоздавший: урок уже прошёл")
    if span is None:
        return arrived
    starts, ends = span
    if arrived <= starts:
        raise MarkRefused(f"Пришёл к началу урока ({starts:%H:%M}) — поставьте «Был», а не «Опоздал»")
    if arrived >= ends:
        raise MarkRefused(f"Пришёл после конца урока ({ends:%H:%M}) — это «Не был», а не опоздание")
    return arrived


# --- Оценки ---------------------------------------------------------------------


def edit_locked(lesson: Lesson, user, scale) -> bool:
    """Заперта ли клетка для этого человека: окно правки учителя и закрытая четверть."""
    role = getattr(user, "role", "")
    if role != ROLE_TEACHER:
        return False
    if (today() - lesson.date).days > scale.edit_days:
        return True
    return False


def grade_bounds(lesson: Lesson, scale) -> tuple[int, int]:
    """Допустимые баллы: ФО от 1 до максимума ФО, СОР и СОЧ от 0 до максимума урока."""
    if lesson.kind == LessonKind.FO:
        return 1, scale.fo_max
    return 0, lesson.max_score or (scale.fo_max)


@transaction.atomic
def set_grade(
    lesson: Lesson, student, value, *, comment: str | None = None, actor, calendar: SchoolCalendar, scale
) -> Grade | None:
    """Поставить, изменить или снять оценку одному ученику за урок."""
    if not lesson.is_live:
        raise MarkRefused("Урок отменён: оценки не ставятся")
    if not calendar.lesson_started(lesson.date, lesson.slot, lesson_groups(lesson)):
        raise MarkRefused("Урок ещё впереди")
    if edit_locked(lesson, actor, scale):
        raise MarkRefused(f"Оценка старше {scale.edit_days} дней: её правит академический директор")
    quarter = calendar.quarter_of(lesson.date)
    if quarter is not None and quarter.is_closed and getattr(actor, "role", "") == ROLE_TEACHER:
        raise MarkRefused("Четверть закрыта: оценки правят Кымбат и администратор")
    if student.pk not in set(member_ids(lesson.course.cohort, lesson.date)):
        raise MarkRefused("Этого ученика нет в составе урока")
    row = Grade.objects.filter(lesson=lesson, student=student).first()
    if value is None or value == "":
        if row is not None:
            record_change(instance=row, field_name="value", old_value=row.value, new_value="", actor=actor)
            row.delete()
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise MarkRefused("Оценка — целое число") from error
    low, high = grade_bounds(lesson, scale)
    if number < low or number > high:
        raise MarkRefused(f"Баллы от {low} до {high}")
    # оценка ставится только тому, кто был: отсутствующий становится присутствующим
    absent = Attendance.objects.filter(lesson=lesson, student=student, mark=Mark.ABSENT).first()
    if absent is not None:
        record_change(instance=absent, field_name="mark", old_value=absent.mark, new_value="", actor=actor)
        absent.delete()
    if row is None:
        row = Grade.objects.create(
            lesson=lesson, student=student, value=number, comment=(comment or "")[:300], created_by=_actor(actor)
        )
        record_change(instance=row, field_name="value", old_value="", new_value=number, actor=actor)
        if comment:
            record_change(instance=row, field_name="comment", old_value="", new_value=comment[:300], actor=actor)
    else:
        changes = {}
        if row.value != number:
            changes["value"] = number
        if comment is not None and row.comment != comment[:300]:
            changes["comment"] = comment[:300]
        for name, new in changes.items():
            record_change(instance=row, field_name=name, old_value=getattr(row, name), new_value=new, actor=actor)
            setattr(row, name, new)
        if changes:
            row.created_by = (
                _actor(actor) if getattr(actor, "role", "") in (ROLE_TEACHER, ROLE_ADMIN) else row.created_by
            )
            row.save()
    # урок с оценкой считается отмеченным: иначе журнал показывал бы «не отмечен» с баллами
    if lesson.marked_at is None:
        lesson.marked_at = timezone.now()
        lesson.marked_by = _actor(actor)
        lesson.save(update_fields=["marked_at", "marked_by", "updated_at"])
    cache.invalidate()
    return row


@transaction.atomic
def set_lesson_meta(lesson: Lesson, *, actor, **fields) -> Lesson:
    """Тема, домашнее задание, вид оценивания, номер и максимум — в журнал по полю."""
    for name in ("topic", "homework", "kind", "number", "max_score"):
        if name not in fields:
            continue
        value = fields[name]
        if name in ("number", "max_score"):
            value = int(value) if value not in (None, "") else None
        if name == "kind" and value not in (LessonKind.FO, LessonKind.SOR, LessonKind.SOCH):
            raise MarkRefused("Вид оценивания: ФО, СОР или СОЧ")
        if name == "max_score" and value is not None and value <= 0:
            raise MarkRefused("Максимум баллов больше нуля")
        if name in ("topic", "homework"):
            value = str(value or "")[: 200 if name == "topic" else 2000]
        old = getattr(lesson, name)
        if old != value:
            record_change(instance=lesson, field_name=name, old_value=old, new_value=value, actor=actor)
            setattr(lesson, name, value)
    if lesson.kind != LessonKind.FO and not lesson.max_score:
        lesson.max_score = (
            lesson.course.subject.sor_max if lesson.kind == LessonKind.SOR else lesson.course.subject.soch_max
        )
    lesson.save()
    return lesson


def kind_label(lesson: Lesson) -> str:
    if lesson.kind == LessonKind.SOR:
        return f"СОР {lesson.number}" if lesson.number else "СОР"
    if lesson.kind == LessonKind.SOCH:
        return "СОЧ"
    return "ФО"
