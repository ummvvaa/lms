"""Каталог стипендий, сохранённые и подбор под профиль (фаза 44).

Три правила, из-за которых этот файл выглядит именно так:

* инвариант №10 — подбор ходит только по справочнику: модель получает
  список стипендий с номерами и ссылаться может только на них. Справочник
  пуст — так и говорится, а не достраивается по памяти;
* инвариант №14 — непроверенная запись едет к ученику вместе с плашкой;
* инвариант №4 — дедлайн живёт у самой стипендии. Задача и календарь
  на него ссылаются, а не копируют: сдвинулся — сдвинулось у всех.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone

from core.phrasing import counted
from students.models import Student
from universities.models import SavedScholarship, Scholarship


def soon_days() -> int:
    """Через сколько дней дедлайн считается «ближайшим» — для счётчика сверху."""
    return int(getattr(settings, "SCHOLARSHIP_SOON_DAYS", 30))


#: Сколько стипендий уходит в модель. Больше — лишний контекст и лишние деньги.
CANDIDATES = 25

#: Сколько показываем в подборе.
TOP_N = 6


# --- Человеческие подписи --------------------------------------------------


def amount_title(row: Scholarship) -> str:
    """«$5 000 – $20 000» или «до $20 000». Пусто — сумма не указана."""

    def money(value: Decimal) -> str:
        whole = f"{int(value):,}".replace(",", " ")
        return f"{whole} {row.currency}".strip()

    if row.amount_min is not None and row.amount_max is not None:
        if row.amount_min == row.amount_max:
            return money(row.amount_min)
        return f"{money(row.amount_min)} – {money(row.amount_max)}"
    if row.amount_max is not None:
        return f"до {money(row.amount_max)}"
    if row.amount_min is not None:
        return f"от {money(row.amount_min)}"
    return ""


def deadline_state(deadline: dt.date | None, today: dt.date | None = None) -> str:
    """Состояние дедлайна словами — считает сервер, а не экран.

    Склонения числительных живут на сервере с фазы 17: «остался 1 день»
    и «осталось 2 дня» — разные слова, и собирать их во фронте нельзя.
    """
    if deadline is None:
        return "срок не указан"
    today = today or timezone.localdate()
    left = (deadline - today).days
    if left < 0:
        return "срок прошёл"
    if left == 0:
        return "дедлайн сегодня"
    if left == 1:
        return "остался 1 день"
    return f"через {counted(left, ('день', 'дня', 'дней'))}"


# --- Каталог ----------------------------------------------------------------


@dataclass
class ScholarshipFilters:
    """Фильтры каталога. Пустое поле — фильтра нет."""

    query: str = ""
    country: str = ""
    level: str = ""
    funding_type: str = ""
    basis: str = ""
    #: только те, у кого срок ещё не прошёл
    open_only: bool = False

    @classmethod
    def from_request(cls, params) -> ScholarshipFilters:
        return cls(
            query=(params.get("q") or "").strip(),
            country=(params.get("country") or "").strip(),
            level=(params.get("level") or "").strip(),
            funding_type=(params.get("funding_type") or "").strip(),
            basis=(params.get("basis") or "").strip(),
            open_only=str(params.get("open_only", "")).lower() in {"1", "true", "yes"},
        )


def base_queryset(*, for_student: bool) -> QuerySet[Scholarship]:
    """Справочник целиком. Ученику — только показываемые записи."""
    qs = Scholarship.objects.select_related("university").all()
    return qs.filter(is_active=True) if for_student else qs


def apply_filters(qs: QuerySet[Scholarship], filters: ScholarshipFilters) -> QuerySet[Scholarship]:
    if filters.query:
        qs = qs.filter(
            Q(name__icontains=filters.query)
            | Q(organizer__icontains=filters.query)
            | Q(country__icontains=filters.query)
        )
    if filters.country:
        qs = qs.filter(country__iexact=filters.country)
    if filters.level:
        # пустой уровень у записи означает «любой», и он не должен выпадать
        qs = qs.filter(Q(level=filters.level) | Q(level=""))
    if filters.funding_type:
        qs = qs.filter(funding_type=filters.funding_type)
    if filters.basis:
        column = {"international": "for_international", "merit": "for_merit", "need": "for_need"}.get(filters.basis)
        if column:
            qs = qs.filter(**{column: True})
    if filters.open_only:
        today = timezone.localdate()
        qs = qs.filter(Q(deadline__isnull=True) | Q(deadline__gte=today))
    return qs


def stats(qs: QuerySet[Scholarship]) -> dict:
    """Три числа сверху каталога.

    Сумма считается по каждой валюте отдельно: складывать доллары
    с евро по выдуманному курсу мы не станем — число получилось бы
    красивым и неверным.
    """
    today = timezone.localdate()
    horizon = today + dt.timedelta(days=soon_days())
    rows = list(qs)
    totals: dict[str, Decimal] = {}
    for row in rows:
        amount = row.amount_max or row.amount_min
        if amount is None:
            continue
        currency = row.currency or "USD"
        totals[currency] = totals.get(currency, Decimal("0")) + amount
    return {
        "total": len(rows),
        "soon": sum(1 for row in rows if row.deadline and today <= row.deadline <= horizon),
        "soon_days": soon_days(),
        "funding": [
            {"currency": currency, "amount": int(amount)}
            for currency, amount in sorted(totals.items(), key=lambda pair: -pair[1])
        ],
    }


def facets(qs: QuerySet[Scholarship]) -> dict:
    """Из чего выбирать в фильтрах — по тому, что есть в справочнике."""
    from universities.models import FundingType, ProgramLevel

    countries = sorted({row for row in qs.values_list("country", flat=True) if row})
    return {
        "countries": countries,
        "levels": [{"value": value, "title": title} for value, title in ProgramLevel.choices],
        "funding_types": [{"value": value, "title": title} for value, title in FundingType.choices],
        "bases": [
            {"value": "international", "title": "Для иностранцев"},
            {"value": "merit", "title": "За заслуги"},
            {"value": "need", "title": "По нужде"},
        ],
    }


def saved_ids(student: Student | None) -> set[int]:
    if student is None:
        return set()
    return set(SavedScholarship.objects.filter(student=student).values_list("scholarship_id", flat=True))


# --- Подбор под профиль -----------------------------------------------------


SYSTEM = """Ты объясняешь ученику школы, чем ему полезны стипендии из справочника.

