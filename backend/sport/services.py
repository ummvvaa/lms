"""Действия секций: запись, перевод, отметка по QR и вручную, посещение.

Вьюхи только разбирают запрос и проверяют право по реестру
(`core.domains.CABINET_WRITERS`); что происходит с записью — здесь,
одним местом, чтобы экран, перенос из бота и тесты шли тем же путём.

Лимит часа проверяется под блокировкой строки занятия (`select_for_update`):
двое, нажавшие на последнее место одновременно, встают в очередь у базы,
и второй уже видит, что мест нет.
"""

from __future__ import annotations

import datetime as dt
import time

from django.core import signing
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from core import school_rules
from core.audit import record_event
from core.domains import Source
from core.parallels import parallel_of
from sport.models import (
    EnrollmentSource,
    MarkMethod,
    Section,
    SectionEnrollment,
    SectionMark,
    SectionSettings,
    SectionSlot,
    SessionEnd,
)

#: событие в журнале ученика: записался, перевели, вышел
EVENT = "sport_section"
#: модель и поле настройки записи в журнале
SETTINGS_LABEL = "sport.SectionSettings"
#: сколько ждёт отметка, отсканированная до входа в LMS
HOLD_SECONDS = 120
#: ключ сессии браузера, где отметка ждёт входа
HOLD_KEY = "sport_scan_hold"
#: соль подписи токена QR: подпись от SECRET_KEY, другой подписью токен не подделать
TOKEN_SALT = "sport.section-mark"


class Refused(ValueError):
    """Так сделать нельзя — текст объясняет почему."""


def _title(user) -> str:
    return (getattr(user, "full_name", "") or getattr(user, "email", "") or "")[:250]


def student_parallel(student) -> int:
    """Параллель ученика — параллель его группы."""
    return parallel_of(student)


def slot_words(slot: SectionSlot) -> str:
    """«Сб 12:00–13:00» — короткая подпись часа."""
    return f"{short_day(slot.weekday)} {slot.starts:%H:%M}–{slot.ends:%H:%M}"


def short_day(weekday: int) -> str:
    names = (_("Пн"), _("Вт"), _("Ср"), _("Чт"), _("Пт"), _("Сб"), _("Вс"))
    return names[weekday]


def _event(student, text: str, *, actor, source: str = Source.MANUAL) -> None:
    record_event(student=student, code=EVENT, text=text, actor=actor, source=source)


# --- Настройка «Запись открыта до» ------------------------------------------------------


def settings_row() -> SectionSettings:
    row = SectionSettings.objects.order_by("pk").first()
    return row or SectionSettings.objects.create()


def enroll_until() -> dt.datetime | None:
    row = SectionSettings.objects.order_by("pk").first()
    return row.enroll_until if row else None


def is_open(now: dt.datetime | None = None) -> bool:
    until = enroll_until()
    return until is not None and (now or timezone.now()) <= until


@transaction.atomic
def set_enroll_until(value: dt.datetime | None, *, actor) -> SectionSettings:
    """Открыть запись до даты или закрыть (пусто). Правка — в журнал, было → стало."""
    from core.models import AuditLog

    row = SectionSettings.objects.select_for_update().order_by("pk").first() or SectionSettings.objects.create()
    old = row.enroll_until
    row.enroll_until = value
    row.updated_by = actor if getattr(actor, "pk", None) else None
    row.save()

    def words(moment):
        return timezone.localtime(moment).strftime("%d.%m.%Y %H:%M") if moment else ""

    if old != value:
        AuditLog.objects.create(
            actor=row.updated_by,
            actor_role=getattr(actor, "role", "") or "",
            model_label=SETTINGS_LABEL,
            object_id=str(row.pk),
            field_name="enroll_until",
            domain_code="sport",
            old_value=words(old),
            new_value=words(value),
            source=Source.MANUAL,
        )
    return row


# --- Места ---------------------------------------------------------------------------------


def active_enrollments():
    """Действующие записи живых учеников: архивный ученик место не держит."""
    return SectionEnrollment.objects.filter(ended_at__isnull=True, student__archived_at__isnull=True)


