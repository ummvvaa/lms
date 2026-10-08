"""Фоновый разбор: по одному вызову модели на ученика, плашка с процентом."""

from __future__ import annotations

from celery import shared_task
from django.utils import translation

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
        with translation.override(row.language):
            run(row)
        done += 1
        if row.status == AnalysisStatus.FAILED:
            failed += 1
        if task_id:
            BackgroundJob.objects.filter(task_id=task_id, status=BackgroundJob.Status.RUNNING).update(
                percent=min(jobs.CEILING, round(done / max(1, total) * jobs.CEILING)),
                stage=f"{done}/{total}",
                steps_done=done,
            )
    if task_id:
        if failed and failed == total:
            first = next((r.error for r in rows if r.error), "")
            jobs.fail(task_id, first)
        else:
            jobs.complete(task_id, link="/career-tests?tab=analyses")
    return {"done": done, "failed": failed}
