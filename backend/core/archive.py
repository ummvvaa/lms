"""Архив: мягкое удаление, человеческое описание последствий и возврат.

Инвариант №13. Удаляем не «Вы уверены?», а «Удалить Ахметову Алию?
У неё 4 вуза, 12 задач и 3 эссе — они тоже уйдут в архив». Поэтому
последствия считаются на сервере по настоящим связям, а не пишутся
руками в текст кнопки.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.apps import apps
from django.db import models, transaction
from django.utils import timezone

from core.archivable import Archivable
from core.audit import model_label
from core.domains import PROFILE_MODELS
from core.models import ArchiveEntry


def is_archivable(model: type[models.Model]) -> bool:
    return isinstance(model, type) and issubclass(model, Archivable)


def resolve_model(label: str) -> type[models.Model] | None:
    """Модель по метке `app_label.ModelName`. Неизвестная метка — None."""
    try:
        return apps.get_model(label)
    except (LookupError, ValueError):
        return None


def manager_of(model: type[models.Model]):
    """Менеджер, видящий всё, включая архивное."""
    return getattr(model, "all_objects", model._default_manager)


def title_of(instance: models.Model) -> str:
    """Человеческое имя записи: то, что увидит человек в диалоге."""
    for attr in ("full_name", "title", "name", "code"):
        value = getattr(instance, attr, None)
        if value:
            return str(value)
    return str(instance)


def kind_of(instance: models.Model) -> str:
    return str(instance._meta.verbose_name)


def _cascade_children(instance: models.Model) -> list[models.Model]:
    """Записи, которые уйдут вместе с этой — на один уровень вниз.

    Берём только каскадные связи: то, что и так исчезло бы при физическом
    удалении. Записи, которые каскад не тронул бы, трогать не наше дело.
    """
    found: list[models.Model] = []
    for relation in instance._meta.related_objects:
        if relation.on_delete is not models.CASCADE:
            continue
        related_model = relation.related_model
        if not is_archivable(related_model):
            continue
        query = {relation.field.name: instance}
        found.extend(manager_of(related_model).filter(**query))
    return found


def collect(instance: models.Model) -> list[models.Model]:
    """Вся ветка: сама запись и всё архивируемое под ней."""
    collected: list[models.Model] = [instance]
    seen: set[tuple[str, Any]] = {(model_label(instance), instance.pk)}
    queue = [instance]
    while queue:
        current = queue.pop()
        for child in _cascade_children(current):
            key = (model_label(child), child.pk)
            if key in seen:
                continue
            seen.add(key)
            collected.append(child)
            queue.append(child)
    return collected


def countable(related: list[models.Model]) -> list[models.Model]:
    """То, что человек считает записями.

    Пять профилей один-к-одному со Student — это части самой карточки,
    а не отдельные вещи. «У неё 4 вуза, 12 задач и 3 эссе» — вот что
    надо сказать; «и ещё пять профилей» только мешает читать.
    """
    return [item for item in related if model_label(item) not in PROFILE_MODELS]


def summarize(related: list[models.Model]) -> tuple[str, list[dict]]:
    """«4 вуза, 12 задач и 3 эссе» плюс те же числа списком."""
    counts: dict[str, int] = {}
    for item in countable(related):
        name = str(item._meta.verbose_name_plural)
        counts[name] = counts.get(name, 0) + 1

    rows = [{"title": name, "count": count} for name, count in sorted(counts.items(), key=lambda x: -x[1])]
    parts = [f"{row['count']} — {row['title'].lower()}" for row in rows]
    if not parts:
        return "", rows
    phrase = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " и " + parts[-1]
    return phrase, rows


def _revive_user(entry: ArchiveEntry) -> int:
    """Учётная запись отключается флагом, а не архивируется.

    Физически её удалять нельзя — на ней висит журнал правок, — поэтому
    «удаление» пользователя это отключение доступа, а возврат из архива
    его включает обратно.
    """
    from accounts.models import User

    return User.objects.filter(pk=entry.object_id, is_active=False).update(is_active=True)


#: Записи, у которых мягкое удаление сделано своим полем, а не общим архивом.
REVIVERS = {"accounts.User": _revive_user}


#: Здесь слово набирают всегда, сколько бы связей ни было: удаление ученика
#: и целой группы слишком дорого, чтобы проходить одним случайным кликом.
ALWAYS_TYPED = {"students.Student", "students.StudyGroup"}


def is_soft(label: str, model: type[models.Model]) -> bool:
    """Мягкое ли удаление у этой модели.

    Кроме общего архива есть записи со своим способом: учётная запись
    отключается флагом, потому что на ней висит журнал правок.
    """
    return is_archivable(model) or label in REVIVERS


def preview(instance: models.Model) -> dict:
    """Текст диалога подтверждения: что уйдёт и что за этим последует."""
    branch = collect(instance)
    related = countable(branch[1:])
    phrase, rows = summarize(related)
    soft = is_soft(model_label(instance), type(instance))

    consequences: list[str] = []
    if related:
        consequences.append(f"Вместе с записью уйдёт связанное: {phrase}")
    if model_label(instance) in REVIVERS:
        consequences.append("Доступ будет отключён, а запись попадёт в архив — оттуда её можно включить обратно")
    elif soft:
        consequences.append("Запись отправится в архив: её можно вернуть оттуда со всеми связями")
    else:
        consequences.append("Запись будет удалена насовсем — у неё нет истории, возвращать нечего")
    consequences.append("Записи журнала изменений останутся на месте")

    return {
        "model": model_label(instance),
        "id": instance.pk,
        "title": title_of(instance),
        "kind": kind_of(instance),
        "soft": soft,
        # без склонения: «Удалить ученик «Ахметова Алия»?» — так по-русски
        # не говорят, а падеж названия модели программно не вывести
        "what": f"Удалить «{title_of(instance)}»?",
        "summary": phrase,
        "related": rows,
        "related_count": len(related),
        "consequences": consequences,
        # слово набирают там, где удаление тянет за собой чужую работу,
        # и всегда — когда сносят ученика или группу
        "confirm_word": ("УДАЛИТЬ" if model_label(instance) in ALWAYS_TYPED or len(related) >= 3 else ""),
    }


@transaction.atomic
def archive(instance: models.Model, *, actor=None) -> ArchiveEntry:
    """Отправить запись и всё, что под ней, в архив."""
    branch = collect(instance)
    # в архив уходит всё, включая профили; в описании их не считаем
    related = countable(branch[1:])
    phrase, _rows = summarize(related)
    batch = uuid.uuid4()
    now = timezone.now()

    entry = ArchiveEntry.objects.create(
        batch=batch,
        model_label=model_label(instance),
        object_id=str(instance.pk),
        title=title_of(instance),
        kind_title=kind_of(instance),
        summary=phrase,
        related_count=len(related),
        actor=actor,
    )

    by_model: dict[type[models.Model], list[Any]] = {}
    for item in branch:
        by_model.setdefault(type(item), []).append(item.pk)
    for model, pks in by_model.items():
        # трогаем только живые: то, что уже лежало в архиве отдельно,
        # не должно перескочить в это удаление и всплыть при возврате
        manager_of(model).filter(pk__in=pks, archived_at__isnull=True).update(archived_at=now, archive_batch=batch)

    return entry


@transaction.atomic
def restore(entry: ArchiveEntry, *, actor=None) -> dict:
    """Вернуть из архива всё, что ушло в составе этого удаления."""
    if entry.is_restored:
        return {"restored": 0, "detail": "Эта запись уже восстановлена"}

    reviver = REVIVERS.get(entry.model_label)
    if reviver is not None:
        restored = reviver(entry)
    else:
        restored = 0
        for model in apps.get_models():
            if not is_archivable(model):
                continue
            restored += manager_of(model).filter(archive_batch=entry.batch).update(archived_at=None, archive_batch=None)

    entry.restored_at = timezone.now()
    entry.restored_by = actor
    entry.save(update_fields=["restored_at", "restored_by"])
    return {
        "restored": restored,
        "detail": f"Восстановлено записей: {restored}. Связи вернулись вместе с ними",
    }


def blockers(instance: models.Model) -> list[str]:
    """Почему запись без истории удалить нельзя — человеческим текстом.

    Справочник удаляется физически, и `PROTECT` тут не ошибка сервера,
    а осмысленный отказ: программу держат списки учеников.
    """
    reasons: list[str] = []
    for relation in instance._meta.related_objects:
        if relation.on_delete is not models.PROTECT:
            continue
        related_model = relation.related_model
        rows = manager_of(related_model).filter(**{relation.field.name: instance})
        count = rows.count()
        if not count:
            continue
        title = f"{related_model._meta.verbose_name_plural}: {count}"
        # архивная ссылка держит запись так же крепко, как живая, но
        # в интерфейсе её не видно — об этом надо сказать прямо
        if is_archivable(related_model):
            hidden = rows.filter(archived_at__isnull=False).count()
            if hidden:
                title += f" (из них в архиве: {hidden})"
        reasons.append(title)
    return reasons
