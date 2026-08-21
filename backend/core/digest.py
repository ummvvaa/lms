"""Ежедневный дайджест изменений по домену директора.

Открывается при входе: что поменялось в вашем домене за сутки и что ждёт
вашего решения.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from core.domains import domain_of_role
from core.models import AuditLog
from suggestions.models import Suggestion, SuggestionStatus


def build(*, user, days: int = 1) -> dict:
    """Собрать дайджест для пользователя."""
    domain = domain_of_role(user.role)
    since = timezone.now() - timedelta(days=days)

    if domain is None:
        return {"domain": None, "since": since, "changes": 0, "by_field": [], "pending": [], "sources": {}}

    entries = AuditLog.objects.filter(domain_code=domain.code, created_at__gte=since)

    by_field = list(entries.values("field_name").annotate(n=Count("id")).order_by("-n")[:10])
    sources = {row["source"]: row["n"] for row in entries.values("source").annotate(n=Count("id"))}

    pending = list(
        Suggestion.objects.filter(domain_code=domain.code, status=SuggestionStatus.PENDING)
        .annotate(n=Count("changes"))
        .values("id", "command", "source_type", "created_at", "n")[:10]
    )

    recent = list(
        entries.select_related("actor")
        .order_by("-created_at")[:20]
        .values("field_name", "old_value", "new_value", "source", "created_at", "student_id")
    )

    return {
        "domain": domain.code,
        "domain_title": domain.title,
        "since": since,
        "changes": entries.count(),
        "by_field": by_field,
        "sources": sources,
        "pending": pending,
        "recent": recent,
    }
