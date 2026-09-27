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

from academics import calendar as school_calendar

#: Через сколько минут после звонка напоминать о неотмеченном уроке
REMIND_AFTER_MINUTES = 10


@shared_task(name="academics.remind_unmarked")
def remind_unmarked() -> int:
    """Учителю — уведомление о каждом уроке, не отмеченном через 10 минут после звонка."""

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
    from core.models import Notification
    from materials.services import notify

    rows = Lesson.objects.filter(
        date=day, status=LessonStatus.PLANNED, marked_at__isnull=True, reminded_at__isnull=True
    ).select_related("course", "course__subject", "course__cohort", "teacher", "substitute")
    for lesson in rows:
        bell = calendar.bell(lesson.slot, school_calendar.lesson_groups(lesson))
        if bell is None:
            continue
        starts = dt.datetime.combine(day, bell[0], tzinfo=now.tzinfo)
        if now < starts + dt.timedelta(minutes=REMIND_AFTER_MINUTES):
            continue
        who = lesson.substitute or lesson.teacher
        notify(
            who,
            kind=Notification.Kind.LESSON_UNMARKED,
            template="Не отмечен урок: {lesson}, {when}",
            link=f"/lessons/{lesson.pk}",
            lesson=lesson_words(lesson),
            when=f"{lesson.slot} урок",
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
