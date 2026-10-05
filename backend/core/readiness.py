"""Readiness Score — единый процент готовности ученика.

Считается на бэкенде в одном модуле и отдаётся вычисляемым полем.
Веса доменов, стартовые планки, цели и баллы внутри доменов — правила школы
(`core.school_rules`, раздел «Готовность»), а не код: администратор меняет
их с экрана. Правила читаются одним запросом на расчёт; цикл по ученикам
читает их один раз (`readiness_rules`) и передаёт в `compute`.

Слабое звено определяется по количеству восстановимых баллов —
`(100 − значение) × вес`, а не по самому низкому проценту. Домен
с 40% и весом 10 менее важен, чем домен с 70% и весом 35.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.utils.translation import gettext_lazy

from core import school_rules
from students.models import Student

#: домен → правило школы с его весом; сумма 100, вес домена без данных расходится по остальным
WEIGHT_RULES = {
    "exam": school_rules.READINESS_W_EXAM,
    "admission": school_rules.READINESS_W_ADMISSION,
    "talent": school_rules.READINESS_W_TALENT,
    "behavior": school_rules.READINESS_W_BEHAVIOR,
    "sport": school_rules.READINESS_W_SPORT,
}


@dataclass(frozen=True)
class ReadinessRules:
    """Правила школы для расчёта готовности."""

    weights: dict[str, float]
    #: стартовые планки: прогресс считается от них к личной цели ученика
    ielts_floor: float
    sat_floor: float
    #: цели: столько вузов, активностей и соревнований дают полный балл
    target_universities: int
    talent_target: int
    sport_competitions: int
    #: баллы внутри «Поступления» (сумма 100)
    points_list: float
    points_common_app: float
    points_account: float
    points_ready: float
    #: баллы внутри «Спорта» (сумма 100)
    points_competitions: float
    points_certificate: float
    points_leadership: float


def readiness_rules() -> ReadinessRules:
    """Правила расчёта одним запросом."""
    values = school_rules.values()
    return ReadinessRules(
        weights={code: float(values[rule]) for code, rule in WEIGHT_RULES.items()},
        ielts_floor=float(values[school_rules.READINESS_IELTS_FLOOR]),
        sat_floor=float(values[school_rules.READINESS_SAT_FLOOR]),
        target_universities=int(values[school_rules.READINESS_TARGET_UNIVERSITIES]),
        talent_target=int(values[school_rules.READINESS_TALENT_TARGET]),
        sport_competitions=int(values[school_rules.READINESS_SPORT_COMPETITIONS]),
        points_list=float(values[school_rules.READINESS_POINTS_LIST]),
        points_common_app=float(values[school_rules.READINESS_POINTS_COMMON_APP]),
        points_account=float(values[school_rules.READINESS_POINTS_ACCOUNT]),
        points_ready=float(values[school_rules.READINESS_POINTS_READY]),
        points_competitions=float(values[school_rules.READINESS_POINTS_COMPETITIONS]),
        points_certificate=float(values[school_rules.READINESS_POINTS_CERTIFICATE]),
        points_leadership=float(values[school_rules.READINESS_POINTS_LEADERSHIP]),
    )


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


def _exam_value(student: Student, rules: ReadinessRules) -> float | None:
    """Прогресс от стартовой планки к личной цели, а не голое отношение к цели."""
    profile = getattr(student, "exam", None)
    if profile is None:
        return None
    parts: list[float] = []

    ielts, ielts_target = _f(profile.ielts_current), _f(profile.ielts_target)
    if ielts is not None and ielts_target and ielts_target > rules.ielts_floor:
        parts.append(clamp((ielts - rules.ielts_floor) / (ielts_target - rules.ielts_floor)))

    sat, sat_target = _f(profile.sat_current), _f(profile.sat_target)
    if sat is not None and sat_target and sat_target > rules.sat_floor:
        parts.append(clamp((sat - rules.sat_floor) / (sat_target - rules.sat_floor)))

    return (sum(parts) / len(parts)) * 100 if parts else None


def _admission_value(student: Student, rules: ReadinessRules) -> float | None:
    profile = getattr(student, "admission", None)
    if profile is None:
        return None
    rows = list(student.universities.all())
    ready = sum(1 for r in rows if r.application_status in ("ready", "submitted", "accepted"))

    value = clamp(len(rows) / rules.target_universities) * rules.points_list
    value += rules.points_common_app if profile.has_common_app else 0
    value += rules.points_account if profile.has_application_account else 0
    value += clamp(ready / rules.target_universities) * rules.points_ready
    return value


def _talent_value(student: Student, rules: ReadinessRules) -> float | None:
    if not hasattr(student, "talent"):
        return None
    return clamp(student.activities.count() / rules.talent_target) * 100


def _behavior_value(student: Student, rules: ReadinessRules) -> float | None:
    profile = getattr(student, "behavior", None)
    if profile is None:
        return None
    # «Выполнение ДЗ, %» считается из сдач за четверть (`homework.services`), руками не вносится
    from homework.services import completion_pct

    parts = [x for x in (profile.attendance_percent, completion_pct(student.pk)) if x is not None]
    return sum(parts) / len(parts) if parts else None


def _sport_value(student: Student, rules: ReadinessRules) -> float | None:
    """Спорт есть не у всех — у кого нет, его вес разойдётся по остальным."""
    profile = getattr(student, "sport", None)
    if profile is None or profile.sport_type_id is None:
        return None
    competitions = list(student.competitions.all())
    value = clamp(len(competitions) / rules.sport_competitions) * rules.points_competitions
    if any(c.has_certificate for c in competitions):
        value += rules.points_certificate
    if profile.leadership_role:
        value += rules.points_leadership
    return clamp(value, 0, 100)


#: Порядок важен только для читаемости — вклад задаётся весами.
CALCULATORS = (
    ("exam", gettext_lazy("Экзамены"), _exam_value),
    ("admission", gettext_lazy("Поступление"), _admission_value),
    ("talent", gettext_lazy("Портфолио"), _talent_value),
    ("behavior", gettext_lazy("Учебная дисциплина"), _behavior_value),
    ("sport", gettext_lazy("Спорт"), _sport_value),
)


def compute(student: Student, rules: ReadinessRules | None = None) -> Readiness:
    """Посчитать готовность одного ученика.

    Домены без данных исключаются, их вес поровну расходится по остальным —
    иначе у неспортсмена потолок готовности был бы 90%. Цикл по ученикам
    передаёт `rules` сам: правила школы читаются один раз, а не на каждого.
    """
    rules = rules or readiness_rules()
    weights = rules.weights

    raw: list[tuple[str, str, float]] = []
    skipped: list[tuple[str, str]] = []
    missing_weight = 0.0
    for code, lazy_title, calc in CALCULATORS:
        # подпись — на языке ответа: дальше она уходит строкой в JSON и в промпты
        title = str(lazy_title)
        value = calc(student, rules)
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
