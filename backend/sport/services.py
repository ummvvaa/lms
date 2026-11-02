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
from students.models import Student

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


def active_list(student) -> list[SectionEnrollment]:
    """Все действующие записи ученика — по секциям, в порядке записи."""
    return list(
        SectionEnrollment.objects.filter(student=student, ended_at__isnull=True)
        .select_related("section", "slot")
        .order_by("enrolled_at", "id")
    )


def active_in(student, section) -> SectionEnrollment | None:
    """Действующая запись ученика в этой секции — в одной секции она одна."""
    return (
        SectionEnrollment.objects.filter(student=student, section=section, ended_at__isnull=True)
        .select_related("section", "slot")
        .first()
    )


def sections_max() -> int:
    """Во сколько секций ученик записывается сам — правило школы."""
    return int(school_rules.value(school_rules.SPORT_SECTIONS_MAX))


def slots_for(student, section: Section | None = None):
    """Занятия, подходящие ученику по классу."""
    grade = student_parallel(student)
    qs = SectionSlot.objects.filter(
        section__archived_at__isnull=True, parallel_from__lte=grade, parallel_to__gte=grade
    ).select_related("section")
    if section is not None:
        qs = qs.filter(section=section)
    return qs.order_by("section__order", "section__title", "weekday", "starts")


def overlap(one: SectionSlot, other: SectionSlot) -> bool:
    """Два часа совпадают по дню и хотя бы минутой по времени."""
    return one.weekday == other.weekday and one.starts < other.ends and other.starts < one.ends


# --- Запись ---------------------------------------------------------------------------------


class NeedsConfirm(Refused):
    """Директору можно, но сначала подтвердить: сверх предела секций или лимита часа."""

    def __init__(self, warnings: list[str]):
        super().__init__(" · ".join(warnings))
        self.warnings = warnings


def check(
    *, student, slot: SectionSlot, by_director: bool = False, keep: SectionEnrollment | None = None, rows=None
) -> tuple[list[str], list[str]]:
    """Можно ли записать ученика на час: отказы и предупреждения, без записи.

    Отказ — для всех: закрытая запись у ученика, чужая параллель, час
    пересекается с другой секцией ученика. Предел секций и лимит часа
    ученика останавливают, а директору — предупреждение. `keep` — запись,
    которую переводят в другую секцию: её место и час в расчёт не идут.
    Одним путём идут запись, перевод, запись гостя и массовые действия.
    """
    refusals: list[str] = []
    warnings: list[str] = []
    if slot.archived_at is not None or slot.section.archived_at is not None:
        return [_("Такого занятия нет")], []
    rows = [r for r in (active_list(student) if rows is None else rows) if keep is None or r.pk != keep.pk]
    current = next((r for r in rows if r.section_id == slot.section_id), None)
    if current is not None and current.slot_id == slot.pk:
        return [], []
    if not by_director and not is_open():
        choosing_hour = current is not None and current.slot_id is None
        if not choosing_hour:
            refusals.append(_("Запись на секции закрыта — обратитесь к директору спорта"))
    if not slot.fits(student_parallel(student)):
        refusals.append(
            _("Это занятие для параллелей {grades}").format(grades=f"{slot.parallel_from}–{slot.parallel_to}")
        )
    for row in rows:
        if row.section_id != slot.section_id and row.slot_id and overlap(row.slot, slot):
            refusals.append(
                _("В это время у ученика секция «{title}», {slot}").format(
                    title=row.section.title, slot=slot_words(row.slot)
                )
            )
    limit = sections_max()
    if current is None and len(rows) + 1 > limit:
        if by_director:
            warnings.append(
                _("Сверх предела: секций у ученика станет {n}, по правилам школы — не больше {limit}").format(
                    n=len(rows) + 1, limit=limit
                )
            )
        else:
            refusals.append(_("Больше секций нельзя: по правилам школы не больше {limit}").format(limit=limit))
    busy = taken(slot)
    if busy >= slot.capacity:
        if by_director:
            warnings.append(
                _("Сверх лимита часа: мест {capacity}, записано {taken}").format(capacity=slot.capacity, taken=busy)
            )
        else:
            refusals.append(_("На этот час мест нет"))
    return refusals, warnings


