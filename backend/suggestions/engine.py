"""Применение и откат предложений.

Применение — одна транзакция:

1. проверить, что старое значение всё ещё актуально; если нет — пометить
   конфликт и пропустить строку, не затирая чужую правку;
2. записать новое значение;
3. создать запись аудита со ссылкой на предложение (инвариант №9).

Откат — обратный набор изменений, тоже через аудит: история не переписывается,
а дополняется.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from core.audit import ValueRejected, apply_changes, coerce, to_text
from core.domains import Source, can_write_for, can_write_shared
from core.labels import field_title, model_title, value_title
from suggestions.models import Suggestion, SuggestionChange, SuggestionStatus


def _instance_for(change: SuggestionChange):
    """Объект, к которому относится строка предложения."""
    model = apps.get_model(change.model_label)
    if change.object_id:
        return model.objects.filter(pk=change.object_id).first()
    if change.student_id:
        return model.objects.filter(student_id=change.student_id).first()
    return None


def refresh_old_values(suggestion: Suggestion) -> None:
    """Подтянуть текущие значения полей — для показа в предпросмотре."""
    for change in suggestion.changes.all():
        instance = _instance_for(change)
        if instance is None:
            continue
        current = to_text(getattr(instance, change.field_name, None))
        if change.old_value != current:
            change.old_value = current
            change.save(update_fields=["old_value"])


def _may_write(suggestion: Suggestion, model_label: str, field_name: str) -> bool:
    """Право на строку: своё поле домена, сквозная модель или — у администратора —
    поле домена, за который создано предложение (фаза 35)."""
    role = suggestion.role
    return can_write_for(role, suggestion.domain_code, model_label, field_name) or can_write_shared(role, model_label)


@transaction.atomic
def _create_new_objects(suggestion: Suggestion, rows: list[SuggestionChange], *, actor) -> tuple[int, list[dict]]:
    """Собрать новые записи из строк предложения.

    Предложение умеет не только править существующее: массовая постановка
    задач и разбор вуза заводят новые строки — и всё равно проходят через
    руку человека (инвариант №3).

    Значение вида «@ключ» — ссылка на запись, которая создаётся в этом же
    предложении: программа ссылается на вуз, требование — на программу.
    Идём кругами, пока получается создать хоть что-то.
    """
    groups: dict[tuple[str, str], list[SuggestionChange]] = {}
    for row in rows:
        groups.setdefault((row.model_label, row.new_object_key), []).append(row)

    created, rejected = 0, []
    made: dict[str, Any] = {}
    pending = list(groups.items())

    while pending:
        progressed = False
        postponed: list = []
        for (model_label, key), group in pending:
            if not all(_may_write(suggestion, model_label, row.field_name) for row in group):
                rejected.append({"change": group[0].pk, "reason": f"«{model_title(model_label)}» ведёт другой домен"})
                progressed = True
                continue
            if any(_is_pending_reference(row.new_value, made) for row in group):
                postponed.append(((model_label, key), group))
                continue

            instance = _create_one(suggestion, model_label, group, made=made, actor=actor)
            if instance is None:
                rejected.append({"change": group[0].pk, "reason": group[0].conflict or "Значение не подошло колонке"})
            else:
                made[key] = instance
                created += len(group)
            progressed = True

        if not progressed:
            for (_label, _key), group in postponed:
                rejected.append({"change": group[0].pk, "reason": "Не на что сослаться: связанная запись не создана"})
            break
        pending = postponed
    return created, rejected


def _is_reference(value) -> bool:
    return isinstance(value, str) and value.startswith("@")


def _is_pending_reference(value, made: dict[str, Any]) -> bool:
    """Ссылка на запись, которую в этом предложении ещё не создали."""
    return _is_reference(value) and value[1:] not in made


def _create_one(suggestion: Suggestion, model_label: str, group, *, made: dict[str, Any], actor):
    """Собрать одну новую запись. Кривое значение отменяет всю запись."""
    model = apps.get_model(model_label)
    instance = model()
    student_id = next((row.student_id for row in group if row.student_id), None)
    if student_id and hasattr(instance, "student_id"):
        instance.student_id = student_id

    values: dict[str, Any] = {}
    for row in group:
        raw = made[row.new_value[1:]] if _is_reference(row.new_value) else (row.new_value or None)
        try:
            values[row.field_name] = coerce(instance, row.field_name, raw)
        except ValueRejected as error:
            row.conflict = str(error)
            row.save(update_fields=["conflict"])
            return None
    if not values:
        return None

    apply_changes(instance, values, actor=actor, source=Source.AI, suggestion=suggestion)
    for row in group:
        row.is_applied = True
        row.object_id = str(instance.pk)
        row.conflict = ""
        row.save(update_fields=["is_applied", "object_id", "conflict"])
    return instance


@transaction.atomic
def apply_suggestion(suggestion: Suggestion, *, actor, change_ids: list[int] | None = None) -> dict:
    """Применить принятые строки предложения.

    `change_ids` — что именно принял человек. Если не передан, применяются
    строки с отметкой `is_accepted`.
    """
    changes = suggestion.changes.all()
    if change_ids is not None:
        changes = changes.filter(pk__in=change_ids)
        SuggestionChange.objects.filter(pk__in=change_ids).update(is_accepted=True)
    else:
        changes = changes.filter(is_accepted=True)

    applied, conflicts, rejected = 0, [], []

    # строки с общим `new_object_key` — это одна новая запись, а не правки
    rows = list(changes.select_related("student"))
    created, rejected_new = _create_new_objects(
        suggestion, [row for row in rows if row.new_object_key and not row.is_applied], actor=actor
    )
    applied += created
    rejected += rejected_new

    for change in [row for row in rows if not row.new_object_key]:
        if change.is_applied:
            continue
        # право проверяем ещё раз на применении: роль автора могла смениться
        if not _may_write(suggestion, change.model_label, change.field_name):
            rejected.append(
                {
                    "change": change.pk,
                    "reason": f"«{field_title(change.model_label, change.field_name)}» ведёт другой директор",
                }
            )
            continue

        instance = _instance_for(change)
        if instance is None:
            rejected.append({"change": change.pk, "reason": "Запись уже удалили — применять некуда"})
            continue

        current = to_text(getattr(instance, change.field_name, None))
        if current != change.old_value:
            # кто-то успел поправить это поле — не затираем
            title = field_title(change.model_label, change.field_name)
            was = value_title(change.model_label, change.field_name, change.old_value) or "пусто"
            now = value_title(change.model_label, change.field_name, current) or "пусто"
            change.conflict = f"«{title}»: ожидали «{was}», а сейчас там «{now}» — кто-то поправил раньше вас"
            change.save(update_fields=["conflict"])
            conflicts.append({"change": change.pk, "expected": change.old_value, "actual": current})
            continue

        try:
            value = coerce(instance, change.field_name, change.new_value or None)
        except ValueRejected as error:
            # модель могла предложить мусор — строка отклоняется, а не роняет применение
            rejected.append({"change": change.pk, "reason": str(error)})
            continue
        apply_changes(
            instance,
            {change.field_name: value},
            actor=actor,
            source=Source.AI if suggestion.source_type != "manual" else Source.MANUAL,
            suggestion=suggestion,
        )
        change.is_applied = True
        change.conflict = ""
        change.save(update_fields=["is_applied", "conflict"])
        applied += 1

    total = suggestion.changes.count()
    done = suggestion.changes.filter(is_applied=True).count()
    suggestion.status = (
        SuggestionStatus.APPLIED
        if done == total and total
        else SuggestionStatus.PARTIALLY_APPLIED if done else suggestion.status
    )
    suggestion.resolved_at = timezone.now()
    suggestion.save(update_fields=["status", "resolved_at"])

    return {
        "applied": applied,
        "conflicts": conflicts,
        "rejected": rejected,
        "status": suggestion.status,
    }


@transaction.atomic
def revert_suggestion(suggestion: Suggestion, *, actor) -> dict:
    """Откатить применённые строки: вернуть прежние значения через аудит."""
    reverted, skipped = 0, []

    for change in suggestion.changes.filter(is_applied=True):
        instance = _instance_for(change)
        if instance is None:
            skipped.append({"change": change.pk, "reason": "Запись уже удалили — откатывать нечего"})
            continue

        current = to_text(getattr(instance, change.field_name, None))
        if current != to_text(change.new_value):
            # поле уже поменяли после применения — откатывать вслепую нельзя
            shown = value_title(change.model_label, change.field_name, current) or "пусто"
            skipped.append(
                {
                    "change": change.pk,
                    "reason": f"«{field_title(change.model_label, change.field_name)}» правили после применения: "
                    f"сейчас там «{shown}». Оставили как есть",
                }
            )
            continue

        try:
            value = coerce(instance, change.field_name, change.old_value or None)
        except ValueRejected as error:
            skipped.append({"change": change.pk, "reason": str(error)})
            continue
        apply_changes(
            instance,
            {change.field_name: value},
            actor=actor,
            source=Source.MANUAL,
            suggestion=suggestion,
        )
        change.is_applied = False
        change.save(update_fields=["is_applied"])
        reverted += 1

    suggestion.status = SuggestionStatus.REVERTED
    suggestion.resolved_at = timezone.now()
    suggestion.save(update_fields=["status", "resolved_at"])
    return {"reverted": reverted, "skipped": skipped, "status": suggestion.status}


def accept_above(suggestion: Suggestion, *, threshold: float, actor) -> dict:
    """«Принять все выше порога» — отдельное явное действие с записью в журнал."""
    ids = list(suggestion.changes.filter(confidence__gte=threshold, is_applied=False).values_list("pk", flat=True))
    result = apply_suggestion(suggestion, actor=actor, change_ids=ids)
    result["threshold"] = threshold
    result["selected"] = len(ids)
    return result


@transaction.atomic
def create_suggestion(
    *,
    author,
    role: str,
    domain_code: str,
    source_type: str,
    rows: list[dict[str, Any]],
    command: str = "",
    source_ref: str = "",
) -> tuple[Suggestion, list[dict]]:
    """Создать предложение, отбросив строки чужого домена.

    Валидация в коде, а не в промпте (инвариант №3): модель может предложить
    что угодно, но чужой домен сюда не попадёт.
    """
    from suggestions.validators import validate_changes

    outcome = validate_changes(rows, role=role, domain_code=domain_code)

    suggestion = Suggestion.objects.create(
        author=author,
        role=role,
        domain_code=domain_code,
        command=command,
        source_type=source_type,
        source_ref=source_ref,
        status=SuggestionStatus.PENDING,
    )

    for row in outcome.accepted:
        model_label = row["model"]
        student_id = row.get("student")
        model = apps.get_model(model_label)

        # объект адресуется либо напрямую (раунд вуза), либо через ученика (профиль)
        instance = None
        if row.get("object_id"):
            instance = model.objects.filter(pk=row["object_id"]).first()
        elif student_id:
            instance = model.objects.filter(student_id=student_id).first()

        SuggestionChange.objects.create(
            suggestion=suggestion,
            student_id=student_id,
            model_label=model_label,
            object_id=str(instance.pk) if instance else "",
            new_object_key=row.get("new_object_key", ""),
            field_name=row["field"],
            old_value=to_text(getattr(instance, row["field"], None)) if instance else "",
            new_value=to_text(row.get("value")),
            confidence=row.get("confidence", 1),
            source_ref=row.get("source_ref", ""),
            source_quote=row.get("source_quote", ""),
        )

    return suggestion, outcome.rejected
