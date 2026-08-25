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


#: Модели, у которых загрузка заводит новые строки, а не правит готовые.
#: Их откат убирает в архив целиком: обнулённая по полям строка — это
#: мусор, который человек потом не отличит от настоящей записи.
CREATED_BY_IMPORT = ("students.ParentContact", "students.Competition")


def _created_by(batch: ImportBatch, label: str, object_id: str) -> bool:
    """Запись появилась в этой загрузке, а не была правлена ею.

    Признак: самая первая строка журнала по объекту принадлежит этой
    загрузке и говорит «было пусто». Правку существующей записи такой
    проверкой не спутать — у неё первая строка старше загрузки.
    """
    first = AuditLog.objects.filter(model_label=label, object_id=object_id).order_by("created_at", "id").first()
    return first is not None and first.import_batch_id == batch.pk and first.old_value == ""


def _remove_created(batch: ImportBatch, *, actor=None) -> tuple[set[tuple[str, str]], int]:
    """Убрать в архив записи, которые завела эта загрузка."""
    from core.archive import archive

    handled: set[tuple[str, str]] = set()
    removed = 0
    for label in CREATED_BY_IMPORT:
        ids = set(batch.audit_entries.filter(model_label=label).values_list("object_id", flat=True))
        for object_id in ids:
            if not _created_by(batch, label, object_id):
                continue
            handled.add((label, str(object_id)))
            model = apps.get_model(label)
            instance = getattr(model, "all_objects", model._default_manager).filter(pk=object_id).first()
            if instance is None or getattr(instance, "archived_at", None) is not None:
                continue
            archive(instance, actor=actor)
            removed += 1
    return handled, removed


@transaction.atomic
def revert_batch(batch: ImportBatch, *, actor=None) -> dict:
    """Вернуть значения, которые поставила эта загрузка.

    Идём от последних изменений к первым: внутри одной загрузки поле
    могло меняться дважды, и возвращать надо к самому раннему «было».
    """
    reverted = 0
    skipped: list[dict] = []

    # то, что загрузка завела с нуля, убираем целиком — по полям такую
    # строку не откатить: до загрузки её просто не было
    handled, removed = _remove_created(batch, actor=actor)

    entries = list(batch.audit_entries.order_by("-created_at", "-id"))
    for entry in entries:
        if (entry.model_label, str(entry.object_id)) in handled:
            continue
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
    if removed:
        detail += f". Убрано в архив записей, заведённых этой загрузкой: {removed}"
    if skipped:
        detail += f". Не тронуто, потому что правили руками после загрузки: {len(skipped)}"
    return {
        "reverted": reverted,
        "removed": removed,
        "skipped": skipped,
        "status": batch.status,
        "detail": detail,
    }