Правила, нарушать нельзя:
- пиши только про стипендии из переданного списка и ссылайся на них по полю id;
- ничего не добавляй от себя: стипендии, которой нет в списке, не существует;
- не обещай, что ученик её получит, и не употребляй слова «шанс», «вероятность», «прогноз»;
- по каждой скажи: почему подходит и чего не хватает по требованиям;
- пиши по-русски, коротко, без общих слов.
"""

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "id стипендии из переданного списка"},
                    "why": {"type": "string", "description": "почему подходит"},
                    "missing": {"type": "string", "description": "чего не хватает"},
                },
                "required": ["id", "why"],
            },
        },
        "note": {"type": "string", "description": "общее замечание, если данных мало"},
    },
    "required": ["picks"],
}


@dataclass
class Match:
    """Одна стипендия в подборке."""

    row: Scholarship
    why: str = ""
    missing: str = ""
    reasons: list[str] = field(default_factory=list)
    #: насколько запись подошла правилам — по нему идёт порядок
    score: int = 0


def _profile_facts(student: Student) -> dict:
    """Что берём из профиля. Ярлыков и статусов здесь нет (инвариант №7)."""
    admission = getattr(student, "admission", None)
    exam = getattr(student, "exam", None)
    return {
        "country": getattr(admission, "target_country", "") or "",
        "level": getattr(admission, "target_level", "") or "",
        "gpa": getattr(exam, "gpa", None),
        "ielts": getattr(exam, "ielts_current", None),
        "sat": getattr(exam, "sat_current", None),
    }


def _rule_pick(student: Student) -> tuple[list[Match], dict]:
    """Отбор правилами: страна, уровень, срок ещё не прошёл.

    Работает и без модели — тогда объяснением служат сами причины отбора.
    """
    facts = _profile_facts(student)
    today = timezone.localdate()
    qs = base_queryset(for_student=True).filter(Q(deadline__isnull=True) | Q(deadline__gte=today))

    picks: list[Match] = []
    for row in qs:
        reasons: list[str] = []
        score = 0
        if facts["country"] and row.country:
            if row.country.lower() == facts["country"].lower():
                reasons.append(f"страна совпадает с вашей целью — {row.country}")
                score += 3
            else:
                continue
        elif not row.country:
            reasons.append("страна не ограничена")
            score += 1
        if facts["level"] and row.level:
            if row.level == facts["level"]:
                reasons.append("подходит вашему уровню обучения")
                score += 2
            else:
                continue
        elif not row.level:
            score += 1
        if row.for_international:
            reasons.append("рассчитана на иностранных студентов")
            score += 2
        if row.deadline:
            score += 1
            reasons.append(deadline_state(row.deadline, today))
        picks.append(
            Match(
                row=row,
                reasons=reasons,
                why="; ".join(reasons),
                missing=_rule_missing(row),
                score=score,
            )
        )

    picks.sort(key=lambda m: (-m.score, m.row.deadline or dt.date.max))
    return picks, facts


def _rule_missing(row: Scholarship) -> str:
    """Чего не хватает — по тексту требований, без выдумок про пороги."""
    if not row.requirements.strip():
        return "требования в справочнике не заполнены — проверьте на странице стипендии"
    return f"проверьте требования: {row.requirements.strip()[:180]}"


def pick_for(student: Student, *, actor=None, role: str = "") -> dict:
    """Подбор стипендий под профиль ученика.

    Правила отбирают, модель формулирует. Без модели подбор всё равно
    работает: объяснением служат причины отбора.
    """
    from suggestions.llm import LLMUnavailable, complete, is_available
    from suggestions.llm import status as llm_status

    picks, facts = _rule_pick(student)
    total = base_queryset(for_student=True).count()
    if total == 0:
        return {
            "picks": [],
            "note": "Справочник стипендий пока пуст — подбирать не из чего. " "Наполняет его директор по поступлению.",
            "offline": True,
            "offline_reason": "",
            "considered": 0,
        }
    if not picks:
        return {
            "picks": [],
            "note": "Под ваш профиль в справочнике ничего не нашлось: проверьте целевую страну "
            "и уровень обучения в портфолио — по ним и идёт отбор.",
            "offline": True,
            "offline_reason": "",
            "considered": total,
        }

    shortlist = picks[:CANDIDATES]
    note = ""
    offline = True
    offline_reason = ""
    if is_available():
        try:
            answer = complete(
                system=SYSTEM,
                user=_prompt(shortlist, facts),
                purpose="scholarship_pick",
                actor=actor,
                role=role,
                schema=RESULT_SCHEMA,
                max_tokens=1200,
            )
            parsed = answer.parsed if isinstance(answer.parsed, dict) else {}
            note = str(parsed.get("note") or "")
            # принимаем только номера из переданного списка (инвариант №10)
            known = {m.row.pk: m for m in shortlist}
            said = []
            for item in parsed.get("picks") or []:
                if not isinstance(item, dict):
                    continue
                match = known.get(item.get("id"))
                if match is None:
                    continue
                match.why = str(item.get("why") or match.why)
                match.missing = str(item.get("missing") or match.missing)
                said.append(match)
            if said:
                shortlist = said
                offline = False
        except LLMUnavailable:
            offline_reason = llm_status()["detail"]
    else:
        offline_reason = llm_status()["detail"]

    return {
        "picks": [_as_dict(match) for match in shortlist[:TOP_N]],
        "note": note,
        "offline": offline,
        "offline_reason": offline_reason if offline else "",
        "considered": total,
    }


def _prompt(picks: list[Match], facts: dict) -> str:
    lines = ["Профиль ученика:"]
    lines.append(f"- целевая страна: {facts['country'] or 'не указана'}")
    lines.append(f"- уровень обучения: {facts['level'] or 'не указан'}")
    lines.append(f"- GPA: {facts['gpa'] if facts['gpa'] is not None else 'нет данных'}")
    lines.append(f"- IELTS: {facts['ielts'] if facts['ielts'] is not None else 'нет данных'}")
    lines.append(f"- SAT: {facts['sat'] if facts['sat'] is not None else 'нет данных'}")
    lines.append("")
    lines.append("Стипендии справочника:")
    for match in picks:
        row = match.row
        parts = [f"id={row.pk}", row.name]
        if row.organizer:
            parts.append(f"организатор: {row.organizer}")
        if row.country:
            parts.append(f"страна: {row.country}")
        parts.append(f"финансирование: {row.get_funding_type_display()}")
        if amount_title(row):
            parts.append(f"сумма: {amount_title(row)}")
        if row.deadline:
            parts.append(f"дедлайн: {row.deadline:%d.%m.%Y}")
        if row.requirements:
            parts.append(f"требования: {row.requirements[:200]}")
        lines.append("- " + "; ".join(parts))
    lines.append("")
    lines.append("Отбери до шести самых подходящих и объясни каждую.")
    return "\n".join(lines)


def _as_dict(match: Match) -> dict:
    row = match.row
    return {
        "id": row.pk,
        "name": row.name,
        "organizer": row.organizer,
        "country": row.country,
        "funding_title": row.get_funding_type_display(),
        "amount_title": amount_title(row),
        "deadline": row.deadline.isoformat() if row.deadline else None,
        "deadline_state": deadline_state(row.deadline),
        "basis_titles": row.basis_titles,
        "is_verified": row.is_verified,
        "verification_note": row.verification_note,
        "why": match.why,
        "missing": match.missing,
    }


# --- Что видит директор по поступлению --------------------------------------


def attention(*, limit: int = 50) -> dict:
    """Кто сохранил стипендии, у кого дедлайн на неделе, кто не сохранил ничего."""
    from students.models import Student as StudentModel

    today = timezone.localdate()
    week = today + dt.timedelta(days=7)

    rows = (
        SavedScholarship.objects.select_related("student", "scholarship")
        .order_by("student__last_name", "student__first_name")
        .all()
    )
    by_student: dict[int, dict] = {}
    for row in rows:
        entry = by_student.setdefault(
            row.student_id,
            {
                "student": row.student_id,
                "student_name": str(row.student),
                "saved": 0,
                "soon": [],
            },
        )
        entry["saved"] += 1
        if row.scholarship.deadline and today <= row.scholarship.deadline <= week:
            entry["soon"].append(
                {
                    "name": row.scholarship.name,
                    "deadline": row.scholarship.deadline.isoformat(),
                    "deadline_state": deadline_state(row.scholarship.deadline, today),
                }
            )

    saved_students = set(by_student)
    without = [
        {"student": s.pk, "student_name": str(s)}
        for s in StudentModel.objects.all().order_by("last_name", "first_name")[:limit]
        if s.pk not in saved_students
    ]
    return {
        "total_scholarships": Scholarship.objects.count(),
        "saved_by": sorted(by_student.values(), key=lambda row: -row["saved"])[:limit],
        "deadline_this_week": [row for row in by_student.values() if row["soon"]],
        "without_saved": without,
    }
