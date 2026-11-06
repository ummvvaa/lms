"""Ответы API профтеста: словари строк для экранов."""

from __future__ import annotations

from academics.payloads import person, student_brief
from career.analysis import RULES
from career.models import CareerAnalysis, CareerAttempt, CareerTest
from career.scoring import bounds


def option_dict(option) -> dict:
    return {"id": option.pk, "label": option.label, "value": option.value}


def scale_dict(scale) -> dict:
    return {"id": scale.pk, "code": scale.code, "title": scale.title, "description": scale.description}


def test_brief(test: CareerTest) -> dict:
    return {"id": test.pk, "title": test.title, "is_active": test.is_active}


def test_row(
    test: CareerTest,
    *,
    items: int,
    scales: int,
    assigned: int,
    done: int,
    in_progress: int,
    used: bool = False,
    can_remove: bool = False,
) -> dict:
    """Строка списка. `used` — попытки у теста есть хоть где-то (тогда «В архив», а не
    «Удалить»); счётчики — по группам смотрящего."""
    return {
        **test_brief(test),
        "instruction": test.instruction,
        "analysis_min_score": test.analysis_min_score,
        "items": items,
        "scales": scales,
        "assigned": assigned,
        "done": done,
        "in_progress": in_progress,
        "file_name": test.file_name,
        "created_at": test.created_at,
        "created_by": person(test.created_by),
        "used": used,
        "can_remove": can_remove,
    }


def test_detail(test: CareerTest, groups: list[dict]) -> dict:
    return {
        **test_brief(test),
        "instruction": test.instruction,
        "analysis_min_score": test.analysis_min_score,
        "file_name": test.file_name,
        "created_at": test.created_at,
        "created_by": person(test.created_by),
        "options": [option_dict(o) for o in test.options.all()],
        "scales": [scale_dict(s) for s in test.scales.all()],
        "items": [
            {
                "id": item.pk,
                "number": item.number,
                "text": item.text,
                "scale": item.scale.code if item.scale_id else "",
                "sign": item.sign,
                "choices": [
                    {"id": c.pk, "label": c.label, "scale": c.scale.code, "value": c.value} for c in item.choices.all()
                ],
            }
            for item in test.items.select_related("scale").prefetch_related("choices__scale")
        ],
        "ranges": [
            {"scale": r.scale.code if r.scale_id else "", "low": r.low, "high": r.high, "label": r.label}
            for r in test.ranges.select_related("scale")
        ],
        "groups": [
            {
                "group": row["group"].pk,
                "code": row["group"].code,
                "parallel": row["group"].parallel,
                "whole": row["whole"],
                "students": row["students"],
            }
            for row in groups
        ],
    }


def scores_dict(attempt: CareerAttempt) -> list[dict]:
    """Баллы по убыванию с границами возможного — для полосок."""
    limits = bounds(attempt.test)
    rows = []
    for row in attempt.scores.select_related("scale"):
        low, high = limits.get(row.scale_id, (0, 0))
        rows.append(
            {
                "scale": row.scale_id,
                "code": row.scale.code,
                "title": row.scale.title,
                "score": row.score,
                "label": row.label,
                "low": low,
                "high": high,
            }
        )
    rows.sort(key=lambda r: (-r["score"], r["title"]))
    return rows


def attempt_dict(attempt: CareerAttempt, *, with_scores: bool = True, with_student: bool = False) -> dict:
    out = {
        "id": attempt.pk,
        "test": test_brief(attempt.test),
        "status": attempt.status,
        "started_at": attempt.started_at,
        "finished_at": attempt.finished_at,
        "archived_at": attempt.archived_at,
        "threshold": attempt.test.analysis_min_score,
    }
    if with_student:
        out["student"] = student_brief(attempt.student)
    if with_scores and attempt.is_done:
        out["scores"] = scores_dict(attempt)
    return out


def analysis_dict(analysis: CareerAnalysis, *, for_student: bool = False) -> dict:
    out = {
        "id": analysis.pk,
        "status": analysis.status,
        "status_title": analysis.get_status_display(),
        "summary": analysis.summary_student if for_student else analysis.summary,
        "error": analysis.error,
        "created_at": analysis.created_at,
        "finished_at": analysis.finished_at,
        "language": analysis.language,
        "visible_to_student": analysis.visible_to_student,
        "edited_at": analysis.edited_at,
        #: разбор считался по прежним правилам — показывается как есть, с плашкой
        "legacy": analysis.rules < RULES,
        "tests": [
            {"id": a.test_id, "title": a.test.title, "attempt": a.pk, "finished_at": a.finished_at}
            for a in analysis.attempts.select_related("test").order_by("finished_at", "id")
        ],
        #: профиль интересов — по каждой шкале теста; у разборов до 04.11.2026 пуст
        "profile": [
            {
                "id": scale.pk,
                "order": scale.order,
                "test": scale.test_title,
                "title": scale.title,
                "score": scale.score,
                "top": scale.top,
                "label": scale.label,
                "meaning": scale.meaning_student if for_student else scale.meaning,
            }
            for scale in analysis.scales.all()
        ],
        "directions": [
            {
                "id": d.pk,
                "order": d.order,
                "title": d.title,
                "title_abroad": d.title_abroad,
                "reasoning": d.reasoning_student if for_student else d.reasoning,
                "professions": d.professions,
                "exams": d.exams,
                "subjects": d.subjects,
                "next_steps": d.next_steps,
                "programs": [
                    {"id": p.pk, "name": p.name, "university": p.university.name, "level_title": p.get_level_display()}
                    for p in d.programs.select_related("university")
                ],
            }
            for d in analysis.directions.all()
        ],
    }
    if not for_student:
        # версия для ученика — рядом с версией учителя, он правит обе;
        # имена сотрудников ученику не показываются: кто запустил и кто правил — только своим
        out["summary_student"] = analysis.summary_student
        out["has_student_version"] = bool(analysis.summary_student)
        for row, d in zip(out["directions"], analysis.directions.all(), strict=False):
            row["reasoning_student"] = d.reasoning_student
        for row, scale in zip(out["profile"], analysis.scales.all(), strict=False):
            row["meaning_student"] = scale.meaning_student
        out["student"] = student_brief(analysis.student)
        # «Пересчитать» запускает разбор группы ученика по тем же тестам
        out["group_id"] = analysis.student.group_id
        out["created_by"] = person(analysis.created_by)
        out["edited_by"] = person(analysis.edited_by)
    return out
