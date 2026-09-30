"""Отчёты родителям: сборка снимка строками, статусы, «Обновить данные», текст сообщения.

Снимок собирается сборкой и хранится строками `ReportLine`: родитель видит
ровно то, что проверил куратор, и чтение ничего не пересчитывает. Статусы:
`draft → checked → exported → sent`. «Выгружен» ставится сам при скачивании
или «Поделиться»; «отправлен родителям» куратор отмечает вручную.
«Обновить данные» пересобирает снимок и откатывает статус в черновик,
только если данные изменились.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from academics.calendar import SchoolCalendar, date_words, month_title, scale_of, today
from academics.models import (
    ParentReport,
    ReportCadence,
    ReportLine,
    ReportPeriod,
    ReportSection,
    ReportSettings,
    ReportStatus,
    Scheme,
)
from academics.results import student_attendance, student_summary
from core.audit import record_event
from students.models import Student


class ReportRefused(ValueError):
    """С отчётом так нельзя — текст объясняет почему."""


def period_title(kind: str, start: dt.date, end: dt.date, year_title: str = "") -> str:
    """«сентябрь 2026» или «1 четверть 2026–2027»."""
    if kind == ReportPeriod.MONTH:
        return month_title(start)
    return f"{_quarter_number(start, end)} четверть {year_title}".strip()


def _quarter_number(start: dt.date, end: dt.date) -> str:
    from academics.models import Quarter

    row = Quarter.objects.filter(starts=start, ends=end).first()
    return str(row.number) if row else ""


# --- Сборка --------------------------------------------------------------------


def _fmt(value) -> str:
    if value is None:
        return "нет"
    if isinstance(value, float):
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return str(value)


#: подпись первой строки посещаемости; по ней же список отчётов берёт процент
ATTENDANCE_ROW = "Присутствие на уроках"

#: у предмета нет ни одной оценки за период — одна фраза на строку
NO_GRADES = "оценок пока нет"


def _clip(text: str, limit: int) -> str:
    """Обрезать по границе слова: «Рекомендательн» в отчёте родителям — брак."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rstrip()
    cut = cut[: cut.rfind(" ")] if " " in cut else cut
    return cut.rstrip(" ,;") + "…"