def taken(slot: SectionSlot) -> int:
    return active_enrollments().filter(slot=slot).count()


def taken_map(slots) -> dict[int, int]:
    rows = active_enrollments().filter(slot__in=slots).values("slot_id").annotate(n=Count("id"))
    return {row["slot_id"]: row["n"] for row in rows}


def active_of(student) -> SectionEnrollment | None:
    return (
        SectionEnrollment.objects.filter(student=student, ended_at__isnull=True)
        .select_related("section", "slot")
        .first()
    )


def slots_for(student, section: Section | None = None):
    """Занятия, подходящие ученику по классу."""
    grade = student_parallel(student)
    qs = SectionSlot.objects.filter(
        section__archived_at__isnull=True, parallel_from__lte=grade, parallel_to__gte=grade
    ).select_related("section")
    if section is not None:
        qs = qs.filter(section=section)
    return qs.order_by("section__order", "section__title", "weekday", "starts")


# --- Запись ---------------------------------------------------------------------------------


@transaction.atomic
def enroll(*, student, slot: SectionSlot, actor, by_director: bool = False) -> SectionEnrollment:
    """Записать ученика на час занятия, перевести в другой час или в другую секцию.

    Ученик записывается сам только при открытой записи; час для записи
    без часа он выбирает и при закрытой. Директор записывает всегда.
    Лимит проверяется под блокировкой строки занятия — и у директора тоже.
    """
    locked = SectionSlot.objects.select_for_update(of=("self",)).select_related("section").filter(pk=slot.pk).first()
    if locked is None or locked.section.archived_at is not None:
        raise Refused(_("Такого занятия нет"))
    current = (
        SectionEnrollment.objects.select_for_update(of=("self",))
        .filter(student=student, ended_at__isnull=True)
        .select_related("section", "slot")
        .first()
    )
    if not by_director and not is_open():
        choosing_hour = current is not None and current.slot_id is None and current.section_id == locked.section_id
        if not choosing_hour:
            raise Refused(_("Запись на секции закрыта — обратитесь к директору спорта"))
    if not locked.fits(student_parallel(student)):
        raise Refused(
            _("Это занятие для параллелей {grades}").format(grades=f"{locked.parallel_from}–{locked.parallel_to}")
        )
    if current is not None and current.slot_id == locked.pk:
        return current
    if taken(locked) >= locked.capacity:
        raise Refused(_("На этот час мест нет"))
    now = timezone.now()
    where = f"{locked.section.title}, {slot_words(locked)}"
    with translation.override("ru"):
        if current is not None and current.section_id == locked.section_id:
            current.slot = locked
            current.slot_set_by = actor if by_director else None
            current.slot_set_at = now
            current.save(update_fields=["slot", "slot_set_by", "slot_set_at"])
            _event(student, _("Секция: час занятия — {where}").format(where=where), actor=actor)
            return current
        if current is not None:
            _close(current, actor=actor, now=now)
        row = SectionEnrollment.objects.create(
            student=student,
            section=locked.section,
            slot=locked,
            enrolled_at=now,
            source=EnrollmentSource.DIRECTOR if by_director else EnrollmentSource.LMS,
            created_by=actor if getattr(actor, "pk", None) else None,
            slot_set_by=actor if by_director else None,
            slot_set_at=now,
        )
        _event(student, _("Секция: записан — {where}").format(where=where), actor=actor)
    return row


def _close(row: SectionEnrollment, *, actor, now) -> None:
    row.ended_at = now
    row.ended_by = actor if getattr(actor, "pk", None) else None
    row.save(update_fields=["ended_at", "ended_by"])


@transaction.atomic
def leave(*, student, actor, by_director: bool = False) -> SectionEnrollment:
    """Выйти из секции: запись закрывается, место освобождается, история остаётся."""
    current = SectionEnrollment.objects.select_for_update().filter(student=student, ended_at__isnull=True).first()
    if current is None:
        raise Refused(_("Ученик не записан ни в одну секцию"))
    if not by_director and not is_open():
        raise Refused(_("Запись закрыта — сменить секцию можно через директора спорта"))
    _close(current, actor=actor, now=timezone.now())
    with translation.override("ru"):
        _event(student, _("Секция: вышел из секции «{title}»").format(title=current.section.title), actor=actor)
    return current


