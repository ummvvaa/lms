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
