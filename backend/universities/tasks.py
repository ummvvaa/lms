"""Фоновые задачи справочника вузов."""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone
from django.utils.translation import gettext_noop

from core.i18n import language_of, render

log = logging.getLogger(__name__)


#: Причина, с которой закрывается предложение сверки, когда расхождения
#: больше нет: сайт и справочник сошлись без решения директора
SYNC_RESOLVED_ITSELF = gettext_noop("Устарело: расхождения с сайтом больше нет")


@shared_task(name="universities.sync_deadlines")
def sync_deadlines(*, limit: int = 50) -> dict:
    """Обойти раунды и сложить расхождения в предложения — по одному на вуз.

    Дата сверки пишется в раунд напрямую (`check_round`): это служебная
    отметка, решать в ней нечего. Предложением становится только расхождение
    дедлайна с сайтом. Поле без источника не меняется: каждая строка несёт
    ссылку и фрагмент страницы, по которым директор проверит число.

    Сверка ночная, а решают предложения не каждый день. Раньше нерешённое
    расхождение назавтра ложилось новым предложением — и так каждую ночь
    (D47). Теперь у вуза одно висящее предложение сверки: повторная сверка
    обновляет его строки, а сошедшееся с сайтом закрывает сама.
    """
    from accounts.models import Role, User
    from universities.models import AdmissionRound
    from universities.sync import check_round

    rounds = (
        AdmissionRound.objects.select_related("program__university")
        .exclude(source_url="", program__university__website="")
        .order_by("checked_at")[:limit]
    )

    by_university: dict[int, list[dict]] = {}
    names: dict[int, str] = {}
    agreed: list[int] = []
    checked, failures = 0, []
    for admission_round in rounds:
        result = check_round(admission_round)
        checked += 1
        if not result.get("ok"):
            failures.append({"round": admission_round.pk, "reason": result.get("reason")})
            continue
        if not result.get("found"):
            continue
        if not result.get("changed"):
            agreed.append(admission_round.pk)
            continue

        fact = result["fact"]
        university = admission_round.program.university
        names[university.pk] = university.name
        by_university.setdefault(university.pk, []).append(
            {
                "model": "universities.AdmissionRound",
                "field": "deadline",
                "value": fact["deadline"],
                "object_id": admission_round.pk,
                "confidence": 0.8,
                "source_ref": fact["source_url"],
                "source_quote": fact["quote"],
            }
        )

    # предложение адресовано директору по поступлению — это его домен,
    # и тексты сверки пишутся на его языке
    author = User.objects.filter(role=Role.DIRECTOR_ADMISSION).order_by("pk").first()
    closed = _drop_agreed_rounds(agreed, lang=language_of(author))
    suggestions, changes, rejected = [], 0, []
    for university_id, rows in by_university.items():
        suggestion, refused = _suggestion_of_university(university_id, names[university_id], rows, author=author)
        suggestions.append(suggestion.pk)
        changes += suggestion.changes.count()
        rejected += refused
    return {
        "checked": checked,
        "suggestions": suggestions,
        # одно число для плашки операций: сколько предложений сейчас несут расхождения
        "suggestion": suggestions[0] if suggestions else None,
        "changes": changes,
        "closed": closed,
        "rejected": rejected,
        "failures": failures,
    }


def _pending_sync():
    from suggestions.models import Suggestion, SuggestionSource, SuggestionStatus

    return Suggestion.objects.filter(
        source_type=SuggestionSource.WEB_SYNC, command="sync_deadlines", status=SuggestionStatus.PENDING
    )


def _suggestion_of_university(university_id: int, name: str, rows: list[dict], *, author):
    """Висящее предложение сверки этого вуза — обновить; нет — завести."""
    from accounts.models import Role
    from suggestions.engine import create_suggestion, replace_rows
    from universities.models import AdmissionRound

    round_ids = [
        str(pk)
        for pk in AdmissionRound.objects.filter(program__university_id=university_id).values_list("pk", flat=True)
    ]
    source_ref = render(
        language_of(author), "фоновая сверка {date} · {name}", date=timezone.localdate().isoformat(), name=name
    )
    existing = (
        _pending_sync()
        .filter(changes__model_label="universities.AdmissionRound", changes__object_id__in=round_ids)
        .order_by("created_at")
        .distinct()
        .first()
    )
    if existing is not None:
        return existing, replace_rows(existing, rows, source_ref=source_ref)
    return create_suggestion(
        author=author,
        role=Role.DIRECTOR_ADMISSION,
        domain_code="admission",
        source_type="web_sync",
        command="sync_deadlines",
        rows=rows,
        source_ref=source_ref,
    )


def _drop_agreed_rounds(round_ids: list[int], *, lang: str = "ru") -> int:
    """Раунд сошёлся с сайтом — его строка из висящей сверки уходит.

    Предложение, в котором строк не осталось, закрывается само: решать
    в нём больше нечего.
    """
    from suggestions.models import SuggestionChange, SuggestionStatus

    if not round_ids:
        return 0
    stale = SuggestionChange.objects.filter(
        suggestion__in=_pending_sync(),
        model_label="universities.AdmissionRound",
        object_id__in=[str(pk) for pk in round_ids],
    )
    touched = set(stale.values_list("suggestion_id", flat=True))
    stale.delete()
    emptied = _pending_sync().filter(pk__in=touched, changes__isnull=True)
    return emptied.update(
        status=SuggestionStatus.REJECTED, reject_reason=render(lang, SYNC_RESOLVED_ITSELF), resolved_at=timezone.now()
    )


@shared_task(name="universities.run_match_selection")
def run_match_selection(run_id: int = 0, **kwargs) -> dict:
    """Прогон подбора в фоне: этапы отчитываются через `MatchRun` (фаза 40).

    `run_id` принимается и именованным: повтор из плашки операций зовёт
    задачу по имени с сохранёнными аргументами (фаза 47).
    """
    from universities.selection import execute

    return execute(run_id or kwargs.get("run_id"))