def build_lines(
    student: Student, *, start: dt.date, end: dt.date, calendar: SchoolCalendar, config: ReportSettings, quarter=None
) -> list[dict]:
    """Строки снимка по разделам из настроек. Комментариев учителей нет — решение владельца.

    У 8–10 разделов «Экзамены и вузы» и «Документы» нет: поступление
    ведётся только у 11 (`core/parallels.py`), и пустой раздел в отчёте
    родителям читался бы как недоработка ребёнка.
    """
    from core.parallels import has_admission

    graduate = has_admission(student)
    lines: list[dict] = []
    scale = scale_of(calendar.year)
    order = 0

    def add(section: str, title: str, value: str, note: str = "") -> None:
        nonlocal order
        order += 1
        lines.append(
            {"section": section, "order": order, "title": title[:120], "value": value[:120], "note": note[:300]}
        )

    if config.section_attendance:
        totals = student_attendance(student.pk, start, min(end, today()))
        if totals.total:
            # подпись строки не повторяет заголовок раздела «Посещаемость»
            # процент — по минутам урока (`results.Presence`): опоздание на 10 минут
            # из 40 — это 75 % урока, а не целый урок
            add(
                ReportSection.ATTENDANCE,
                ATTENDANCE_ROW,
                f"{totals.pct} %" if totals.pct is not None else "нет",
                f"уроков с отметкой: {totals.total}, по минутам урока",
            )
            add(ReportSection.ATTENDANCE, "Пропуски без причины", str(totals.absent))
            add(ReportSection.ATTENDANCE, "По уважительной причине", str(totals.excused))
            add(ReportSection.ATTENDANCE, "Опоздания", str(totals.late))
            if totals.late:
                add(
                    ReportSection.ATTENDANCE,
                    "Минут опозданий",
                    str(totals.late_minutes),
                    f"без времени прихода: {totals.late_unknown}" if totals.late_unknown else "",
                )
        else:
            add(ReportSection.ATTENDANCE, "Уроков с отметкой", "пока не было")

    if config.section_grades:
        for item in student_summary(student.pk, start, min(end, today()), scale, quarter=quarter):
            course, stats = item["course"], item["stats"]
            missed = stats.absent + stats.excused
            if course.subject.scheme == Scheme.FO:
                value = f"ФО {_fmt(stats.fo_avg)}" if stats.fo_avg is not None else NO_GRADES
                add(ReportSection.GRADES, course.subject.title, value, f"пропусков {missed}" if missed else "")
                continue
            parts = []
            if stats.fo_avg is not None:
                parts.append(f"ФО {_fmt(stats.fo_avg)}")
            if stats.sor_max:
                parts.append(f"СОР {stats.sor_got} из {stats.sor_max}")
            if stats.soch_max:
                parts.append(f"СОЧ {stats.soch_got} из {stats.soch_max}")
            if stats.final is not None:
                value = f"итог {stats.final}"
            elif stats.quarter_grade is not None:
                value = f"сейчас выходит {stats.quarter_grade}"
            elif parts:
                value = "оценок пока мало"
            else:
                # одна фраза, а не «оценок пока мало» рядом с «оценок нет»
                add(ReportSection.GRADES, course.subject.title, NO_GRADES)
                continue
            add(ReportSection.GRADES, course.subject.title, value, ", ".join(parts))

    if config.section_exams and graduate:
        exam = getattr(student, "exam", None)
        if exam is not None:
            if exam.ielts_current is not None or exam.ielts_target is not None:
                add(
                    ReportSection.EXAMS,
                    "IELTS",
                    _fmt(float(exam.ielts_current)) if exam.ielts_current is not None else "ещё не сдавал",
                    f"цель {_fmt(float(exam.ielts_target))}" if exam.ielts_target is not None else "",
                )
            if exam.sat_current is not None or exam.sat_target is not None:
                add(
                    ReportSection.EXAMS,
                    "SAT",
                    str(exam.sat_current) if exam.sat_current is not None else "ещё не сдавал",
                    f"цель {exam.sat_target}" if exam.sat_target is not None else "",
                )
        from universities.models import StudentUniversity

        unis = list(
            StudentUniversity.objects.filter(student=student)
            .select_related("program", "program__university")
            .order_by("-is_priority", "id")[:5]
        )
        if unis:
            add(
                ReportSection.EXAMS,
                "Вузы в списке",
                str(len(unis)),
                ", ".join(row.program.university.name for row in unis if row.program_id and row.program.university_id)[
                    :300
                ],
            )
        if not lines or lines[-1]["section"] != ReportSection.EXAMS:
            add(ReportSection.EXAMS, "Результаты и вузы", "пока не внесены")

    if config.section_documents and graduate:
        from students import documents
        from students.portfolio import REQUIRED_DOCUMENTS

        state = documents.state_of(Student.objects.filter(pk=student.pk)).get(student.pk)
        if state:
            add(ReportSection.DOCUMENTS, "Собрано", f"{state['collected']} из {state['total']}")
            titles = {row["code"]: row["title"] for row in documents.types()}
            missing = [
                titles.get(code, code)
                for code in REQUIRED_DOCUMENTS
                if state["cells"][code]["state"] in ("none", "bad")
            ]
            if missing:
                add(ReportSection.DOCUMENTS, "Не хватает", _clip(", ".join(missing), 120))

    if config.section_discipline:
        from students.models import BehaviorRemark

        remarks = BehaviorRemark.objects.filter(student=student, date__gte=start, date__lte=end).count()
        add(ReportSection.DISCIPLINE, "Замечания", str(remarks) if remarks else "нет")

    return lines


def fingerprint_of(lines: list[dict]) -> str:
    digest = hashlib.sha256()
    for line in lines:
        digest.update(f"{line['section']}|{line['title']}|{line['value']}|{line['note']}\n".encode())
    return digest.hexdigest()


