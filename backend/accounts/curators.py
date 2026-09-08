"""Кураторы и их группы (фаза 60).

Единственное место, где считается, какие группы ведёт куратор сегодня.
Отсюда питаются скоупинг учеников (`core.scope`), очередь подтверждений,
кабинет куратора и экран администратора. Второго источника — по текстовому
полю группы, по имени, по списку во вьюхе — быть не может (инвариант №2).
"""

from __future__ import annotations

import datetime as dt

from django.db import models, transaction
from django.utils import timezone

from accounts.models import CuratorAssignment, Role, User


def active_assignments(on: dt.date | None = None) -> models.QuerySet[CuratorAssignment]:
    """Назначения, действующие в день `on` (по умолчанию сегодня)."""
    day = on or timezone.localdate()
    # группа в архиве куратору не видна: назначение остаётся историей
    return CuratorAssignment.objects.filter(since__lte=day, group__archived_at__isnull=True).filter(
        models.Q(until__isnull=True) | models.Q(until__gt=day)
    )


def curated_group_ids(user, on: dt.date | None = None) -> list[int]:
    """Группы, которые человек ведёт как куратор сегодня. Не куратору — пусто."""
    if user is None or getattr(user, "role", "") != Role.CURATOR or not user.is_active:
        return []
    return list(active_assignments(on).filter(curator=user).values_list("group_id", flat=True))


def curator_of(group, on: dt.date | None = None) -> CuratorAssignment | None:
    """Действующее назначение группы или None."""
    return active_assignments(on).filter(group=group).select_related("curator").first()


class AssignmentRefused(ValueError):
    """Назначить нельзя — текст объясняет почему."""


@transaction.atomic
def assign(*, group, curator: User, since: dt.date, actor=None) -> CuratorAssignment:
    """Назначить или сменить куратора группы с даты `since`.

    Открытая запись группы закрывается той же датой: в день смены группу
    ведёт уже новый человек. История остаётся строками — ничего не
    переписывается и не удаляется.
    """
    if curator.role != Role.CURATOR:
        raise AssignmentRefused("Назначить можно только учётную запись с ролью «Куратор»")
    if not curator.is_active:
        raise AssignmentRefused("У этой учётной записи отключён доступ — сначала включите его")

    # блокируем открытую запись группы: две смены подряд не должны
    # закрыть одну и ту же запись двумя разными датами
    current = (
        CuratorAssignment.objects.select_for_update()
        .filter(group=group, until__isnull=True)
        .select_related("curator")
        .first()
    )
    if current is not None:
        if current.curator_id == curator.pk:
            raise AssignmentRefused(f"{curator.full_name or curator.email} уже ведёт группу {group.code}")
        if since <= current.since:
            raise AssignmentRefused(f"Дата смены не раньше начала действующего назначения ({current.since:%d.%m.%Y})")
        current.until = since
        current.save(update_fields=["until"])

    return CuratorAssignment.objects.create(group=group, curator=curator, since=since, created_by=actor)
