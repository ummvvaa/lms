"""Очередь предложений от учеников у директора (фаза 37).

Сортировка — по расхождению с текущим значением: IELTS 8.5 вместо 6.0
директор должен увидеть первым, а совпадающее с профилем значение
может подождать. Расхождение считается по границам шкалы из реестра,
а не на глаз.
"""

from __future__ import annotations

from core.domains import DOMAINS, ROLE_STUDENT, domain_of_role, spec_of_field
from core.labels import field_title
from suggestions.models import Suggestion, SuggestionSource, SuggestionStatus
from suggestions.serializers import SuggestionChangeSerializer


def _number(text: str) -> float | None:
    try:
        return float(str(text).replace(",", "."))
    except (TypeError, ValueError):
        return None


def divergence(change) -> float:
    """Насколько предложенное расходится с текущим, от 0 до 1.

    Обе стороны числа и у поля есть шкала — доля шкалы между ними.
    Значения просто разные — небольшая константа: расхождение есть,
    но измерить его нечем. Текущее пусто — ноль: новая информация
    ни с чем не расходится и может подождать.
    """
    if not change.old_value:
        return 0.0
    if change.old_value == change.new_value:
        return 0.0
    old, new = _number(change.old_value), _number(change.new_value)
    if old is not None and new is not None:
        spec = spec_of_field(change.model_label, change.field_name)
        if spec and spec.maximum is not None and spec.minimum is not None and spec.maximum > spec.minimum:
            return min(1.0, abs(new - old) / (spec.maximum - spec.minimum))
        return min(1.0, abs(new - old) / max(abs(old), abs(new), 1.0))
    return 0.15


def pending_for(role: str) -> list[Suggestion]:
    """Нерешённые предложения учеников для роли: директору — свой домен."""
    rows = (
        Suggestion.objects.filter(role=ROLE_STUDENT, status=SuggestionStatus.PENDING)
        .prefetch_related("changes__student")
        .select_related("author")
    )
    domain = domain_of_role(role)
    if domain is not None:
        rows = rows.filter(domain_code=domain.code)
    return list(rows)


def kind_of(changes) -> dict:
    """Характер правки для чипа в строке очереди (фаза 49).

    Три случая, и они означают разное: значения не было вовсе, значение
    поправили, значение сильно разошлось с прежним. Считается здесь,
    рядом с расхождением, — чтобы очередь и кабинет говорили одно и то же.
    """
    if all(not change.old_value for change in changes):
        return {"code": "new", "title": "Новое"}
    gap = max((divergence(change) for change in changes), default=0.0)
    if gap >= 0.2:
        return {"code": "gap", "title": "Расхождение"}
    return {"code": "edit", "title": "Правка"}


def queue_payload(role: str) -> list[dict]:
    """Строки очереди «От учеников», отсортированные по расхождению."""
    items = []
    for suggestion in pending_for(role):
        changes = list(suggestion.changes.all())
        gap = max((divergence(c) for c in changes), default=0.0)
        student = next((c.student for c in changes if c.student_id), None)
        items.append(
            {
                "id": suggestion.pk,
                "student": student.pk if student else None,
                "student_name": student.full_name if student else "",
                # класс и группа — в строке очереди: «Сериков Арсен · 11Б»
                "student_group": student.group.code if student and student.group_id else "",
                "domain": suggestion.domain_code,
                "domain_title": DOMAINS[suggestion.domain_code].title if suggestion.domain_code in DOMAINS else "",
                "created_at": suggestion.created_at,
                "divergence": round(gap, 3),
                "kind": kind_of(changes),
                "changes": SuggestionChangeSerializer(changes, many=True).data,
            }
        )
    # сортировка устойчивая: при равном расхождении свежее выше
    items.sort(key=lambda row: row["created_at"], reverse=True)
    items.sort(key=lambda row: row["divergence"], reverse=True)
    return items


def mine_payload(user) -> list[dict]:
    """Предложения самого ученика: что на проверке, что решено и почему.

    По этому списку кабинет ставит пометку «ждёт проверки» и показывает
    причину отклонения с кнопкой «внести заново».
    """
    rows = (
        Suggestion.objects.filter(author=user, source_type=SuggestionSource.STUDENT)
        .prefetch_related("changes")
        .order_by("-created_at")[:100]
    )
    return [
        {
            "id": s.pk,
            "status": s.status,
            "status_title": s.get_status_display(),
            "reject_reason": s.reject_reason,
            "created_at": s.created_at,
            "resolved_at": s.resolved_at,
            # ключи «model» и «field» — служебные: фронт кладёт их обратно
            # в запрос при повторной подаче; человеку показывается field_title
            "changes": [
                {
                    "model": c.model_label,
                    "field": c.field_name,
                    "field_title": field_title(c.model_label, c.field_name),
                    "object_id": c.object_id,
                    "new_object_key": c.new_object_key,
                    "new_value": c.new_value,
                    "is_applied": c.is_applied,
                }
                for c in s.changes.all()
            ],
        }
        for s in rows
    ]
