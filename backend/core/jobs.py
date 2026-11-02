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

Запуск живёт так: «В очереди» (запись заведена, задача отдана Celery) →
«Идёт» (воркер её взял, сигнал `task_prerun`) → «Готово», «Не получился»
или «Отменён». Пока запуск той же операции над тем же объектом в очереди
или идёт, второй не заводится — кнопка ведёт к идущему.

Отмена кооперативная: статус «Отменён» и есть флаг. `llm.complete`
проверяет его до вызова модели и после — поздний ответ записывается
в журнал расходов, но дальше не идёт (`Cancelled`). Задачу в очереди
снимает `revoke` без `terminate`: убить воркер посреди запроса к модели
значит потерять запись о расходе, который провайдер всё равно спишет.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from importlib import import_module

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from core.i18n import language_of, translate
from core.models import BackgroundJob, Notification

log = logging.getLogger(__name__)

#: Запуск ещё не закончился: в очереди или идёт.
ACTIVE = (BackgroundJob.Status.QUEUED, BackgroundJob.Status.RUNNING)

#: Что сделать с доменными записями операции, когда запуск закрыт не ею
#: самой — отменён или признан зависшим. Путь к функции `(job, status, error)`:
#: общий механизм о разборах и отчётах не знает.
CLOSE_HOOKS = {
    "career_analysis": "career.tasks.close_rows",
}


class Cancelled(Exception):
    """Запуск отменили: результат не сохраняется, расход уже записан."""


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


def _target(target) -> tuple[str, int | None]:
    if target is None:
        return "", None
    from core.audit import model_label

    return model_label(target), target.pk


def start(
    *,
    user,
    kind: str,
    title: str,
    task_id: str = "",
    link: str = "",
    retry_task: str = "",
    retry_payload: dict | None = None,
    target=None,
) -> BackgroundJob:
    """Завести операцию. Вызывается там же, где задача уходит в Celery."""
    target_model, target_id = _target(target)
    return BackgroundJob.objects.create(
        owner=user,
        kind=kind,
        title=title[:200],
        task_id=task_id or "",
        link=link,
        retry_task=retry_task,
        retry_payload=json.dumps(retry_payload or {}, ensure_ascii=False) if retry_payload else "",
        target_model=target_model,
        target_id=target_id,
    )


def active_for(*, kind: str, target=None, user=None) -> BackgroundJob | None:
    """Идущий запуск той же операции над тем же объектом.

    Объект есть — неважно, кто запускал: второй разбор той же группы
    не нужен никому. Объекта нет — запуск личный, сравниваем по автору.
    """
    sweep()
    target_model, target_id = _target(target)
    rows = BackgroundJob.objects.filter(kind=kind, status__in=ACTIVE)
    if target_model:
        rows = rows.filter(target_model=target_model, target_id=target_id)
    else:
        rows = rows.filter(target_model="", owner=user)
    return rows.order_by("-created_at").first()


def latest_for(*, kind: str, target=None, user=None) -> BackgroundJob | None:
    """Последний запуск операции над объектом — для строки статуса на экране."""
    sweep()
    target_model, target_id = _target(target)
    rows = BackgroundJob.objects.filter(kind=kind)
    if target_model:
        rows = rows.filter(target_model=target_model, target_id=target_id)
    else:
        rows = rows.filter(target_model="", owner=user)
    return rows.order_by("-created_at").first()


def launch(
    *,
    user,
    kind: str,
    title: str,
    task,
    kwargs: dict,
    target=None,
    link: str = "",
    retry: bool = True,
) -> tuple[BackgroundJob, bool]:
    """Отдать операцию в фон, если такая же уже не идёт.

    Запись заводится до отправки задачи: иначе воркер мог бы взять её
    раньше, чем появится строка, и сигналы старта прошли бы мимо.
    Возвращает запуск и признак «заведён сейчас».
    """
    running = active_for(kind=kind, target=target, user=user)
    if running is not None:
        return running, False
    task_id = uuid.uuid4().hex
    job = start(
        user=user,
        kind=kind,
        title=title,
        task_id=task_id,
        link=link,
        retry_task=task.name if retry else "",
        retry_payload=kwargs if retry else None,
        target=target,
    )
    task.apply_async(kwargs=kwargs, task_id=task_id)
    return job, True


