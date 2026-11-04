"""Выгрузка разборов профтеста в Word: кому можно, что идёт в файл, журнал.

Выгружают только учитель профориентации и администратор (`rights.manages`),
граница — группа ученика: чужая группа — 404. В файл идёт версия
профориентолога со всеми его правками (`career.word`).

Самый частый случай — один ученик, язык его разбора — файл отдаётся сразу
(`immediate`). Если для файла нужна модель, ответ «нужно подготовить»
(`NeedsPreparation`).

В журнал изменений пишется, кто выгрузил, каких учеников и на каком языке —
событием по ученику; текстов разбора в журнале нет.
"""

from __future__ import annotations

from django.utils.translation import gettext as _

from career import word

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


def needs_model(analyses: list, language: str) -> bool:
    """Нужна ли модель: перевод разбора на другой язык или общая картина нескольких разборов."""
    return len(analyses) > 1 or any(row.language != language for row in analyses)


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


def immediate(student, *, language: str, actor) -> tuple[bytes, str]:
    """Файл одного ученика без модели: содержимое и имя."""
    analyses = word.ready_analyses(student)
    if not analyses:
        raise Refused(_("У ученика нет готового разбора"))
    if needs_model(analyses, language):
        raise NeedsPreparation(_("Файл нужно подготовить: перевод или общая картина по тестам"))
    payload = word.render(student, [word.text_of(row) for row in analyses], language=language, actor=actor)
    journal([student], language=language, actor=actor)
    return payload, word.file_name(student)