def _lock_student(student) -> None:
    """Строка ученика под блокировкой: две записи одного ученика в разные секции идут по очереди."""
    Student.objects.select_for_update().filter(pk=student.pk).first()


def _guests_become_members(student, slot: SectionSlot, now) -> None:
    """Записали на час гостя: его сегодняшняя и будущие отметки на этом часе — обычные."""
    SectionMark.objects.filter(student=student, slot=slot, is_guest=True, date__gte=local_now().date()).update(
        is_guest=False
    )


@transaction.atomic
def enroll(*, student, slot: SectionSlot, actor, by_director: bool = False, force: bool = False) -> SectionEnrollment:
    """Записать ученика на час занятия или перевести в другой час той же секции.

    Запись в другую секцию прежние записи не закрывает (02.11.2026): секций
    у ученика может быть несколько, часы не пересекаются. Ученик записывается
    сам только при открытой записи и в пределах правила школы; час для записи
    без часа он выбирает и при закрытой. Директор записывает всегда, сверх
    предела и лимита часа — только подтвердив (`force`). Лимит считается
    под блокировкой строки занятия.
    """
    locked = SectionSlot.objects.select_for_update(of=("self",)).select_related("section").filter(pk=slot.pk).first()
    if locked is None or locked.section.archived_at is not None:
        raise Refused(_("Такого занятия нет"))
    _lock_student(student)
    rows = active_list(student)
    current = next((r for r in rows if r.section_id == locked.section_id), None)
    if current is not None and current.slot_id == locked.pk:
        return current
    refusals, warnings = check(student=student, slot=locked, by_director=by_director, rows=rows)
    if refusals:
        raise Refused(refusals[0])
    if warnings and not force:
        raise NeedsConfirm(warnings)
    now = timezone.now()
    where = f"{locked.section.title}, {slot_words(locked)}"
    with translation.override("ru"):
        if current is not None:
            current.slot = locked
            current.slot_set_by = actor if by_director else None
            current.slot_set_at = now
            current.save(update_fields=["slot", "slot_set_by", "slot_set_at"])
            _event(student, _("Секция: час занятия — {where}").format(where=where), actor=actor)
            _guests_become_members(student, locked, now)
            return current
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
    _guests_become_members(student, locked, now)
    return row


@transaction.atomic
def transfer(row: SectionEnrollment, *, slot: SectionSlot, actor, force: bool = False) -> SectionEnrollment:
    """Директор переводит запись: в другой час этой секции или в другую секцию.

    В другую секцию — прежняя запись закрывается, новая открывается одним
    шагом: не прошла проверка — обе остаются как были.
    """
    if slot.section_id == row.section_id:
        return enroll(student=row.student, slot=slot, actor=actor, by_director=True, force=force)
    locked = SectionEnrollment.objects.select_for_update().filter(pk=row.pk, ended_at__isnull=True).first()
    if locked is None:
        raise Refused(_("Запись уже закрыта"))
    _lock_student(row.student)
    refusals, warnings = check(student=row.student, slot=slot, by_director=True, keep=locked)
    if refusals:
        raise Refused(refusals[0])
    if warnings and not force:
        raise NeedsConfirm(warnings)
    _close(locked, actor=actor, now=timezone.now())
    with translation.override("ru"):
        _event(
            row.student,
            _("Секция: переведён из «{title}» в другую секцию").format(title=locked.section.title),
            actor=actor,
        )
    return enroll(student=row.student, slot=slot, actor=actor, by_director=True, force=True)


def _close(row: SectionEnrollment, *, actor, now) -> None:
    row.ended_at = now
    row.ended_by = actor if getattr(actor, "pk", None) else None
    row.save(update_fields=["ended_at", "ended_by"])


@transaction.atomic
def leave(*, student, actor, section=None, by_director: bool = False) -> SectionEnrollment:
    """Выйти из одной секции: её запись закрывается, место освобождается, история остаётся.

    Записей у ученика может быть несколько — выходят из конкретной секции.
    """
    query = SectionEnrollment.objects.select_for_update().filter(student=student, ended_at__isnull=True)
    if section is not None:
        query = query.filter(section=section)
    rows = list(query.select_related("section")[:2])
    if not rows:
        raise Refused(_("Ученик не записан в эту секцию"))
    if len(rows) > 1:
        raise Refused(_("Выберите, из какой секции выйти"))
    current = rows[0]
    if not by_director and not is_open():
        raise Refused(_("Запись закрыта — выйти из секции можно через директора спорта"))
    _close(current, actor=actor, now=timezone.now())
    with translation.override("ru"):
        _event(student, _("Секция: вышел из секции «{title}»").format(title=current.section.title), actor=actor)
    return current