def begin(task_id: str) -> None:
    """Воркер взял задачу: запуск из очереди переходит в «Идёт»."""
    if not task_id:
        return
    BackgroundJob.objects.filter(task_id=task_id, status=BackgroundJob.Status.QUEUED).update(
        status=BackgroundJob.Status.RUNNING, started_at=timezone.now(), updated_at=timezone.now()
    )


def step(task_id: str, stage: str) -> None:
    """Отметить этап: название на плашке и процент по числу этапов."""
    if not task_id:
        return
    job = BackgroundJob.objects.filter(task_id=task_id, status__in=ACTIVE).first()
    if job is None:
        return
    total = STEPS.get(job.kind, 3)
    job.steps_done = min(job.steps_done + 1, total)
    job.stage = stage[:120]
    job.percent = min(CEILING, round(job.steps_done / total * CEILING))
    fields = ["steps_done", "stage", "percent", "updated_at"]
    if job.status == BackgroundJob.Status.QUEUED:
        # сигнал старта мог не дойти (задача в том же процессе) — этап и есть старт
        job.status, job.started_at = BackgroundJob.Status.RUNNING, timezone.now()
        fields += ["status", "started_at"]
    job.save(update_fields=fields)


def complete(task_id: str, *, link: str = "") -> None:
    """Операция закончилась. Уведомление уходит в колокольчик.

    Закрывается только незакрытый запуск: отменённый остаётся отменённым,
    даже если задача дошла до конца.
    """
    job = BackgroundJob.objects.filter(task_id=task_id, status__in=ACTIVE).first()
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
    job = BackgroundJob.objects.filter(task_id=task_id, status__in=ACTIVE).first()
    if job is None:
        return
    job.status = BackgroundJob.Status.FAILED
    # в фоне активного языка нет: запасной текст — на языке владельца операции
    job.error = (error or translate(language_of(job.owner), "Операция не завершилась"))[:300]
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error", "finished_at", "updated_at"])
    _notify(job, done=False)


def can_cancel(job: BackgroundJob, user) -> bool:
    """Отменить может тот, кто запустил, и администратор."""
    from core.domains import ROLE_ADMIN

    if user is None or job.status not in ACTIVE:
        return False
    return job.owner_id == user.pk or getattr(user, "role", "") == ROLE_ADMIN


def cancel(job: BackgroundJob, *, by) -> bool:
    """Отменить запуск: статус, снятие задачи из очереди, журнал изменений.

    Уведомления о своей отмене нет: человек сам нажал кнопку.
    """
    from core.audit import record_change

    if job.status not in ACTIVE:
        return False
    old = job.status
    job.status = BackgroundJob.Status.CANCELLED
    job.cancelled_by = by
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "cancelled_by", "finished_at", "updated_at"])
    _revoke(job.task_id)
    record_change(instance=job, field_name="status", old_value=old, new_value=job.status, actor=by)
    _close_rows(job)
    return True


def _revoke(task_id: str) -> None:
    """Снять задачу из очереди. Идущую не убиваем: её остановит флаг."""
    if not task_id or getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return
    from config.celery import app

    try:
        app.control.revoke(task_id)
    except Exception:  # брокер недоступен — статус «Отменён» всё равно остановит задачу
        log.warning("не удалось снять задачу %s из очереди", task_id, exc_info=True)


def is_cancelled(task_id: str) -> bool:
    return (
        bool(task_id) and BackgroundJob.objects.filter(task_id=task_id, status=BackgroundJob.Status.CANCELLED).exists()
    )


def raise_if_cancelled() -> None:
    """Флаг отмены для того, кто сейчас внутри задачи Celery.

    Вне задачи (вызов из веб-запроса) отменять нечего — проверка молчит.
    """
    from celery import current_task

    request = getattr(current_task, "request", None) if current_task else None
    task_id = getattr(request, "id", "") or ""
    if is_cancelled(task_id):
        # задача говорит на языке запустившего (`in_actor_language`)
        raise Cancelled(_("Запуск отменён"))


