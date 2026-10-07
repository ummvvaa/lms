"""Журнал писем доступа, дневной бюджет и очередь массовых приглашений."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from accounts.logins import address_of, student_archived
from accounts.models import InviteMail, LinkPurpose, MailDayBudget, User
from core import mail, phrasing, school_rules, stored_text

ALMATY = ZoneInfo("Asia/Almaty")
PENDING = (InviteMail.Status.QUEUED, InviteMail.Status.SENDING)
UNKNOWN_RESULT = gettext_noop("Результат отправки неизвестен: проверьте журнал почтового сервиса перед повтором")


def _actor_name(actor) -> str:
    return (actor.full_name or actor.handle) if actor is not None else ""


def _lock_day():
    """Один замок для прямых писем, двух массовых входов и фоновых задач."""
    while True:
        day = timezone.now().astimezone(UTC).date()
        MailDayBudget.objects.get_or_create(day=day)
        MailDayBudget.objects.select_for_update().get(day=day)
        now = timezone.now()
        if now.astimezone(UTC).date() == day:
            return now
        # Ожидание могло пересечь полночь UTC. До резерва берём замок
        # новых суток, иначе параллельный запрос считал бы другой бюджет.


def _spent(now) -> int:
    """Неопределённая попытка занимает все сутки, которые могла затронуть."""
    start = datetime.combine(now.astimezone(UTC).date(), time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    return InviteMail.objects.filter(
        Q(status=InviteMail.Status.SENT, sent_at__gte=start, sent_at__lt=end)
        | Q(status=InviteMail.Status.SENDING)
        | (Q(uncertain=True, started_at__lt=end) & (Q(finished_at__gte=start) | Q(finished_at__isnull=True)))
    ).count()


def _limit() -> int:
    return int(school_rules.value(school_rules.MAIL_DAILY_LIMIT))


def _next_slot(now, limit: int):
    """Следующий день с местом; время очереди всегда по Алматы."""
    # До 05:00 Алматы сутки провайдера ещё не сменились: ближайшее
    # свободное утро будет сегодня, после сброса в 00:00 UTC.
    day = now.astimezone(UTC).date() + timedelta(days=1)
    while True:
        moment = datetime.combine(day, time(9), tzinfo=ALMATY)
        count = InviteMail.objects.filter(
            status=InviteMail.Status.QUEUED,
            scheduled_at__gte=moment,
            scheduled_at__lt=moment + timedelta(days=1),
        ).count()
        if not limit or count < limit:
            return moment
        day += timedelta(days=1)


def _recent(user, now):
    days = int(school_rules.value(school_rules.INVITE_REPEAT_DAYS))
    if not days:
        return None
    return (
        InviteMail.objects.filter(
            user=user,
            purpose=LinkPurpose.INVITE,
            status=InviteMail.Status.SENT,
            sent_at__gt=now - timedelta(days=days),
            token__used_at__isnull=True,
            token__expires_at__gt=now,
        )
        .order_by("-sent_at")
        .first()
    )


def _skip_reason(user, *, now, force: bool, pending_id=None) -> str:
    if not user.is_active:
        return _("Учётная запись отключена")
    if student_archived(user):
        return _("Учётная запись в архиве — вход закрыт")
    if not address_of(user):
        return _("Нет почты")
    pending = InviteMail.objects.filter(user=user, bulk=True, status__in=PENDING)
    if pending_id is not None:
        pending = pending.exclude(pk=pending_id)
    if pending.exists():
        return _("Приглашение уже в очереди или отправляется")
    recent = None if force else _recent(user, now)
    if recent is not None:
        return _("Письмо уже уходило {moment}").format(moment=phrasing.until(recent.sent_at))
    return ""


def _new_entry(user, *, actor, address, purpose, **fields):
    return InviteMail.objects.create(
        user=user, actor=actor, actor_name=_actor_name(actor), address=address, purpose=purpose, **fields
    )


def deliver(*, user, address, purpose, sender, actor=None, entry=None, token=None, secrets=()) -> bool:
    """Записать фактический ответ транспорта; прямые письма не ставятся в очередь."""
    if entry is None:
        with transaction.atomic():
            now = _lock_day()
            entry = _new_entry(
                user,
                actor=actor,
                address=address,
                purpose=purpose,
                status=InviteMail.Status.SENDING,
                started_at=now,
                token=token,
            )
    elif token is not None:
        InviteMail.objects.filter(pk=entry.pk).update(token=token, address=address)
    try:
        # Тело уже собрано на языке адресата. Причина результата хранится
        # по-русски и переводится отдельно на язык читающего историю.
        with translation.override("ru"):
            result = sender()
    except Exception as error:
        # Незнакомая ошибка не превращает попытку в вечную запись «отправляется».
        # Повторять её автоматически нельзя: SMTP мог уже принять письмо.
        result = mail.SendResult(False, mail.safe_error(error, secrets=secrets), uncertain=True)
    finished_at = timezone.now()
    InviteMail.objects.filter(pk=entry.pk).update(
        status=InviteMail.Status.SENT if result.sent else InviteMail.Status.FAILED,
        sent_at=finished_at if result.sent else None,
        finished_at=finished_at,
        error=result.error,
        uncertain=result.uncertain,
    )
    return result.sent


def _send_reserved(entry) -> bool:
    from accounts import magic_link

    try:
        _, sent_to = magic_link.issue_for(entry.user, purpose=LinkPurpose.INVITE, actor=entry.actor, mail_entry=entry)
        if not sent_to:
            # Подтверждённый адрес мог исчезнуть после выбора из очереди.
            InviteMail.objects.filter(pk=entry.pk, status=InviteMail.Status.SENDING).update(
                status=InviteMail.Status.FAILED, error=gettext_noop("Нет почты"), finished_at=timezone.now()
            )
        return bool(sent_to)
    except Exception as error:
        InviteMail.objects.filter(pk=entry.pk).update(
            status=InviteMail.Status.FAILED, error=mail.safe_error(error), uncertain=True, finished_at=timezone.now()
        )
        return False


def bulk_invite(users, *, actor, force: bool = False) -> dict:
    """Отправить сколько позволяет бюджет; остаток сохранить без выпуска ссылок."""
    result = {"sent": 0, "queued": 0, "failed": 0, "skipped": [], "failures": []}
    seen = set()
    for selected in users:
        if selected.pk in seen:
            continue
        seen.add(selected.pk)
        with transaction.atomic():
            # NO KEY UPDATE сериализует заявки получателю, но не мешает
            # внешнему ключу прямого письма, уже занявшего дневной замок.
            user = User.objects.select_for_update(no_key=True).get(pk=selected.pk)
            now = timezone.now()
            reason = _skip_reason(user, now=now, force=force)
            if reason:
                result["skipped"].append({"user": user.pk, "email": address_of(user), "reason": reason})
                continue
            now = _lock_day()
            limit = _limit()
            queued = bool(limit and _spent(now) >= limit)
            entry = _new_entry(
                user,
                actor=actor,
                address=address_of(user),
                purpose=LinkPurpose.INVITE,
                status=InviteMail.Status.QUEUED if queued else InviteMail.Status.SENDING,
                scheduled_at=_next_slot(now, limit) if queued else None,
                started_at=None if queued else now,
                bulk=True,
                force=force,
            )
        if queued:
            result["queued"] += 1
        elif _send_reserved(entry):
            result["sent"] += 1
        else:
            result["failed"] += 1
            entry.refresh_from_db(fields=["error", "uncertain"])
            result["failures"].append({"email": entry.address, "reason": _error_text(entry)})
    return result


def _claim(pk):
    """Проверить очередь заново и занять дневное место до вызова SMTP."""
    snapshot = InviteMail.objects.filter(pk=pk).first()
    if snapshot is None:
        return None
    with transaction.atomic():
        user = User.objects.select_for_update(no_key=True).filter(pk=snapshot.user_id).first()
        entry = InviteMail.objects.select_for_update().get(pk=pk)
        now = timezone.now()
        if entry.status != InviteMail.Status.QUEUED or entry.scheduled_at > now:
            return None
        with translation.override("ru"):
            reason = (
                _("Учётная запись удалена")
                if user is None
                else _skip_reason(user, now=now, force=entry.force, pending_id=entry.pk)
            )
        if reason:
            entry.status = InviteMail.Status.CANCELLED
            entry.error = reason
            entry.finished_at = now
            entry.save(update_fields=["status", "error", "finished_at"])
            return None
        now = _lock_day()
        limit = _limit()
        if limit and _spent(now) >= limit:
            entry.scheduled_at = _next_slot(now, limit)
            entry.save(update_fields=["scheduled_at"])
            return None
        entry.user = user
        entry.address = address_of(user)
        entry.started_at = now
        entry.status = InviteMail.Status.SENDING
        entry.save(update_fields=["address", "started_at", "status"])
        return entry


def drain_queue() -> dict:
    """Периодический запуск догоняет пропущенное утро, но не шлёт до 09:00."""
    now = timezone.now()
    # После потери процесса неизвестно, принял ли сервер письмо. Сохраняем
    # неопределённость и расход суток; заново такое письмо само не отправится.
    InviteMail.objects.filter(status=InviteMail.Status.SENDING, started_at__lt=now - timedelta(hours=1)).update(
        status=InviteMail.Status.FAILED,
        uncertain=True,
        finished_at=now,
        error=UNKNOWN_RESULT,
    )
    result = {"sent": 0, "failed": 0}
    if now.astimezone(ALMATY).hour < 9:
        return result
    pending = list(
        InviteMail.objects.filter(status=InviteMail.Status.QUEUED, scheduled_at__lte=now)
        .order_by("scheduled_at", "created_at", "pk")
        .values_list("pk", flat=True)[:500]
    )
    for pk in pending:
        entry = _claim(pk)
        if entry is not None:
            result["sent" if _send_reserved(entry) else "failed"] += 1
    return result


def queue_summary() -> dict:
    pending = InviteMail.objects.filter(bulk=True, status__in=PENDING)
    next_send = (
        pending.filter(status=InviteMail.Status.QUEUED)
        .order_by("scheduled_at")
        .values_list("scheduled_at", flat=True)
        .first()
    )
    return {"pending": pending.count(), "next_send_at": next_send.isoformat() if next_send else None}


def cancel_queue(*, actor) -> dict:
    """Отменить только ещё не взятые письма; отправляемые остаются в истории."""
    cancelled = InviteMail.objects.filter(bulk=True, status=InviteMail.Status.QUEUED).update(
        status=InviteMail.Status.CANCELLED,
        cancelled_by=actor,
        cancelled_by_name=_actor_name(actor),
        finished_at=timezone.now(),
    )
    return {"cancelled": cancelled}


def history(user, *, limit=20) -> list[dict]:
    """История для карточки без содержимого письма и одноразовых ссылок."""

    def stamp(value):
        return value.isoformat() if value else None

    return [
        {
            "id": entry.pk,
            "status": entry.status,
            "status_title": _("Результат неизвестен") if entry.uncertain else str(entry.get_status_display()),
            "purpose": entry.purpose,
            "purpose_title": str(entry.get_purpose_display()),
            "address": entry.address,
            "actor": entry.actor_id,
            "actor_name": entry.actor_name,
            "created_at": stamp(entry.created_at),
            "scheduled_at": stamp(entry.scheduled_at),
            "finished_at": stamp(entry.finished_at),
            "sent_at": stamp(entry.sent_at),
            "error": _error_text(entry),
            "uncertain": entry.uncertain,
        }
        for entry in InviteMail.objects.filter(user=user)[:limit]
    ]


def _error_text(entry) -> str:
    text = stored_text.localize(entry.error)
    if entry.uncertain and entry.error != UNKNOWN_RESULT:
        return f"{_(UNKNOWN_RESULT)}. {text}".strip()
    return text
