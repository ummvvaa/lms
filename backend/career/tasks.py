"""Фоновый разбор: по одному вызову модели на ученика, плашка с процентом."""

from __future__ import annotations

from celery import shared_task
from django.utils import timezone, translation

from core.models import BackgroundJob

JOB_KIND = "career_analysis"


@shared_task(name="career.analyze", bind=True)
def analyze(self, analysis_ids: list[int] | None = None, **kwargs) -> dict:
    """Разобрать перечисленные записи; язык — тот, с которым их открыли."""
    from career.analysis import run
    from career.models import AnalysisStatus, CareerAnalysis
    from core import jobs

    ids = list(analysis_ids or kwargs.get("analysis_ids") or [])
    task_id = getattr(getattr(self, "request", None), "id", "") or ""
    rows = list(CareerAnalysis.objects.filter(pk__in=ids, status=AnalysisStatus.RUNNING).select_related("student"))
    total = len(rows)
    done = 0
    failed = 0
    for row in rows:
        # отменили между учениками — следующих не разбираем; строки закрыла отмена
        if jobs.is_cancelled(task_id):
            return {"done": done, "failed": failed, "cancelled": True}
        with translation.override(row.language):
            run(row)
        done += 1
        if row.status == AnalysisStatus.FAILED:
            failed += 1
        if task_id:
            # `updated_at` — признак жизни: долгий пакет не считается зависшим
            BackgroundJob.objects.filter(task_id=task_id, status__in=jobs.ACTIVE).update(
                status=BackgroundJob.Status.RUNNING,
                percent=min(jobs.CEILING, round(done / max(1, total) * jobs.CEILING)),
                stage=f"{done}/{total}",
                steps_done=done,
                updated_at=timezone.now(),
            )
    if jobs.is_cancelled(task_id):
        return {"done": done, "failed": failed, "cancelled": True}
    if task_id:
        if failed and failed == total:
            first = next((r.error for r in rows if r.error), "")
            jobs.fail(task_id, first)
        else:
            jobs.complete(task_id, link="/career-tests?tab=analyses")
    return {"done": done, "failed": failed}


VERSION_KIND = "career_student_version"


@shared_task(name="career.student_version", bind=True)
def student_version(self, analysis_id: int = 0, actor_id: int = 0, **kwargs) -> dict:
    """Версия разбора для ученика в фоне: переписывание целого разбора идёт минутами.

    Получилась — разбор сразу показан ученику: за этим кнопку и нажимали.
    Не получилась — причина у запуска, разбор ученику не показан.
    """
    from accounts.models import User
    from career.analysis import StudentVersionUnavailable, write_student_version
    from career.models import CareerAnalysis
    from core import jobs
    from core.i18n import language_of

    task_id = getattr(getattr(self, "request", None), "id", "") or ""
    row = CareerAnalysis.objects.filter(pk=analysis_id or kwargs.get("analysis_id")).first()
    actor = User.objects.filter(pk=actor_id or kwargs.get("actor_id")).first()
    if row is None:
        return {"ok": False}
    with translation.override(language_of(actor) if actor else row.language):
        try:
            write_student_version(row, actor=actor)
        except StudentVersionUnavailable as error:
            jobs.fail(task_id, str(error))
            return {"ok": False}
    row.visible_to_student = True
    row.save(update_fields=["visible_to_student"])
    return {"ok": True}


def close_rows(job: BackgroundJob) -> None:
    """Запуск отменён или завис: его неразобранные строки закрываются так же."""
    from career.models import AnalysisStatus, CareerAnalysis

    if job.status == BackgroundJob.Status.CANCELLED:
        status, error = AnalysisStatus.CANCELLED, ""
    else:
        status, error = AnalysisStatus.FAILED, job.error
    CareerAnalysis.objects.filter(job=job, status=AnalysisStatus.RUNNING).update(
        status=status, error=error[:300], finished_at=timezone.now()
    )
