"""Запуск фоновой операции: очередь, двойной запуск, отмена, зависание.

Отмена кооперативная: статус «Отменён» и есть флаг, который `llm.complete`
проверяет до вызова модели и после. Поздний ответ отменённого запуска
записывается в журнал расходов, но не сохраняется и ничего не перезаписывает.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core import jobs
from core.models import AuditLog, BackgroundJob, Notification
from suggestions.models import LLMCall
from suggestions.providers import Completion, Usage

LIVE = {
    "PROVIDER": "fake",
    "API_KEY": "k",
    "BASE_URL": "",
    "MODEL": "fake-1",
    "TIMEOUT": 600,
    "SYNC_TIMEOUT": 30,
    "RETRIES": 2,
    "RETRY_DELAY": 0,
    "SEARCH": False,
}


class CancellingProvider:
    """Пока модель «думает», запуск отменяют — ответ приходит поздно."""

    name = "fake"

    def __init__(self, cancel_job=None) -> None:
        self.cancel_job, self.calls = cancel_job, 0

    def is_configured(self) -> bool:
        return True

    def complete(self, **kwargs):
        self.calls += 1
        if self.cancel_job is not None:
            job = BackgroundJob.objects.get(pk=self.cancel_job())
            jobs.cancel(job, by=job.owner)
        return Completion(
            content="поздний ответ",
            parsed={"title": "Поздняя задача", "days": 3},
            model="fake-1",
            usage=Usage(100, 50),
            raw={"id": "msg_1"},
        )


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def provider(monkeypatch):
    def install(instance):
        monkeypatch.setattr("suggestions.llm.get_provider", lambda: instance)
        return instance

    return install


# --- Очередь и двойной запуск -------------------------------------------------


@pytest.mark.django_db
def test_new_launch_waits_in_queue_and_starts_with_the_worker(make_user):
    user = make_user("director_exam")
    job = jobs.start(user=user, kind="paste", title="Разбор", task_id="t-1")
    assert job.status == BackgroundJob.Status.QUEUED and job.started_at is None

    jobs.begin("t-1")
    job.refresh_from_db()
    assert job.status == BackgroundJob.Status.RUNNING and job.started_at is not None


@pytest.mark.django_db
def test_second_launch_over_the_same_object_is_not_created(make_user, student):
    """Пока идёт запуск той же операции по тому же объекту — новый не заводится."""
    from suggestions.tasks import explain_match

    first_user, second_user = make_user("director_exam"), make_user("director_admission")
    BackgroundJob.objects.create(
        owner=first_user,
        kind="explain_match",
        title="x",
        task_id="t-run",
        status=BackgroundJob.Status.RUNNING,
        target_model="students.Student",
        target_id=student.pk,
    )

    job, created = jobs.launch(
        user=second_user, kind="explain_match", title="y", task=explain_match, kwargs={}, target=student
    )

    assert created is False and job.task_id == "t-run"
    assert BackgroundJob.objects.count() == 1


@pytest.mark.django_db
def test_finished_launch_does_not_block_a_new_one(make_user, student):
    user = make_user("director_exam")
    old = jobs.start(user=user, kind="explain_match", title="x", task_id="t-old", target=student)
    jobs.complete("t-old")
    old.refresh_from_db()
    assert jobs.active_for(kind="explain_match", target=student) is None


# --- Отмена ------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_cancel_marks_cancelled_and_late_answer_is_not_saved(api, make_user, provider, student):
    """Отменили, пока модель думала: расход записан, задачи у ученика не появились."""
    from roadmap.models import Task
    from suggestions.tasks import run_operation

    user = make_user("director_admission")
    provider(CancellingProvider(cancel_job=lambda: BackgroundJob.objects.get().pk))
    job, created = jobs.launch(
        user=user,
        kind="operation",
        title="Задачи пачкой",
        task=run_operation,
        kwargs={
            "code": "bulk_tasks",
            "actor_id": user.pk,
            "role": user.role,
            "payload": {"students": [student.pk], "text": "сдать эссе"},
        },
    )

    job.refresh_from_db()
    assert created is True
    assert job.status == BackgroundJob.Status.CANCELLED
    assert job.cancelled_by == user and job.finished_at is not None
    # расход остался в журнале вызовов, а поздний ответ дальше не пошёл
    assert LLMCall.objects.filter(purpose="bulk_tasks").count() == 1
    assert not Task.objects.filter(title="Поздняя задача").exists()
    from suggestions.models import Suggestion

    assert not Suggestion.objects.exists()
    # о своей отмене не уведомляем
    assert not Notification.objects.filter(recipient=user).exists()
    entry = AuditLog.objects.get(model_label="core.BackgroundJob")
    assert entry.new_value == "cancelled" and entry.actor == user


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_cancelled_launch_does_not_call_the_model_at_all(make_user, provider):
    """Отменили, пока стоял в очереди: модель не вызывается, денег не тратим."""
    from suggestions.tasks import run_operation

    user = make_user("director_admission")
    model = provider(CancellingProvider())
    job = jobs.start(user=user, kind="operation", title="x", task_id="t-q")
    jobs.cancel(job, by=user)
    run_operation.apply(
        kwargs={"code": "focus_today", "actor_id": user.pk, "role": user.role, "payload": {}}, task_id="t-q"
    )

    assert model.calls == 0
    job.refresh_from_db()
    assert job.status == BackgroundJob.Status.CANCELLED


@pytest.mark.django_db
def test_only_the_owner_and_the_admin_cancel(api, make_user):
    owner, stranger, admin = make_user("director_exam"), make_user("director_admission"), make_user("admin")
    job = jobs.start(user=owner, kind="paste", title="Разбор", task_id="t-c")

    api.force_authenticate(stranger)
    assert api.post(f"/api/jobs/{job.pk}/cancel/").status_code == 404
    job.refresh_from_db()
    assert job.status == BackgroundJob.Status.QUEUED

    api.force_authenticate(admin)
    answer = api.post(f"/api/jobs/{job.pk}/cancel/")
    assert answer.status_code == 200 and answer.data["status"] == "cancelled"
    job.refresh_from_db()
    assert job.cancelled_by == admin

    api.force_authenticate(owner)
    assert api.post(f"/api/jobs/{job.pk}/cancel/").status_code == 400, "закончившийся не отменяется"


@pytest.mark.django_db
def test_owner_cancels_own_launch_and_it_leaves_the_panel(api, make_user):
    owner = make_user("director_exam")
    job = jobs.start(user=owner, kind="paste", title="Разбор", task_id="t-o")
    api.force_authenticate(owner)
    assert api.get("/api/jobs/").data["results"][0]["can_cancel"] is True

    assert api.post(f"/api/jobs/{job.pk}/cancel/").status_code == 200
    assert api.get("/api/jobs/").data["results"] == []


# --- Зависшие запуски и уведомления ---------------------------------------------


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_stale_running_launch_is_closed_with_no_answer(make_user):
    """Без признаков жизни дольше `TIMEOUT × (RETRIES + 1) + 60` — «нет ответа»."""
    user = make_user("director_exam")
    job = jobs.start(user=user, kind="paste", title="Разбор", task_id="t-s")
    jobs.begin("t-s")
    limit = jobs.stale_after()
    assert limit == dt.timedelta(seconds=600 * 3 + 60)
    BackgroundJob.objects.filter(pk=job.pk).update(updated_at=timezone.now() - limit - dt.timedelta(seconds=5))

    fresh = jobs.start(user=user, kind="paste", title="Свежий", task_id="t-f")
    jobs.begin("t-f")

    assert jobs.sweep() == 1
    job.refresh_from_db()
    fresh.refresh_from_db()
    assert job.status == BackgroundJob.Status.FAILED and job.error == "нет ответа"
    assert fresh.status == BackgroundJob.Status.RUNNING
    assert Notification.objects.filter(recipient=user, kind=Notification.Kind.JOB_FAILED).count() == 1


@pytest.mark.django_db
def test_bell_rings_on_done_and_on_failed(make_user):
    user = make_user("director_exam")
    jobs.start(user=user, kind="paste", title="Первый", task_id="t-d", link="/suggestions/1")
    jobs.start(user=user, kind="paste", title="Второй", task_id="t-e")
    jobs.complete("t-d")
    jobs.fail("t-e", "провайдер вернул 503")

    done = Notification.objects.get(recipient=user, kind=Notification.Kind.JOB_DONE)
    failed = Notification.objects.get(recipient=user, kind=Notification.Kind.JOB_FAILED)
    assert done.link == "/suggestions/1"
    assert "провайдер вернул 503" in failed.text


@pytest.mark.django_db
def test_cancelled_launch_is_not_reopened_by_late_signals(make_user):
    """Задача дошла до конца после отмены — запуск остаётся отменённым, звонка нет."""
    user = make_user("director_exam")
    job = jobs.start(user=user, kind="paste", title="Разбор", task_id="t-l")
    jobs.cancel(job, by=user)
    jobs.complete("t-l")
    jobs.fail("t-l", "сбой")
    job.refresh_from_db()
    assert job.status == BackgroundJob.Status.CANCELLED
    assert not Notification.objects.filter(recipient=user).exists()
