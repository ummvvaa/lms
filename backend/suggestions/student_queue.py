"""Очередь предложений от учеников у директора (фаза 37).

Сортировка — по расхождению с текущим значением: IELTS 8.5 вместо 6.0
директор должен увидеть первым, а совпадающее с профилем значение
может подождать. Расхождение считается по границам шкалы из реестра,
а не на глаз.
"""

from __future__ import annotations

from pathlib import Path

from core.domains import (
    CURATOR_CONFIRM_DOMAINS,
    DOMAINS,
    ROLE_CURATOR,
    ROLE_STUDENT,
    domains_of_role,
    spec_of_field,
)
from core.labels import field_title
from students.attention import sharp_jump
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


def for_role(rows, role: str, group_ids: list[int] | None = None):
    """Сузить предложения учеников до того, что роль вправе решать.

    Директору — свой домен по всей школе; куратору — домены, где он
    **подтверждает**, и только ученики его групп (фаза 60); администратору —
    всё на чтение. Одна функция на очередь, кабинет и `SuggestionViewSet`:
    два источника той же очереди разошлись бы в первый же месяц.

    Дисциплину куратор с фазы 66 ведёт сам, а не подтверждает, — и в очередь
    она не попадает: очередь про то, что внёс о себе ученик и ждёт решения.
    """
    if role == ROLE_CURATOR:
        return rows.filter(
            domain_code__in=CURATOR_CONFIRM_DOMAINS,
            changes__student__group_id__in=list(group_ids or []),
        ).distinct()
    # у директора по поступлению доменов два — «Поступление» и «Документы»
    # (фаза 60): очередь показывает строки всех доменов роли
    codes = [d.code for d in domains_of_role(role)]
    return rows if not codes else rows.filter(domain_code__in=codes)


def pending_for(role: str, group_ids: list[int] | None = None, *, escalated: bool | None = False) -> list[Suggestion]:
    """Нерешённые предложения учеников для роли: директору — свой домен,
    куратору — его группы в доменах куратора.

    `escalated` — переданные владельцу строки (фаза 62): у куратора они
    уходят из очереди в отдельный блок (`False` — очередь, `True` — блок),
    у владельца остаются в очереди и встают наверх (`None` — все).
    """
    rows = (
        Suggestion.objects.filter(role=ROLE_STUDENT, status=SuggestionStatus.PENDING)
        .prefetch_related("changes__student")
        .select_related("author", "escalated_by")
    )
    if escalated is True:
        rows = rows.filter(escalated_by__isnull=False)
    elif escalated is False:
        rows = rows.filter(escalated_by__isnull=True)
    return list(for_role(rows, role, group_ids))


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


def _document_payload(suggestion: Suggestion) -> dict | None:
    """Документ строки очереди (фаза 62): что за файл и где его открыть."""
    if suggestion.source_type != SuggestionSource.DOCUMENT:
        return None
    from students.documents import document_of

    document = document_of(suggestion)
    if document is None:
        return None
    return {
        "id": document.pk,
        "doc_type": document.doc_type,
        "doc_type_title": document.get_doc_type_display(),
        "file_name": document.title or Path(document.file.name).name,
        "content_type": document.content_type,
        "expires_at": document.expires_at,
        "file_url": f"/api/documents/{document.pk}/file/",
    }


def queue_payload(role: str, group_ids: list[int] | None = None, *, escalated: bool | None = False) -> list[dict]:
    """Строки очереди «От учеников», отсортированные по расхождению.

    Переданные владельцу строки (фаза 62) у владельца стоят первыми:
    куратор уже посмотрел и просит решения — это важнее сортировки
    по расхождению.
    """
    items = []
    for suggestion in pending_for(role, group_ids, escalated=escalated):
        changes = list(suggestion.changes.all())
        gap = max((divergence(c) for c in changes), default=0.0)
        student = next((c.student for c in changes if c.student_id), None)
        items.append(
            {
                "source_type": suggestion.source_type,
                "document": _document_payload(suggestion),
                "escalated": suggestion.escalated_by_id is not None,
                "escalated_by_name": (
                    (suggestion.escalated_by.full_name or suggestion.escalated_by.email)
                    if suggestion.escalated_by_id
                    else ""
                ),
                "escalation_comment": suggestion.escalation_comment,
                "escalated_at": suggestion.escalated_at,
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
                # «резкий скачок» (фаза 61): считает сервер по порогам школы,
                # чтобы у куратора и у владельца домена он значил одно и то же
                "sharp_jump": any(sharp_jump(c.model_label, c.field_name, c.old_value, c.new_value) for c in changes),
                "changes": SuggestionChangeSerializer(changes, many=True).data,
            }
        )
    # сортировка устойчивая: при равном расхождении свежее выше,
    # переданные владельцу — над всеми
    items.sort(key=lambda row: row["created_at"], reverse=True)
    items.sort(key=lambda row: row["divergence"], reverse=True)
    items.sort(key=lambda row: row["escalated"], reverse=True)
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
