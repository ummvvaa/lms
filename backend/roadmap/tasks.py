"""Фоновые задачи роадмапа: дневной прогон напоминаний (фаза 39)."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="roadmap.daily_reminders")
def daily_reminders() -> dict:
    """Автозадачи о регистрации и напоминания о событиях — раз в день."""
    from roadmap.reminders import run_daily

    return run_daily()


@shared_task(name="roadmap.generate_plan")
def generate_plan(plan_id: int = 0, **kwargs) -> dict:
    """Собрать задачи плана поступления в фоне (фаза 41).

    `plan_id` принимается и именованным: повтор из плашки операций зовёт
    задачу по имени с сохранёнными аргументами (фаза 47).
    """
    from roadmap.models import ApplicationPlan
    from roadmap.plans import generate

    plan_id = plan_id or kwargs.get("plan_id")
    plan = (
        ApplicationPlan.objects.select_related("student__user", "program__university", "admission_round")
        .filter(pk=plan_id)
        .first()
    )
    if plan is None:
        return {"error": "плана нет"}
    try:
        generate(plan)
        return {"plan": plan.pk, "suggestion": plan.pending_suggestion_id}
    except Exception as error:  # план не должен зависнуть в «идёт»
        plan.generation_status = ApplicationPlan.Generation.FAILED
        plan.save(update_fields=["generation_status", "updated_at"])
        raise error