@transaction.atomic
def build_report(
    student: Student,
    *,
    kind: str,
    start: dt.date,
    end: dt.date,
    calendar: SchoolCalendar,
    config: ReportSettings,
    quarter=None,
    actor=None,
) -> ParentReport:
    """Собрать или пересобрать отчёт ученика за период.

    Повторная сборка меняет снимок и откатывает статус в черновик только
    при изменении данных; слово куратора и отметки остаются.
    """
    lines = build_lines(student, start=start, end=end, calendar=calendar, config=config, quarter=quarter)
    digest = fingerprint_of(lines)
    year_title = calendar.year.title if calendar.year else ""
    report = ParentReport.objects.filter(student=student, period_kind=kind, period_start=start).first()
    now = timezone.now()
    if report is None:
        report = ParentReport.objects.create(
            student=student,
            period_kind=kind,
            period_start=start,
            period_end=end,
            title=period_title(kind, start, end, year_title),
            built_at=now,
            fingerprint=digest,
        )
        changed = True
    else:
        changed = report.fingerprint != digest
        report.built_at = now
        report.period_end = end
        report.title = period_title(kind, start, end, year_title)
        if changed:
            report.fingerprint = digest
            if report.status != ReportStatus.DRAFT:
                report.status = ReportStatus.DRAFT
                report.checked_at = None
                report.checked_by = None
        report.save()
    if changed:
        ReportLine.objects.filter(report=report).delete()
        ReportLine.objects.bulk_create([ReportLine(report=report, **line) for line in lines])
        record_event(student=student, code="report_built", text=f"за {report.title}", actor=actor)
    return report


def build_for_period(
    *, kind: str, start: dt.date, end: dt.date, calendar: SchoolCalendar, quarter=None, students=None, actor=None
) -> list[ParentReport]:
    """Собрать отчёты всем действующим ученикам (или переданным) за период."""
    config = report_settings(calendar)
    rows = students if students is not None else Student.objects.filter(is_active=True).select_related("exam", "group")
    out = []
    from academics import cache

    with cache.scope():
        for student in rows:
            out.append(
                build_report(
                    student,
                    kind=kind,
                    start=start,
                    end=end,
                    calendar=calendar,
                    config=config,
                    quarter=quarter,
                    actor=actor,
                )
            )
    return out


def word_on(report: ParentReport) -> bool:
    """Включён ли раздел «Слово куратора» в настройках отчётов года периода.

    Выключен — слово не печатается в PDF и не предлагается к правке на экране;
    написанное раньше не стирается: включат раздел — оно вернётся.
    """
    from academics.calendar import current_year, report_settings_of
    from academics.models import AcademicYear

    year = (
        AcademicYear.objects.filter(starts__lte=report.period_start, ends__gte=report.period_start).first()
        or current_year()
    )
    return report_settings_of(year).section_curator


def report_settings(calendar: SchoolCalendar) -> ReportSettings:
    if calendar.year is None:
        return ReportSettings()
    row, _ = ReportSettings.objects.get_or_create(year=calendar.year)
    return row


def month_bounds(day: dt.date) -> tuple[dt.date, dt.date]:
    first = day.replace(day=1)
    last = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return first, last


def is_last_friday(day: dt.date) -> bool:
    return day.weekday() == 4 and (day + dt.timedelta(days=7)).month != day.month


def notify_curators(reports: list[ParentReport], period: str) -> int:
    """Куратору каждой группы — одно уведомление: «отчёты собраны, N ждут проверки»."""
    from accounts.curators import active_assignments
    from core.models import Notification
    from materials.services import notify

    by_group: dict[int, int] = {}
    for report in reports:
        if report.status == ReportStatus.DRAFT and report.student.group_id:
            by_group[report.student.group_id] = by_group.get(report.student.group_id, 0) + 1
    sent = 0
    for row in active_assignments().filter(group_id__in=list(by_group)).select_related("curator"):
        notify(
            row.curator,
            kind=Notification.Kind.REPORTS_BUILT,
            template="Отчёты родителям за {period} собраны: {count} ждут проверки",
            link="/reports",
            period=period,
            count=by_group[row.group_id],
        )
        sent += 1
    return sent


# --- Статусы ---------------------------------------------------------------------