@transaction.atomic
def import_enrollment(*, student, section: Section, slot: SectionSlot | None, enrolled_at, actor=None):
    """Запись из бота: дата из файла, лимит не проверяется — бот его уже проверял.

    Повторный перенос того же ученика в ту же секцию ничего не меняет.
    """
    current = SectionEnrollment.objects.select_for_update().filter(student=student, ended_at__isnull=True).first()
    if current is not None:
        return current, False
    row = SectionEnrollment.objects.create(
        student=student,
        section=section,
        slot=slot,
        enrolled_at=enrolled_at,
        source=EnrollmentSource.BOT,
    )
    with translation.override("ru"):
        _event(
            student,
            _("Секция: перенесён из бота — {title}").format(title=section.title),
            actor=actor,
            source=Source.IMPORT,
        )
    return row, True


@transaction.atomic
def remove_slot(slot: SectionSlot, *, move_to: SectionSlot | None, actor) -> int:
    """Убрать занятие: записанных — в выбранный час той же секции или «без часа».

    Само занятие уходит в архив: на нём остаются отметки прошлых недель.
    Лимит часа, куда переводят, не проверяется: директор переносит людей
    сознательно, а без часа ученик всё равно остаться не должен.
    """
    if move_to is not None and (move_to.section_id != slot.section_id or move_to.pk == slot.pk):
        raise Refused(_("Перевести можно только в другой час этой секции"))
    if move_to is not None and (move_to.parallel_from > slot.parallel_from or move_to.parallel_to < slot.parallel_to):
        raise Refused(_("Час, куда переводят, — для других параллелей"))
    rows = list(SectionEnrollment.objects.select_for_update().filter(slot=slot, ended_at__isnull=True))
    now = timezone.now()
    for row in rows:
        row.slot = move_to
        row.slot_set_by = actor if move_to is not None else None
        row.slot_set_at = now if move_to is not None else None
        row.save(update_fields=["slot", "slot_set_by", "slot_set_at"])
    slot.archived_at = now
    slot.save(update_fields=["archived_at"])
    return len(rows)


# --- Расписание: что идёт сейчас ---------------------------------------------------------


def local_now() -> dt.datetime:
    return timezone.localtime()


def _at(day: dt.date, moment: dt.time) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, moment))


def session_state(slot: SectionSlot, day: dt.date, now: dt.datetime | None = None) -> str:
    """«soon» — ещё не началось, «live» — идёт, «past» — закончилось (или закончено раньше)."""
    now = now or local_now()
    if SessionEnd.objects.filter(slot=slot, date=day).exists():
        return "past"
    if now < _at(day, slot.starts):
        return "soon"
    if now < _at(day, slot.ends):
        return "live"
    return "past"


def sessions_today(now: dt.datetime | None = None):
    now = now or local_now()
    return list(
        SectionSlot.objects.filter(weekday=now.date().weekday(), section__archived_at__isnull=True)
        .select_related("section")
        .order_by("starts", "section__order")
    )


def session_dates(slot: SectionSlot, start: dt.date, end: dt.date) -> list[dt.date]:
    """Даты занятий часа между двумя датами включительно."""
    first = start + dt.timedelta(days=(slot.weekday - start.weekday()) % 7)
    out = []
    day = first
    while day <= end:
        out.append(day)
        day += dt.timedelta(days=7)
    return out


def next_session(slot: SectionSlot, now: dt.datetime | None = None) -> dt.datetime:
    now = now or local_now()
    day = now.date()
    for offset in range(8):
        candidate = day + dt.timedelta(days=offset)
        if candidate.weekday() == slot.weekday and _at(candidate, slot.ends) > now:
            return _at(candidate, slot.starts)
    return _at(day + dt.timedelta(days=7), slot.starts)


