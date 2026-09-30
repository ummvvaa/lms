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
from django.utils.translation import gettext as _

from core.archivable import Archivable
from core.audit import model_label
from core.domains import PROFILE_MODELS
from core.models import ArchiveEntry
from core.phrasing import listing, tn


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
    return listing(parts), rows


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


#: Слово, которое набирают руками там, где ошибка стоит дорого. Человеку
#: показывается на его языке (`confirm_word`); русское принимается всегда.
CONFIRM_WORD = "УДАЛИТЬ"  # i18n-skip: исходное слово для сравнения, показывается через confirm_word()


def confirm_word() -> str:
    """Слово подтверждения на языке ответа: «УДАЛИТЬ», «ЖОЮ», «DELETE»."""
    return _("УДАЛИТЬ")


def is_confirm_word(typed: str) -> bool:
    """Набрано ли слово подтверждения — на языке человека или по-русски."""
    word = (typed or "").strip().upper()
    return word in {CONFIRM_WORD, confirm_word().upper()}


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
        consequences.append(_("Вместе с записью уйдёт связанное: {related}").format(related=phrase))
    if model_label(instance) in REVIVERS:
        consequences.append(_("Доступ будет отключён, а запись попадёт в архив — оттуда её можно включить обратно"))
    elif soft:
        consequences.append(_("Запись отправится в архив: её можно вернуть оттуда со всеми связями"))
    else:
        consequences.append(_("Запись будет удалена насовсем — у неё нет истории, возвращать нечего"))
    consequences.append(_("Записи журнала изменений останутся на месте"))

    return {
        "model": model_label(instance),
        "id": instance.pk,
        "title": title_of(instance),
        "kind": kind_of(instance),
        "soft": soft,
        # без склонения: «Удалить ученик «Ахметова Алия»?» — так по-русски
        # не говорят, а падеж названия модели программно не вывести
        "what": _("Удалить «{title}»?").format(title=title_of(instance)),
        "summary": phrase,
        "related": rows,
        "related_count": len(related),
        "consequences": consequences,
        # слово набирают там, где удаление тянет за собой чужую работу,
        # и всегда — когда сносят ученика или группу
        "confirm_word": (confirm_word() if model_label(instance) in ALWAYS_TYPED or len(related) >= 3 else ""),
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
        return {"restored": 0, "detail": _("Эта запись уже восстановлена")}

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
        "detail": _("Восстановлено записей: {count}. Связи вернулись вместе с ними").format(count=restored),
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
                title += " " + _("(из них в архиве: {count})").format(count=hidden)
        reasons.append(title)
    return reasons


# --- Полная очистка (фаза 28) ----------------------------------------------


def _mark_audit_purged(items: list[tuple[str, Any, str]], batch: Any = None) -> int:
    """Пометить записи журнала как относящиеся к удалённому насовсем.

    Записи не удаляются никогда: журнал изменений и существует затем,
    чтобы через год можно было понять, кто и что поменял. Но вести
    с них на несуществующую карточку нельзя, а «students.Student#57»
    вместо имени не читается — поэтому имя сохраняем строкой.
    """
    from core.models import AuditLog

    touched = 0
    for label, object_id, title in items:
        touched += AuditLog.objects.filter(model_label=label, object_id=str(object_id)).update(
            object_deleted=True, object_purged=True, object_title=title[:250], archive_batch=batch
        )
    return touched


def _journal_title(instance: models.Model, root: str) -> str:
    """Как запись назовётся в журнале после безвозвратного удаления.

    Своего имени задачи или эссе мало: через год «Собрать рекомендации»
    ничего не скажет, если непонятно, чьи. Имя ученика дописываем, если
    его там ещё нет.
    """
    own = title_of(instance)
    if root and root not in own:
        return f"{own} — {root}"
    return own


def _drop_files(instance: models.Model) -> int:
    """Стереть файлы записи с диска: строка уйдёт, файл остаться не должен."""
    removed = 0
    for field in instance._meta.get_fields():
        if not isinstance(field, models.FileField):
            continue
        value = getattr(instance, field.name, None)
        if not value:
            continue
        try:
            value.storage.delete(value.name)
            removed += 1
        except Exception:  # файла может уже не быть — это не повод падать
            continue
    from core.purge import drop_stored

    return removed + drop_stored(instance)


def primary_of(entry: ArchiveEntry):
    """Сама запись, которую положили в архив. Уже стёрта — None."""
    model = resolve_model(entry.model_label)
    if model is None:
        return None
    return manager_of(model).filter(pk=entry.object_id).first()


def purge_preview(entry: ArchiveEntry) -> dict:
    """Что именно уйдёт навсегда и чего это будет стоить.

    С фазы 67 числа считаются обходом настоящих связей (`core.purge`),
    а не текстом в коде: список последствий, написанный руками, разошёлся
    бы с делом в первый же раз, когда в базе появится новая таблица.
    """
    from core import purge as erasing

    instance = primary_of(entry)
    branch = _branch_of(entry)
    related = countable(branch[1:]) if branch else []
    phrase, rows = summarize(related)

    base = {
        "id": entry.pk,
        "title": entry.title,
        "kind": entry.kind_title,
        "found": len(branch),
        "summary": phrase,
        "related": rows,
        "what": _("Удалить «{title}» навсегда?").format(title=entry.title),
    }

    if instance is None:
        # записи уже нет: считать нечего, но сказать об этом надо честно.
        # `consequences` здесь обязателен, как и везде: без него окно
        # подтверждения падало на `.map` и вместо вопроса показывало ошибку (фаза 81)
        warning = _("Самой записи в базе уже нет — уйдёт только строка архива")
        return {
            **base,
            "kept": [],
            "erased": [],
            "impact": [],
            "email": "",
            "confirm": {"kind": "word", "value": confirm_word(), "email": ""},
            "warning": warning,
            "consequences": [warning, _("Записи журнала останутся на месте")],
        }

    numbers = erasing.preview(instance)
    email = numbers["email"]

    # человеческие строки последствий — из тех же чисел, что и списки:
    # два источника одного и того же разошлись бы в первую же правку
    consequences = [numbers["warning"]]
    if numbers["files"]:
        size = erasing.megabytes(numbers["bytes"])
        consequences.append(
            _("С диска удалятся файлы: {count} ({size})").format(count=numbers["files"], size=size)
            if size
            else _("С диска удалятся файлы: {count}").format(count=numbers["files"])
        )
    kept = sum(row["count"] for row in numbers["kept"])
    if kept:
        consequences.append(
            _("Записи журнала останутся ({count}): автор в них станет текстом — имя, почта и дата удаления").format(
                count=kept
            )
        )
    else:
        consequences.append(_("Записи журнала останутся и будут помечены именем «{title}»").format(title=entry.title))

    return {
        "consequences": consequences,
        **base,
        **numbers,
        # подтверждение осмысленным вводом: где у записи есть почта, набирают
        # её — так видно, кого именно стирают; где почты нет, остаётся слово
        "confirm": {
            "kind": "email" if email else "word",
            "value": email or confirm_word(),
            "email": email,
        },
    }


def _branch_of(entry: ArchiveEntry) -> list[models.Model]:
    """Записи этого удаления — по номеру партии, включая архивные."""
    model = resolve_model(entry.model_label)
    if model is None or not is_archivable(model):
        return []
    found: list[models.Model] = []
    for candidate in apps.get_models():
        if not is_archivable(candidate):
            continue
        found.extend(manager_of(candidate).filter(archive_batch=entry.batch))
    return found


@transaction.atomic
def purge(entry: ArchiveEntry, *, actor=None) -> dict:
    """Стереть из базы то, что лежало в архиве этим удалением.

    Записи журнала остаются: инвариант №13 запрещает не удаление как
    таковое, а потерю истории. Поэтому перед удалением мы забираем имена
    и раскладываем их по записям журнала.
    """
    if entry.is_purged:
        return {"purged": 0, "detail": _("Эта запись уже удалена навсегда")}
    if entry.is_restored:
        return {"purged": 0, "detail": _("Запись восстановлена — удалять из архива нечего")}

    from core import purge as erasing

    # с фазы 67 стирает общий код (`core.purge`): он же считает предпросмотр,
    # он же снимает автора текстовым следом, им же пользуется чистка
    # вымышленных. Учётная запись больше не исключение — журнал переживает
    # её удаление, потому что автор в нём перестаёт быть ссылкой
    instance = primary_of(entry)
    signed: dict[str, int] = {}
    removed = 0
    files = 0
    marked = 0

    if instance is not None:
        outcome = erasing.erase(instance, actor=actor, batch=entry.batch)
        removed += outcome["erased"]
        files += outcome["files"]
        marked += outcome["audit_marked"]
        signed = outcome["signed"]

    # то, что лежало в этой же партии, но каскадом не ушло: своё удаление
    # у каждой строки, и порядок здесь не важен — связей между ними нет
    leftovers = _branch_of(entry)
    if leftovers:
        names = [(model_label(item), item.pk, _journal_title(item, entry.title)) for item in leftovers]
        files += sum(_drop_files(item) for item in leftovers)
        for item in leftovers:
            try:
                item.delete()
            except models.ProtectedError:
                # на запись ссылается что-то живое: снести её молча нельзя
                continue
            removed += 1
        marked += _mark_audit_purged(names, entry.batch)

    entry.purged_at = timezone.now()
    entry.purged_by = actor
    entry.save(update_fields=["purged_at", "purged_by"])

    return {
        "purged": removed,
        "files": files,
        "audit_marked": marked,
        "signed": signed,
        "detail": _purge_detail(removed=removed, files=files, marked=marked, title=entry.title, signed=signed),
    }


def _purge_detail(*, removed: int, files: int, marked: int, title: str, signed: dict) -> str:
    """Итог стирания одной фразой: файлы и подписи — только если они были."""
    params = {"removed": removed, "files": files, "marked": marked, "title": title, "signed": sum(signed.values())}
    if files and signed:
        text = _(
            "Удалено навсегда записей: {removed}, файлов: {files}. Записи журнала остались ({marked})"
            " и помечены именем «{title}», подписано именем автора: {signed}"
        )
    elif files:
        text = _(
            "Удалено навсегда записей: {removed}, файлов: {files}. Записи журнала остались ({marked})"
            " и помечены именем «{title}»"
        )
    elif signed:
        text = _(
            "Удалено навсегда записей: {removed}. Записи журнала остались ({marked})"
            " и помечены именем «{title}», подписано именем автора: {signed}"
        )
    else:
        text = _("Удалено навсегда записей: {removed}. Записи журнала остались ({marked}) и помечены именем «{title}»")
    return text.format(**params)


def purge_batch_preview(*, older_than_days: int) -> dict:
    """Массовая очистка: сколько записей уйдёт и каких видов."""
    edge = timezone.now() - timezone.timedelta(days=older_than_days)
    rows = ArchiveEntry.objects.filter(created_at__lt=edge, restored_at__isnull=True, purged_at__isnull=True).exclude(
        model_label__in=REVIVERS
    )
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row.kind_title or row.model_label] = kinds.get(row.kind_title or row.model_label, 0) + 1
    return {
        "older_than_days": older_than_days,
        "entries": rows.count(),
        "kinds": [{"title": name, "count": count} for name, count in sorted(kinds.items(), key=lambda x: -x[1])],
        "what": tn(
            older_than_days,
            "Очистить архив старше {n} дня?|Очистить архив старше {n} дней?|Очистить архив старше {n} дней?",
        ),
        "consequences": [
            _("Записи будут стёрты из базы — восстановить их будет нельзя"),
            _("Учётные записи в очистку не попадают: на них висит журнал правок"),
            _("Записи журнала изменений останутся и будут помечены"),
        ],
        "confirm_word": confirm_word(),
    }


@transaction.atomic
def purge_batch(*, older_than_days: int, actor=None) -> dict:
    """Вычистить архив старше указанного срока."""
    edge = timezone.now() - timezone.timedelta(days=older_than_days)
    rows = list(
        ArchiveEntry.objects.filter(created_at__lt=edge, restored_at__isnull=True, purged_at__isnull=True).exclude(
            model_label__in=REVIVERS
        )
    )
    purged, records, files = 0, 0, 0
    for entry in rows:
        result = purge(entry, actor=actor)
        if result["purged"] or entry.is_purged:
            purged += 1
        records += result.get("purged", 0)
        files += result.get("files", 0)
    return {
        "entries": purged,
        "purged": records,
        "files": files,
        "detail": (
            _(
                "Очищено удалений: {entries}, записей стёрто: {records}, файлов: {files}. "
                "Журнал изменений остался на месте"
            )
            if files
            else _("Очищено удалений: {entries}, записей стёрто: {records}. Журнал изменений остался на месте")
        ).format(entries=purged, records=records, files=files),
    }
