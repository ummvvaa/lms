"""Фоновые операции: одна плашка на все долгие дела (фаза 47).

До этой фазы каждая долгая операция объяснялась по-своему: у подбора вузов
была своя плашка, у генерации плана — своя, а у разбора файла и вызовов
модели не было никакой, и человек просто ждал, не зная, идёт ли что-нибудь.

Правила, ради которых это сведено в одно место:

* операция дольше трёх секунд уходит в фон, а на экране остаётся плашка
  с названием и процентом — работать она не мешает;
* несколько операций — список, а не стопка плашек друг на друге;
* когда закончилось, приходит уведомление в колокольчик: человек мог уйти
  на другой экран, и результат не должен потеряться;
* сбой говорит, что не получилось и почему, и даёт повторить.

Проценты собираются по этапам, которые называет сама операция: она знает,
сколько их у неё, а общий механизм — нет.
"""

from __future__ import annotations

import json
import logging

from django.utils import timezone

from core.models import BackgroundJob, Notification

log = logging.getLogger(__name__)

#: Сколько этапов у операции обычно. Из этого считается процент: этап
#: назван — доля пройдена. Неизвестный вид считаем трёхэтапным.
STEPS = {
    "paste": 2,
    "parse_file": 3,
    "explain_match": 2,
    "essay_questions": 2,
    "operation": 2,
    "parse_university": 2,
    "verify_requirements": 3,
    "parse_activity": 2,
    "parse_image": 2,
    "selection": 4,
    "plan": 3,
}

#: Потолок процента до завершения: сотня ставится только по факту.
CEILING = 90


def start(
    *,
    user,
    kind: str,
    title: str,
    task_id: str = "",
    link: str = "",
    retry_task: str = "",
    retry_payload: dict | None = None,
) -> BackgroundJob:
    """Завести операцию. Вызывается там же, где задача уходит в Celery."""
    return BackgroundJob.objects.create(
        owner=user,
        kind=kind,
        title=title[:200],
        task_id=task_id or "",
        link=link,
        retry_task=retry_task,
        retry_payload=json.dumps(retry_payload or {}, ensure_ascii=False) if retry_payload else "",
    )


def step(task_id: str, stage: str) -> None:
    """Отметить этап: название на плашке и процент по числу этапов."""
    if not task_id:
        return
    job = BackgroundJob.objects.filter(task_id=task_id, status=BackgroundJob.Status.RUNNING).first()
    if job is None:
        return
    total = STEPS.get(job.kind, 3)
    job.steps_done = min(job.steps_done + 1, total)
    job.stage = stage[:120]
    job.percent = min(CEILING, round(job.steps_done / total * CEILING))
    job.save(update_fields=["steps_done", "stage", "percent", "updated_at"])


def complete(task_id: str, *, link: str = "") -> None:
    """Операция закончилась. Уведомление уходит в колокольчик."""
    job = BackgroundJob.objects.filter(task_id=task_id).exclude(status=BackgroundJob.Status.DONE).first()
    if job is None:
        return
    job.status = BackgroundJob.Status.DONE
    job.percent = 100
    job.finished_at = timezone.now()
    if link:
        job.link = link
    job.save(update_fields=["status", "percent", "finished_at", "link", "updated_at"])
    _notify(job, done=True)


def fail(task_id: str, error: str) -> None:
    """Операция не получилась: плашка говорит почему и даёт повторить."""
    job = BackgroundJob.objects.filter(task_id=task_id).exclude(status=BackgroundJob.Status.FAILED).first()
    if job is None:
        return
    job.status = BackgroundJob.Status.FAILED
    job.error = (error or "Операция не завершилась")[:300]
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error", "finished_at", "updated_at"])
    _notify(job, done=False)


def _notify(job: BackgroundJob, *, done: bool) -> None:
    """Уведомление о конце — даже если человек ушёл с экрана."""
    from materials.services import notify

    if job.owner_id is None:
        return
    try:
        if done:
            notify(
                job.owner,
                kind=Notification.Kind.JOB_DONE,
                template="{title} — готово",
                link=job.link or "/dashboard",
                title=job.title,
            )
        else:
            notify(
                job.owner,
                kind=Notification.Kind.JOB_FAILED,
                template="{title} — не получилось: {error}",
                link=job.link or "/dashboard",
                title=job.title,
                error=job.error,
            )
    except Exception:  # уведомление не должно ронять саму операцию
        log.exception("не удалось отправить уведомление о фоновой операции %s", job.pk)


def payload(job: BackgroundJob) -> dict:
    """Строка списка операций для плашки."""
    return {
        "id": job.pk,
        "kind": job.kind,
        "title": job.title,
        "status": job.status,
        "stage": job.stage,
        "percent": job.percent,
        "link": job.link,
        "error": job.error,
        "can_retry": bool(job.retry_task),
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


def mine(user, *, limit: int = 10) -> list[dict]:
    """Что показывать в плашке: идущее и недавно сорвавшееся.

    Готовое из плашки уходит само — про него уже сказал колокольчик.
    """
    rows = BackgroundJob.objects.filter(owner=user, dismissed=False).exclude(status=BackgroundJob.Status.DONE)
    return [payload(job) for job in rows[:limit]]


def retry(job: BackgroundJob) -> BackgroundJob | None:
    """Повторить сорвавшуюся операцию тем же вызовом.

    Имя задачи берётся из записи и ищется среди зарегистрированных
    в Celery: выполнить произвольное имя из запроса нельзя.
    """
    from config.celery import app

    if not job.retry_task or job.retry_task not in app.tasks:
        return None
    kwargs = json.loads(job.retry_payload or "{}")
    task = app.tasks[job.retry_task].delay(**kwargs)
    return start(
        user=job.owner,
        kind=job.kind,
        title=job.title,
        task_id=task.id,
        link=job.link,
        retry_task=job.retry_task,
        retry_payload=kwargs,
    )
