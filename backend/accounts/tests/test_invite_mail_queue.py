"""Письма доступа: достоверный журнал, UTC-бюджет и устойчивая очередь."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from smtplib import SMTPDataError
from threading import Event, local

import pytest
from django.db import close_old_connections, connection, transaction
from django.db.models import QuerySet

from accounts import magic_link, mailing, temporary
from accounts.models import InviteMail, LinkPurpose, MagicLinkToken, MailDayBudget, Role, User
from core import mail

pytestmark = pytest.mark.django_db


@pytest.fixture
def django_db_setup(django_db_setup, django_db_blocker, request):
    """После проверок конкуренции вернуть миграционные справочники.

    Этот внешний слой завершается после flush внутри pytest-django.
    serialized_rollback восстанавливает данные до следующего теста,
    но без этого слоя последний flush оставляет --reuse-db без справочников.
    Обычным тестам файла дополнительная сериализация не нужна.
    """
    marker = request.node.get_closest_marker("django_db")
    snapshot = None
    if marker is not None and marker.kwargs.get("transaction", False):
        with django_db_blocker.unblock():
            snapshot = connection.creation.serialize_db_to_string()
    try:
        yield
    finally:
        if snapshot is not None:
            with django_db_blocker.unblock():
                connection.creation.deserialize_db_from_string(snapshot)


@pytest.fixture
def moment(monkeypatch):
    clock = [datetime(2026, 10, 7, 6, tzinfo=UTC)]
    monkeypatch.setattr(mailing.timezone, "now", lambda: clock[0])
    return clock


@pytest.fixture
def people(make_user):
    return [make_user(email=f"mail-{index}@example.kz") for index in range(7)]


def test_every_access_mail_has_actual_result_and_actor(make_user, mailoutbox, moment):
    user = make_user(email="recipient@example.kz")
    actor = make_user(Role.ADMIN, full_name="Администратор")
    token, address = magic_link.issue_for(user, purpose=LinkPurpose.INVITE, actor=actor)
    magic_link.issue(user.email, purpose=LinkPurpose.RESET)
    magic_link.issue(user.email, purpose=LinkPurpose.LOGIN)
    magic_link.issue_confirmation(user, "personal@example.kz")
    raw = temporary.issue(user)
    assert temporary.send_letter(user, raw, actor=actor)
    assert address == user.email
    assert len(mailoutbox) == 5
    entries = InviteMail.objects.filter(user=user)
    assert set(entries.values_list("purpose", flat=True)) == set(InviteMail.Purpose.values)
    assert entries.filter(status=InviteMail.Status.SENT, sent_at=moment[0]).count() == 5
    invitation = entries.get(purpose=LinkPurpose.INVITE)
    assert invitation.actor == actor
    assert invitation.actor_name == actor.full_name
    assert token not in str(mailing.history(user))
    assert raw not in str(mailing.history(user))


def test_smtp_error_is_failed_and_secrets_are_removed(make_user, monkeypatch):
    user = make_user()
    token = "sensitive-invitation-token-which-must-not-leak"
    monkeypatch.setattr(magic_link.secrets, "token_urlsafe", lambda size: token)

    def rejected(*args, **kwargs):
        raise SMTPDataError(550, f"denied {token}".encode())

    monkeypatch.setattr(mail.EmailMultiAlternatives, "send", rejected)
    raw, address = magic_link.issue_for(user, purpose=LinkPurpose.INVITE)
    assert raw == token and address == ""
    entry = InviteMail.objects.get()
    assert entry.status == InviteMail.Status.FAILED
    assert entry.sent_at is None and not entry.uncertain
    assert "550" in entry.error and token not in entry.error
    password = "abcd-efgh-jkmn"

    def rejected_password(*args, **kwargs):
        raise SMTPDataError(550, f"denied {password}".encode())

    monkeypatch.setattr(mail.EmailMultiAlternatives, "send", rejected_password)
    assert not temporary.send_letter(user, password)
    assert password not in str(mailing.history(user))


def test_console_mail_is_not_marked_as_sent(make_user, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
    _, address = magic_link.issue_for(make_user(), purpose=LinkPurpose.INVITE)
    assert address == ""
    assert InviteMail.objects.get().status == InviteMail.Status.FAILED


@pytest.mark.parametrize("exception", [RuntimeError, ValueError, OSError])
def test_unexpected_transport_error_never_exposes_temporary_password(make_user, monkeypatch, exception):
    password = "abcd-efgh-jkmn"

    def rejected(*args, **kwargs):
        raise exception(f"unexpected transport error: {password}")

    monkeypatch.setattr(mail.EmailMultiAlternatives, "send", rejected)
    user = make_user()
    assert not temporary.send_letter(user, password)
    row = mailing.history(user)[0]
    assert password not in row["error"]
    assert row["uncertain"] is True
    assert row["status_title"] == "Результат неизвестен"
    assert "проверьте журнал" in row["error"]


def test_bulk_spreads_days_without_creating_tokens_early(people, set_rules, moment, mailoutbox):
    set_rules(mail_daily_limit=2)
    result = mailing.bulk_invite(people, actor=None)
    assert (result["sent"], result["queued"], result["failed"]) == (2, 5, 0)
    assert MagicLinkToken.objects.count() == 2
    pending = list(InviteMail.objects.filter(status=InviteMail.Status.QUEUED).order_by("scheduled_at", "pk"))
    assert [row.scheduled_at.astimezone(mailing.ALMATY).day for row in pending] == [8, 8, 9, 9, 10]
    assert all(row.scheduled_at.astimezone(mailing.ALMATY).hour == 9 for row in pending)
    assert mailing.queue_summary()["pending"] == 5
    moment[0] = datetime(2026, 10, 8, 3, 59, tzinfo=UTC)
    assert mailing.drain_queue()["sent"] == 0
    moment[0] += timedelta(minutes=1)
    assert mailing.drain_queue()["sent"] == 2
    assert len(mailoutbox) == 4
    token = MagicLinkToken.objects.filter(user=pending[0].user).get()
    assert token.expires_at == moment[0] + timedelta(days=2)
    assert mailing.drain_queue()["sent"] == 0


def test_recent_and_pending_duplicates_force_does_not_bypass_cap(people, set_rules, moment):
    set_rules(mail_daily_limit=2)
    assert mailing.bulk_invite([people[0]], actor=None)["sent"] == 1
    assert len(mailing.bulk_invite([people[0]], actor=None)["skipped"]) == 1
    assert mailing.bulk_invite([people[0]], actor=None, force=True)["sent"] == 1
    assert mailing.bulk_invite([people[0]], actor=None, force=True)["queued"] == 1
    assert len(mailing.bulk_invite([people[0]], actor=None, force=True)["skipped"]) == 1
    assert InviteMail.objects.filter(user=people[0], status=InviteMail.Status.QUEUED).count() == 1


def test_legacy_link_has_no_fake_sent_record_and_does_not_block_mail(people):
    magic_link.issue_for(people[0], purpose=LinkPurpose.INVITE, send=False)
    assert not InviteMail.objects.exists()
    assert mailing.bulk_invite([people[0]], actor=None)["sent"] == 1
    assert InviteMail.objects.count() == 1


def test_no_email_and_inactive_are_skipped_without_tokens(people):
    people[0].is_active = False
    people[0].save(update_fields=["is_active"])
    people[1].email = None
    people[1].login = "no.email"
    people[1].save(update_fields=["email", "login"])
    result = mailing.bulk_invite(people[:2], actor=None)
    assert len(result["skipped"]) == 2
    assert not InviteMail.objects.exists() and not MagicLinkToken.objects.exists()


def test_direct_mail_reservation_reduces_budget_before_smtp_finishes(people, set_rules, monkeypatch):
    set_rules(mail_daily_limit=1)

    def transport(**kwargs):
        # Прямая отправка ещё не завершена, но место уже занято.
        result = mailing.bulk_invite([people[1]], actor=None)
        assert result["queued"] == 1 and result["sent"] == 0
        return mail.SendResult(True)

    monkeypatch.setattr(mail, "send_result", transport)
    magic_link.issue(people[0].email, purpose=LinkPurpose.RESET)
    assert InviteMail.objects.filter(status=InviteMail.Status.SENT).count() == 1


def test_utc_reset_does_not_follow_local_midnight(people, set_rules, moment):
    set_rules(mail_daily_limit=1)
    moment[0] = datetime(2026, 10, 7, 18, 59, tzinfo=UTC)
    assert mailing.bulk_invite([people[0]], actor=None)["sent"] == 1
    moment[0] += timedelta(minutes=2)
    assert mailing.bulk_invite([people[1]], actor=None)["queued"] == 1
    moment[0] = datetime(2026, 10, 8, tzinfo=UTC)
    assert mailing.bulk_invite([people[2]], actor=None)["sent"] == 1


def test_queue_created_after_local_midnight_uses_nearest_morning(people, set_rules, moment):
    set_rules(mail_daily_limit=1)
    moment[0] = datetime(2026, 10, 7, 18, 59, tzinfo=UTC)
    mailing.bulk_invite([people[0]], actor=None)
    moment[0] = datetime(2026, 10, 7, 23, tzinfo=UTC)
    mailing.bulk_invite([people[1]], actor=None)
    entry = InviteMail.objects.get(status=InviteMail.Status.QUEUED)
    assert entry.scheduled_at == datetime(2026, 10, 8, 4, tzinfo=UTC)


def test_budget_relocks_new_utc_day_after_waiting_across_midnight(moment, monkeypatch):
    old = datetime(2026, 10, 7, 23, 59, tzinfo=UTC)
    new = datetime(2026, 10, 8, tzinfo=UTC)
    moment[0] = old
    original_get = QuerySet.get

    def get_after_wait(queryset, *args, **kwargs):
        row = original_get(queryset, *args, **kwargs)
        if queryset.model is MailDayBudget and queryset.query.select_for_update:
            moment[0] = new
        return row

    monkeypatch.setattr(QuerySet, "get", get_after_wait)
    with transaction.atomic():
        assert mailing._lock_day() == new
    assert set(MailDayBudget.objects.values_list("day", flat=True)) == {old.date(), new.date()}


@pytest.mark.parametrize("sent,uncertain", [(False, True), (True, False), (False, False)])
def test_result_crossing_utc_midnight_accounts_for_possible_delivery_days(
    people, set_rules, moment, monkeypatch, sent, uncertain
):
    set_rules(mail_daily_limit=1)
    started = datetime(2026, 10, 7, 23, 59, 59, tzinfo=UTC)
    finished = datetime(2026, 10, 8, 0, 0, 2, tzinfo=UTC)
    moment[0] = started

    def transport(**kwargs):
        moment[0] = finished
        return mail.SendResult(sent, "" if sent else "SMTP unavailable", uncertain=uncertain)

    monkeypatch.setattr(mail, "send_result", transport)
    magic_link.issue_for(people[0], purpose=LinkPurpose.RESET)
    entry = InviteMail.objects.get()
    assert entry.started_at == started and entry.finished_at == finished
    assert entry.sent_at == (finished if sent else None)
    assert mailing._spent(started) == int(uncertain)
    assert mailing._spent(finished) == int(sent or uncertain)
    assert mailing._spent(finished + timedelta(days=1)) == 0
    if uncertain:
        assert mailing.bulk_invite([people[1]], actor=None)["queued"] == 1


def test_stale_sending_cleanup_keeps_new_day_reserved_until_uncertainty_ends(people, moment):
    started = datetime(2026, 10, 7, 23, 59, tzinfo=UTC)
    moment[0] = datetime(2026, 10, 8, 1, tzinfo=UTC)
    entry = InviteMail.objects.create(
        user=people[0],
        address=people[0].email,
        purpose=LinkPurpose.INVITE,
        status=InviteMail.Status.SENDING,
        started_at=started,
    )
    mailing.drain_queue()
    entry.refresh_from_db()
    assert entry.status == InviteMail.Status.FAILED and entry.uncertain
    assert entry.finished_at == moment[0]
    assert mailing._spent(started) == 1
    assert mailing._spent(moment[0]) == 1
    assert mailing._spent(moment[0] + timedelta(days=1)) == 0


def test_uncertain_attempt_without_completion_remains_reserved(people, moment):
    InviteMail.objects.create(
        user=people[0],
        address=people[0].email,
        purpose=LinkPurpose.INVITE,
        status=InviteMail.Status.FAILED,
        started_at=moment[0] - timedelta(days=1),
        uncertain=True,
    )
    assert mailing._spent(moment[0]) == 1


def test_cancel_does_not_cancel_in_flight_and_keeps_actor(people, make_user, set_rules, moment):
    set_rules(mail_daily_limit=1)
    actor = make_user(Role.ADMIN)
    mailing.bulk_invite(people[:3], actor=actor)
    sent = InviteMail.objects.get(status=InviteMail.Status.SENT)
    sent.status = InviteMail.Status.SENDING
    sent.save(update_fields=["status"])
    assert mailing.cancel_queue(actor=actor) == {"cancelled": 2}
    assert InviteMail.objects.filter(status=InviteMail.Status.CANCELLED, cancelled_by=actor).count() == 2
    assert InviteMail.objects.filter(status=InviteMail.Status.CANCELLED, finished_at=moment[0]).count() == 2
    assert mailing.queue_summary()["pending"] == 1
    moment[0] += timedelta(days=1)
    assert mailing.drain_queue() == {"sent": 0, "failed": 0}
    sent.refresh_from_db()
    assert sent.status == InviteMail.Status.FAILED and sent.uncertain


def test_worker_rechecks_address_and_disabled_account(people, set_rules, moment):
    set_rules(mail_daily_limit=1)
    mailing.bulk_invite(people[:3], actor=None)
    people[1].is_active = False
    people[1].save(update_fields=["is_active"])
    people[2].email = "changed@example.kz"
    people[2].save(update_fields=["email"])
    moment[0] += timedelta(days=2)
    assert mailing.drain_queue()["sent"] == 1
    assert InviteMail.objects.get(user=people[1]).status == InviteMail.Status.CANCELLED
    assert InviteMail.objects.get(user=people[2]).address == "changed@example.kz"


def test_worker_does_not_mail_archived_student(people, set_rules, moment):
    from students.models import Student

    set_rules(mail_daily_limit=1)
    student = Student.objects.create(user=people[1], first_name="Ученик", last_name="Архивный", graduation_year=2027)
    mailing.bulk_invite(people[:2], actor=None)
    student.archived_at = moment[0]
    student.save(update_fields=["archived_at"])
    moment[0] += timedelta(days=1)
    assert mailing.drain_queue()["sent"] == 0
    entry = InviteMail.objects.get(user=people[1])
    assert entry.status == InviteMail.Status.CANCELLED and "архив" in entry.error


def test_zero_budget_and_zero_repeat_interval_allow_unlimited(people, set_rules):
    set_rules(mail_daily_limit=0, invite_repeat_days=0)
    assert mailing.bulk_invite(people, actor=None)["sent"] == len(people)
    assert mailing.bulk_invite(people, actor=None)["sent"] == len(people)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_bulk_calls_share_budget_and_pending_constraint(people, set_rules, monkeypatch):
    set_rules(mail_daily_limit=2)
    monkeypatch.setattr(mail, "send_result", lambda **kwargs: mail.SendResult(True))

    def send(ids):
        close_old_connections()
        try:
            return mailing.bulk_invite(list(User.objects.filter(pk__in=ids)), actor=None)
        finally:
            close_old_connections()

    ids = [person.pk for person in people]
    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(send, [ids, ids, ids]))
    assert sum(row["sent"] for row in outcomes) == 2
    assert InviteMail.objects.filter(status=InviteMail.Status.SENDING).count() == 0
    assert InviteMail.objects.filter(status=InviteMail.Status.SENT).count() == 2
    assert InviteMail.objects.filter(status=InviteMail.Status.QUEUED).count() == 5


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_parallel_workers_claim_each_letter_once_and_respect_daily_budget(people, set_rules, monkeypatch, moment):
    set_rules(mail_daily_limit=1)
    monkeypatch.setattr(mail, "send_result", lambda **kwargs: mail.SendResult(True))
    mailing.bulk_invite(people, actor=None)
    moment[0] += timedelta(days=7)
    set_rules(mail_daily_limit=2)

    def drain(_number):
        close_old_connections()
        try:
            return mailing.drain_queue()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(drain, range(3)))
    assert sum(row["sent"] for row in outcomes) == 2
    assert InviteMail.objects.filter(status=InviteMail.Status.SENT).count() == 3
    assert InviteMail.objects.filter(status=InviteMail.Status.QUEUED).count() == 4


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_direct_and_bulk_to_same_user_do_not_deadlock(people, set_rules, monkeypatch):
    set_rules(mail_daily_limit=1)
    monkeypatch.setattr(mail, "send_result", lambda **kwargs: mail.SendResult(True))
    day_held = Event()
    bulk_waiting = Event()
    caller = local()
    original_lock = mailing._lock_day

    def controlled_lock():
        if caller.kind == "bulk":
            bulk_waiting.set()
        now = original_lock()
        if caller.kind == "direct":
            day_held.set()
            assert bulk_waiting.wait(timeout=5)
        return now

    monkeypatch.setattr(mailing, "_lock_day", controlled_lock)

    def send(kind):
        close_old_connections()
        caller.kind = kind
        try:
            user = User.objects.get(pk=people[0].pk)
            if kind == "direct":
                return magic_link.issue_for(user, purpose=LinkPurpose.RESET)
            assert day_held.wait(timeout=5)
            return mailing.bulk_invite([user], actor=None)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        direct = pool.submit(send, "direct")
        bulk = pool.submit(send, "bulk")
        assert direct.result(timeout=10)[1] == people[0].email
        assert bulk.result(timeout=10)["queued"] == 1
    assert InviteMail.objects.filter(status=InviteMail.Status.SENT).count() == 1
