"""Фоновые задачи: разбор текста и файлов, вызовы модели.

Все обращения к модели и разбор файлов уходят в Celery. Эндпойнт
возвращает id задачи, фронт опрашивает статус и показывает прогресс.
"""

from __future__ import annotations

import functools
import logging

from celery import shared_task
from django.utils import translation
from django.utils.translation import gettext as _

log = logging.getLogger(__name__)


def in_actor_language(func):
    """Задача говорит на языке того, кто её запустил.

    В фоне активного языка нет: этапы плашки, ошибки и ответ операции
    без этого ушли бы по-русски любому. Язык — `language_of` автора запуска.
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        from accounts.models import User
        from core.i18n import language_of

        actor = User.objects.filter(pk=kwargs.get("actor_id")).first() if kwargs.get("actor_id") else None
        with translation.override(language_of(actor)):
            return func(self, *args, **kwargs)

    return wrapper


def progress(task, stage: str) -> None:
    """Отметить этап: и для опроса статуса, и для общей плашки операций.

    В синхронном (eager) режиме состояние Celery не трогаем: там
    `update_state` затирает сохранённый результат, и опрос статуса вечно
    видит PROGRESS. Плашку отмечаем всегда — она читает свою запись,
    а не состояние задачи (фаза 47).
    """
    from core import jobs

    jobs.step(getattr(task.request, "id", "") or "", stage)
    if getattr(task.request, "is_eager", False):
        return
    task.update_state(state="PROGRESS", meta={"stage": stage})


@shared_task(bind=True, name="suggestions.parse_paste")
@in_actor_language
def parse_paste(self, *, text: str, actor_id: int, role: str, domain_code: str, command: str = "paste_as_is") -> dict:
    """Разобрать вставленный текст и собрать предложение."""
    from accounts.models import User
    from suggestions.engine import create_suggestion
    from suggestions.parsers import rows_for_suggestion

    actor = User.objects.filter(pk=actor_id).first()
    progress(self, _("Разбираю текст"))
    # правила разбирают знакомые строки, модель добирает остальное
    rows, ambiguities = rows_for_suggestion(text, actor=actor, role=role)

    progress(self, _("Собираю предложение"))
    suggestion, rejected = create_suggestion(
        author=actor,
        role=role,
        domain_code=domain_code,
        source_type="paste",
        command=command,
        rows=rows,
        source_ref="вставленный текст",  # i18n-skip: источник сохраняется в базе как данные
    )

    return {
        "suggestion": suggestion.pk,
        "rows": len(rows),
        "ambiguities": ambiguities,
        "rejected": rejected,
    }


@shared_task(bind=True, name="suggestions.parse_file")
@in_actor_language
def parse_file(self, *, content: str, filename: str, actor_id: int, role: str, domain_code: str) -> dict:
    """Разобрать загруженный файл тем же путём, что и вставленный текст."""
    progress(self, _("Читаю {filename}").format(filename=filename))
    return parse_paste(text=content, actor_id=actor_id, role=role, domain_code=domain_code, command="upload_file")


@shared_task(bind=True, name="suggestions.explain_match")
@in_actor_language
def explain_match(self, *, student_id: int, program_id: int, actor_id: int) -> dict:
    """Объяснить человеческим языком, чего не хватает ученику."""
    from accounts.models import User
    from suggestions.explain import explain_student_program

    actor = User.objects.filter(pk=actor_id).first()
    progress(self, _("Сверяю с требованиями"))
    return explain_student_program(student_id=student_id, program_id=program_id, actor=actor)


@shared_task(bind=True, name="suggestions.essay_questions")
@in_actor_language
def essay_questions(self, *, essay_id: int, prompt: str, actor_id: int) -> dict:
    """Вопросы ученику по эссе. Текст не пишется и не переписывается."""
    from accounts.models import User
    from suggestions.essay_assist import ask_questions

    actor = User.objects.filter(pk=actor_id).first()
    return ask_questions(essay_id=essay_id, prompt=prompt, actor=actor)


# --- Фаза 20: операции уровня управления ---------------------------------
#
# Все вызовы модели идут фоновой задачей: провайдер отвечает секундами,
# и держать на этом запрос директора незачем.


def _actor(actor_id: int):
    from accounts.models import User

    return User.objects.filter(pk=actor_id).first()


@shared_task(bind=True, name="suggestions.run_operation")
@in_actor_language
def run_operation(self, *, code: str, actor_id: int, role: str, payload: dict) -> dict:
    """Одна операция уровня управления по её коду."""
    from suggestions import operations

    actor = _actor(actor_id)
    progress(self, _("Собираю данные"))

    handlers = {
        "explain_list": lambda: operations.explain_list(
            student_ids=payload.get("students") or [], actor=actor, role=role
        ),
        "week_changes": lambda: operations.week_changes(actor=actor, role=role, days=int(payload.get("days") or 7)),
        "focus_today": lambda: operations.focus_today(actor=actor, role=role),
        "bulk_tasks": lambda: operations.bulk_tasks(
            student_ids=payload.get("students") or [], wish=payload.get("text") or "", actor=actor, role=role
        ),
        "prep_plan": lambda: operations.prep_plan(student_id=int(payload["student"]), actor=actor, role=role),
        "gap_to_tasks": lambda: operations.gap_to_tasks(student_id=int(payload["student"]), actor=actor, role=role),
        "check_balance": lambda: operations.check_balance(student_id=int(payload["student"]), actor=actor, role=role),
    }
    handler = handlers.get(code)
    if handler is None:
        return {"ok": False, "detail": _("Такой операции нет")}

    progress(self, _("Собираю ответ"))
    return handler().as_dict()


@shared_task(bind=True, name="suggestions.parse_university")
@in_actor_language
def parse_university(self, *, text: str, actor_id: int, role: str) -> dict:
    """Разобрать вуз по названию или ссылке."""
    from suggestions.extraction import NeedsModel
    from suggestions.extraction import parse_university as run

    progress(self, _("Собираю карточку вуза"))
    try:
        return run(text=text, actor=_actor(actor_id), role=role)
    except NeedsModel as error:
        return {"ok": False, "detail": str(error)}


@shared_task(bind=True, name="suggestions.verify_requirements")
@in_actor_language
def verify_requirements(self, *, program_id: int, actor_id: int, role: str) -> dict:
    """Сверить требования программы с официальным сайтом вуза."""
    from suggestions.verify_requirements import CannotVerify
    from suggestions.verify_requirements import verify as run

    progress(self, _("Читаю официальный сайт"))
    try:
        return run(program_id=program_id, actor=_actor(actor_id), role=role)
    except CannotVerify as error:
        return {"ok": False, "detail": str(error)}


@shared_task(bind=True, name="suggestions.parse_activity")
@in_actor_language
def parse_activity(self, *, text: str, student_id: int, actor_id: int, role: str) -> dict:
    """Разобрать описание активности."""
    from suggestions.extraction import NeedsModel
    from suggestions.extraction import parse_activity as run

    progress(self, _("Разбираю описание"))
    try:
        return run(text=text, student_id=student_id, actor=_actor(actor_id), role=role)
    except NeedsModel as error:
        return {"ok": False, "detail": str(error)}


@shared_task(bind=True, name="suggestions.parse_image")
@in_actor_language
def parse_image(self, *, payload: bytes, media_type: str, kind: str, student_id: int, actor_id: int, role: str) -> dict:
    """Фото грамоты или скриншот с баллами."""
    from suggestions.extraction import NeedsModel, parse_certificate, parse_score_screenshot
    from suggestions.llm import InvalidImage

    progress(self, _("Читаю изображение"))
    run = parse_certificate if kind == "certificate" else parse_score_screenshot
    try:
        return run(payload=payload, media_type=media_type, student_id=student_id, actor=_actor(actor_id), role=role)
    except (NeedsModel, InvalidImage) as error:
        return {"ok": False, "detail": str(error)}
