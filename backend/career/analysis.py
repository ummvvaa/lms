"""Разбор результатов профтеста моделью.

Модель получает не ответы, а профиль: шкалы с баллом не ниже порога теста
и подписями интерпретации, названия тестов, параллель; имени ученика
в запросе нет — только номер (как у остальных операций помощника).
Направления, профессии и предметы — текстом разбора; программы — только
номерами из справочника школы (инвариант 10). Ответ хранится строками
`CareerAnalysis` и `CareerAnalysisDirection`; в доменные поля ученика
ничего не пишется.

Один набор сданных попыток разбирается один раз (`fingerprint`):
повторный запуск по тем же попыткам возвращает готовый разбор, пока
учитель не нажмёт «Пересчитать» (решение владельца, 08.10.2026).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from career.models import AnalysisStatus, CareerAnalysis, CareerAnalysisDirection, CareerAttempt
from core.parallels import has_admission, parallel_of
from students.models import Student
from universities.models import Program

#: сколько программ справочника отдаём модели — как у прежнего профтеста
CANDIDATES = 60
MAX_DIRECTIONS = 5
MAX_TOKENS = 2600

# fmt: off
SYSTEM = (  # i18n-skip: промпт ИИ — язык ответа модели настраивается отдельно
    """Ты помогаешь учителю профориентации понять, какие направления обучения и профессии
подходят ученику по результатам психологических тестов профориентации.

Правила, нарушать нельзя:
- опирайся только на переданные результаты — шкалы, баллы и их подписи; ничего не додумывай
  о личности ученика;
- предлагай от трёх до пяти направлений, каждое — с объяснением через конкретные шкалы и баллы,
  а не вообще;
- для каждого направления назови две–четыре профессии, школьные предметы и экзамены, которые
  под него нужны;
- программы указывай ТОЛЬКО номерами из переданного списка справочника школы; программы, которой
  нет в списке, не существует — не называй её никак; список пуст или подходящих нет — оставь поле
  пустым и скажи об этом в объяснении;
