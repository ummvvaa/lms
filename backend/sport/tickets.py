"""Раздача билетов: анонс, «Забрать» после старта, очередь по времени нажатия.

Первые N нажавших получают билет, остальные встают в очередь. Отказ от
билета («Не смогу пойти», «Не нужно», «не забрал» у директора, истёкший
ответ) освобождает билет, и он предлагается первому в очереди: у того
`offer_minutes` минут ответить. Всё, что меняет число занятых билетов,
идёт под блокировкой строки раздачи — последний билет не достаётся двоим.

Уведомления собираются на языке получателя: текст хранится готовой
строкой (`core.Notification`), а читают его ученики на трёх языках.
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from core.models import Notification
from core.parallels import ADMISSION_PARALLEL
from sport.models import HELD, ClaimStatus, TicketClaim, TicketDrop
from sport.services import Refused, student_parallel
from students.models import Student

#: за сколько минут до старта раздачи приходит напоминание
REMIND_MINUTES = 5
#: куда ведёт уведомление о билетах: у 8–10 — раздел «Спорт», у 11 — вкладка «Спорт» портфолио
LINK_JUNIOR = "/sport?sport=tickets"
LINK_GRADUATE = "/my-data?tab=sport&sport=tickets"


def link_for(student) -> str:
    return LINK_GRADUATE if student_parallel(student) == ADMISSION_PARALLEL else LINK_JUNIOR


def audience(drop: TicketDrop):
    """Ученики классов раздачи со своей учёткой. Ученик без группы — выпускник, как везде."""
    grades = Q(group__parallel__gte=drop.parallel_from, group__parallel__lte=drop.parallel_to)
    if drop.parallel_from <= ADMISSION_PARALLEL <= drop.parallel_to:
        grades |= Q(group__isnull=True)
    return Student.objects.filter(grades, is_active=True, user__isnull=False, user__is_active=True).select_related(
        "user", "group"
    )


def _when(value: dt.datetime) -> str:
    return timezone.localtime(value).strftime("%d.%m %H:%M")


def _notify(students, kind: str, build) -> int:
    """Уведомление каждому на его языке: `build()` собирает текст внутри перевода."""
    rows = []
    for student in students:
        with translation.override(getattr(student.user, "language", "") or "ru"):
            rows.append(
                Notification(recipient=student.user, kind=kind, text=str(build())[:500], link=link_for(student))
            )
    Notification.objects.bulk_create(rows, batch_size=500)
    return len(rows)


def announce(drop: TicketDrop) -> int:
    """Анонс всем ученикам классов раздачи — один раз."""
    if drop.announced_at is not None:
        return 0
    sent = _notify(
        audience(drop),
        Notification.Kind.TICKET_ANNOUNCED,
        lambda: _("Бесплатные билеты: {title}. Раздача начнётся {at}, один билет в руки").format(
            title=drop.title, at=_when(drop.opens_at)
        ),
    )
    TicketDrop.objects.filter(pk=drop.pk).update(announced_at=timezone.now())
    return sent


def remind_soon(now: dt.datetime | None = None) -> int:
    """За пять минут до старта — напоминание тем же ученикам, один раз на раздачу."""
    now = now or timezone.now()
    sent = 0
    due = TicketDrop.objects.filter(
        reminded_at__isnull=True, opens_at__gt=now, opens_at__lte=now + dt.timedelta(minutes=REMIND_MINUTES)
    )
    for drop in due:
        if TicketDrop.objects.filter(pk=drop.pk, reminded_at__isnull=True).update(reminded_at=now) != 1:
            continue
        sent += _notify(
            audience(drop),
            Notification.Kind.TICKET_REMINDER,
            lambda drop=drop: _("Через пять минут начнётся раздача билетов: {title}").format(title=drop.title),
        )
    return sent


def held(drop: TicketDrop) -> int:
    return drop.claims.filter(status__in=HELD).count()


def queue_place(claim: TicketClaim) -> int | None:
    """Место в очереди: сколько ждущих нажали раньше, плюс один."""
    if claim.status != ClaimStatus.QUEUED:
        return None
    earlier = claim.drop.claims.filter(status=ClaimStatus.QUEUED).filter(
        Q(pressed_at__lt=claim.pressed_at) | Q(pressed_at=claim.pressed_at, pk__lt=claim.pk)
    )
    return earlier.count() + 1


def _lock(drop: TicketDrop) -> TicketDrop:
    return TicketDrop.objects.select_for_update().get(pk=drop.pk)


@transaction.atomic
def claim(*, drop: TicketDrop, student, now: dt.datetime | None = None) -> TicketClaim:
    """«Забрать»: билет, если ещё есть, иначе место в очереди. Один билет в руки."""
    now = now or timezone.now()
    drop = _lock(drop)
    if drop.archived_at is not None:
        raise Refused(_("Раздача отменена"))
    if now < drop.opens_at:
        raise Refused(_("Раздача ещё не началась"))
    if now >= drop.event_at:
        raise Refused(_("Событие уже прошло"))
    if not drop.parallel_from <= student_parallel(student) <= drop.parallel_to:
        raise Refused(
            _("Эта раздача — для параллелей {grades}").format(grades=f"{drop.parallel_from}–{drop.parallel_to}")
        )
    existing = drop.claims.filter(student=student).first()
    if existing is not None:
        return existing
    status = ClaimStatus.RECEIVED if held(drop) < drop.count else ClaimStatus.QUEUED
    return TicketClaim.objects.create(drop=drop, student=student, pressed_at=now, status=status, decided_at=now)


@transaction.atomic
def give_up(row: TicketClaim, *, missed: bool = False) -> TicketClaim:
    """Отказ: «Не смогу пойти», «Не нужно», «Выйти из очереди» или «не забрал» у директора."""
    _lock(row.drop)
    row.refresh_from_db()
    now = timezone.now()
    if missed:
        if row.status != ClaimStatus.RECEIVED:
            raise Refused(_("Не забрать можно только полученный билет"))
        row.status = ClaimStatus.MISSED
    elif row.status in HELD:
        row.status = ClaimStatus.DECLINED
    elif row.status == ClaimStatus.QUEUED:
        row.status = ClaimStatus.LEFT
    else:
        raise Refused(_("Билета и места в очереди уже нет"))
    row.decided_at = now
    row.save(update_fields=["status", "decided_at"])
    offer_next(row.drop)
    return row


@transaction.atomic
def accept(row: TicketClaim) -> TicketClaim:
    """«Беру билет» — пока не вышло время на ответ."""
    _lock(row.drop)
    row.refresh_from_db()
    if row.status != ClaimStatus.OFFERED:
        raise Refused(_("Билет вам сейчас не предложен"))
    now = timezone.now()
    if row.offer_until and now > row.offer_until:
        raise Refused(_("Время на ответ вышло — билет ушёл следующему"))
    row.status = ClaimStatus.RECEIVED
    row.from_queue = True
    row.decided_at = now
    row.save(update_fields=["status", "from_queue", "decided_at"])
    return row


def offer_next(drop: TicketDrop, now: dt.datetime | None = None) -> int:
    """Свободные билеты — первым в очереди по времени нажатия. Вызывается под блокировкой раздачи."""
    now = now or timezone.now()
    drop = TicketDrop.objects.get(pk=drop.pk)
    if now >= drop.event_at:
        return 0
    free = drop.count - held(drop)
    if free <= 0:
        return 0
    waiting = list(
        drop.claims.filter(status=ClaimStatus.QUEUED)
        .select_related("student__user")
        .order_by("pressed_at", "id")[:free]
    )
    until = now + dt.timedelta(minutes=drop.offer_minutes)
    for row in waiting:
        row.status = ClaimStatus.OFFERED
        row.offered_at = now
        row.offer_until = until
        row.decided_at = now
        row.save(update_fields=["status", "offered_at", "offer_until", "decided_at"])
    _notify(
        [row.student for row in waiting if row.student.user_id],
        Notification.Kind.TICKET_OFFERED,
        lambda: _("Освободился билет: {title}. Подтвердите до {until}, иначе он уйдёт следующему").format(
            title=drop.title, until=timezone.localtime(until).strftime("%H:%M")
        ),
    )
    return len(waiting)


def expire_offers(now: dt.datetime | None = None) -> int:
    """Не ответил вовремя — билет следующему в очереди."""
    now = now or timezone.now()
    expired = 0
    drop_ids = set(
        TicketClaim.objects.filter(status=ClaimStatus.OFFERED, offer_until__lt=now).values_list("drop_id", flat=True)
    )
    for drop_id in drop_ids:
        with transaction.atomic():
            drop = TicketDrop.objects.select_for_update().get(pk=drop_id)
            expired += drop.claims.filter(status=ClaimStatus.OFFERED, offer_until__lt=now).update(
                status=ClaimStatus.EXPIRED, decided_at=now
            )
            offer_next(drop, now)
    return expired


def stage(drop: TicketDrop, now: dt.datetime | None = None) -> str:
    """«announce» — до старта, «open» — идёт, «gone» — разобраны, «past» — событие прошло."""
    now = now or timezone.now()
    if now >= drop.event_at:
        return "past"
    if now < drop.opens_at:
        return "announce"
    return "gone" if held(drop) >= drop.count else "open"
