"""Запись куратора перекрывает висящее предложение ученика.

Куратор вносит данные ученика своих групп напрямую, без очереди. Если по тому
же полю у ученика уже ждёт решения предложение, побеждает запись куратора:
строка очереди закрывается статусом «перекрыто записью куратора», и ученик
видит у себя «куратор внёс значение X». Это не отклонение — причины нет,
просто внесли за него. Обратный порядок — куратор внёс, ученик после этого
предлагает другое — работает как обычно: новая строка в очереди.

Что считается «тем же полем»:

* у профиля и у существующей записи — тот же объект и то же поле;
* у новой попытки — тот же экзамен и та же дата; у новой цели — тот же
  экзамен. Предложенная запись перекрывается целиком, всеми своими строками;
* активности и соревнования не перекрываются: одинаковых двух не бывает,
  и что делать с предложенной, куратор решает сам в очереди.

В одном предложении ученика бывает несколько полей. Перекрытые строки
выносятся в отдельное закрытое предложение, остальные остаются ждать
решения как были — очереди и применению про перекрытие знать не нужно.
"""

from __future__ import annotations

from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.utils import timezone

from core.audit import model_label, student_id_of, to_text
from core.domains import ROLE_CURATOR, ROLE_STUDENT
from suggestions.models import Suggestion, SuggestionChange, SuggestionSource, SuggestionStatus

#: у новой записи «то же самое» определяют эти поля
NEW_ROW_KEYS: dict[str, tuple[str, ...]] = {
    "students.ExamAttempt": ("exam_type", "date"),
    "students.ExamGoal": ("exam",),
}


def _pending_changes(student_id: int, label: str):
    return SuggestionChange.objects.filter(
        suggestion__role=ROLE_STUDENT,
        suggestion__source_type=SuggestionSource.STUDENT,
        suggestion__status=SuggestionStatus.PENDING,
        student_id=student_id,
        model_label=label,
    ).select_related("suggestion")


@transaction.atomic
def _close(changes: list[SuggestionChange], values: dict[int, str]) -> int:
    """Закрыть строки как перекрытые; остальное предложение не трогать."""
    by_suggestion: dict[int, list[SuggestionChange]] = {}
    for change in changes:
        by_suggestion.setdefault(change.suggestion_id, []).append(change)

    now = timezone.now()
    for rows in by_suggestion.values():
        suggestion = rows[0].suggestion
        ids = [row.pk for row in rows]
        for row in rows:
            row.superseded_value = values.get(row.pk, "")
            row.save(update_fields=["superseded_value"])
        target = suggestion
        if suggestion.changes.exclude(pk__in=ids).exists():
            # в предложении остаются живые строки: перекрытые уезжают в своё
            target = Suggestion.objects.create(
                author=suggestion.author,
                role=suggestion.role,
                domain_code=suggestion.domain_code,
                source_type=suggestion.source_type,
                status=SuggestionStatus.PENDING,
            )
            SuggestionChange.objects.filter(pk__in=ids).update(suggestion=target)
        target.status = SuggestionStatus.SUPERSEDED
        target.resolved_at = now
        target.save(update_fields=["status", "resolved_at"])
    return len(changes)


def by_field(instance, field_name: str, new_value, *, actor) -> int:
    """Куратор записал поле существующего объекта — закрыть предложения по нему."""
    if getattr(actor, "role", "") != ROLE_CURATOR:
        return 0
    student_id = student_id_of(instance)
    if student_id is None:
        return 0
    rows = list(
        _pending_changes(student_id, model_label(instance)).filter(
            field_name=field_name, object_id=str(instance.pk), new_object_key=""
        )
    )
    if not rows:
        return 0
    text = to_text(new_value)
    return _close(rows, {row.pk: text for row in rows})


def by_new_row(instance, *, actor) -> int:
    """Куратор завёл запись — закрыть предложенные учеником такие же.

    «Такая же» — по ключам `NEW_ROW_KEYS`. Предложенная запись закрывается
    целиком: её строки объединены `new_object_key` внутри одного предложения.
    """
    if getattr(actor, "role", "") != ROLE_CURATOR:
        return 0
    label = model_label(instance)
    keys = NEW_ROW_KEYS.get(label)
    student_id = student_id_of(instance)
    if not keys or student_id is None:
        return 0

    proposed: dict[tuple[int, str], list[SuggestionChange]] = {}
    for change in _pending_changes(student_id, label).exclude(new_object_key=""):
        proposed.setdefault((change.suggestion_id, change.new_object_key), []).append(change)

    def same(rows: list[SuggestionChange]) -> bool:
        offered = {row.field_name: row.new_value for row in rows}
        for key in keys:
            attname = instance._meta.get_field(key).attname
            if offered.get(key, "") != to_text(getattr(instance, attname, None)):
                return False
        return True

    closing = [row for rows in proposed.values() if same(rows) for row in rows]
    if not closing:
        return 0
    values = {}
    for row in closing:
        try:
            attname = instance._meta.get_field(row.field_name).attname
        except FieldDoesNotExist:
            # поля в модели может не быть — строку всё равно закрываем
            attname = row.field_name
        values[row.pk] = to_text(getattr(instance, attname, None))
    return _close(closing, values)
