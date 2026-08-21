"""Фоновые задачи: разбор текста и файлов, вызовы модели.

Все обращения к модели и разбор файлов уходят в Celery. Эндпойнт
возвращает id задачи, фронт опрашивает статус и показывает прогресс.
"""

from __future__ import annotations

import logging

from celery import shared_task

log = logging.getLogger(__name__)


def progress(task, stage: str) -> None:
    """Отметить этап для опроса с фронта.

    В синхронном (eager) режиме состояние не трогаем: там `update_state`
    затирает сохранённый результат, и опрос статуса вечно видит PROGRESS.
    """
    if getattr(task.request, "is_eager", False):
        return
    task.update_state(state="PROGRESS", meta={"stage": stage})


@shared_task(bind=True, name="suggestions.parse_paste")
def parse_paste(self, *, text: str, actor_id: int, role: str, domain_code: str, command: str = "paste_as_is") -> dict:
    """Разобрать вставленный текст и собрать предложение."""
    from accounts.models import User
    from suggestions.engine import create_suggestion
    from suggestions.parsers import rows_for_suggestion

    actor = User.objects.filter(pk=actor_id).first()
    progress(self, "Разбираю текст")
    rows, ambiguities = rows_for_suggestion(text)

    progress(self, "Собираю предложение")
    suggestion, rejected = create_suggestion(
        author=actor,
        role=role,
        domain_code=domain_code,
        source_type="paste",
        command=command,
        rows=rows,
        source_ref="вставленный текст",
    )

    return {
        "suggestion": suggestion.pk,
        "rows": len(rows),
        "ambiguities": ambiguities,
        "rejected": rejected,
    }


@shared_task(bind=True, name="suggestions.parse_file")
def parse_file(self, *, content: str, filename: str, actor_id: int, role: str, domain_code: str) -> dict:
    """Разобрать загруженный файл тем же путём, что и вставленный текст."""
    progress(self, f"Читаю {filename}")
    return parse_paste(text=content, actor_id=actor_id, role=role, domain_code=domain_code, command="upload_file")


@shared_task(bind=True, name="suggestions.explain_match")
def explain_match(self, *, student_id: int, program_id: int, actor_id: int) -> dict:
    """Объяснить человеческим языком, чего не хватает ученику."""
    from accounts.models import User
    from suggestions.explain import explain_student_program

    actor = User.objects.filter(pk=actor_id).first()
    progress(self, "Сверяю с требованиями")
    return explain_student_program(student_id=student_id, program_id=program_id, actor=actor)


@shared_task(bind=True, name="suggestions.essay_questions")
def essay_questions(self, *, essay_id: int, prompt: str, actor_id: int) -> dict:
    """Вопросы ученику по эссе. Текст не пишется и не переписывается."""
    from accounts.models import User
    from suggestions.essay_assist import ask_questions

    actor = User.objects.filter(pk=actor_id).first()
    return ask_questions(essay_id=essay_id, prompt=prompt, actor=actor)
