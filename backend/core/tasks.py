"""Фоновые задачи ядра."""

from __future__ import annotations

from celery import shared_task
from django.utils import timezone


@shared_task(name="core.snapshot_readiness")
def snapshot_readiness() -> int:
    """Снять недельный срез готовности по всем активным ученикам."""
    from core.models import ReadinessSnapshot
    from core.readiness import compute
    from students.models import Student

    today = timezone.localdate()
    students = Student.objects.filter(is_active=True).select_related("behavior", "admission", "exam", "talent", "sport")

    created = 0
    for student in students:
        result = compute(student)
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
