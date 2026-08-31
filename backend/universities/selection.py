"""Прогон подбора вузов: этапы, воронка, категории, снимок (фаза 40).

Расчёт идёт фоновой задачей и отчитывается этапами — показ процесса
объясняет, что происходит. Результат — датированный снимок: проценты
и категории на момент запуска; живой разбор «почему такой процент»
считается отдельным запросом по текущему профилю.

Всё здесь — соответствие требованиям, не шанс поступления (инвариант №11).
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from students.models import Student
from universities.matching import MatchResult, match
from universities.models import (
    MatchRun,
    MatchRunResult,
    MatchRunStatus,
    Program,
    ResultSection,
    RunTier,
)

#: Этапы прогона — по порядку, подписи читает человек на экране расчёта.
STAGES: tuple[tuple[str, str, int], ...] = (
    ("filter", "Отбираем программы", 15),
    ("profile", "Оцениваем профиль", 35),
    ("analyze", "Разбираем вузы", 60),
    ("assemble", "Собираем финальный список", 80),
    ("strategy", "Готовим стратегию", 95),
)

#: Сколько программ разбирается подробно и сколько попадает в финал.
ANALYZED_LIMIT = 40
FINAL_LIMIT = 12


def stage_titles() -> list[dict]:
    return [{"code": code, "title": title, "at": at} for code, title, at in STAGES]


def tier_for(percent: int) -> str:
    """Категория по проценту. Границы — в настройках, не в коде."""
    tiers = settings.MATCH_TIERS
    if percent >= tiers["safety"]:
        return RunTier.SAFETY
    if percent >= tiers["match"]:
        return RunTier.MATCH
    if percent >= tiers["reach"]:
        return RunTier.REACH
    return RunTier.DREAM


def _tokens(text: str) -> list[str]:
    return [word for word in text.replace(",", " ").split() if len(word) > 2]


def filter_programs(major: str, level: str, countries: list[str]):
    """Фильтр по специальности, уровню и странам — только справочник."""
    programs = Program.objects.filter(is_active=True).select_related("university", "requirement")
    if level:
        programs = programs.filter(level=level)
    if countries:
        programs = programs.filter(university__country__in=countries)
    if major:
        matched = []
        tokens = [token.lower() for token in _tokens(major)]
        for program in programs:
            name = program.name.lower()
            if any(token in name for token in tokens):
                matched.append(program)
        return matched
    return list(programs)


def goal_percents(student: Student, programs) -> dict[int, int]:
    """Процент «если закрыть разрывы» — при целевых баллах из целей (фаза 39).

    Считается на копии значений, ничего не сохраняя, как `what_if`.
    Цель ниже текущего балла не понижает: разрыв закрывают вверх.
    """
    from universities.matching import _goal_score

    exam = getattr(student, "exam", None)
    if exam is None:
        return {p.pk: match(student, p).percent for p in programs}

    ielts_goal = _goal_score(student, "IELTS") or exam.ielts_target
    sat_goal = _goal_score(student, "SAT") or exam.sat_target

    original = (exam.ielts_current, exam.sat_current)
    try:
        if ielts_goal is not None:
            exam.ielts_current = max(Decimal(str(ielts_goal)), exam.ielts_current or Decimal(0))
        if sat_goal is not None:
            exam.sat_current = max(int(sat_goal), exam.sat_current or 0)
        return {p.pk: match(student, p).percent for p in programs}
    finally:
        exam.ielts_current, exam.sat_current = original


def start_run(student: Student, *, major: str = "", level: str = "", countries: list[str] | None = None) -> MatchRun:
    """Создать прогон со снимком профиля и поставить расчёт в очередь."""
    exam = getattr(student, "exam", None)
    run = MatchRun.objects.create(
        student=student,
        major=major.strip() or getattr(getattr(student, "admission", None), "target_major", "") or "",
        level=level,
        countries=",".join(countries or []),
        snapshot_gpa=getattr(exam, "gpa", None),
        snapshot_ielts=getattr(exam, "ielts_current", None),
        snapshot_sat=getattr(exam, "sat_current", None),
        snapshot_grade=student.grade,
        snapshot_graduation_year=student.graduation_year,
    )
    from universities.tasks import run_match_selection

    run_match_selection.delay(run.pk)
    return run


def _advance(run: MatchRun, stage: str, progress: int) -> None:
    run.stage = stage
    run.progress = progress
    run.save(update_fields=["stage", "progress"])


def execute(run_id: int) -> dict:
    """Тело фоновой задачи: пять этапов с отметками прогресса."""
    run = MatchRun.objects.select_related("student").filter(pk=run_id).first()
    if run is None:
        return {"error": "прогона нет"}
    if run.status != MatchRunStatus.RUNNING:
        # двойная доставка задачи не должна дублировать строки результата
        return {"run": run.pk, "already": run.status}
    student = run.student
    countries = [c for c in run.countries.split(",") if c]

    try:
        _advance(run, "filter", 15)
        run.funnel_catalog = Program.objects.filter(is_active=True).count()
        filtered = filter_programs(run.major, run.level, countries)
        run.funnel_filtered = len(filtered)
        run.save(update_fields=["funnel_catalog", "funnel_filtered"])

        _advance(run, "profile", 35)
        results: list[MatchResult] = [match(student, program) for program in filtered]
        by_id = {r.program_id: r for r in results}

        _advance(run, "analyze", 60)
        # подробно разбираются программы с заведёнными требованиями,
        # по убыванию соответствия; остальные остаются «другими»
        scored = sorted((r for r in results if r.has_requirements), key=lambda r: (-r.percent, r.university_name))
        analyzed = scored[:ANALYZED_LIMIT]
        run.funnel_analyzed = len(analyzed)
        goals = goal_percents(student, [p for p in filtered if p.pk in {r.program_id for r in analyzed}])

        _advance(run, "assemble", 80)
        final = analyzed[:FINAL_LIMIT]
        run.funnel_final = len(final)
        run.save(update_fields=["funnel_analyzed", "funnel_final"])

        final_ids = {r.program_id for r in final}
        analyzed_ids = {r.program_id for r in analyzed}
        rows: list[MatchRunResult] = []
        position = 0
        for result in final:
            position += 1
            rows.append(
                MatchRunResult(
                    run=run,
                    program_id=result.program_id,
                    percent_now=result.percent,
                    percent_goal=max(goals.get(result.program_id, result.percent), result.percent),
                    tier=tier_for(result.percent),
                    section=ResultSection.TOP,
                    position=position,
                )
            )
        for result in analyzed:
            if result.program_id in final_ids:
                continue
            position += 1
            rows.append(
                MatchRunResult(
                    run=run,
                    program_id=result.program_id,
                    percent_now=result.percent,
                    percent_goal=max(goals.get(result.program_id, result.percent), result.percent),
                    section=ResultSection.STRONG,
                    position=position,
                )
            )
        # «другие» — прошли фильтр, но подробно не разбирались:
        # порядок по мировому рейтингу, незаполненный рейтинг — в конец
        others = [p for p in filtered if p.pk not in analyzed_ids]
        others.sort(key=lambda p: (p.university.world_rank is None, p.university.world_rank or 0, p.university.name))
        for program in others:
            position += 1
            result = by_id[program.pk]
            rows.append(
                MatchRunResult(
                    run=run,
                    program_id=program.pk,
                    percent_now=result.percent,
                    percent_goal=result.percent,
                    section=ResultSection.OTHER,
                    position=position,
                )
            )
        MatchRunResult.objects.bulk_create(rows)

        _advance(run, "strategy", 95)
        from universities.strategy import build_strategy

        strategy = build_strategy(student, run, final)
        run.strategy_position = strategy["position"]
        run.strategy_improve = strategy["improve"]
        run.strategy_next = strategy["next_step"]
        run.strategy_offline = strategy["offline"]

        run.status = MatchRunStatus.DONE
        run.stage = ""
        run.progress = 100
        run.finished_at = timezone.now()
        run.save()
        return {"run": run.pk, "final": run.funnel_final}
    except Exception as error:  # прогон не должен молча зависнуть в «считается»
        run.status = MatchRunStatus.FAILED
        run.error = str(error)[:250]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        raise


def methodology() -> list[str]:
    """«Как считаются проценты и категории» — человеческим языком.

    Собирается на сервере из тех же настроек, которыми считает движок:
    объяснение не может разойтись с расчётом.
    """
    weights = settings.MATCH_WEIGHTS
    tiers = settings.MATCH_TIERS
    weight_line = ", ".join(
        f"{title} — {int(weights[key])}%"
        for key, title in (
            ("gpa", "GPA"),
            ("english", "английский (IELTS или TOEFL)"),
            ("standardized", "стандартный тест (SAT или ACT)"),
            ("portfolio", "портфолио"),
        )
        if key in weights
    )
    return [
        "Процент — это соответствие требованиям программы, а не шанс поступления: "
        "он считается механически от порогов, заведённых в справочнике.",
        f"Позиции и веса: {weight_line}. Группа альтернатив (IELTS/TOEFL, SAT/ACT) весит как одна позиция — "
        "достаточно сдать один экзамен из пары.",
        "По каждой позиции считается, насколько текущий балл закрывает порог. Счёт идёт от нижней планки "
        "шкалы экзамена, а не от нуля: IELTS 6.0 при пороге 6.5 — это не 92%.",
        "Пустой порог в справочнике значит «требования нет» — такая позиция не участвует.",
        f"Категории по проценту: от {int(tiers['safety'])}% — Safety, от {int(tiers['match'])}% — Match, "
        f"от {int(tiers['reach'])}% — Reach, ниже — Dream. Границы задаются настройками школы.",
        "«Если закрыть разрывы» — тот же расчёт при целевых баллах из ваших целей по экзаменам.",
        "Требования, не подтверждённые школой, помечаются отдельно — процент по ним стоит перепроверить.",
    ]
