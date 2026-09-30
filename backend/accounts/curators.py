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
from django.utils.translation import gettext

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


ALL_GROUPS = "all"


def picked_groups(user, code: str | None, on: dt.date | None = None) -> tuple[list[int], str]:
    """Группы, по которым куратор смотрит кабинет, и код выбора, как его понял сервер.

    Выбор группы приходит с клиента (`?group=CHICAGO`): он запоминается во
    вкладке браузера и мог остаться от другого куратора, от снятого назначения
    или от группы, ушедшей в архив (фаза 80). Источник групп — только действующие
    назначения, поэтому выбор с ними сверяется на каждом запросе:

    - пусто или «all» — все группы куратора;
    - код своей группы — она одна;
    - чужой или несуществующий код — первая назначенная по коду, молча.
      Пустой ответ здесь выглядел как «в группе нет учеников», и куратор
      с одной группой выбраться из него не мог: переключателя у него нет.
    """
    rows = list(
        active_assignments(on).filter(curator=user).order_by("group__code").values_list("group_id", "group__code")
    )
    if getattr(user, "role", "") != Role.CURATOR or not user.is_active:
        rows = []
    wanted = str(code or "").strip()
    if not wanted or wanted == ALL_GROUPS or not rows:
        return [pk for pk, _ in rows], ALL_GROUPS
    for pk, own in rows:
        if own.lower() == wanted.lower():
            return [pk], own
    first_pk, first_code = rows[0]
    return [first_pk], first_code


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
        raise AssignmentRefused(gettext("Назначить можно только учётную запись с ролью «Куратор»"))
    if not curator.is_active:
        raise AssignmentRefused(gettext("У этой учётной записи отключён доступ — сначала включите его"))

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
            raise AssignmentRefused(
                gettext("{curator} уже ведёт группу {group}").format(
                    curator=curator.full_name or curator.handle, group=group.code
                )
            )
        if since <= current.since:
            raise AssignmentRefused(
                gettext("Дата смены не раньше начала действующего назначения ({date})").format(
                    date=f"{current.since:%d.%m.%Y}"
                )
            )
        current.until = since
        current.save(update_fields=["until"])

    return CuratorAssignment.objects.create(group=group, curator=curator, since=since, created_by=actor)
