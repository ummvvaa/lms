"""Фоновые задачи учебной части: напоминание об уроке и сбор отчётов родителям.

Напоминание — только колокольчик, через 10 минут после звонка, по уроку одно.
Писем учителю нет (решение владельца). Отчёты — последняя пятница месяца
в 08:00 по Алматы: beat запускает задачу по пятницам, последняя ли это
пятница, задача проверяет сама; после закрытия четверти — из самого действия.
"""

from __future__ import annotations

import datetime as dt

from celery import shared_task
from django.utils import timezone
from django.utils.translation import gettext_noop

from academics import calendar as school_calendar


@shared_task(name="academics.remind_unmarked")
def remind_unmarked() -> int:
    """Учителю — уведомление о каждом уроке, не отмеченном через N минут после звонка на урок.

    N — настройка школы «Напоминание о неотмеченном уроке» (по умолчанию 10).
    """

    calendar = school_calendar.load()
    now = timezone.localtime()
    day = now.date()
    sent = 0
    from academics import cache

    with cache.scope():
        return _remind(calendar, now, day, sent)


def _remind(calendar, now, day, sent) -> int:
    from academics.models import Lesson, LessonStatus
    from academics.teachers import lesson_words
    from core import school_rules
    from core.i18n import language_of, render
    from core.models import Notification
    from materials.services import notify

    wait = dt.timedelta(minutes=school_rules.value(school_rules.UNMARKED_REMIND_MINUTES))
    rows = Lesson.objects.filter(
        date=day,
        status=LessonStatus.PLANNED,
        marked_at__isnull=True,
        reminded_at__isnull=True,
        # урок предмета «только расписание» в LMS не отмечают — и не напоминают
        course__subject__in_lms=True,
    ).select_related("course", "course__subject", "course__cohort", "teacher", "substitute")
    for lesson in rows:
        bell = calendar.bell(lesson.slot, school_calendar.lesson_groups(lesson))
        if bell is None:
            continue
        starts = dt.datetime.combine(day, bell[0], tzinfo=now.tzinfo)
        if now < starts + wait:
            continue
        who = lesson.substitute or lesson.teacher
        if who is None:
            # учитель не назначен: напомнить некому, а метка «напомнили»
            # отняла бы напоминание у того, кого назначат потом
            continue
        notify(
            who,
            kind=Notification.Kind.LESSON_UNMARKED,
            # шаблон переводит `notify` на язык учителя
            template=gettext_noop("Не отмечен урок: {lesson}, {when}"),
            link=f"/lessons/{lesson.pk}",
            lesson=lesson_words(lesson),
            when=render(language_of(who), "{slot} урок", slot=lesson.slot),
        )
        lesson.reminded_at = timezone.now()
        lesson.save(update_fields=["reminded_at"])
        sent += 1
    return sent


@shared_task(name="academics.build_monthly_reports")
def build_monthly_reports(force: bool = False) -> int:
    """Собрать отчёты за месяц, если сегодня последняя пятница (или `force`)."""
    from academics.models import ReportCadence, ReportPeriod
    from academics.reports import build_for_period, is_last_friday, month_bounds, notify_curators, report_settings

    calendar = school_calendar.load()
    day = school_calendar.today()
    if not force and not is_last_friday(day):
        return 0
    config = report_settings(calendar)
    if config.cadence == ReportCadence.QUARTER and not force:
        return 0
    start, end = month_bounds(day)
    reports = build_for_period(kind=ReportPeriod.MONTH, start=start, end=end, calendar=calendar)
    if reports:
        notify_curators(reports, reports[0].title)
    return len(reports)


@shared_task(name="academics.build_quarter_reports")
def build_quarter_reports(quarter_id: int) -> int:
    """Отчёты за четверть — из самого действия закрытия четверти."""
    from academics.models import Quarter, ReportPeriod
    from academics.reports import build_for_period, notify_curators

    quarter = Quarter.objects.select_related("year").filter(pk=quarter_id).first()
    if quarter is None:
        return 0
    calendar = school_calendar.load(quarter.year)
    reports = build_for_period(
        kind=ReportPeriod.QUARTER, start=quarter.starts, end=quarter.ends, calendar=calendar, quarter=quarter
    )
    if reports:
        notify_curators(reports, reports[0].title)
    return len(reports)


@shared_task(name="academics.draft_report")
def draft_report(report_id: int, actor_id: int | None = None, overwrite: bool = False) -> str:
    """Черновик текстов отчёта по шаблону школы — модель отвечает долго, поэтому в очереди."""
    from academics.models import ParentReport
    from academics.report_drafts import draft
    from accounts.models import User

    report = ParentReport.objects.select_related("student", "student__group").filter(pk=report_id).first()
    if report is None:
        return "нет отчёта"  # i18n-skip: результат задачи Celery, человек его не видит
    actor = User.objects.filter(pk=actor_id).first() if actor_id else None
    return draft(report, actor=actor, overwrite=overwrite).draft_state


@shared_task(name="academics.export_reports")
def export_reports(job: str, user_id: int, ids: list[int], file_format: str, zip_name: str) -> str:
    """Архив отчётов группы: PDF — через LibreOffice, это десятки секунд."""
    from academics.report_files import run_export

    return run_export(job, user_id=user_id, ids=ids, file_format=file_format, zip_name=zip_name)
