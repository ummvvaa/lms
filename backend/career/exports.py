"""Выгрузка разборов профтеста в Word: кому можно, что идёт в файл, журнал.

Выгружают только учитель профориентации и администратор (`rights.manages`),
граница — группа ученика: чужая группа — 404. В файл идёт версия
профориентолога со всеми его правками (`career.word`).

Самый частый случай — один ученик, язык его разбора — файл отдаётся сразу
(`immediate`). Файлу нужна модель — перевод разбора на язык выгрузки или
«Общая картина» нескольких разборов (`career.translation`) — ответ «нужно
подготовить» (`NeedsPreparation`): подготовка идёт фоновым запуском. Уже
сохранённые перевод и общая картина модель второй раз не зовут.

Перевод или общая картина у ученика не получились — его файл всё равно
собирается: на языке разбора или без общей картины, с пометкой в итоге
(`Prepared.notes`).

В журнал изменений пишется, кто выгрузил, каких учеников и на каком языке —
событием по ученику; текстов разбора в журнале нет.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils.translation import gettext as _

from career import translation, word

#: языки файла — те же три, что в интерфейсе
LANGUAGES = ("ru", "kk", "en")
#: код события журнала (`core.labels.EXTRA_TITLES`)
EVENT = "career_export"


class Refused(ValueError):
    """Файл не собрать — текст объясняет почему."""


class NeedsPreparation(Refused):
    """Файлу нужна модель — перевод или общая картина: подготовка идёт в фоне."""


def language_or_none(raw) -> str | None:
    value = str(raw or "").strip().lower()
    return value if value in LANGUAGES else None


@dataclass
class Prepared:
    """Готовый файл ученика: содержимое, имя, язык и что не получилось."""

    payload: bytes
    name: str
    language: str
    notes: list[str] = field(default_factory=list)


def journal(students: list, *, language: str, actor) -> None:
    """Кто выгрузил, кого и на каком языке — событием по каждому ученику."""
    from core.audit import record_event

    for student in students:
        record_event(
            student=student,
            code=EVENT,
            text=_("Word, язык: {language}").format(language=language),
            actor=actor,
        )


def build(student, *, language: str, actor, use_model: bool) -> Prepared:
    """Файл ученика. Без `use_model` — только из сохранённого, иначе `NeedsPreparation`."""
    analyses = word.ready_analyses(student)
    if not analyses:
        raise Refused(_("нет готового разбора"))
    texts = [word.text_of(row) for row in analyses]
    notes: list[str] = []
    final = language
    shown = []
    for row, text in zip(analyses, texts, strict=True):
        if row.language == language:
            shown.append(text)
            continue
        stored = translation.fresh_translation(row, language)
        if stored is None:
            if not use_model:
                raise NeedsPreparation(_("Файл нужно подготовить: перевод или общая картина по тестам"))
            try:
                stored = translation.translate(row, text, language, actor=actor)
            except translation.TranslationFailed as error:
                notes.append(_("перевод не получился ({reason}) — файл на языке разбора").format(reason=error))
                final, shown = analyses[0].language, texts
                break
        shown.append(translation.apply(text, stored))
    overview = None
    if len(analyses) > 1:
        picture = translation.fresh_overview(student, analyses, final)
        if picture is None:
            if not use_model:
                raise NeedsPreparation(_("Файл нужно подготовить: перевод или общая картина по тестам"))
            try:
                picture = translation.write_overview(student, analyses, texts, final, actor=actor)
            except translation.TranslationFailed as error:
                notes.append(_("общая картина не получилась ({reason})").format(reason=error))
        overview = translation.overview_text(picture) if picture is not None else None
    payload = word.render(student, shown, language=final, actor=actor, overview=overview)
    return Prepared(payload, word.file_name(student), final, notes)


def immediate(student, *, language: str, actor) -> Prepared:
    """Файл одного ученика без модели — сразу; выгрузка пишется в журнал."""
    try:
        prepared = build(student, language=language, actor=actor, use_model=False)
    except NeedsPreparation:
        raise
    except Refused as error:
        raise Refused(_("У ученика нет готового разбора")) from error
    journal([student], language=prepared.language, actor=actor)
    return prepared


# --- Подготовка в фоне -------------------------------------------------------------------

#: вид фоновой операции (`core.jobs`)
JOB_KIND = "career_export"
ZIP_TYPE = "application/zip"


def needs_model(student, language: str) -> bool:
    """Нужна ли модель для файла: перевода на этот язык нет или общей картины нет."""
    analyses = word.ready_analyses(student)
    if not analyses:
        return False
    if any(row.language != language and translation.fresh_translation(row, language) is None for row in analyses):
        return True
    return len(analyses) > 1 and translation.fresh_overview(student, analyses, language) is None


def zip_name(group, *, whole_group: bool, moment=None) -> str:  # i18n-skip: имя архива задано школой
    """«Профтест_11A_04.11.2026.zip», для отмеченных — «Профтест_выбранные_04.11.2026.zip»."""
    from django.utils import timezone

    day = timezone.localtime(moment or timezone.now()).strftime("%d.%m.%Y")
    who = word.safe(group.code) if whole_group and group is not None else "выбранные"
    return f"Профтест_{who}_{day}.zip"


def link_of(export) -> str:
    """Куда ведёт уведомление «Файлы готовы»: разборы группы и окно с файлом."""
    from urllib.parse import quote

    group = f"&group={quote(export.group.code)}" if export.group_id else ""
    return f"/career-tests?tab=analyses{group}&export={export.pk}"


def keep_days() -> int:
    from core import school_rules

    return int(school_rules.value(school_rules.CAREER_EXPORT_DAYS))


def _names(students: list) -> str:
    from academics.payloads import short_name

    return ", ".join(short_name(f"{s.last_name} {s.first_name}") for s in students)


def outcome(ready: int, skipped: list[tuple], notes: list[tuple]) -> str:
    """«Готово 21, пропущено 4: нет готового разбора — Иванов И., …»; пометки — отдельной строкой."""
    lines = [_("Готово {count}").format(count=ready) if not skipped else ""]
    if skipped:
        reasons: dict[str, list] = {}
        for student, reason in skipped:
            reasons.setdefault(reason, []).append(student)
        parts = "; ".join(f"{reason} — {_names(rows)}" for reason, rows in reasons.items())
        lines = [
            _("Готово {ready}, пропущено {skipped}: {parts}").format(ready=ready, skipped=len(skipped), parts=parts)
        ]
    for student, note in notes:
        lines.append(f"{_names([student])}: {note}")
    return "\n".join(line for line in lines if line)


def run(export, *, students: list, actor, task_id: str = "") -> None:
    """Собрать файлы учеников по одному: ход — на плашке, итог — в выгрузке и колокольчике.

    Ученик без готового разбора пропускается; перевод или общая картина
    не получились — файл всё равно собирается, с пометкой в итоге.
    """
    import io
    import zipfile

    from django.core.files.base import ContentFile
    from django.utils import timezone

    from career.models import ExportStatus
    from core import jobs
    from core.models import BackgroundJob

    files: list[tuple[object, Prepared]] = []
    skipped: list[tuple] = []
    notes: list[tuple] = []
    total = len(students)
    for index, student in enumerate(students, start=1):
        if jobs.is_cancelled(task_id):
            return
        try:
            prepared = build(student, language=export.language, actor=actor, use_model=True)
        except jobs.Cancelled:
            return
        except Refused as error:
            skipped.append((student, str(error)))
        else:
            files.append((student, prepared))
            notes.extend((student, note) for note in prepared.notes)
        export.done = index
        export.save(update_fields=["done"])
        if task_id:
            # `updated_at` — признак жизни: долгая группа не считается зависшей
            BackgroundJob.objects.filter(task_id=task_id, status__in=jobs.ACTIVE).update(
                status=BackgroundJob.Status.RUNNING,
                percent=min(jobs.CEILING, round(index / max(1, total) * jobs.CEILING)),
                stage=f"{index}/{total}",
                steps_done=index,
                updated_at=timezone.now(),
            )
    if jobs.is_cancelled(task_id):
        return
    export.outcome = outcome(len(files), skipped, notes)
    export.finished_at = timezone.now()
    if not files:
        export.status = ExportStatus.FAILED
        export.save(update_fields=["outcome", "finished_at", "status"])
        jobs.fail(task_id, _("Файлов нет: ни у кого из учеников нет готового разбора"))
        return
    if export.whole_group or total > 1:
        buffer = io.BytesIO()
        used: set[str] = set()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for _student, prepared in files:
                name, counter = prepared.name, 2
                while name in used:
                    name = prepared.name.replace(".docx", f"_{counter}.docx")
                    counter += 1
                used.add(name)
                archive.writestr(name, prepared.payload)
        payload, name = buffer.getvalue(), zip_name(export.group, whole_group=export.whole_group)
    else:
        payload, name = files[0][1].payload, files[0][1].name
    export.file.save(name, ContentFile(payload), save=False)
    export.file_name = name
    export.status = ExportStatus.DONE
    export.expires_at = export.finished_at + timezone.timedelta(days=keep_days())
    export.save(update_fields=["outcome", "finished_at", "file", "file_name", "status", "expires_at"])
    for language in {prepared.language for _student, prepared in files}:
        journal(
            [student for student, prepared in files if prepared.language == language], language=language, actor=actor
        )
    jobs.complete(task_id, link=link_of(export))


def is_expired(export) -> bool:
    from django.utils import timezone

    return export.expires_at is not None and export.expires_at <= timezone.now()


def expire(export) -> None:
    """Срок хранения вышел: файл удаляется, строка с итогом остаётся."""
    from career.models import ExportStatus

    if export.file:
        export.file.delete(save=False)
    export.file = ""
    export.status = ExportStatus.EXPIRED
    export.save(update_fields=["file", "status"])


def purge() -> int:
    """Удалить файлы выгрузок, чей срок хранения вышел (раз в сутки и при скачивании)."""
    from django.utils import timezone

    from career.models import CareerExport, ExportStatus

    rows = list(CareerExport.objects.filter(status=ExportStatus.DONE, expires_at__lte=timezone.now()))
    for row in rows:
        expire(row)
    return len(rows)


def can_download(export, user) -> bool:
    """Скачать может тот, кто запускал, и администратор."""
    from core.domains import ROLE_ADMIN

    return export.owner_id == getattr(user, "pk", None) or getattr(user, "role", "") == ROLE_ADMIN


def export_dict(export, viewer) -> dict:
    from core import jobs

    return {
        "id": export.pk,
        "status": export.status,
        "status_title": export.get_status_display(),
        "language": export.language,
        "total": export.total,
        "done": export.done,
        "outcome": export.outcome,
        "file_name": export.file_name,
        "has_file": bool(export.file) and export.status == "done",
        "group": export.group.code if export.group_id else "",
        "whole_group": export.whole_group,
        "created_at": export.created_at,
        "expires_at": export.expires_at,
        "run": jobs.payload(export.job, viewer) if export.job_id else None,
    }


def job_title(group, students: list, *, whole_group: bool) -> str:
    """Название запуска на плашке и в колокольчике: «Word профтеста — группа 11A»."""
    from academics.payloads import short_name

    if whole_group and group is not None:
        return _("Word профтеста — группа {code}").format(code=group.code)
    if len(students) == 1:
        student = students[0]
        return _("Word профтеста — {name}").format(name=short_name(f"{student.last_name} {student.first_name}"))
    return _("Word профтеста — отмеченные ученики, {count}").format(count=len(students))


def running_for(user, *, group, students: list[int], language: str):
    """Та же подготовка того же человека уже идёт — второй запуск не нужен, ведём к идущему."""
    import json

    from career.models import CareerExport, ExportStatus
    from core import jobs

    jobs.sweep()
    rows = CareerExport.objects.filter(
        owner=user, status=ExportStatus.RUNNING, language=language, job__status__in=jobs.ACTIVE
    ).select_related("job", "group")
    if group is not None:
        return rows.filter(group=group, whole_group=True).first()
    wanted = sorted(students)
    for row in rows.filter(whole_group=False):
        payload = json.loads(row.job.retry_payload or "{}")
        if sorted(payload.get("students") or []) == wanted:
            return row
    return None
