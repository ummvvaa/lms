"""Составы: кто учится на уроке в этот день.

Группа — все действующие ученики группы; подгруппа — членство с датами;
поток — объединение частей без задвоения. Всё считается по дате: перевод
ученика в другую подгруппу не переписывает прошлое.
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from academics import cache
from academics.calendar import today
from academics.models import Cohort, CohortKind, CohortMembership, StreamPart
from students.models import Student, StudyGroup


def group_cohort(group: StudyGroup) -> Cohort:
    """Состав «вся группа» — заводится при первом обращении."""
    cohort = Cohort.objects.filter(kind=CohortKind.GROUP, group=group).first()
    if cohort is None:
        cohort = Cohort.objects.create(kind=CohortKind.GROUP, group=group, name=group.code, short_name=group.code)
    return cohort


def member_ids(cohort: Cohort, on: dt.date | None = None) -> list[int]:
    """Ученики состава на дату — упорядоченный список без повторов."""
    day = on or today()
    store = cache.current()
    if store is not None:
        return store.roster.members(cohort.pk, day)
    if cohort.kind == CohortKind.GROUP:
        return list(
            Student.objects.filter(group_id=cohort.group_id, is_active=True)
            .order_by("last_name", "first_name", "id")
            .values_list("pk", flat=True)
        )
    if cohort.kind == CohortKind.SUBGROUP:
        rows = CohortMembership.objects.filter(cohort=cohort, since__lte=day).filter(
            Q(until__isnull=True) | Q(until__gt=day)
        )
        return list(
            Student.objects.filter(pk__in=rows.values("student_id"), is_active=True)
            .order_by("last_name", "first_name", "id")
            .values_list("pk", flat=True)
        )
    seen: set[int] = set()
    for part in StreamPart.objects.filter(stream=cohort).select_related("part"):
        seen.update(member_ids(part.part, day))
    return list(
        Student.objects.filter(pk__in=seen).order_by("last_name", "first_name", "id").values_list("pk", flat=True)
    )


def members(cohort: Cohort, on: dt.date | None = None) -> list[Student]:
    ids = member_ids(cohort, on)
    by_id = {s.pk: s for s in Student.objects.filter(pk__in=ids).select_related("group")}
    return [by_id[i] for i in ids if i in by_id]


def group_ids_of(cohort: Cohort) -> list[int]:
    """Группы, чьи ученики входят в состав."""
    store = cache.current()
    if store is not None:
        return store.roster.groups_of(cohort.pk)
    if cohort.kind == CohortKind.SUBGROUP and not cohort.group_id and cohort.stream_id:
        # подгруппа внутри потока: её группы — группы потока
        return group_ids_of(cohort.stream)
    if cohort.kind in (CohortKind.GROUP, CohortKind.SUBGROUP):
        return [cohort.group_id] if cohort.group_id else []
    out: list[int] = []
    for part in StreamPart.objects.filter(stream=cohort).select_related("part"):
        for gid in group_ids_of(part.part):
            if gid not in out:
                out.append(gid)
    return out


def kind_title(cohort: Cohort) -> str:
    return {CohortKind.GROUP: _("вся группа"), CohortKind.SUBGROUP: _("подгруппа"), CohortKind.STREAM: _("поток")}[
        CohortKind(cohort.kind)
    ]


def cohorts_of_student(student_id: int, on: dt.date | None = None) -> list[int]:
    """Все составы, куда ученик входит на дату: группа, подгруппы, потоки с ними."""
    day = on or today()
    store = cache.current()
    if store is not None:
        return store.roster.cohorts_of_student(student_id, day)
    student = Student.objects.filter(pk=student_id).first()
    if student is None:
        return []
    ids: list[int] = []
    if student.group_id:
        group = Cohort.objects.filter(kind=CohortKind.GROUP, group_id=student.group_id).values_list("pk", flat=True)
        ids.extend(group)
    subgroups = (
        CohortMembership.objects.filter(student_id=student_id, since__lte=day)
        .filter(Q(until__isnull=True) | Q(until__gt=day))
        .values_list("cohort_id", flat=True)
    )
    ids.extend(subgroups)
    streams = StreamPart.objects.filter(part_id__in=ids).values_list("stream_id", flat=True)
    ids.extend(streams)
    return list(dict.fromkeys(ids))


def students_share(a: Cohort, b: Cohort, on: dt.date | None = None) -> bool:
    """Есть ли у двух составов общие ученики. Две подгруппы одной группы — нет."""
    if a.pk == b.pk:
        return True
    if a.kind == CohortKind.SUBGROUP and b.kind == CohortKind.SUBGROUP and a.group_id == b.group_id:
        return bool(set(member_ids(a, on)) & set(member_ids(b, on)))
    return bool(set(member_ids(a, on)) & set(member_ids(b, on)))


@transaction.atomic
def split_group(
    *, group: StudyGroup, subject, parts: list[list[int]], since: dt.date, rule: str = "", actor=None
) -> list[Cohort]:
    """Разделить группу на подгруппы по предмету с даты.

    Прежние подгруппы группы по этому предмету закрываются датой: их журналы
    остаются, новые уроки идут в новые подгруппы.
    """
    old = Cohort.objects.filter(kind=CohortKind.SUBGROUP, group=group, subject=subject)
    for cohort in old:
        CohortMembership.objects.filter(cohort=cohort, until__isnull=True).update(until=since)
    made: list[Cohort] = []
    allowed = set(Student.objects.filter(group=group, is_active=True).values_list("pk", flat=True))
    for index, ids in enumerate(parts, start=1):
        cohort = Cohort.objects.create(
            kind=CohortKind.SUBGROUP,
            group=group,
            subject=subject,
            number=index,
            name=f"{group.code} · подгр. {index}",  # i18n-skip: название состава хранится в базе как данные
            short_name=f"подгр. {index}",  # i18n-skip: название состава хранится в базе как данные
            rule=rule[:60],
        )
        CohortMembership.objects.bulk_create(
            [CohortMembership(cohort=cohort, student_id=sid, since=since) for sid in ids if sid in allowed]
        )
        made.append(cohort)
    cache.invalidate()
    return made


@transaction.atomic
def set_members(cohort: Cohort, ids: list[int], since: dt.date) -> None:
    """Новый состав подгруппы с даты: ушедшие закрываются, пришедшие открываются."""
    current = {row.student_id: row for row in CohortMembership.objects.filter(cohort=cohort, until__isnull=True)}
    wanted = set(ids)
    for sid, row in current.items():
        if sid not in wanted:
            row.until = since
            row.save(update_fields=["until"])
    for sid in wanted - set(current):
        CohortMembership.objects.create(cohort=cohort, student_id=sid, since=since)
    cache.invalidate()


@transaction.atomic
def make_stream(*, name: str, parts: list[Cohort], stream: Cohort | None = None) -> Cohort:
    """Собрать или пересобрать поток из групп и подгрупп."""
    if stream is None:
        stream = Cohort.objects.create(kind=CohortKind.STREAM, name=name[:120], short_name=name[:60])
    else:
        stream.name = name[:120]
        stream.short_name = name[:60]
        stream.save(update_fields=["name", "short_name"])
        StreamPart.objects.filter(stream=stream).delete()
    StreamPart.objects.bulk_create([StreamPart(stream=stream, part=part) for part in parts if part.pk != stream.pk])
    cache.invalidate()
    return stream
