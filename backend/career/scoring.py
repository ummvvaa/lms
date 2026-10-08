"""Подсчёт баллов по ключу теста: код, а не модель.

Балл шкалы — сумма баллов ответов её вопросов со знаком вопроса; у вопроса
со своими вариантами балл и шкалу даёт выбранный вариант. Подпись —
по диапазонам интерпретации теста: сначала диапазон самой шкалы, потом общий.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from career.models import AttemptStatus, CareerAttempt, CareerAttemptScore, CareerRange, CareerTest


def label_for(ranges: list[CareerRange], scale_id: int, score: int) -> str:
    """Подпись балла: диапазон шкалы важнее общего; нет подходящего — пусто."""
    own = [r for r in ranges if r.scale_id == scale_id and r.low <= score <= r.high]
    if own:
        return own[0].label
    common = [r for r in ranges if r.scale_id is None and r.low <= score <= r.high]
    return common[0].label if common else ""


def compute(attempt: CareerAttempt) -> dict[int, int]:
    """Баллы по шкалам по сохранённым ответам: id шкалы → балл."""
    test: CareerTest = attempt.test
    totals: dict[int, int] = {scale.pk: 0 for scale in test.scales.all()}
    items = {item.pk: item for item in test.items.all()}
    answers = attempt.answers.select_related("option", "choice")
    for answer in answers:
        item = items.get(answer.item_id)
        if item is None:
            continue
        if answer.choice_id and answer.choice is not None:
            scale_id = answer.choice.scale_id or item.scale_id
            if scale_id in totals:
                totals[scale_id] += answer.choice.value
        elif answer.option_id and answer.option is not None and item.scale_id in totals:
            totals[item.scale_id] += answer.option.value * (item.sign or 1)
    return totals


def unanswered(attempt: CareerAttempt) -> int:
    """Сколько вопросов без ответа."""
    total = attempt.test.items.count()
    answered = attempt.answers.count()
    return max(0, total - answered)


@transaction.atomic
def finish(attempt: CareerAttempt) -> list[CareerAttemptScore]:
    """Закрыть попытку: посчитать баллы, разложить строками, пометить сданной."""
    totals = compute(attempt)
    ranges = list(attempt.test.ranges.all())
    attempt.scores.all().delete()
    rows = [
        CareerAttemptScore(attempt=attempt, scale_id=scale_id, score=score, label=label_for(ranges, scale_id, score))
        for scale_id, score in totals.items()
    ]
    CareerAttemptScore.objects.bulk_create(rows)
    attempt.status = AttemptStatus.DONE
    attempt.finished_at = timezone.now()
    attempt.save(update_fields=["status", "finished_at"])
    return rows


def bounds(test: CareerTest) -> dict[int, tuple[int, int]]:
    """Наименьший и наибольший возможный балл каждой шкалы — для полосок."""
    options = [o.value for o in test.options.all()]
    lo_opt, hi_opt = (min(options), max(options)) if options else (0, 0)
    out: dict[int, list[int]] = {scale.pk: [0, 0] for scale in test.scales.all()}
    for item in test.items.prefetch_related("choices"):
        choices = list(item.choices.all())
        if choices:
            # у вопроса с вариантами выбирается один: каждая шкала может получить
            # свой наибольший и свой наименьший вариант, а может не получить ничего
            per_scale: dict[int, list[int]] = {}
            for choice in choices:
                per_scale.setdefault(choice.scale_id, []).append(choice.value)
            for scale_id, values in per_scale.items():
                if scale_id in out:
                    out[scale_id][0] += min(0, min(values))
                    out[scale_id][1] += max(0, max(values))
            continue
        if item.scale_id not in out:
            continue
        a, b = lo_opt * (item.sign or 1), hi_opt * (item.sign or 1)
        out[item.scale_id][0] += min(a, b)
        out[item.scale_id][1] += max(a, b)
    return {k: (v[0], v[1]) for k, v in out.items()}
