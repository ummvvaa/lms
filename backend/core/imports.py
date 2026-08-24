"""История загрузок и отмена импорта целиком.

Механика та же, что у отката предложений: обратный набор изменений через
журнал. Если поле после импорта правили руками, откат его не трогает —
и говорит об этом, а не затирает чужую работу молча.
"""

from __future__ import annotations

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from core.audit import ValueRejected, apply_changes, coerce, to_text
from core.domains import Source
from core.labels import field_title
from core.models import AuditLog, ImportBatch


def _instance_for(entry: AuditLog):
    """Объект, к которому относится запись журнала. Архивный тоже считается."""
    try:
        model = apps.get_model(entry.model_label)
    except (LookupError, ValueError):
        return None
    manager = getattr(model, "all_objects", model._default_manager)
    return manager.filter(pk=entry.object_id).first()


def _title(entry: AuditLog) -> str:
    """Человеческое имя поля из записи журнала — для отчёта об откате."""
    return field_title(entry.model_label, entry.field_name)


@transaction.atomic
def revert_batch(batch: ImportBatch, *, actor=None) -> dict:
    """Вернуть значения, которые поставила эта загрузка.

    Идём от последних изменений к первым: внутри одной загрузки поле
    могло меняться дважды, и возвращать надо к самому раннему «было».
    """
    reverted = 0
    skipped: list[dict] = []

    entries = list(batch.audit_entries.order_by("-created_at", "-id"))
    for entry in entries:
        instance = _instance_for(entry)
        if instance is None:
            skipped.append({"entry": entry.pk, "field_title": _title(entry), "reason": "Запись уже удалена"})
            continue

        current = to_text(getattr(instance, entry.field_name, None))
        if current != entry.new_value:
            shown = current or "пусто"
            skipped.append(
                {
                    "entry": entry.pk,
                    "field_title": _title(entry),
                    "student": entry.student_id,
                    "reason": f"После загрузки поле правили руками: сейчас там «{shown}». Оставили как есть",
                }
            )
            continue

        try:
            value = coerce(instance, entry.field_name, entry.old_value or None)
        except ValueRejected as error:
            skipped.append({"entry": entry.pk, "field_title": _title(entry), "reason": str(error)})
            continue

        apply_changes(instance, {entry.field_name: value}, actor=actor, source=Source.IMPORT)
        reverted += 1

    batch.status = ImportBatch.Status.REVERTED if not skipped else ImportBatch.Status.PARTIAL
    batch.reverted_at = timezone.now()
    batch.reverted_by = actor
    batch.save(update_fields=["status", "reverted_at", "reverted_by"])

    detail = f"Возвращено прежних значений: {reverted}"
    if skipped:
        detail += f". Не тронуто, потому что правили руками после загрузки: {len(skipped)}"
    return {"reverted": reverted, "skipped": skipped, "status": batch.status, "detail": detail}