- не обещай поступление и не употребляй слова «шанс», «вероятность», «прогноз»;
- не ставь диагнозов и не оценивай ученика как человека: пиши об интересах и сильных сторонах;
- пиши подробно и по делу: разбор читает учитель и обсуждает его с учеником."""
)
# fmt: on

RESULT_SCHEMA = {  # i18n-skip: схема ответа для модели ИИ
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "общий вывод о профиле интересов, три–шесть предложений"},
        "directions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "название направления"},
                    "why": {"type": "string", "description": "почему подходит — по шкалам и баллам"},
                    "professions": {"type": "string", "description": "две–четыре профессии через запятую"},
                    "subjects": {"type": "string", "description": "школьные предметы под направление"},
                    "exams": {"type": "string", "description": "экзамены под направление"},
                    "programs": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "номера программ из переданного списка",
                    },
                },
                "required": ["title", "why"],
            },
        },
    },
    "required": ["directions"],
}


class AnalysisRefused(ValueError):
    """Разбор не запускается — причина словами."""


@dataclass(frozen=True)
class Plan:
    """Что сделает запуск: новые разборы, готовые и кого пропустили."""

    create: list[tuple[Student, list[CareerAttempt]]]
    reuse: list[CareerAnalysis]
    skipped: list[tuple[Student, str]]


def fingerprint_of(attempts: list[CareerAttempt]) -> str:
    return ",".join(str(pk) for pk in sorted(attempt.pk for attempt in attempts))


def profile_lines(attempt: CareerAttempt) -> list[str]:
    """Шкалы попытки не ниже порога теста — строками для модели; пусто — считать не из чего."""
    threshold = attempt.test.analysis_min_score
    rows = [row for row in attempt.scores.select_related("scale") if row.score >= threshold]
    rows.sort(key=lambda row: (-row.score, row.scale.order))
    return [f"- {row.scale.title}: {row.score}" + (f" — {row.label}" if row.label else "") for row in rows]


def _candidates(student: Student) -> list[Program]:
    """Программы справочника — только 11 параллели: у 8–10 поступления нет."""
    if not has_admission(student):
        return []
    return list(
        Program.objects.filter(is_active=True, university__is_active=True)
        .select_related("university")
        .order_by("university__world_rank", "university__name")[:CANDIDATES]
    )


def _prompt(student: Student, attempts: list[CareerAttempt], programs: list[Program]) -> str:
    """Запрос модели: профиль выше порога и программы справочника; имени ученика нет."""
    lines = [
        f"Ученик №{student.pk}, {parallel_of(student)} параллель.",
        "Результаты тестов профориентации:",
    ]  # i18n-skip: промпт ИИ
    for attempt in attempts:
        test = attempt.test
        when = timezone.localtime(attempt.finished_at).strftime("%d.%m.%Y") if attempt.finished_at else ""
        lines.append("")
        lines.append(f"Тест «{test.title}»" + (f", пройден {when}" if when else "") + ":")  # i18n-skip: промпт ИИ
        rows = profile_lines(attempt)
        if rows:
            lines.append(
                f"(шкалы с баллом не ниже {test.analysis_min_score}; остальные не показаны)"
            )  # i18n-skip: промпт ИИ
            lines.extend(rows)
        else:
            lines.append("(ни одна шкала не набрала балла выше порога)")  # i18n-skip: промпт ИИ
    lines.append("")
    if programs:
        lines.append("Программы справочника школы (только из них можно выбирать):")  # i18n-skip: промпт ИИ
        for program in programs:
            lines.append(
                f"- id={program.pk}: {program.name} · {program.university.name} · {program.get_level_display()}"
            )
    else:
        lines.append("Программ справочника для этого ученика нет: поле programs оставь пустым.")  # i18n-skip: промпт ИИ
    lines.append("")
    lines.append("Назови от трёх до пяти направлений.")  # i18n-skip: промпт ИИ
    return "\n".join(lines)


def plan(students: list[Student], tests: list, *, force: bool = False) -> Plan:
    """Кому разбор нужен: у ученика сданы все выбранные тесты и набор ещё не разбирался."""
    from career.services import done_attempts

    create: list[tuple[Student, list[CareerAttempt]]] = []
    reuse: list[CareerAnalysis] = []
    skipped: list[tuple[Student, str]] = []
    wanted = {test.pk for test in tests}
    for student in students:
        attempts = list(done_attempts(student, tests))
        have = {attempt.test_id for attempt in attempts}
        if have != wanted:
            skipped.append((student, _("сданы не все выбранные тесты")))
            continue
        if not any(profile_lines(attempt) for attempt in attempts):
            skipped.append((student, _("ни одна шкала не выше порога — разбирать нечего")))
            continue
        key = fingerprint_of(attempts)
        existing = (
            CareerAnalysis.objects.filter(student=student, fingerprint=key)
            .exclude(status=AnalysisStatus.FAILED)
            .first()
        )
        if existing is not None and not force:
            reuse.append(existing)
            continue
        create.append((student, attempts))
    return Plan(create=create, reuse=reuse, skipped=skipped)


@transaction.atomic
def open_analysis(student: Student, attempts: list[CareerAttempt], *, actor, language: str) -> CareerAnalysis:
    row = CareerAnalysis.objects.create(
        student=student, fingerprint=fingerprint_of(attempts), created_by=actor, language=language
    )
    row.attempts.set(attempts)
    return row


def run(analysis: CareerAnalysis) -> CareerAnalysis:
    """Один вызов модели; ошибка остаётся у разбора с причиной."""
    from core.i18n import active_language, render
    from suggestions.llm import LLMUnavailable, complete

    student = analysis.student
    attempts = list(analysis.attempts.select_related("test").order_by("finished_at", "id"))
    programs = _candidates(student)
    known = {program.pk: program for program in programs}
    try:
        answer = complete(
            language=active_language(),
            system=SYSTEM,
            user=_prompt(student, attempts, programs),
            purpose="career_test",
            actor=analysis.created_by,
            role=getattr(analysis.created_by, "role", ""),
            schema=RESULT_SCHEMA,
            max_tokens=MAX_TOKENS,
        )
    except LLMUnavailable as error:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = (str(error) or render(analysis.language, "Модель сейчас недоступна"))[:300]
        analysis.finished_at = timezone.now()
        analysis.save(update_fields=["status", "error", "finished_at"])
        return analysis

    parsed = answer.parsed if isinstance(answer.parsed, dict) else {}
    rows = parsed.get("directions")
    analysis.summary = str(parsed.get("summary") or "").strip()
    if not isinstance(rows, list) or not rows:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = render(analysis.language, "Модель вернула пустой разбор — попробуйте пересчитать")
        analysis.finished_at = timezone.now()
        analysis.save(update_fields=["summary", "status", "error", "finished_at"])
        return analysis

    order = 0
    for item in rows[:MAX_DIRECTIONS]:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            continue
        order += 1
        direction = CareerAnalysisDirection.objects.create(
            analysis=analysis,
            order=order,
            title=str(item["title"]).strip()[:150],
            reasoning=str(item.get("why") or "").strip(),
            professions=str(item.get("professions") or "").strip()[:300],
            subjects=str(item.get("subjects") or "").strip()[:300],
            exams=str(item.get("exams") or "").strip()[:300],
        )
        picked = [known[pid] for pid in (item.get("programs") or []) if isinstance(pid, int) and pid in known]
        if picked:
            direction.programs.set(picked)
    if order == 0:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = render(analysis.language, "Разбор пришёл без направлений — попробуйте пересчитать")
    else:
        analysis.status = AnalysisStatus.DONE
        analysis.error = ""
    analysis.finished_at = timezone.now()
    analysis.save(update_fields=["summary", "status", "error", "finished_at"])
    return analysis
