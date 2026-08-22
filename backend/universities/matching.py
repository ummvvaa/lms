"""Движок соответствия: проходит ли ученик по баллам и чего не хватает.

Результат вычисляемый, не хранимый: профиль меняется каждый день, а копия
вердикта устаревала бы молча. Кэшируется по необходимости на уровне запроса.

Формулировки — конструктивные, без внутренних ярлыков (инвариант №7):
не «слабый кандидат», а «не хватает 0.5 IELTS».
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from core.readiness import clamp
from students.models import Student
from universities.models import AdmissionRequirement, Program


@dataclass(frozen=True)
class Criterion:
    """Один критерий: текущее значение, порог, разрыв."""

    code: str
    title: str
    current: float | None
    threshold: float
    unit: str = ""
    #: шаг округления разрыва: IELTS ходит по 0.5, SAT — по 10
    step: float = 1.0
    #: группа альтернатив: IELTS и TOEFL взаимозаменяемы, как SAT и ACT.
    #: Достаточно выполнить любой критерий группы.
    group: str = ""
    #: считается ли разрыв числом. Портфолио — нет: «не хватает 1 портфолио» бессмысленно
    countable: bool = True

    @property
    def is_met(self) -> bool:
        return self.current is not None and self.current >= self.threshold

    @property
    def is_unknown(self) -> bool:
        """Данных о себе нет — это не «не проходит», это «неизвестно»."""
        return self.current is None

    @property
    def achievement(self) -> float:
        """Степень достижения порога, 0..1.

        Считается от нижней планки шкалы (`MATCH_FLOORS`), а не от нуля:
        IELTS 6.0 при пороге 6.5 — это не 92%, потому что шкала начинается
        не с нуля. Данных нет — считаем нулём, но отдельно помечаем.
        """
        if self.is_met:
            return 1.0
        if self.current is None:
            return 0.0
        floor = settings.MATCH_FLOORS.get(self.code, 0.0)
        span = self.threshold - floor
        if span <= 0:
            return 1.0 if self.current >= self.threshold else 0.0
        return clamp((self.current - floor) / span)

    @property
    def gap_exact(self) -> float:
        """Точная разница. Из-за плавающей точки бывает 0.09999 вместо 0.1."""
        if self.current is None:
            return self.threshold
        return max(0.0, self.threshold - self.current)

    @property
    def gap(self) -> float:
        """Разрыв, округлённый вверх до шага экзамена.

        IELTS ходит по 0.5, SAT — по 10: «не хватает 0.1 IELTS» бессмысленно,
        добрать можно только полбалла.
        """
        exact = self.gap_exact
        if exact <= 0:
            return 0.0
        steps = exact / self.step
        # допуск гасит хвосты плавающей точки: 6.5-6.0 = 0.4999... это ровно один шаг
        whole = int(steps + 1e-9)
        rounded = (whole + (0 if abs(steps - whole) < 1e-9 else 1)) * self.step
        return round(rounded, 2)

    def phrase(self) -> str:
        """Человеческая формулировка по одному критерию."""
        if self.is_unknown:
            return f"{self.title}: нет данных, нужен {self._fmt(self.threshold)}"
        if self.is_met:
            return f"{self.title}: {self._fmt(self.current)} — проходит"
        return f"не хватает {self._fmt(self.gap)} {self.title}"

    def short_gap(self) -> str:
        """Фрагмент для сводной фразы: «0.5 IELTS»."""
        if self.is_unknown:
            return f"данных по {self.title}"
        if not self.countable:
            return self.title
        return f"{self._fmt(self.gap)} {self.title}"

    def _fmt(self, value: float | None) -> str:
        if value is None:
            return "—"
        return str(int(value)) if float(value).is_integer() else str(round(value, 1))

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "title": self.title,
            "current": self.current,
            "threshold": self.threshold,
            "gap": self.gap,
            "gap_exact": round(self.gap_exact, 3),
            "is_met": self.is_met,
            "is_unknown": self.is_unknown,
            "group": self.group,
            "achievement": round(self.achievement, 3),
            "phrase": self.phrase(),
        }


@dataclass(frozen=True)
class MatchResult:
    """Вердикт по одной программе."""

    program_id: int
    program_name: str
    university_name: str
    country: str
    has_requirements: bool
    criteria: tuple[Criterion, ...]

    @property
    def unmet(self) -> tuple[Criterion, ...]:
        """Невыполненные требования с учётом альтернатив.

        IELTS и TOEFL — разные способы подтвердить английский: если сдан один,
        второй не требуется. Иначе ученик с IELTS 7.0 висел бы «не хватает
        данных по TOEFL» и ни одна программа не открывалась бы никогда.
        """
        satisfied_groups = {c.group for c in self.criteria if c.group and c.is_met}
        out: list[Criterion] = []
        seen_groups: set[str] = set()

        for criterion in self.criteria:
            if criterion.is_met:
                continue
            if not criterion.group:
                out.append(criterion)
                continue
            if criterion.group in satisfied_groups or criterion.group in seen_groups:
                continue
            # из группы показываем один критерий: тот, по которому есть данные
            alternatives = [c for c in self.criteria if c.group == criterion.group and not c.is_met]
            with_data = [c for c in alternatives if not c.is_unknown]
            out.append(min(with_data, key=lambda c: c.gap) if with_data else alternatives[0])
            seen_groups.add(criterion.group)
        return tuple(out)

    @property
    def is_open(self) -> bool:
        """Проходит, если ни один известный критерий не нарушен."""
        return self.has_requirements and not self.unmet

    @property
    def positions(self) -> tuple[tuple[str, tuple[Criterion, ...]], ...]:
        """Критерии, сгруппированные в позиции.

        Группа альтернатив — одна позиция: IELTS и TOEFL это два способа
        подтвердить английский, а не два отдельных требования.
        """
        grouped: dict[str, list[Criterion]] = {}
        for criterion in self.criteria:
            key = criterion.group or criterion.code
            grouped.setdefault(key, []).append(criterion)
        return tuple((key, tuple(items)) for key, items in grouped.items())

    @property
    def percent(self) -> int:
        """Соответствие требованиям, 0..100.

        Это НЕ шанс поступления и не прогноз (инвариант №11): число
        считается механически от порогов справочника. Требований нет —
        и процента нет: считать не от чего.
        """
        if not self.has_requirements or not self.criteria:
            return 0

        weights = settings.MATCH_WEIGHTS
        total_weight = 0.0
        earned = 0.0
        for key, items in self.positions:
            weight = weights.get(key, weights.get(items[0].code, 10.0))
            # из группы берём лучшее: достаточно сдать один из альтернативных
            best = max(item.achievement for item in items)
            total_weight += weight
            earned += best * weight

        if total_weight <= 0:
            return 0
        return round(earned / total_weight * 100)

    def breakdown(self) -> list[dict]:
        """Разбивка по позициям: процент без объяснения бесполезен."""
        weights = settings.MATCH_WEIGHTS
        rows: list[dict] = []
        for key, items in self.positions:
            best = max(items, key=lambda c: c.achievement)
            rows.append(
                {
                    "code": key,
                    "title": " или ".join(dict.fromkeys(item.title for item in items)),
                    "weight": weights.get(key, weights.get(items[0].code, 10.0)),
                    "achievement": round(best.achievement, 3),
                    "percent": round(best.achievement * 100),
                    "is_met": any(item.is_met for item in items),
                    "is_unknown": all(item.is_unknown for item in items),
                    "gap_phrase": "" if best.is_met else best.short_gap(),
                    "criteria": [item.as_dict() for item in items],
                }
            )
        return rows

    @property
    def status(self) -> str:
        if not self.has_requirements:
            return "unknown"
        if self.is_open:
            return "open"
        return "gap"

    def summary(self) -> str:
        """«Не хватает 0.5 IELTS и 60 SAT» — то, что видит ученик.

        Собирается из коротких фрагментов: «не хватает» произносится один раз,
        а названия экзаменов остаются в своём регистре.
        """
        if not self.has_requirements:
            return "Требования этой программы ещё не заведены в справочнике"
        if self.is_open:
            return "Вы проходите по всем заведённым требованиям"
        parts = [c.short_gap() for c in self.unmet]
        joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " и " + parts[-1]
        return f"Не хватает {joined}"

    def as_dict(self) -> dict:
        return {
            "program": self.program_id,
            "program_name": self.program_name,
            "university_name": self.university_name,
            "country": self.country,
            "status": self.status,
            "has_requirements": self.has_requirements,
            "is_open": self.is_open,
            "percent": self.percent,
            "summary": self.summary(),
            "breakdown": self.breakdown(),
            "criteria": [c.as_dict() for c in self.criteria],
        }


def _number(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _best_score(student: Student, exam_type: str) -> float | None:
    """Лучший официальный балл по экзамену из истории попыток.

    Профиль хранит текущее значение, но официальная сдача из `ExamAttempt`
    (инвариант №5) точнее — по ней и считаем, если она есть.
    """
    best = (
        student.exam_attempts.filter(exam_type=exam_type, attempt_format="official", total_score__isnull=False)
        .order_by("-total_score")
        .values_list("total_score", flat=True)
        .first()
    )
    return _number(best)


def build_criteria(student: Student, requirement: AdmissionRequirement) -> tuple[Criterion, ...]:
    """Собрать критерии, по которым есть требование.

    Пустой порог означает «требования нет» — такой критерий не создаётся.
    """
    exam = getattr(student, "exam", None)
    criteria: list[Criterion] = []

    if requirement.min_gpa is not None:
        criteria.append(
            Criterion("gpa", "GPA", _number(exam.gpa) if exam else None, _number(requirement.min_gpa), step=0.1)
        )

    if requirement.min_ielts is not None:
        current = _best_score(student, "IELTS") or (_number(exam.ielts_current) if exam else None)
        criteria.append(Criterion("ielts", "IELTS", current, _number(requirement.min_ielts), step=0.5, group="english"))

    if requirement.min_toefl is not None:
        criteria.append(
            Criterion("toefl", "TOEFL", _best_score(student, "TOEFL"), float(requirement.min_toefl), group="english")
        )

    if requirement.min_sat is not None:
        current = _best_score(student, "SAT") or (_number(exam.sat_current) if exam else None)
        criteria.append(Criterion("sat", "SAT", current, float(requirement.min_sat), step=10, group="standardized"))

    if requirement.min_act is not None:
        criteria.append(
            Criterion("act", "ACT", _best_score(student, "ACT"), float(requirement.min_act), group="standardized")
        )

    if requirement.portfolio_required:
        criteria.append(
            Criterion(
                "portfolio",
                "работ в портфолио",
                float(student.activities.count()),
                1.0,
                countable=False,
            )
        )

    return tuple(criteria)


def match(student: Student, program: Program) -> MatchResult:
    """Соответствие ученика одной программе."""
    requirement = getattr(program, "requirement", None)
    return MatchResult(
        program_id=program.pk,
        program_name=program.name,
        university_name=program.university.name,
        country=program.university.country,
        has_requirements=requirement is not None,
        criteria=build_criteria(student, requirement) if requirement else (),
    )


def match_student_list(student: Student) -> list[MatchResult]:
    """Как ученик выглядит на фоне своего списка вузов."""
    rows = student.universities.select_related("program__university", "program__requirement").all()
    return [match(student, row.program) for row in rows]


def open_programs(student: Student, *, programs: Iterable[Program] | None = None) -> list[MatchResult]:
    """Какие программы открываются при текущем профиле."""
    if programs is None:
        programs = Program.objects.filter(is_active=True).select_related("university", "requirement")
    return [match(student, program) for program in programs]


def what_if(student: Student, *, ielts_delta: float = 0.0, sat_delta: int = 0, gpa_delta: float = 0.0) -> dict:
    """Что откроется, если поднять IELTS, SAT или GPA.

    Считаем на копии значений, ничего не сохраняя: вопрос гипотетический.
    Возвращаем не только «сколько открылось», но и весь пересчитанный
    список — ползунки должны двигать карточки, а не одну цифру.
    """
    programs = list(Program.objects.filter(is_active=True).select_related("university", "requirement"))
    before_results = open_programs(student, programs=programs)
    before = {m.program_id for m in before_results if m.is_open}
    percent_before = {m.program_id: m.percent for m in before_results}

    exam = getattr(student, "exam", None)
    original = (exam.ielts_current, exam.sat_current, exam.gpa) if exam else (None, None, None)
    try:
        if exam:
            if exam.ielts_current is not None and ielts_delta:
                exam.ielts_current = Decimal(str(_number(exam.ielts_current) + ielts_delta))
            if exam.sat_current is not None and sat_delta:
                exam.sat_current = exam.sat_current + sat_delta
            if exam.gpa is not None and gpa_delta:
                exam.gpa = Decimal(str(round(_number(exam.gpa) + gpa_delta, 2)))
        after_results = open_programs(student, programs=programs)
    finally:
        if exam:
            exam.ielts_current, exam.sat_current, exam.gpa = original

    after = {m.program_id for m in after_results if m.is_open}
    unlocked = [m.as_dict() for m in after_results if m.program_id in after - before]

    rows = []
    for result in sorted(after_results, key=lambda m: (-m.percent, m.university_name)):
        payload = result.as_dict()
        payload["percent_before"] = percent_before.get(result.program_id, 0)
        payload["became_open"] = result.program_id in after - before
        rows.append(payload)

    return {
        "ielts_delta": ielts_delta,
        "sat_delta": sat_delta,
        "gpa_delta": gpa_delta,
        "open_before": len(before),
        "open_after": len(after),
        "unlocked": unlocked,
        "results": rows,
    }


#: Сколько программ каждой категории школа считает здоровым списком.
BALANCE_TARGET = {"reach": 2, "target": 3, "safety": 1}

TIER_TITLES = {"reach": "reach — с запасом вверх", "target": "target — по силам", "safety": "safety — подстраховка"}


def list_balance(student: Student) -> dict:
    """Соотношение reach / target / safety в списке ученика.

    Считается по фактическим записям справочника: сколько чего есть,
    сколько добрать. Никаких «шансов» — только состав списка (инвариант №11).
    """
    rows = student.universities.select_related("program__university", "program__requirement").all()
    counts = {tier: 0 for tier in BALANCE_TARGET}
    for row in rows:
        if row.tier in counts:
            counts[row.tier] += 1

    gaps = {tier: max(0, target - counts[tier]) for tier, target in BALANCE_TARGET.items()}
    missing = [tier for tier, gap in gaps.items() if gap]

    if not rows:
        advice = "Список пуст — начните с двух-трёх программ, по которым ученик проходит уже сейчас"
    elif not missing:
        advice = "Список сбалансирован: есть и запас вверх, и подстраховка"
    else:
        parts = [f"{TIER_TITLES[tier]}: не хватает {gaps[tier]}" for tier in missing]
        advice = "; ".join(parts)

    return {
        "student": student.pk,
        "student_name": student.full_name,
        "total": len(rows),
        "counts": counts,
        "target": dict(BALANCE_TARGET),
        "gaps": gaps,
        "advice": advice,
        "programs": [
            {
                "program": row.program_id,
                "tier": row.tier,
                "university_name": row.program.university.name,
                "program_name": row.program.name,
            }
            for row in rows
        ],
    }
