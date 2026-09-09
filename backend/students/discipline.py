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
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

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


def recount_attendance(student: Student) -> int | None:
    """Пересчитать процент посещаемости из дней. Дней нет — не трогать.

    Возвращает записанный процент или `None`, если считать не по чему.
    """
    days = AttendanceDay.objects.filter(student=student)
    total = days.count()
    if not total:
        return None
    present = days.filter(present=True).count()
    percent = round(present * 100 / total)
    profile, _ = BehaviorProfile.objects.get_or_create(student=student)
    if profile.attendance_percent != percent:
        BehaviorProfile.objects.filter(pk=profile.pk).update(attendance_percent=percent)
    return percent


@transaction.atomic
def mark_day(*, student: Student, date: dt.date, present: bool, reason: str = "", actor) -> AttendanceDay:
    """Отметить один день. Повторная отметка того же дня — правка, не дубль."""
    row, created = AttendanceDay.objects.get_or_create(
        student=student,
        date=date,
        defaults={"present": present, "reason": reason[:200], "noted_by": _actor(actor)},
    )
    if not created:
        changed = row.present != present or row.reason != reason[:200]
        row.present = present
        row.reason = reason[:200]
        row.noted_by = _actor(actor)
        row.save(update_fields=["present", "reason", "noted_by", "updated_at"])
        if changed and _is_late(date):
            # правка задним числом — отдельной строкой журнала: по ней видно,
            # что посещаемость меняли не в тот день, когда она случилась
            record_event(
                student=student,
                code="attendance_late_edit",
                text=f"{date:%d.%m.%Y}: {'был' if present else 'не был'}"
                + (f", {reason}" if reason else "")
                + f" (правка спустя {(timezone.localdate() - date).days} дн.)",
                actor=actor,
            )
    recount_attendance(student)
    return row


def _is_late(date: dt.date) -> bool:
    return (timezone.localdate() - date).days > LATE_EDIT_DAYS


def _actor(actor):
    return actor if getattr(actor, "pk", None) else None


def day_sheet(*, group, date: dt.date) -> dict:
    """Лист посещаемости группы за день: все присутствуют, пока не снято.

    Пустой день — это «все были», а не «никого не отмечали»: учителю
    проще снять три отметки, чем поставить двадцать. Что день ещё не
    сохраняли, видно по признаку `saved`.
    """
    students = list(Student.objects.filter(group=group, is_active=True).order_by("last_name", "first_name"))
    marks = {row.student_id: row for row in AttendanceDay.objects.filter(student__in=students, date=date)}
    return {
        "group": group.pk,
        "group_code": group.code,
        "date": date,
        "saved": bool(marks),
        "late": _is_late(date),
        "rows": [
            {
                "student": s.pk,
                "full_name": s.full_name,
                "present": marks[s.pk].present if s.pk in marks else True,
                "reason": marks[s.pk].reason if s.pk in marks else "",
                "marked": s.pk in marks,
            }
            for s in students
        ],
        "absent": sum(1 for row in marks.values() if not row.present),
        "total": len(students),
    }


@transaction.atomic
def save_day(*, group, date: dt.date, rows: list[dict], actor) -> dict:
    """Сохранить лист за день. Строки не про своих учеников отбрасываются."""
    allowed = {s.pk: s for s in Student.objects.filter(group=group, is_active=True).select_related("group")}
    saved = 0
    for row in rows:
        try:
            student_id = int(row.get("student"))
        except (TypeError, ValueError):
            continue
        student = allowed.get(student_id)
        if student is None:
            continue
        mark_day(
            student=student,
            date=date,
            present=bool(row.get("present", True)),
            reason=str(row.get("reason") or "").strip(),
            actor=actor,
        )
        saved += 1
    # `written` — сколько строк записали; `saved` в листе значит другое:
    # «этот день уже отмечали». Разные вещи, разные имена
    return {"written": saved, **day_sheet(group=group, date=date)}


def attendance_history(student: Student, *, limit: int = 60) -> list[dict]:
    """Последние дни ученика — для карточки: когда именно не был."""
    return [
        {"date": row.date, "present": row.present, "reason": row.reason}
        for row in AttendanceDay.objects.filter(student=student).order_by("-date")[:limit]
    ]


# --- Замечания ---------------------------------------------------------------


def recount_remarks(student: Student) -> int:
    """Пересчитать счётчик замечаний из строк."""
    count = BehaviorRemark.objects.filter(student=student).count()
    profile, _ = BehaviorProfile.objects.get_or_create(student=student)
    if profile.remarks_count != count:
        BehaviorProfile.objects.filter(pk=profile.pk).update(remarks_count=count)
    return count


@transaction.atomic
def add_remark(*, student: Student, text: str, date: dt.date | None = None, actor) -> BehaviorRemark:
    """Записать замечание словами — и пересчитать счётчик профиля."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Замечание без текста не записывается: через месяц никто не вспомнит, за что")
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
