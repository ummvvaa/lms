"""Readiness Score — единый процент готовности ученика.

Считается на бэкенде в одном модуле и отдаётся вычисляемым полем.
Веса берутся из настроек (`READINESS_WEIGHTS`), а не зашиты в код:
школа их подкручивает без выката.

Слабое звено определяется по количеству восстановимых баллов —
`(100 − значение) × вес`, а не по самому низкому проценту. Домен
с 40% и весом 10 менее важен, чем домен с 70% и весом 35.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from students.models import Student


def _f(value) -> float | None:
    """Число или None — в базе много незаполненных полей."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def clamp(x: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, x))


@dataclass(frozen=True)
class Part:
    """Одна составляющая готовности."""

    code: str
    title: str
    value: float  # 0..100
    weight: float  # вклад в итог, в процентах

    @property
    def recoverable(self) -> float:
        """Сколько баллов итога можно вернуть, доведя эту часть до 100."""
        return (100.0 - self.value) * self.weight / 100.0


@dataclass(frozen=True)
class Readiness:
    """Результат расчёта."""

    score: int
    parts: tuple[Part, ...]
    weakest: Part | None
    #: домены, исключённые из расчёта: данных нет, вес разошёлся по остальным.
    #: Отдаются наружу, чтобы ученик видел все пять блоков и понимал,
    #: почему какие-то не считаются, а не думал, что их забыли
    skipped: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "parts": [
                {
                    "code": p.code,
                    "title": p.title,
                    "value": round(p.value, 1),
                    "weight": round(p.weight, 1),
                    "recoverable": round(p.recoverable, 1),
                }
                for p in self.parts
            ],
            "weakest": self.weakest.code if self.weakest else None,
            "weakest_title": self.weakest.title if self.weakest else None,
            "skipped": [{"code": code, "title": title} for code, title in self.skipped],
        }


def _exam_value(student: Student) -> float | None:
    """Прогресс от стартовой планки к личной цели, а не голое отношение к цели."""
    profile = getattr(student, "exam", None)
    if profile is None:
        return None
    cfg = settings.READINESS_BASELINES
    parts: list[float] = []

    ielts, ielts_target = _f(profile.ielts_current), _f(profile.ielts_target)
    if ielts is not None and ielts_target and ielts_target > cfg["IELTS_FLOOR"]:
        parts.append(clamp((ielts - cfg["IELTS_FLOOR"]) / (ielts_target - cfg["IELTS_FLOOR"])))

    sat, sat_target = _f(profile.sat_current), _f(profile.sat_target)
    if sat is not None and sat_target and sat_target > cfg["SAT_FLOOR"]:
        parts.append(clamp((sat - cfg["SAT_FLOOR"]) / (sat_target - cfg["SAT_FLOOR"])))

    return (sum(parts) / len(parts)) * 100 if parts else None


def _admission_value(student: Student) -> float | None:
    profile = getattr(student, "admission", None)
    if profile is None:
        return None
    cfg = settings.READINESS_ADMISSION
    rows = list(student.universities.all())
    ready = sum(1 for r in rows if r.application_status in ("ready", "submitted", "accepted"))

    value = clamp(len(rows) / cfg["TARGET_UNIVERSITIES"]) * cfg["POINTS_LIST"]
    value += cfg["POINTS_COMMON_APP"] if profile.has_common_app else 0
    value += cfg["POINTS_ACCOUNT"] if profile.has_application_account else 0
    value += clamp(ready / cfg["TARGET_UNIVERSITIES"]) * cfg["POINTS_READY"]
    return value


def _talent_value(student: Student) -> float | None:
    if not hasattr(student, "talent"):
        return None
    target = settings.READINESS_TALENT_TARGET
    return clamp(student.activities.count() / target) * 100


def _behavior_value(student: Student) -> float | None:
    profile = getattr(student, "behavior", None)
    if profile is None:
        return None
    parts = [x for x in (profile.attendance_percent, profile.homework_percent) if x is not None]
    return sum(parts) / len(parts) if parts else None


def _sport_value(student: Student) -> float | None:
    """Спорт есть не у всех — у кого нет, его вес разойдётся по остальным."""
    profile = getattr(student, "sport", None)
    if profile is None or profile.sport_type_id is None:
        return None
    cfg = settings.READINESS_SPORT
    competitions = list(student.competitions.all())
    value = clamp(len(competitions) / cfg["TARGET_COMPETITIONS"]) * cfg["POINTS_COMPETITIONS"]
    if any(c.has_certificate for c in competitions):
        value += cfg["POINTS_CERTIFICATE"]
    if profile.leadership_role:
        value += cfg["POINTS_LEADERSHIP"]
    return clamp(value, 0, 100)


#: Порядок важен только для читаемости — вклад задаётся весами.
CALCULATORS = (
    ("exam", "Экзамены", _exam_value),
    ("admission", "Поступление", _admission_value),
    ("talent", "Портфолио", _talent_value),
    ("behavior", "Учебная дисциплина", _behavior_value),
    ("sport", "Спорт", _sport_value),
)


def compute(student: Student) -> Readiness:
    """Посчитать готовность одного ученика.

    Домены без данных исключаются, их вес поровну расходится по остальным —
    иначе у неспортсмена потолок готовности был бы 90%.
    """
    weights: dict[str, float] = dict(settings.READINESS_WEIGHTS)

    raw: list[tuple[str, str, float]] = []
    skipped: list[tuple[str, str]] = []
    missing_weight = 0.0
    for code, title, calc in CALCULATORS:
        value = calc(student)
        if value is None:
            missing_weight += weights.get(code, 0.0)
            skipped.append((code, title))
            continue
        raw.append((code, title, value))

    if not raw:
        return Readiness(score=0, parts=(), weakest=None, skipped=tuple(skipped))

    bonus = missing_weight / len(raw)
    parts = tuple(Part(code, title, value, weights.get(code, 0.0) + bonus) for code, title, value in raw)

    total = sum(p.value * p.weight / 100.0 for p in parts)
    weakest = max(parts, key=lambda p: p.recoverable)
    return Readiness(score=round(total), parts=parts, weakest=weakest, skipped=tuple(skipped))