@transaction.atomic
def import_enrollment(*, student, section: Section, slot: SectionSlot | None, enrolled_at, actor=None):
    """Запись из бота: дата из файла, лимит не проверяется — бот его уже проверял.

    Повторный перенос того же ученика в ту же секцию ничего не меняет.
    """
    current = (
        SectionEnrollment.objects.select_for_update()
        .filter(student=student, section=section, ended_at__isnull=True)
        .first()
    )
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
    """Отметка по свежему коду. Ответ — состояние для экрана телефона, а не исключение.

    Засчитывается в секцию отсканированного кода. Записан в неё на другой
    час — «не твоё занятие»; не записан вовсе — гостевая отметка (02.11.2026).
    """
    now = now or local_now()
    slot = SectionSlot.all_objects.select_related("section").filter(pk=slot_id).first()
    if slot is None or day != now.date() or day.weekday() != slot.weekday:
        return {"state": "stale"}
    mine = active_in(student, slot.section)
    if mine is not None and mine.slot_id is None:
        return {"state": "no_hour", "session": _slot_brief(slot)}
    if mine is not None and mine.slot_id != slot.pk:
        return {"state": "foreign", "session": _slot_brief(slot), "mine": _slot_brief(mine.slot)}
    # не записан в эту секцию — пришёл гостем: отметка гостевая, директор может записать его на час
    guest = mine is None
    state = session_state(slot, day, now)
    if state == "soon":
        return {"state": "not_started", "session": _slot_brief(slot), "starts_at": _at(day, slot.starts).isoformat()}
    if state == "past":
        return {"state": "ended", "session": _slot_brief(slot)}
    with transaction.atomic():
        row, created = SectionMark.objects.get_or_create(
            student=student,
            slot=slot,
            date=day,
            defaults={"method": MarkMethod.QR, "marked_at": timezone.now(), "is_guest": guest},
        )
    if row.is_guest:
        state = "guest" if created else "guest_already"
    else:
        state = "marked" if created else "already"
    return {"state": state, "session": _slot_brief(slot), "marked_at": timezone.localtime(row.marked_at).isoformat()}


@transaction.atomic
def mark_manually(*, student, slot: SectionSlot, day: dt.date, actor) -> tuple[SectionMark, bool]:
    """Директор отмечает пришедшего без телефона: на занятие его часа, не в будущем."""
    if day.weekday() != slot.weekday:
        raise Refused(_("В этот день у часа нет занятия"))
    if day > local_now().date():
        raise Refused(_("Занятие ещё не прошло"))
    mine = active_in(student, slot.section)
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
            SectionMark.objects.filter(
                student_id=row.student_id, slot_id=row.slot_id, date__in=dates, is_guest=False
            ).values_list("date", flat=True)
        )
    came = sum(1 for d in dates if d in marks)
    return round(100 * came / len(dates))


def month_percents(rows, month: str | None = None) -> dict[int, int | None]:
    """Посещение за месяц по записям (ключ — запись) — одним запросом отметок.

    Записей у ученика может быть несколько: процент у каждой свой, по её часу.
    Гостевые отметки в процент не входят.
    """
    first, last = month_bounds(month)
    rows = list(rows)
    marks: dict[tuple[int, int], set[dt.date]] = {}
    query = Q(date__gte=first, date__lte=last, is_guest=False)
    for mark in SectionMark.objects.filter(query, student_id__in=[r.student_id for r in rows]).values(
        "student_id", "slot_id", "date"
    ):
        marks.setdefault((mark["student_id"], mark["slot_id"]), set()).add(mark["date"])
    return {r.pk: percent(r, first, last, marks.get((r.student_id, r.slot_id), set())) for r in rows}


def below_threshold(value) -> bool:
    return value is not None and value < int(school_rules.value(school_rules.SPORT_ATTENDANCE_BELOW))
