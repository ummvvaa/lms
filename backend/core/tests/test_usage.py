"""Доставка событий, снимок роли, минимальный состав записи и срок хранения."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.utils import timezone

from accounts.models import Role, User
from core import usage
from core.models import UsageEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def published(monkeypatch):
    batches = []

    def publish(*, args, producer, retry, ignore_result):
        assert retry is False and ignore_result is True
        assert producer is not None
        batches.append(args[0])

    monkeypatch.setattr("core.tasks.record_usage_events.apply_async", publish)
    return batches


def request_for(user, url_name=None):
    return SimpleNamespace(user=user, resolver_match=SimpleNamespace(url_name=url_name), query_params={}, data={})


def test_track_waits_for_commit_and_snapshots_role_and_time(make_user, published, django_capture_on_commit_callbacks):
    actor = make_user(Role.CURATOR)
    before = timezone.now()
    with django_capture_on_commit_callbacks(execute=True):
        usage.track(request_for(actor), "journal.grade.set")
        assert published == []
        actor.role = Role.DIRECTOR_EXAM
        actor.save(update_fields=["role"])
    assert len(published) == 1 and len(published[0]) == 1
    event = published[0][0]
    assert event["role"] == Role.CURATOR
    assert event["actor_id"] == actor.pk
    assert event["action"] == "journal.grade.set" and event["screen"] == "/journals/:id"
    assert before <= datetime.fromisoformat(event["occurred_at"]) <= timezone.now()
    usage.store_events(published[0])
    assert UsageEvent.objects.get().role == Role.CURATOR


def test_rolled_back_operation_publishes_nothing(make_user, published, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(ValueError), transaction.atomic():
            usage.track(request_for(make_user(Role.ADMIN)), "report.build")
            raise ValueError("откат")
    assert published == []


def test_broker_failure_does_not_fail_action_or_log_data(
    make_user, monkeypatch, caplog, django_capture_on_commit_callbacks
):
    secret = "private-token-and-password"

    def broken(*args, **kwargs):
        raise ConnectionError(secret)

    monkeypatch.setattr("core.tasks.record_usage_events.apply_async", broken)
    with django_capture_on_commit_callbacks(execute=True):
        usage.track(request_for(make_user(Role.ADMIN)), "access.link.issue")
    assert secret not in caplog.text
    assert "Не удалось передать" in caplog.text


def test_publisher_limits_own_connection_and_never_waits_for_shared_pool(
    make_user, monkeypatch, django_capture_on_commit_callbacks
):
    from core.tasks import record_usage_events

    app = record_usage_events.app
    original = app.connection_for_write
    original_options = dict(app.conf.broker_transport_options)
    connections = []
    releases = []

    def connection_for_write(**options):
        connection = original(**options)
        connections.append(connection)
        release = connection.release

        def close():
            releases.append(connection)
            release()

        monkeypatch.setattr(connection, "release", close)
        return connection

    def no_pool(*args, **kwargs):
        pytest.fail("Аналитика не должна получать producer или connection из общего пула")

    def publish(*, args, producer, retry, ignore_result):
        assert retry is False and ignore_result is True
        assert producer.connection is connections[0]
        assert len(args[0]) == 1

    monkeypatch.setattr(app.pool, "acquire", no_pool)
    monkeypatch.setattr(app.producer_pool, "acquire", no_pool)
    monkeypatch.setattr(app, "connection_for_write", connection_for_write)
    monkeypatch.setattr(record_usage_events, "apply_async", publish)
    with django_capture_on_commit_callbacks(execute=True):
        usage.track(request_for(make_user(Role.ADMIN)), "report.build")

    assert len(connections) == 1 and releases == connections
    connection = connections[0]
    assert connection.connect_timeout == usage.PUBLISH_TIMEOUT == 0.25
    for key in ("socket_connect_timeout", "socket_timeout", "connect_retries_timeout"):
        assert connection.transport_options[key] == usage.PUBLISH_TIMEOUT
    assert connection.transport_options["retry_on_timeout"] is False
    assert connection.transport_options["max_retries"] == 0
    assert app.conf.broker_transport_options == original_options


@pytest.mark.parametrize("failure", ["connection", "publication"])
def test_timeout_is_private_and_closes_the_unpooled_connection(
    failure, make_user, monkeypatch, caplog, django_capture_on_commit_callbacks
):
    from core.tasks import record_usage_events

    app = record_usage_events.app
    original = app.connection_for_write
    released = []
    secret = "private-broker-password-and-event"

    def connection_for_write(**options):
        if failure == "connection":
            raise TimeoutError(secret)
        connection = original(**options)
        release = connection.release

        def close():
            released.append(True)
            release()

        monkeypatch.setattr(connection, "release", close)
        return connection

    def broken(*args, **kwargs):
        raise TimeoutError(secret)

    monkeypatch.setattr(app, "connection_for_write", connection_for_write)
    monkeypatch.setattr(record_usage_events, "apply_async", broken)
    with django_capture_on_commit_callbacks(execute=True):
        usage.track(request_for(make_user(Role.ADMIN)), "access.link.issue")
    assert released == ([True] if failure == "publication" else [])
    assert secret not in caplog.text
    assert "Не удалось передать" in caplog.text


def test_delivery_repeats_are_scoped_to_actor_and_survive_deletion(
    make_user, published, django_capture_on_commit_callbacks
):
    first = make_user(Role.STUDENT, "first@example.kz")
    second = make_user(Role.STUDENT, "second@example.kz")
    event = {"id": uuid.uuid4(), "action": "screen.open", "screen": "/dashboard"}
    with django_capture_on_commit_callbacks(execute=True):
        usage.track_client(request_for(first), [event])
        usage.track_client(request_for(second), [event])
    assert published[0][0]["event_id"] != published[1][0]["event_id"]
    for batch in published:
        usage.store_events(batch)
        usage.store_events(batch)
    assert UsageEvent.objects.count() == 2
    first_id = first.pk
    User.objects.filter(pk=first_id).delete()
    usage.store_events(published[0])
    assert UsageEvent.objects.count() == 2
    assert UsageEvent.objects.get(event_id=published[0][0]["event_id"]).actor_id is None


def test_actor_deleted_before_worker_preserves_event_without_extra_identity(
    make_user, published, django_capture_on_commit_callbacks
):
    actor = make_user(Role.DIRECTOR_BEHAVIOR)
    with django_capture_on_commit_callbacks(execute=True):
        usage.track(request_for(actor), "auth.login")
    actor.delete()
    usage.store_events(published[0])
    usage.store_events(published[0])
    event = UsageEvent.objects.get()
    assert event.actor_id is None and event.role == Role.DIRECTOR_BEHAVIOR


def test_event_has_no_object_student_body_or_actor_name_columns():
    assert {field.name for field in UsageEvent._meta.fields} == {
        "id",
        "event_id",
        "actor",
        "role",
        "action",
        "screen",
        "occurred_at",
        "source",
    }


def test_helper_skips_missing_unauthenticated_and_nonreal_actors(
    make_user, published, django_capture_on_commit_callbacks
):
    actors = [AnonymousUser(), make_user(Role.STUDENT, "actor@probe.local"), make_user(Role.TEACHER, is_fictional=True)]
    inactive = make_user(Role.ADMIN, is_active=False)
    with django_capture_on_commit_callbacks(execute=True):
        usage.track(None, "auth.login")
        for actor in [*actors, inactive]:
            usage.track(request_for(actor), "auth.login")
    assert published == []


def test_export_is_only_for_allowlisted_file_response(make_user, published, django_capture_on_commit_callbacks):
    actor = make_user(Role.ADMIN)
    with django_capture_on_commit_callbacks(execute=True):
        usage.track(request_for(actor, "mock-template"), "export.download")
        usage.track(request_for(actor, "other-route"), "export.download")
        preview = request_for(actor, "usage-export")
        preview.query_params = {"preview": "1"}
        usage.track(preview, "export.download")
        usage.track(request_for(actor, "acad-report-pdf"), "export.download")
    assert len(published) == 1
    assert published[0][0]["screen"] == "/reports"


def test_retention_cutoff_is_strict_and_weekly_setting_exists(make_user, monkeypatch, settings):
    now = datetime(2026, 10, 7, 10, tzinfo=ZoneInfo("Asia/Almaty"))
    monkeypatch.setattr(usage.timezone, "now", lambda: now)
    actor = make_user(Role.ADMIN)
    for stamp in (now, now - timedelta(days=365), now - timedelta(days=365, microseconds=1)):
        UsageEvent.objects.create(
            event_id=uuid.uuid4(),
            actor=actor,
            role=actor.role,
            action="screen.open",
            screen="/dashboard",
            occurred_at=stamp,
            source="client",
        )
    assert usage.purge_old_events() == 1
    assert usage.purge_old_events() == 0
    assert UsageEvent.objects.count() == 2
    scheduled = settings.CELERY_BEAT_SCHEDULE["purge-usage-events"]
    assert scheduled["task"] == "core.purge_usage_events"
    assert scheduled["schedule"].day_of_week == {0}