def set_word(report: ParentReport, *, actor, curator_word: str) -> bool:
    """Записать слово и кто его написал. Возвращает, изменилось ли слово."""
    word = curator_word.strip()[:2000]
    if word == report.curator_word:
        return False
    report.curator_word = word
    report.word_by = actor if getattr(actor, "pk", None) else None
    report.word_at = timezone.now() if word else None
    return True


@transaction.atomic
def check(report: ParentReport, *, actor, curator_word: str | None = None) -> ParentReport:
    """«Проверено»: слово куратора записано, отчёт готов к выгрузке."""
    if curator_word is not None:
        set_word(report, actor=actor, curator_word=curator_word)
    if report.status == ReportStatus.DRAFT:
        report.status = ReportStatus.CHECKED
        report.checked_at = timezone.now()
        report.checked_by = actor if getattr(actor, "pk", None) else None
        record_event(student=report.student, code="report_checked", text=f"за {report.title}", actor=actor)
    report.save()
    return report


@transaction.atomic
def mark_exported(report: ParentReport, *, actor) -> ParentReport:
    """Скачали или поделились: статус «выгружен» с датой. Черновик выгружать нельзя."""
    if report.status == ReportStatus.DRAFT:
        raise ReportRefused("Сначала проверьте отчёт: черновик не выгружается")
    if report.status == ReportStatus.CHECKED:
        report.status = ReportStatus.EXPORTED
        record_event(student=report.student, code="report_exported", text=f"за {report.title}", actor=actor)
    report.exported_at = timezone.now()
    report.save(update_fields=["status", "exported_at"])
    return report


@transaction.atomic
def mark_sent(report: ParentReport, *, actor, sent: bool = True) -> ParentReport:
    """Отметка «отправлен родителям» — руками, после мессенджера."""
    if sent:
        if report.status == ReportStatus.DRAFT:
            raise ReportRefused("Сначала проверьте и выгрузите отчёт")
        report.status = ReportStatus.SENT
        report.sent_at = timezone.now()
        report.sent_by = actor if getattr(actor, "pk", None) else None
        record_event(student=report.student, code="report_sent", text=f"за {report.title}", actor=actor)
    else:
        report.status = ReportStatus.EXPORTED if report.exported_at else ReportStatus.CHECKED
        report.sent_at = None
        report.sent_by = None
        record_event(student=report.student, code="report_unsent", text=f"за {report.title}", actor=actor)
    report.save()
    return report


# --- Файлы и сообщение -----------------------------------------------------------


def file_stem(report: ParentReport) -> str:
    """«Фамилия Имя — отчёт за сентябрь 2026»."""
    student = report.student
    return f"{student.last_name} {student.first_name} — отчёт за {report.title}"


def zip_name(group_code: str, title: str) -> str:
    return f"{group_code} — отчёты за {title}.zip"


def parent_phones(student: Student) -> list[dict]:
    """Телефоны родителей, основной первым."""
    from students.models import ParentContact

    return [
        {
            "name": row.full_name,
            "relation": row.get_relation_display(),
            "phone": row.phone,
            "is_primary": row.is_primary,
        }
        for row in ParentContact.objects.filter(student=student).exclude(phone="").order_by("-is_primary", "full_name")
    ]


def message_text(report: ParentReport, curator_name: str) -> str:
    """«Добрый день! Отчёт BHS за сентябрь по ученику Фамилия Имя во вложении. Куратор группы BOSTON, Имя»."""
    student = report.student
    period = report.title
    if report.period_kind == ReportPeriod.MONTH:
        period = period.split(" ")[0]
    group = student.group.code if student.group_id else ""
    school = getattr(settings, "SCHOOL_SHORT_NAME", "") or getattr(settings, "SCHOOL_NAME", "")
    first = (curator_name or "").split(" ")[0] if curator_name else ""
    return (
        f"Добрый день! Отчёт {school} за {period} по ученику {student.last_name} {student.first_name} во вложении. "
        f"Куратор группы {group}, {first}".strip().rstrip(",")
    )


def cadence_words(config: ReportSettings) -> str:
    if config.cadence == ReportCadence.QUARTER:
        return "только после закрытия четверти"
    return "последняя пятница месяца, 08:00; после закрытия четверти"


def period_words(start: dt.date, end: dt.date) -> str:
    return f"{date_words(start)} — {date_words(end)}"
