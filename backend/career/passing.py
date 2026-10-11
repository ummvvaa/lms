"""Профориентация без оценок: «тест сдан DD.MM» или «не сдан» (решение владельца, 11.10.2026).

У предмета профориентации нет шкалы. Результат ученика за период — сданная
попытка профтеста в приложении `career` не позже конца периода, когда бы
её ни сдали: тест проходят один раз за обучение. Что считать сданным,
решают два правила школы («Оценки и журнал»): нужен ли готовый разбор
моделью (по умолчанию — да) и минимальный балл сильнейшей шкалы
(по умолчанию 0 — порога нет).
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Exists, Max, OuterRef
from django.utils import timezone

from career.models import AnalysisStatus, AttemptStatus, CareerAnalysis, CareerAttempt
from core import school_rules


def rules() -> tuple[bool, int]:
    """(нужен разбор, минимальный балл) — действующие правила школы."""
    return (
        bool(school_rules.value(school_rules.CAREER_PASS_NEEDS_ANALYSIS)),
        int(school_rules.value(school_rules.CAREER_PASS_MIN_SCORE)),
    )


def pass_map(student_ids, end: dt.date) -> dict[int, dt.date | None]:
    """Дата сдачи по ученикам: последняя попытка, которая считается сданной, не позже `end`."""
    out: dict[int, dt.date | None] = {sid: None for sid in student_ids}
    if not out:
        return out
    needs_analysis, min_score = rules()
    # конец дня `end` по времени школы: попытка, сданная вечером последнего дня, тоже идёт
    limit = timezone.make_aware(dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min))
    rows = (
        CareerAttempt.objects.filter(
            student_id__in=list(out),
            status=AttemptStatus.DONE,
            archived_at__isnull=True,
            test__archived_at__isnull=True,
            finished_at__lt=limit,
        )
        .annotate(top=Max("scores__score"))
        .annotate(analysed=Exists(CareerAnalysis.objects.filter(status=AnalysisStatus.DONE, attempts=OuterRef("pk"))))
        .order_by("finished_at", "pk")
    )
    for row in rows:
        if min_score and (row.top is None or row.top < min_score):
            continue
        if needs_analysis and not row.analysed:
            continue
        out[row.student_id] = timezone.localtime(row.finished_at).date()
    return out


def passed_at(student_id: int, end: dt.date) -> dt.date | None:
    return pass_map([student_id], end)[student_id]