def end_session(slot: SectionSlot, *, actor, day: dt.date | None = None) -> SessionEnd:
    day = day or local_now().date()
    row, _created = SessionEnd.objects.get_or_create(slot=slot, date=day, defaults={"ended_by": actor})
    return row


# --- QR -------------------------------------------------------------------------------


def seconds_now() -> float:
    """Секунды эпохи — окно токена и срок удержания считаются от них."""
    return time.time()


def ttl() -> int:
    return int(school_rules.value(school_rules.SPORT_QR_SECONDS))


def _signer() -> signing.Signer:
    return signing.Signer(salt=TOKEN_SALT, sep=".")


def make_token(slot: SectionSlot, day: dt.date, *, at: float | None = None) -> tuple[str, int]:
    """Токен на окно времени: «занятие.дата.окно.подпись». Второе число — сколько секунд он ещё свежий."""
    seconds = ttl()
    moment = at if at is not None else seconds_now()
    window = int(moment // seconds)
    token = _signer().sign(f"{slot.pk}.{day:%Y%m%d}.{window}")
    return token, int(seconds - moment % seconds)


def read_token(token: str, *, at: float | None = None) -> tuple[int, dt.date] | None:
    """Занятие и дата из свежего токена. Текущее и предыдущее окно — запас на дрожание часов.

    Подделанный, чужой подписью, старый — `None`; отличать их ученику незачем.
    """
    try:
        raw = _signer().unsign(str(token or ""))
        slot_id, day, window = raw.split(".")
        day_value = dt.datetime.strptime(day, "%Y%m%d").date()
        window_value = int(window)
        slot_value = int(slot_id)
    except (signing.BadSignature, ValueError):
        return None
    current = int((at if at is not None else seconds_now()) // ttl())
    if window_value not in (current, current - 1):
        return None
    return slot_value, day_value


def scan_hold(session, slot_id: int, day: dt.date) -> None:
    """Код свежий, а ученик ещё не вошёл: отметка ждёт входа в этом же браузере."""
    session[HOLD_KEY] = {"slot": slot_id, "date": day.isoformat(), "at": seconds_now()}


def take_hold(session) -> tuple[int, dt.date] | None:
    hold = session.pop(HOLD_KEY, None)
    if not isinstance(hold, dict):
        return None
    try:
        if seconds_now() - float(hold["at"]) > HOLD_SECONDS:
            return None
        return int(hold["slot"]), dt.date.fromisoformat(str(hold["date"]))
    except (KeyError, TypeError, ValueError):
        return None


def _slot_brief(slot: SectionSlot) -> dict:
    return {
        "section": slot.section.title,
        "slot": slot_words(slot),
        "day": slot.get_weekday_display(),
        "starts": f"{slot.starts:%H:%M}",
        "ends": f"{slot.ends:%H:%M}",
        "grades": f"{slot.parallel_from}–{slot.parallel_to}",
        "address": slot.section.address,
    }


def mark_by_scan(*, student, slot_id: int, day: dt.date, now: dt.datetime | None = None) -> dict:
    """Отметка по свежему коду. Ответ — состояние для экрана телефона, а не исключение."""
    now = now or local_now()
    slot = SectionSlot.all_objects.select_related("section").filter(pk=slot_id).first()
    if slot is None or day != now.date() or day.weekday() != slot.weekday:
        return {"state": "stale"}
    mine = active_of(student)
    if mine is None:
        return {"state": "not_enrolled", "session": _slot_brief(slot)}
    if mine.slot_id is None and mine.section_id == slot.section_id:
        return {"state": "no_hour", "session": _slot_brief(slot)}
    if mine.slot_id != slot.pk:
        own = _slot_brief(mine.slot) if mine.slot_id else {"section": mine.section.title, "slot": ""}
        return {"state": "foreign", "session": _slot_brief(slot), "mine": own}
    state = session_state(slot, day, now)
    if state == "soon":
        return {"state": "not_started", "session": _slot_brief(slot), "starts_at": _at(day, slot.starts).isoformat()}
    if state == "past":
        return {"state": "ended", "session": _slot_brief(slot)}
    with transaction.atomic():
        row, created = SectionMark.objects.get_or_create(
            student=student, slot=slot, date=day, defaults={"method": MarkMethod.QR, "marked_at": timezone.now()}
        )
    return {
        "state": "marked" if created else "already",
        "session": _slot_brief(slot),
        "marked_at": timezone.localtime(row.marked_at).isoformat(),
    }


@transaction.atomic
def mark_manually(*, student, slot: SectionSlot, day: dt.date, actor) -> tuple[SectionMark, bool]:
    """Директор отмечает пришедшего без телефона: на занятие его часа, не в будущем."""
    if day.weekday() != slot.weekday:
        raise Refused(_("В этот день у часа нет занятия"))
    if day > local_now().date():
        raise Refused(_("Занятие ещё не прошло"))
    mine = active_of(student)
    if mine is None or mine.slot_id != slot.pk:
        raise Refused(_("Ученик записан не на этот час"))
    return SectionMark.objects.get_or_create(
        student=student,
        slot=slot,
        date=day,
        defaults={"method": MarkMethod.MANUAL, "marked_by": actor, "marked_by_title": _title(actor)},
    )


def unmark(*, student, slot: SectionSlot, day: dt.date) -> int:
    """Снять отметку, поставленную по ошибке."""
    deleted, _rows = SectionMark.objects.filter(student=student, slot=slot, date=day).delete()
    return deleted


# --- Посещение -----------------------------------------------------------------------------


def month_bounds(month: str | None) -> tuple[dt.date, dt.date]:
    """Первый и последний день месяца «2026-10»; пусто или мусор — текущий месяц."""
    today = local_now().date()
    try:
        year, number = (int(part) for part in str(month or "").split("-"))
        first = dt.date(year, number, 1)
    except ValueError:
        first = today.replace(day=1)
    following = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return first, following - dt.timedelta(days=1)


def since_of(row: SectionEnrollment) -> dt.date:
    """С какой даты ученик ходит на свой час: назначение часа или запись."""
    moment = row.slot_set_at or row.enrolled_at
    return timezone.localtime(moment).date()


def held_dates(slot: SectionSlot, first: dt.date, last: dt.date, now: dt.datetime | None = None) -> list[dt.date]:
    """Прошедшие занятия часа в промежутке: сегодняшнее — только когда закончилось."""
    now = now or local_now()
    out = []
    for day in session_dates(slot, first, min(last, now.date())):
        if day < now.date() or session_state(slot, day, now) == "past":
            out.append(day)
    return out


def percent(row: SectionEnrollment, first: dt.date, last: dt.date, marks: set[dt.date] | None = None):
    """Посещение записи за промежуток: доля прошедших занятий её часа с отметкой. Нет занятий — `None`."""
    if row.slot_id is None:
        return None
    dates = held_dates(row.slot, max(first, since_of(row)), last)
    if not dates:
        return None
    if marks is None:
        marks = set(
            SectionMark.objects.filter(student_id=row.student_id, slot_id=row.slot_id, date__in=dates).values_list(
                "date", flat=True
            )
        )
    came = sum(1 for d in dates if d in marks)
    return round(100 * came / len(dates))


def month_percents(rows, month: str | None = None) -> dict[int, int | None]:
    """Посещение за месяц по ученикам — одним запросом отметок."""
    first, last = month_bounds(month)
    rows = list(rows)
    marks: dict[tuple[int, int], set[dt.date]] = {}
    query = Q(date__gte=first, date__lte=last)
    for mark in SectionMark.objects.filter(query, student_id__in=[r.student_id for r in rows]).values(
        "student_id", "slot_id", "date"
    ):
        marks.setdefault((mark["student_id"], mark["slot_id"]), set()).add(mark["date"])
    return {r.student_id: percent(r, first, last, marks.get((r.student_id, r.slot_id), set())) for r in rows}


def below_threshold(value) -> bool:
    return value is not None and value < int(school_rules.value(school_rules.SPORT_ATTENDANCE_BELOW))
