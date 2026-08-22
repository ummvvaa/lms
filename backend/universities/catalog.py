"""Каталог программ для ученика: поиск, фильтры, соответствие.

Всё строится на записях справочника. Программы, которой нет в `Program`,
в каталоге не появится — как и в подборе ИИ (инвариант №10).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db.models import Q, QuerySet

from students.models import Student
from universities.matching import match
from universities.models import AdmissionRound, Program, StudentUniversity

#: Пороги уровня соответствия — ими фильтрует каталог и подписывает карточки.
LEVELS = {
    "high": (80, 100, "проходите почти по всему"),
    "medium": (50, 79, "есть куда расти"),
    "low": (0, 49, "далеко"),
}


@dataclass(frozen=True)
class CatalogFilters:
    """Что выбрал ученик в фильтрах."""

    search: str = ""
    country: str = ""
    major: str = ""
    round_type: str = ""
    level: str = ""

    @classmethod
    def from_query(cls, params) -> CatalogFilters:
        return cls(
            search=(params.get("search") or "").strip(),
            country=(params.get("country") or "").strip(),
            major=(params.get("major") or "").strip(),
            round_type=(params.get("round_type") or "").strip(),
            level=(params.get("level") or "").strip(),
        )


def base_queryset() -> QuerySet[Program]:
    return (
        Program.objects.filter(is_active=True, university__is_active=True)
        .select_related("university", "requirement")
        .prefetch_related("rounds")
    )


def apply_filters(queryset: QuerySet[Program], filters: CatalogFilters) -> QuerySet[Program]:
    """Фильтры, которые можно применить в базе. Уровень — уже после расчёта."""
    if filters.search:
        queryset = queryset.filter(Q(name__icontains=filters.search) | Q(university__name__icontains=filters.search))
    if filters.country:
        queryset = queryset.filter(university__country__iexact=filters.country)
    if filters.major:
        queryset = queryset.filter(name__icontains=filters.major)
    if filters.round_type:
        queryset = queryset.filter(rounds__round_type=filters.round_type).distinct()
    return queryset


def level_of(percent: int) -> str:
    for code, (low, high, _title) in LEVELS.items():
        if low <= percent <= high:
            return code
    return "low"


def rounds_payload(program: Program) -> list[dict]:
    """Дедлайны раундов. Дедлайн живёт у вуза, а не у ученика (инвариант №4)."""
    return [
        {
            "id": row.id,
            "round_type": row.round_type,
            "round_title": row.get_round_type_display(),
            "deadline": row.deadline.isoformat(),
            "source_url": row.source_url,
        }
        for row in sorted(program.rounds.all(), key=lambda r: r.deadline)
    ]


def program_card(student: Student, program: Program, *, in_list: dict | None = None) -> dict:
    """Карточка программы глазами конкретного ученика."""
    result = match(student, program)
    payload = result.as_dict()
    payload.update(
        {
            "university": program.university_id,
            "level": level_of(result.percent),
            "rounds": rounds_payload(program),
            "in_my_list": in_list is not None,
            "my_entry": in_list,
        }
    )
    return payload


def build(student: Student, filters: CatalogFilters) -> list[dict]:
    """Каталог для ученика: карточки, отсортированные по соответствию."""
    mine = {
        row.program_id: {
            "id": row.id,
            "tier": row.tier,
            "added_by": row.added_by,
            "is_confirmed": row.is_confirmed,
            "can_remove": row.added_by == "student",
        }
        for row in StudentUniversity.objects.filter(student=student)
    }

    cards = [
        program_card(student, program, in_list=mine.get(program.pk))
        for program in apply_filters(base_queryset(), filters)
    ]

    if filters.level:
        cards = [card for card in cards if card["level"] == filters.level]

    # сверху то, где ученик ближе всего: каталог должен начинаться
    # с достижимого, а не с алфавита
    cards.sort(key=lambda c: (-c["percent"], c["university_name"]))
    return cards


def facets() -> dict:
    """Значения для выпадающих списков — только те, что есть в справочнике."""
    countries = sorted({row for row in base_queryset().values_list("university__country", flat=True) if row})
    majors = sorted({row for row in base_queryset().values_list("name", flat=True) if row})
    round_types = sorted({row for row in AdmissionRound.objects.values_list("round_type", flat=True) if row})
    return {
        "countries": countries,
        "majors": majors,
        "round_types": round_types,
        "levels": [
            {"code": code, "title": title, "from": low, "to": high} for code, (low, high, title) in LEVELS.items()
        ],
        "list_limit": settings.STUDENT_LIST_LIMIT,
    }
