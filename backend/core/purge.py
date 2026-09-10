"""Удаление навсегда: текстовый след автора, предпросмотр по связям, стирание.

До фазы 67 учётную запись нельзя было стереть совсем: на ней висит журнал
правок, и удаление оставило бы историю без автора. Решение владельца:
удаление возможно, но с полным показом последствий — и **журнал не теряет
ни одной строки**.

Как это устроено. Перед удалением автор в записях, где важно «кто»,
заменяется текстовым следом: имя, почта и дата удаления одной строкой
прямо в записи. Ссылка на учётную запись исчезает, подпись остаётся —
и «подтвердил Кымбат» через год читается так же, как читалось вчера.

Что удаляется физически: сама запись и всё, что на неё каскадно
ссылается. Для ученика это карточка, документы с файлами, попытки,
пароли, заметки, посещаемость, замечания. Считаем это не текстом
в коде, а обходом настоящих связей (`Collector` из Django) — тем же
механизмом, каким удаляет сама база. Иначе список последствий разойдётся
с делом в первый же раз, когда кто-нибудь добавит таблицу.

Мягкое удаление не отменяется: архив остаётся первым шагом, «навсегда» —
вторым, из архива. Здесь только второй шаг.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.db import models, transaction
from django.utils import timezone

from core.audit import model_label
from core.domains import PROFILE_MODELS
from core.phrasing import counted

#: Где след автора важен: «кто подтвердил», «кто записал», «кто загрузил».
#: Пары «поле-ссылка → поле-след». Список один на систему: снимок автора,
#: разложенный по вьюхам, разошёлся бы с делом в первую же фазу.
#:
#: Всё, чего здесь нет, обнуляется обычным `SET_NULL` — там имя человека
#: не показывается, и хранить его незачем.
AUTHOR_TRAILS: tuple[tuple[str, str, str], ...] = (
    ("core.AuditLog", "actor", "actor_title"),
    ("students.CuratorNote", "author", "author_title"),
    ("students.BehaviorRemark", "author", "author_title"),
    ("students.MockImport", "uploaded_by", "uploaded_by_title"),
    ("suggestions.Suggestion", "resolved_by", "resolved_by_title"),
    ("roadmap.Task", "author", "author_title"),
)

#: Профили один-к-одному — части карточки, а не отдельные вещи: в списке
#: последствий они только мешают читать (то же правило, что в архиве).


def trail(user) -> str:
    """След удалённого автора: имя, почта и дата удаления одной строкой."""
    name = (getattr(user, "full_name", "") or "").strip()
    email = (getattr(user, "email", "") or "").strip()
    who = f"{name} · {email}" if name and email else (name or email or "без имени")
    return f"{who} · удалён {timezone.localdate():%d.%m.%Y}"[:250]


def detach_author(user) -> dict[str, int]:
    """Заменить ссылки на автора текстовым следом. Возвращает, сколько где.

    Заполняем только пустые следы: если запись уже подписана (так делает
    чистка одноразовых записей прогона), переписывать её нечем и незачем.
    """
    mark = trail(user)
    out: dict[str, int] = {}
    for label, link, title_field in AUTHOR_TRAILS:
        model = _model(label)
        if model is None:
            continue
        count = model._base_manager.filter(**{f"{link}_id": user.pk, title_field: ""}).update(**{title_field: mark})
        if count:
            out[str(model._meta.verbose_name_plural)] = count
    return out


def _model(label: str) -> type[models.Model] | None:
    try:
        return apps.get_model(label)
    except (LookupError, ValueError):
        return None


# --- Предпросмотр -------------------------------------------------------------


def collect(instance: models.Model) -> dict[type[models.Model], list[models.Model]]:
    """Что база снесёт вместе с этой записью — её же обходом связей.

    Смотреть только в `collector.data` нельзя: то, что Django умеет снести
    одним запросом, он кладёт отдельно, в `fast_deletes`, — а это как раз
    попытки, документы и пароли, ради которых предпросмотр и затевался.
    Пропусти их — и модалка пообещает удалить меньше, чем удалит.
    """
    from django.db.models.deletion import Collector

    collector = Collector(using=instance._state.db)
    collector.collect([instance])

    out: dict[type[models.Model], list[models.Model]] = {}
    for model, rows in collector.data.items():
        out.setdefault(model, []).extend(rows)
    for queryset in collector.fast_deletes:
        rows = list(queryset)
        if rows:
            out.setdefault(type(rows[0]), []).extend(rows)
    return out


def _files_of(rows: list[models.Model]) -> tuple[int, int]:
    """Сколько файлов и сколько байт уйдёт с диска."""
    count = 0
    size = 0
    for row in rows:
        for field in row._meta.get_fields():
            if not isinstance(field, models.FileField):
                continue
            value = getattr(row, field.name, None)
            if not value:
                continue
            count += 1
            try:
                size += value.size
            except Exception:  # файла может уже не быть — на счёт это не влияет
                continue
    return count, size


def megabytes(size: int) -> str:
    """Байты человеку: «0,4 МБ». Ноль — пусто, показывать нечего."""
    if size <= 0:
        return ""
    return f"{size / 1024 / 1024:.1f}".replace(".", ",") + " МБ"


def preview(instance: models.Model, *, actor=None) -> dict:
    """Что будет потеряно — числами по настоящим связям.

    Ничего не меняет. Отдаёт три части: что переживёт удаление текстовым
    следом, что исчезнет совсем, и на что это повлияет у соседей.
    """
    data = collect(instance)
    label = model_label(instance)

    kept: list[dict] = []
    erased: list[dict] = []
    files_total = 0
    bytes_total = 0

    for model, rows in data.items():
        model_name = f"{model._meta.app_label}.{model.__name__}"
        if model_name in PROFILE_MODELS:
            continue
        count, size = _files_of(rows)
        files_total += count
        bytes_total += size
        # сама удаляемая запись в списке «что исчезнет» не повторяется
        rows_count = len(rows) - (1 if model_name == label else 0)
        if rows_count > 0:
            erased.append({"title": str(model._meta.verbose_name_plural), "count": rows_count})

    erased.sort(key=lambda row: -row["count"])

    if files_total:
        erased.append({"title": "Файлы на диске", "count": files_total, "note": megabytes(bytes_total)})

    # журнал: строки не теряются ни в одном случае. У учётной записи автор
    # в них становится текстом, у остальных записей остаётся имя объекта —
    # и то и другое человеку надо видеть до того, как он подтвердит
    if label == "accounts.User":
        for title, count in _journal_counts(instance).items():
            kept.append({"title": title, "count": count})
    about = _journal_about(data)
    if about:
        kept.append({"title": "Записи журнала об этой записи", "count": about})

    return {
        "title": _title_of(instance),
        "kind": str(instance._meta.verbose_name),
        "email": (getattr(instance, "email", "") or "").strip(),
        "kept": kept,
        "erased": erased,
        "impact": impact(instance, data),
        "files": files_total,
        "bytes": bytes_total,
        "warning": (
            "Восстановить будет нельзя — ни из архива, ни отменой. "
            "Вернуть эти данные можно только из резервной копии базы"
        ),
    }


def _journal_about(data: dict[type[models.Model], list[models.Model]]) -> int:
    """Сколько строк журнала рассказывают о том, что удаляется.

    Они переживут удаление и сохранят имя: журнал не должен ссылаться
    в пустоту, но и исчезать вместе с объектом ему нельзя (инвариант №13).
    """
    from core.models import AuditLog

    total = 0
    for model, rows in data.items():
        label = f"{model._meta.app_label}.{model.__name__}"
        ids = [str(row.pk) for row in rows]
        if ids:
            total += AuditLog.objects.filter(model_label=label, object_id__in=ids).count()
    return total


def _journal_counts(user) -> dict[str, int]:
    """Сколько записей переживёт удаление, перейдя на текстовый след."""
    out: dict[str, int] = {}
    for label, link, _title in AUTHOR_TRAILS:
        model = _model(label)
        if model is None:
            continue
        count = model._base_manager.filter(**{f"{link}_id": user.pk}).count()
        if count:
            name = str(model._meta.verbose_name_plural)
            out[name] = out.get(name, 0) + count
    return out


def _title_of(instance: models.Model) -> str:
    for attr in ("full_name", "title", "name", "code", "email"):
        value = getattr(instance, attr, None)
        if value:
            return str(value)
    return str(instance)


def impact(instance: models.Model, data: dict | None = None) -> list[str]:
    """На что удаление повлияет у соседей — словами и числами.

    Не «данные будут потеряны», а «в группе CHICAGO станет 19 учеников»:
    последствие видно тому, кто завтра откроет эту группу.
    """
    label = model_label(instance)
    lines: list[str] = []

    if label == "accounts.User":
        student = getattr(instance, "student", None)
        if student is not None:
            lines.append(f"Ученик {student.full_name} останется без входа в систему")
        lines += _curator_impact(instance)
        return lines

    if label == "students.Student":
        lines += _student_impact(instance)
    return lines


def _curator_impact(user) -> list[str]:
    """Группы, которые человек ведёт сегодня, останутся без куратора."""
    from accounts.curators import curated_group_ids
    from students.models import StudyGroup

    ids = curated_group_ids(user)
    if not ids:
        return []
    codes = list(StudyGroup.objects.filter(pk__in=ids).values_list("code", flat=True))
    return [f"Группа {code} останется без куратора" for code in codes]


def _student_impact(student) -> list[str]:
    """Группа, пробники и очередь: где число станет меньше."""
    from students.models import ExamAttempt, Student

    lines: list[str] = []
    if student.group_id:
        left = Student.objects.filter(group_id=student.group_id).exclude(pk=student.pk).count()
        # склонение — с сервера: «станет 1 учеников» читается как сбой
        lines.append(f"В группе {student.group.code} станет {counted(left, ('ученик', 'ученика', 'учеников'))}")

    seen: set[int] = set()
    for attempt in ExamAttempt.all_objects.filter(student=student, mock_import__isnull=False).select_related(
        "mock_import"
    ):
        record = attempt.mock_import
        if record.pk in seen:
            continue
        seen.add(record.pk)
        total = ExamAttempt.all_objects.filter(mock_import=record).count()
        left = counted(total - 1, ("результат", "результата", "результатов"))
        lines.append(f"У пробника от {record.date:%d.%m.%Y} останется {left} из {total}")
    return lines


# --- Само удаление -------------------------------------------------------------


def drop_files(rows: list[models.Model]) -> int:
    """Стереть файлы записей с диска: строка уйдёт, файл остаться не должен."""
    removed = 0
    for row in rows:
        for field in row._meta.get_fields():
            if not isinstance(field, models.FileField):
                continue
            value = getattr(row, field.name, None)
            if not value:
                continue
            try:
                value.storage.delete(value.name)
                removed += 1
            except Exception:  # файла может уже не быть — это не повод падать
                continue
    return removed


@transaction.atomic
def erase(instance: models.Model, *, actor=None, batch=None) -> dict:
    """Стереть запись навсегда, сохранив журнал.

    Порядок важен: сначала след автора, потом файлы, потом сама запись.
    Иначе `SET_NULL` обнулит ссылку раньше, чем мы успеем снять имя,
    и подпись в журнале потеряется молча.

    `batch` — номер удаления из архива: им помечаются записи журнала,
    и по нему экран архива показывает историю того, чего уже нет.
    """
    label = model_label(instance)
    numbers = preview(instance)
    signed: dict[str, int] = {}

    if label == "accounts.User":
        signed = detach_author(instance)

    data = collect(instance)
    files = drop_files([row for rows in data.values() for row in rows])
    names = [(model_label(row), row.pk, _title_of(row)) for rows in data.values() for row in rows]

    instance.delete()

    marked = _mark_audit_deleted(names, batch=batch)
    _record_erasure(numbers, actor=actor, signed=signed, files=files)

    return {
        "erased": sum(len(rows) for rows in data.values()),
        "signed": signed,
        "files": files,
        "audit_marked": marked,
        "detail": _detail(numbers, signed, files),
    }


def _detail(numbers: dict, signed: dict[str, int], files: int) -> str:
    parts = [f"«{numbers['title']}» удалён навсегда"]
    total = sum(row["count"] for row in numbers["erased"] if row["title"] != "Файлы на диске")
    if total:
        parts.append(f"вместе с записями: {total}")
    if files:
        parts.append(f"файлов удалено: {files}")
    kept = sum(signed.values())
    if kept:
        parts.append(f"строк журнала подписано именем: {kept}")
    return ". ".join(parts)


def _mark_audit_deleted(names: list[tuple[str, Any, str]], *, batch=None) -> int:
    """Пометить записи журнала как относящиеся к удалённому насовсем.

    Записи не удаляются никогда: журнал и существует затем, чтобы через
    год можно было понять, кто и что поменял. Но вести с них на карточку,
    которой нет, нельзя, а «students.Student#57» вместо имени не читается.
    """
    from core.models import AuditLog

    marked = 0
    # `object_purged` отличает стёртое навсегда от просто архивного:
    # у первого карточки не будет уже никогда
    fields: dict[str, Any] = {"object_deleted": True, "object_purged": True}
    if batch is not None:
        # по номеру партии экран архива собирает историю удалённого:
        # карточки уже нет, а читать её больше негде
        fields["archive_batch"] = batch
    for label, pk, title in names:
        marked += AuditLog.objects.filter(model_label=label, object_id=str(pk)).update(
            object_title=title[:250], **fields
        )
    return marked


def _record_erasure(numbers: dict, *, actor, signed: dict[str, int], files: int) -> None:
    """Запись о самом удалении остаётся навсегда: кто, кого, когда, сколько.

    Это единственный след того, что запись вообще была. Он пишется тем же
    журналом, что и остальное, — отдельного места для него не заводим.
    """
    from core.models import AuditLog

    parts = [f"{row['title'].lower()}: {row['count']}" for row in numbers["erased"]]
    erased = ", ".join(parts) or "без связанных записей"
    AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_role=getattr(actor, "role", "") or "",
        model_label="core.Erasure",
        object_id="",
        object_title=numbers["title"][:250],
        field_name="erased",
        old_value=numbers["title"],
        new_value=(
            f"{numbers['kind']}: {numbers['title']}"
            + (f" ({numbers['email']})" if numbers["email"] else "")
            + f". Стёрто — {erased}"
            + (f", файлов {files}" if files else "")
            + (f". Журнал подписан именем: {sum(signed.values())}" if signed else "")
        )[:2000],
        object_deleted=True,
    )


# --- Кого удалять нельзя ---------------------------------------------------------


def refusal_for_user(user, *, actor) -> str:
    """Почему удалить эту учётную запись нельзя. Пусто — можно.

    Отказов ровно два, и оба про то, что систему нельзя оставить без
    хозяина: себя и последнего администратора.
    """
    from accounts.models import User
    from core.domains import ROLE_ADMIN

    if getattr(actor, "pk", None) == user.pk:
        return "Себя удалить нельзя: после этого некому будет войти под вашей учётной записью"
    if user.role == ROLE_ADMIN:
        others = User.objects.filter(role=ROLE_ADMIN, is_active=True).exclude(pk=user.pk).count()
        if others == 0:
            return (
                "Это последний администратор. Удалить его нельзя: без администратора "
                "не завести пользователей и не вернуть данные из архива"
            )
    return ""
