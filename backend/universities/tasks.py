"""Фоновые задачи справочника вузов."""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

log = logging.getLogger(__name__)


@shared_task(name="universities.sync_deadlines")
def sync_deadlines(*, limit: int = 50) -> dict:
    """Обойти раунды и сложить расхождения в предложения.

    Поле без источника не меняется: каждая строка предложения несёт ссылку
    и фрагмент страницы, по которым директор проверит число.
    """
    from accounts.models import Role, User
    from suggestions.engine import create_suggestion
    from universities.models import AdmissionRound
    from universities.sync import check_round

    rounds = (
        AdmissionRound.objects.select_related("program__university")
        .exclude(source_url="", program__university__website="")
        .order_by("checked_at")[:limit]
    )

    rows, checked, failures = [], 0, []
    for admission_round in rounds:
        result = check_round(admission_round)
        checked += 1
        if not result.get("ok"):
            failures.append({"round": admission_round.pk, "reason": result.get("reason")})
            continue
        if not result.get("found") or not result.get("changed"):
            continue

        fact = result["fact"]
        rows.append(
            {
                "model": "universities.AdmissionRound",
                "field": "deadline",
                "value": fact["deadline"],
                "object_id": admission_round.pk,
                "confidence": 0.8,
                "source_ref": fact["source_url"],
                "source_quote": fact["quote"],
            }
        )

    if not rows:
        return {"checked": checked, "suggestion": None, "changes": 0, "failures": failures}

    # предложение адресовано директору по поступлению — это его домен
    author = User.objects.filter(role=Role.DIRECTOR_ADMISSION).order_by("pk").first()
    suggestion, rejected = create_suggestion(
        author=author,
        role=Role.DIRECTOR_ADMISSION,
        domain_code="admission",
        source_type="web_sync",
        command="sync_deadlines",
        rows=rows,
        source_ref=f"фоновая сверка {timezone.localdate().isoformat()}",
    )
    return {
        "checked": checked,
        "suggestion": suggestion.pk,
        "changes": suggestion.changes.count(),
        "rejected": rejected,
        "failures": failures,
    }
