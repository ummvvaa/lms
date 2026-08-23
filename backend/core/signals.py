"""Страховка инварианта №9: изменения доменных полей мимо `apply_changes`.

Основной путь записи — `core.audit.apply_changes`, он знает актора
и источник. Но поля можно поменять и мимо него: из админки, из shell,
из скрипта. Сигналы ловят такие случаи и всё равно пишут в журнал.

Чтобы не задваивать записи, `apply_changes` помечает объект флагом
`_audit_handled` — сигнал такой save пропускает.
"""

from __future__ import annotations

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db.models.signals import post_init, post_save
from django.dispatch import receiver

from core.actor import get_actor, get_import_batch
from core.audit import model_label, record_change, to_text
from core.domains import Source, all_model_labels

#: Атрибут, в котором храним снимок доменных полей на момент загрузки.
SNAPSHOT_ATTR = "_domain_snapshot"


def _tracked_fields(instance) -> set[str]:
    from core.domains import owned_fields_map

    return set(owned_fields_map().get(model_label(instance), {}))


def _is_tracked(sender) -> bool:
    return model_label(sender) in all_model_labels()


def _snapshot(instance) -> dict[str, str]:
    """Снимок доменных полей объекта.

    Отложенные колонки не трогаем. Объект, загруженный через `only()`
    или `defer()` — так делает сборщик каскадного удаления, — на обращение
    к отложенному полю идёт в базу за самим собой, снова попадает сюда
    и раньше уходил в бесконечную рекурсию.

    Ссылки читаются по `attname` (`university_id`), а не по объекту:
    значение то же самое, а лишнего запроса за связанной записью нет.
    """
    deferred = instance.get_deferred_fields()
    snapshot: dict[str, str] = {}
    for name in _tracked_fields(instance):
        try:
            attname = instance._meta.get_field(name).attname
        except FieldDoesNotExist:
            continue
        if attname in deferred:
            continue
        snapshot[name] = to_text(getattr(instance, attname, None))
    return snapshot


@receiver(post_init)
def remember_state(sender, instance, **kwargs):
    """Снять снимок доменных полей сразу после загрузки объекта."""
    if not _is_tracked(sender):
        return
    setattr(instance, SNAPSHOT_ATTR, _snapshot(instance))


@receiver(post_save)
def log_untracked_change(sender, instance, created, **kwargs):
    """Записать изменения, прошедшие мимо `apply_changes`."""
    if not _is_tracked(sender):
        return
    snapshot = getattr(instance, SNAPSHOT_ATTR, None)
    handled = getattr(instance, "_audit_handled", ())

    if not created and snapshot is not None:
        current = _snapshot(instance)
        for name, old_text in snapshot.items():
            if name in handled or name not in current:
                continue
            new_text = current[name]
            if new_text != old_text:
                record_change(
                    instance=instance,
                    field_name=name,
                    old_value=old_text,
                    new_value=new_text,
                    # правка из админки идёт мимо apply_changes: актора берём
                    # из контекста запроса, иначе журнал анонимен
                    actor=get_actor(),
                    source=Source.IMPORT if get_import_batch() else Source.MANUAL,
                    import_batch=get_import_batch(),
                )

    setattr(instance, SNAPSHOT_ATTR, _snapshot(instance))
    instance._audit_handled = ()


def ready() -> None:
    """Проверить, что все модели реестра действительно существуют."""
    for label in all_model_labels():
        apps.get_model(label)
