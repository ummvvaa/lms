"""Фоновые задачи ядра."""

from __future__ import annotations

from celery import shared_task
from django.db import OperationalError
from django.utils import timezone


@shared_task(name="core.snapshot_readiness")
def snapshot_readiness() -> int:
    """Снять недельный срез готовности по активным ученикам 11 — у 8–10 её нет."""
    from core.models import ReadinessSnapshot
    from core.parallels import admission_students
    from core.readiness import compute, readiness_rules
    from students.models import Student

    today = timezone.localdate()
    students = admission_students(Student.objects.filter(is_active=True)).select_related(
        "behavior", "admission", "exam", "talent", "sport"
    )

    created = 0
    # правила школы — одним запросом на весь снимок, не на каждого ученика
    rules = readiness_rules()
    for student in students:
        result = compute(student, rules)
        values = {p.code: round(p.value, 1) for p in result.parts}
        ReadinessSnapshot.objects.update_or_create(
            student=student,
            date=today,
            defaults={
                "score": result.score,
                "weakest": result.weakest.code if result.weakest else "",
                **{code: values.get(code) for code in ("exam", "admission", "talent", "behavior", "sport")},
            },
        )
        created += 1
    return created


@shared_task(
    name="core.record_usage_events",
    ignore_result=True,
    acks_late=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def record_usage_events(events: list[dict]) -> int:
    """Пакет аналитики, повтор которого не создаёт новых строк."""
    from core.usage import store_events

    return store_events(events)


@shared_task(name="core.purge_usage_events", ignore_result=True)
def purge_usage_events() -> int:
    """Недельная очистка событий старше года."""
    from core.usage import purge_old_events

    return purge_old_events()