def stale_after() -> dt.timedelta:
    """Сколько ждать запуск в «Идёт» без единого признака жизни.

    Один вызов модели со всеми повторами занимает не дольше
    `LLM_TIMEOUT × (LLM_RETRIES + 1)`; минута сверху — на сборку данных.
    """
    llm = settings.LLM
    seconds = int(llm.get("TIMEOUT", 600)) * (int(llm.get("RETRIES", 2)) + 1) + 60
    return dt.timedelta(seconds=seconds)


def sweep() -> int:
    """Закрыть зависшие запуски: «Идёт» без признаков жизни дольше предела.

    Признак жизни — `updated_at`: каждый этап и каждый ученик пакетного
    разбора его обновляют, поэтому долгий, но живой пакет не закрывается.
    """
    border = timezone.now() - stale_after()
    stale = list(BackgroundJob.objects.filter(status=BackgroundJob.Status.RUNNING, updated_at__lt=border))
    for job in stale:
        fail(job.task_id, translate(language_of(job.owner), "нет ответа"))
        job.refresh_from_db()
        _close_rows(job)
    return len(stale)


def _close_rows(job: BackgroundJob) -> None:
    path = CLOSE_HOOKS.get(job.kind)
    if not path:
        return
    module, name = path.rsplit(".", 1)
    try:
        getattr(import_module(module), name)(job)
    except Exception:
        log.exception("не удалось закрыть записи запуска %s", job.pk)


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
                # переводит `notify` — на язык получателя
                template=gettext_noop("{title} — готово"),
                link=job.link or "/dashboard",
                title=job.title,
            )
        else:
            notify(
                job.owner,
                kind=Notification.Kind.JOB_FAILED,
                template=gettext_noop("{title} — не получилось: {error}"),
                link=job.link or "/dashboard",
                title=job.title,
                error=job.error,
            )
    except Exception:  # уведомление не должно ронять саму операцию
        log.exception("не удалось отправить уведомление о фоновой операции %s", job.pk)


def payload(job: BackgroundJob, viewer=None) -> dict:
    """Строка списка операций для плашки и строки статуса на экране."""
    return {
        "id": job.pk,
        "kind": job.kind,
        "title": job.title,
        "status": job.status,
        "status_title": job.get_status_display(),
        "stage": job.stage,
        "percent": job.percent,
        "link": job.link,
        "error": job.error,
        "task": job.task_id,
        "can_retry": bool(job.retry_task),
        "can_cancel": can_cancel(job, viewer if viewer is not None else job.owner),
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def mine(user, *, limit: int = 10) -> list[dict]:
    """Что показывать в плашке: идущее и недавно сорвавшееся.

    Готовое из плашки уходит само — про него уже сказал колокольчик;
    отменённое — тоже: отменил сам человек.
    """
    sweep()
    rows = BackgroundJob.objects.filter(owner=user, dismissed=False).exclude(
        status__in=(BackgroundJob.Status.DONE, BackgroundJob.Status.CANCELLED)
    )
    return [payload(job, user) for job in rows[:limit]]


def retry(job: BackgroundJob) -> BackgroundJob | None:
    """Повторить сорвавшуюся операцию тем же вызовом.

    Имя задачи берётся из записи и ищется среди зарегистрированных
    в Celery: выполнить произвольное имя из запроса нельзя.
    """
    from config.celery import app

    if not job.retry_task or job.retry_task not in app.tasks:
        return None
    kwargs = json.loads(job.retry_payload or "{}")
    task_id = uuid.uuid4().hex
    again = start(
        user=job.owner,
        kind=job.kind,
        title=job.title,
        task_id=task_id,
        link=job.link,
        retry_task=job.retry_task,
        retry_payload=kwargs,
    )
    again.target_model, again.target_id = job.target_model, job.target_id
    again.save(update_fields=["target_model", "target_id"])
    app.tasks[job.retry_task].apply_async(kwargs=kwargs, task_id=task_id)
    return again
