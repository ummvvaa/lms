"""Отчёты одного места у директора школы и академического директора (24.10.2026).

Отчёт не хранится: он собирается при открытии из того, что уже есть, —
утренних отметок кураторов, уроков и оценок учителей, сдачи ДЗ, пробников
и целей, отчётов родителям, звонков. Хранится только «Просмотрено»
(`ReportSeen`) по виду отчёта и ключу периода. Заново считаются сводки,
которых раньше не было: статусы отчётов родителям по группам, ФО по
параллелям, непроверенное ДЗ по учителям, «достигли цели» по Mock Test,
звонки за неделю.

У отчёта — строки «подпись — число» для окна и таблица для выгрузки;
xlsx собирается тем же кодом (`core.exports`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field

from django.db.models import Avg, Count
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.exports import Column
from core.phrasing import tn
from students.models import AttendanceDay, Student, StudyGroup

#: ниже стольких процентов ФО ученик в отчёте «ниже порога»
FO_BELOW = 60


@dataclass
class Report:
    kind: str
    title: str
    source: str
    period: str
    period_title: str
    lines: list[tuple[str, str]] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    rows: list = field(default_factory=list)
    #: короткая сводка в строку списка: «12 нет · 7 опоздали»
    summary: str = ""
    #: числа для показателей главной: «средний ФО», «уроков не отмечено» — без разбора строк
    figures: dict = field(default_factory=dict)

    def payload(self, *, seen: bool) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "source": self.source,
            "period": self.period,
            "period_title": self.period_title,
            "summary": self.summary,
            "lines": [{"label": label, "value": value} for label, value in self.lines],
            "figures": self.figures,
            "seen": seen,
        }


def _today() -> dt.date:
    return timezone.localdate()


def _monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def _school_day(day: dt.date) -> dt.date:
    """Последний будний день не позже `day` — в выходной отчёт «за сегодня» берёт пятницу."""
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def _span(start: dt.date, end: dt.date) -> str:
    return f"{start:%d.%m}–{end:%d.%m}"


def _groups():
    return StudyGroup.objects.filter(is_active=True).order_by("code")


def _pct(part: int, whole: int) -> str:
    return f"{round(part * 100 / whole)} %" if whole else "0 %"


def _curator_name(group) -> str:
    from accounts.curators import curator_of

    row = curator_of(group)
    return (row.curator.full_name or row.curator.email) if row is not None else ""


# --- Директор школы -----------------------------------------------------------------


def morning(period: str = "") -> Report:
    """Утренняя отметка кураторов за день: кто отметил, кого нет, кто опоздал."""
    day = _parse_day(period) or _school_day(_today())
    groups = list(_groups())
    marks = AttendanceDay.objects.filter(date=day, student__is_active=True, student__group__in=groups)
    by_group: dict[int, dict] = {}
    for group_id, mark, reason, updated in marks.values_list("student__group", "mark", "reason", "updated_at"):
        row = by_group.setdefault(group_id, {"absent": 0, "late": 0, "commented": 0, "last": None})
        if mark == AttendanceDay.Mark.ABSENT:
            row["absent"] += 1
        if mark == AttendanceDay.Mark.LATE:
            row["late"] += 1
        if reason:
            row["commented"] += 1
        row["last"] = max(filter(None, (row["last"], updated)), default=None)
    rows = []
    for group in groups:
        found = by_group.get(group.pk)
        rows.append(
            {
                "group": group.code,
                "curator": _curator_name(group),
                "marked": found is not None,
                "at": timezone.localtime(found["last"]).strftime("%H:%M") if found and found["last"] else "",
                "absent": found["absent"] if found else 0,
                "late": found["late"] if found else 0,
            }
        )
    marked = sum(1 for r in rows if r["marked"])
    absent = sum(r["absent"] for r in rows)
    late = sum(r["late"] for r in rows)
    unmarked = [r["group"] for r in rows if not r["marked"]]
    report = Report(
        kind="morning",
        title=_("Утренняя отметка кураторов"),
        source=_("группы кураторов"),
        period=day.isoformat(),
        period_title=f"{day:%d.%m.%Y}",
        summary=_("отметились {marked} из {total}").format(marked=marked, total=len(rows)),
        lines=[
            (_("Групп отметились"), f"{marked} / {len(rows)}"),
            (_("Нет в школе"), str(absent)),
            (_("Опоздали"), str(late)),
            (_("Не отметились"), ", ".join(unmarked[:6]) + (f" +{len(unmarked) - 6}" if len(unmarked) > 6 else "")),
        ],
        columns=[
            Column(_("Группа"), lambda r: r["group"], 12),
            Column(_("Куратор"), lambda r: r["curator"], 26),
            Column(_("Отмечено в"), lambda r: r["at"], 12),
            Column(_("Нет"), lambda r: r["absent"], 8),
            Column(_("Опоздали"), lambda r: r["late"], 10),
        ],
        rows=rows,
    )
    if not unmarked:
        report.lines.pop()
    return report


def security(period: str = "") -> Report:
    """Отчёт для службы безопасности: кого нет и кто опоздал по утренней отметке за день."""
    from students import discipline

    day = _parse_day(period) or _school_day(_today())
    buckets = discipline.absences(groups=list(_groups()), since=day, until=day)
    rows = [
        {
            "group": bucket["group_code"],
            "name": student["full_name"],
            "mark": discipline.mark_label(student["mark"]),
            "reason": student["reason"],
        }
        for bucket in buckets
        for student in bucket["students"]
    ]
    absent = sum(b["count"] for b in buckets)
    late = sum(b["late_count"] for b in buckets)
    commented = sum(1 for r in rows if r["reason"])
    return Report(
        kind="security",
        title=_("Отчёт для службы безопасности"),
        source=_("собран из утренних отметок"),
        period=day.isoformat(),
        period_title=f"{day:%d.%m.%Y}",
        summary=tn(absent, "{n} отсутствует|{n} отсутствуют|{n} отсутствуют"),
        lines=[
            (_("Отсутствуют"), str(absent)),
            (_("Опоздали"), str(late)),
            (_("С комментарием куратора"), f"{commented} / {len(rows)}"),
            (_("Групп в отчёте"), str(len(buckets))),
        ],
        columns=[
            Column(_("Группа"), lambda r: r["group"], 12),
            Column(_("Ученик"), lambda r: r["name"], 30),
            Column(_("Отметка"), lambda r: r["mark"], 12),
            Column(_("Комментарий куратора"), lambda r: r["reason"], 40),
        ],
        rows=rows,
    )


def parent_report_groups(month: dt.date) -> list[dict]:
    """Отчёты родителям за месяц по группам: не собран, собран, проверен, отправлен."""
    from academics.models import ParentReport, ReportStatus

    start = month.replace(day=1)
    end = (start + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    reports = ParentReport.objects.filter(period_start__gte=start, period_start__lte=end, student__is_active=True)
    counts: dict[int, dict[str, int]] = {}
    for group_id, state, n in reports.values_list("student__group", "status").annotate(n=Count("id")):
        counts.setdefault(group_id, {})[state] = n
    out = []
    for group in _groups():
        found = counts.get(group.pk, {})
        total = sum(found.values())
        size = group.students.filter(is_active=True).count()
        if not total:
            state = "none"
        elif found.get(ReportStatus.SENT, 0) == total:
            state = "sent"
        elif found.get(ReportStatus.DRAFT, 0) == 0:
            state = "checked"
        else:
            state = "built"
        out.append(
            {
                "group_id": group.pk,
                "group": group.code,
                "curator": _curator_name(group),
                "students": size,
                "reports": total,
                "state": state,
                "state_title": str(GROUP_STATES[state]),
            }
        )
    return out


GROUP_STATES = {
    "none": gettext_lazy("не собран"),
    "built": gettext_lazy("собран"),
    "checked": gettext_lazy("проверен куратором"),
    "sent": gettext_lazy("отправлен"),
}


def parent_reports(period: str = "") -> Report:
    month = _parse_month(period) or _today().replace(day=1)
    rows = parent_report_groups(month)
    by_state = {key: sum(1 for r in rows if r["state"] == key) for key in GROUP_STATES}
    ready = sum(r["reports"] for r in rows if r["state"] == "checked")
    return Report(
        kind="parent_reports",
        title=_("Отчёты родителям за {month}").format(month=_month_title(month)),
        source=_("кураторы · проверено {n} из {total} групп").format(
            n=by_state["checked"] + by_state["sent"], total=len(rows)
        ),
        period=f"{month:%Y-%m}",
        period_title=_month_title(month),
        summary=_("к отправке: {n}").format(n=ready),
        lines=[
            (_("Готово к отправке"), str(ready)),
            (_("На проверке у кураторов"), tn(by_state["built"], "{n} группа|{n} группы|{n} групп")),
            (_("Не собраны"), tn(by_state["none"], "{n} группа|{n} группы|{n} групп")),
            (_("Отправлено"), tn(by_state["sent"], "{n} группа|{n} группы|{n} групп")),
        ],
        columns=[
            Column(_("Группа"), lambda r: r["group"], 12),
            Column(_("Куратор"), lambda r: r["curator"], 26),
            Column(_("Учеников"), lambda r: r["students"], 10),
            Column(_("Статус"), lambda r: r["state_title"], 18),
        ],
        rows=rows,
    )


def calls(period: str = "") -> Report:
    """Звонки родителям за неделю — директор и кураторы."""
    from directors.models import CallOutcome, ParentCall

    monday = _parse_day(period) or _monday(_today())
    monday = _monday(monday)
    friday = monday + dt.timedelta(days=6)
    rows = list(
        ParentCall.objects.filter(called_at__date__gte=monday, called_at__date__lte=friday)
        .select_related("student", "student__group")
        .order_by("-called_at")
    )
    count = {key: sum(1 for r in rows if r.outcome == key) for key in CallOutcome.values}
    return Report(
        kind="calls",
        title=_("Звонки родителям за неделю"),
        source=_("вы и кураторы · {span}").format(span=_span(monday, monday + dt.timedelta(days=4))),
        period=monday.isoformat(),
        period_title=_span(monday, monday + dt.timedelta(days=4)),
        summary=tn(len(rows), "{n} звонок|{n} звонка|{n} звонков"),
        lines=[
            (_("Звонков"), str(len(rows))),
            (_("Дозвонились"), str(count[CallOutcome.REACHED])),
            (_("Не ответили"), str(count[CallOutcome.NO_ANSWER])),
            (_("Перезвонить"), str(count[CallOutcome.CALL_BACK])),
        ],
        columns=[
            Column(_("Когда"), lambda r: timezone.localtime(r.called_at).strftime("%d.%m %H:%M"), 14),
            Column(_("Ученик"), lambda r: r.student.full_name, 30),
            Column(_("Группа"), lambda r: r.student.group.code if r.student.group_id else "", 10),
            Column(_("Кто звонил"), lambda r: r.called_by_title, 24),
            Column(_("Итог"), lambda r: r.get_outcome_display(), 14),
            Column(_("Комментарий"), lambda r: r.note, 40),
        ],
        rows=rows,
    )


def attendance_week(period: str = "") -> Report:
    """Посещаемость за неделю по урокам учителей: средняя, ниже порога, дни без причины."""
    from academics.results import attendance_by_students
    from core import school_rules

    monday = _monday(_parse_day(period) or _today())
    end = min(monday + dt.timedelta(days=4), _today())
    threshold = school_rules.value(school_rules.ATTENDANCE_BELOW)
    students = list(Student.objects.filter(is_active=True, group__isnull=False).select_related("group"))
    totals = attendance_by_students([s.pk for s in students], monday, end) if end >= monday else {}
    rows = []
    for student in students:
        t = totals.get(student.pk)
        if t is None or not t.total:
            continue
        rows.append({"student": student, "pct": t.pct, "absent": t.absent, "excused": t.excused, "late": t.late})
    marked = [r for r in rows if r["pct"] is not None]
    below = [r for r in marked if r["pct"] < threshold]
    below.sort(key=lambda r: r["pct"])
    average = round(sum(r["pct"] for r in marked) / len(marked)) if marked else None
    return Report(
        kind="attendance_week",
        title=_("Посещаемость за неделю"),
        source=_("по урокам учителей · {span}").format(span=_span(monday, monday + dt.timedelta(days=4))),
        period=monday.isoformat(),
        period_title=_span(monday, monday + dt.timedelta(days=4)),
        summary=_("средняя {pct}").format(pct=f"{average} %" if average is not None else "—"),
        lines=[
            (_("Средняя"), f"{average} %" if average is not None else _("уроков не было")),
            (_("Ниже {n} %").format(n=round(threshold)), tn(len(below), "{n} ученик|{n} ученика|{n} учеников")),
            (_("Пропусков без причины"), str(sum(r["absent"] for r in rows))),
            (_("Опозданий"), str(sum(r["late"] for r in rows))),
        ],
        columns=[
            Column(_("Ученик"), lambda r: r["student"].full_name, 30),
            Column(_("Группа"), lambda r: r["student"].group.code, 10),
            Column(_("Посещаемость, %"), lambda r: r["pct"], 14),
            Column(_("Без причины"), lambda r: r["absent"], 12),
            Column(_("По уважительной"), lambda r: r["excused"], 14),
            Column(_("Опозданий"), lambda r: r["late"], 12),
        ],
        rows=below,
    )


# --- Академический директор ------------------------------------------------------------


def _fo_by_student(start: dt.date, end: dt.date) -> dict[int, float]:
    """Средний ФО ученика за период в процентах (балл из 10)."""
    from academics.models import Grade, LessonKind

    rows = (
        Grade.objects.filter(lesson__date__gte=start, lesson__date__lte=end, lesson__kind=LessonKind.FO)
        .values("student")
        .annotate(avg=Avg("value"))
    )
    return {row["student"]: float(row["avg"]) * 10 for row in rows}


def grades_parallels(period: str = "") -> Report:
    monday = _monday(_parse_day(period) or _today())
    end = monday + dt.timedelta(days=4)
    fo = _fo_by_student(monday, end)
    students = list(Student.objects.filter(is_active=True, group__isnull=False).select_related("group"))
    by_parallel: dict[int, list[float]] = {}
    below = []
    for student in students:
        value = fo.get(student.pk)
        if value is None:
            continue
        by_parallel.setdefault(student.group.parallel, []).append(value)
        if value < FO_BELOW:
            below.append({"student": student, "fo": round(value)})
    below.sort(key=lambda r: r["fo"])
    lines = []
    for parallel in sorted(by_parallel):
        values = by_parallel[parallel]
        lines.append((_("{n} классы").format(n=parallel), f"{round(sum(values) / len(values))} %"))
    every = [v for values in by_parallel.values() for v in values]
    bars = [
        {
            "parallel": parallel,
            "fo": round(sum(values) / len(values)),
            "below": sum(1 for r in below if r["student"].group.parallel == parallel),
        }
        for parallel, values in sorted(by_parallel.items())
    ]
    lines.append((_("Ниже {n} % по ФО").format(n=FO_BELOW), tn(len(below), "{n} ученик|{n} ученика|{n} учеников")))
    return Report(
        kind="grades_parallels",
        title=_("Успеваемость по параллелям"),
        source=_("ФО по урокам · {span}").format(span=_span(monday, end)),
        period=monday.isoformat(),
        period_title=_span(monday, end),
        summary=_("средний ФО {pct}").format(pct=f"{round(sum(every) / len(every))} %" if every else "—"),
        figures={"fo": round(sum(every) / len(every)) if every else None, "below": len(below), "parallels": bars},
        lines=lines,
        columns=[
            Column(_("Ученик"), lambda r: r["student"].full_name, 30),
            Column(_("Группа"), lambda r: r["student"].group.code, 10),
            Column(_("Параллель"), lambda r: r["student"].group.parallel, 10),
            Column(_("ФО, %"), lambda r: r["fo"], 10),
        ],
        rows=below,
    )


def teacher_rows(start: dt.date, end: dt.date) -> list[dict]:
    """Неотмеченные уроки и непроверенное ДЗ по учителям за период."""
    from academics import calendar as school_calendar
    from academics import schedule
    from academics.payloads import user_name
    from homework.models import Submission

    calendar = school_calendar.load()
    out: dict[int, dict] = {}

    def row(user) -> dict:
        return out.setdefault(
            user.pk,
            {"teacher_id": user.pk, "teacher": user_name(user), "subjects": set(), "lessons": 0, "homework": 0},
        )

    for lesson in schedule.stale_unmarked(calendar, start, end):
        teacher = lesson.substitute or lesson.teacher
        entry = row(teacher)
        entry["lessons"] += 1
        entry["subjects"].add(lesson.course.subject.title)
    unchecked = (
        Submission.objects.filter(
            submitted_at__isnull=False,
            checked_at__isnull=True,
            assignment__lesson__date__gte=start - dt.timedelta(days=7),
            assignment__lesson__date__lte=end,
        )
        .select_related("assignment__lesson__teacher", "assignment__lesson__course__subject")
        .exclude(assignment__lesson__teacher__isnull=True)
    )
    for submission in unchecked:
        lesson = submission.assignment.lesson
        entry = row(lesson.teacher)
        entry["homework"] += 1
        entry["subjects"].add(lesson.course.subject.title)
    rows = [{**r, "subjects": ", ".join(sorted(r["subjects"]))} for r in out.values()]
    rows.sort(key=lambda r: (-(r["lessons"] + r["homework"]), r["teacher"]))
    return rows


def teachers(period: str = "") -> Report:
    monday = _monday(_parse_day(period) or _today())
    end = min(monday + dt.timedelta(days=4), _today())
    rows = teacher_rows(monday, end) if end >= monday else []
    lessons = sum(r["lessons"] for r in rows)
    homework = sum(r["homework"] for r in rows)
    worst = rows[0] if rows else None
    lines = [
        (_("Уроков не отмечено"), _("{n} · учителей: {t}").format(n=lessons, t=sum(1 for r in rows if r["lessons"]))),
        (_("ДЗ не проверено"), tn(homework, "{n} работа|{n} работы|{n} работ")),
    ]
    if worst is not None:
        lines.append(
            (
                _("Больше всего — {name}").format(name=worst["teacher"]),
                _("уроков: {l} · ДЗ: {h}").format(l=worst["lessons"], h=worst["homework"]),
            )
        )
    return Report(
        kind="teachers",
        title=_("Отчёт по учителям"),
        source=_("журналы и ДЗ · {span}").format(span=_span(monday, monday + dt.timedelta(days=4))),
        period=monday.isoformat(),
        period_title=_span(monday, monday + dt.timedelta(days=4)),
        summary=_("уроков: {l} · ДЗ: {h}").format(l=lessons, h=homework),
        figures={"lessons": lessons, "homework": homework, "teachers": sum(1 for r in rows if r["lessons"])},
        lines=lines,
        columns=[
            Column(_("Учитель"), lambda r: r["teacher"], 28),
            Column(_("Предмет"), lambda r: r["subjects"], 28),
            Column(_("Уроков не отмечено"), lambda r: r["lessons"], 18),
            Column(_("ДЗ не проверено"), lambda r: r["homework"], 16),
        ],
        rows=rows,
    )


def last_mock_date() -> dt.date | None:
    from students.models import AttemptFormat, ExamAttempt

    row = (
        ExamAttempt.objects.filter(attempt_format=AttemptFormat.MOCK, student__is_active=True)
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )
    return row


def mock(period: str = "") -> Report:
    """Mock Test одного дня по 11: средние IELTS и SAT, достигли цели, ниже цели, не пришли."""
    from core.parallels import admission_students
    from directors.results import goal_of, goals_map
    from students.models import AttemptFormat, ExamAttempt

    day = _parse_day(period) or last_mock_date() or _today()
    seniors = list(admission_students(Student.objects.filter(is_active=True)).select_related("group"))
    attempts = list(
        ExamAttempt.objects.filter(
            attempt_format=AttemptFormat.MOCK, date=day, student__in=seniors, total_score__isnull=False
        ).select_related("student", "student__group")
    )
    goals = goals_map([s.pk for s in seniors])
    reached = below = 0
    rows = []
    for attempt in attempts:
        goal = goal_of(goals, attempt.student_id, attempt.exam_type)
        gap = float(goal) - float(attempt.total_score) if goal is not None else None
        if gap is not None and gap <= 0:
            reached += 1
        elif gap is not None and gap >= (1 if attempt.exam_type == "IELTS" else 150):
            below += 1
        rows.append({"attempt": attempt, "goal": goal, "gap": gap})
    took = {a.student_id for a in attempts}
    groups_took = {a.student.group_id for a in attempts}
    absent = sum(1 for s in seniors if s.group_id in groups_took and s.pk not in took)

    def average(exam: str) -> str:
        values = [float(a.total_score) for a in attempts if a.exam_type == exam]
        if not values:
            return _("не сдавали")
        mean = sum(values) / len(values)
        return f"{mean:.1f}" if exam == "IELTS" else str(round(mean))

    return Report(
        kind="mock",
        title=_("Mock Test {date}").format(date=f"{day:%d.%m}"),
        source=_("IELTS и SAT · 11 классы · сдавали {n}").format(n=len(took)),
        period=day.isoformat(),
        period_title=f"{day:%d.%m.%Y}",
        summary=_("сдавали {n}").format(n=len(took)),
        figures={"took": len(took), "date": day.isoformat() if attempts else None, "reached": reached},
        lines=[
            (_("IELTS — средний балл"), average("IELTS")),
            (_("SAT — средний балл"), average("SAT")),
            (_("Достигли цели"), f"{reached} / {len(rows)}"),
            (_("Ниже цели на 1.0 / 150+"), str(below)),
            (_("Не пришли"), str(absent)),
        ],
        columns=[
            Column(_("Ученик"), lambda r: r["attempt"].student.full_name, 30),
            Column(_("Группа"), lambda r: r["attempt"].student.group.code if r["attempt"].student.group_id else "", 10),
            Column(_("Экзамен"), lambda r: r["attempt"].exam_type, 10),
            Column(_("Балл"), lambda r: float(r["attempt"].total_score), 8),
            Column(_("Цель"), lambda r: float(r["goal"]) if r["goal"] is not None else "", 8),
            Column(_("До цели"), lambda r: round(r["gap"], 1) if r["gap"] is not None and r["gap"] > 0 else "", 10),
        ],
        rows=rows,
    )


# --- Реестр видов ----------------------------------------------------------------------

BUILDERS: dict[str, Callable[[str], Report]] = {
    "morning": morning,
    "security": security,
    "parent_reports": parent_reports,
    "calls": calls,
    "attendance_week": attendance_week,
    "grades_parallels": grades_parallels,
    "teachers": teachers,
    "mock": mock,
}

#: вид → вкладка экрана «Отчёты»
TOPICS = {
    "morning": "attendance",
    "security": "attendance",
    "attendance_week": "attendance",
    "parent_reports": "parents",
    "calls": "calls",
    "grades_parallels": "grades",
    "teachers": "teachers",
    "mock": "exams",
}


def build(kind: str, period: str = "") -> Report:
    return BUILDERS[kind](period)


def seen_keys(user) -> set[tuple[str, str]]:
    from directors.models import ReportSeen

    return set(ReportSeen.objects.filter(user=user).values_list("kind", "period"))


def mark_seen(user, kind: str, period: str) -> None:
    from directors.models import ReportSeen

    ReportSeen.objects.get_or_create(user=user, kind=kind, period=period[:16])


def recent_periods(kind: str, count: int = 4) -> list[str]:
    """Последние периоды вида для архива на экране: дни, недели, месяцы."""
    day = _school_day(_today())
    if kind in ("morning", "security"):
        out, cursor = [], day
        while len(out) < count:
            if cursor.weekday() < 5:
                out.append(cursor.isoformat())
            cursor -= dt.timedelta(days=1)
        return out
    if kind == "parent_reports":
        month = day.replace(day=1)
        out = []
        for _i in range(count):
            out.append(f"{month:%Y-%m}")
            month = (month - dt.timedelta(days=1)).replace(day=1)
        return out
    if kind == "mock":
        from students.models import AttemptFormat, ExamAttempt

        dates = (
            ExamAttempt.objects.filter(attempt_format=AttemptFormat.MOCK, student__is_active=True)
            .order_by("-date")
            .values_list("date", flat=True)
            .distinct()[:count]
        )
        return [d.isoformat() for d in dates]
    monday = _monday(day)
    return [(monday - dt.timedelta(days=7 * i)).isoformat() for i in range(count)]


def _parse_day(raw: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def _parse_month(raw: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(f"{raw}-01") if raw else None
    except ValueError:
        return None


MONTHS = (
    gettext_lazy("январь"),
    gettext_lazy("февраль"),
    gettext_lazy("март"),
    gettext_lazy("апрель"),
    gettext_lazy("май"),
    gettext_lazy("июнь"),
    gettext_lazy("июль"),
    gettext_lazy("август"),
    gettext_lazy("сентябрь"),
    gettext_lazy("октябрь"),
    gettext_lazy("ноябрь"),
    gettext_lazy("декабрь"),
)


def _month_title(month: dt.date) -> str:
    return f"{MONTHS[month.month - 1]} {month.year}"
