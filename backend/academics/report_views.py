"""Отчёты родителям: список, проверка, слово куратора, обновление, PDF, ZIP, отметка об отправке."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics import calendar as school_calendar
from academics import reports as reporting
from academics import rights
from academics.cache import cached
from academics.calendar import scale_of, today
from academics.models import ParentReport, ReportPeriod, ReportSection, ReportStatus
from academics.payloads import student_brief, user_name
from academics.results import calendar_period
from academics.views import _bad, _forbid, _group_param, _int, _not_found
from accounts.curators import curated_group_ids, curator_of
from core.domains import ROLE_CURATOR
from core.exports import file_response
from core.scope import visible_students
from students.models import Student, StudyGroup


def _reader(request) -> Response | None:
    if not rights.reads_reports(request.user.role):
        return _forbid("Отчёты родителям делают куратор, академический директор, директор школы и администратор")
    return None


def _writer(request) -> Response | None:
    if not rights.writes_reports(request.user.role):
        return _forbid("Отчёты родителям делают куратор, академический директор, директор школы и администратор")
    return None


def _report_for(user, pk: int) -> ParentReport | None:
    row = ParentReport.objects.select_related("student", "student__group", "student__exam").filter(pk=pk).first()
    if row is None or not visible_students(user).filter(pk=row.student_id).exists():
        return None
    return row


def _curator_name(student: Student) -> str:
    assignment = curator_of(student.group) if student.group_id else None
    return user_name(assignment.curator) if assignment else ""


def _summary_chip(report: ParentReport) -> dict:
    lines = [line for line in report.lines.all() if line.section == ReportSection.GRADES]
    twos = [line.title for line in lines if line.value.endswith(" 2") or line.value == "итог 2"]
    threes = [line for line in lines if line.value.endswith(" 3") or line.value == "итог 3"]
    if twos:
        return {"text": "двойка: " + ", ".join(t.lower() for t in twos)[:60], "tone": "bad"}
    if threes:
        return {"text": f"троек: {len(threes)}", "tone": "warn"}
    if lines:
        return {"text": "без троек", "tone": "good"}
    return {"text": "оценок мало", "tone": "neutral"}


def _attendance_value(report: ParentReport) -> str:
    for line in report.lines.all():
        # «Посещаемость» — подпись снимков, собранных до переименования строки
        if line.section == ReportSection.ATTENDANCE and line.title in (reporting.ATTENDANCE_ROW, "Посещаемость"):
            return line.value
    return ""


def report_row(report: ParentReport) -> dict:
    student = report.student
    return {
        "id": report.pk,
        "student": student_brief(student),
        "title": report.title,
        "period_kind": report.period_kind,
        "period_start": report.period_start,
        "status": report.status,
        "status_title": report.get_status_display(),
        "built_at": report.built_at,
        "checked_at": report.checked_at,
        "exported_at": report.exported_at,
        "sent_at": report.sent_at,
        "has_word": bool(report.curator_word.strip()),
        "attendance": _attendance_value(report),
        "grades": _summary_chip(report),
        "phones": reporting.parent_phones(student),
    }


def report_detail(report: ParentReport, user) -> dict:
    student = report.student
    curator = _curator_name(student)
    sections = []
    for code, title in ReportSection.choices:
        lines = [line for line in report.lines.all() if line.section == code]
        if lines:
            sections.append(
                {
                    "code": code,
                    "title": title,
                    "lines": [{"title": line.title, "value": line.value, "note": line.note} for line in lines],
                }
            )
    return {
        **report_row(report),
        "sections": sections,
        "curator_word": report.curator_word,
        "curator": curator,
        "message": reporting.message_text(report, user_name(user) if user.role == ROLE_CURATOR else curator),
        "may_write": rights.writes_reports(user.role),
        "file_name": reporting.file_stem(report) + ".pdf",
        "checked_by": user_name(report.checked_by) if report.checked_by_id else "",
        "sent_by": user_name(report.sent_by) if report.sent_by_id else "",
        # кто написал слово и когда — видно в отчёте (решение владельца, 27.09.2026)
        "word_by": user_name(report.word_by) if report.word_by_id else "",
        "word_at": report.word_at,
    }


def _periods_available(students) -> list[dict]:
    rows = (
        ParentReport.objects.filter(student__in=students)
        .values("period_kind", "period_start", "title")
        .distinct()
        .order_by("-period_start")
    )
    seen = []
    for row in rows:
        code = f"{row['period_kind']}:{row['period_start']}"
        if code not in {s["code"] for s in seen}:
            seen.append({"code": code, "title": row["title"], "kind": row["period_kind"]})
    return seen


def _pick_period(raw: str, available: list[dict]) -> tuple[str, str] | None:
    if raw and ":" in raw:
        kind, start = raw.split(":", 1)
        return kind, start
    if available:
        kind, start = available[0]["code"].split(":", 1)
        return kind, start
    return None


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def reports(request):
    """Список отчётов по группе и периоду со статусами."""
    refusal = _reader(request)
    if refusal:
        return refusal
    user = request.user
    students = visible_students(user).filter(is_active=True)
    groups = StudyGroup.objects.filter(is_active=True).order_by("code")
    if user.role == ROLE_CURATOR:
        groups = groups.filter(pk__in=curated_group_ids(user))
    picked = _group_param(request.query_params.get("group"))
    if picked is not None:
        if picked.pk not in {g.pk for g in groups}:
            return _not_found()
        students = students.filter(group=picked)
    available = _periods_available(students)
    period = _pick_period(str(request.query_params.get("period") or ""), available)
    rows = []
    if period is not None:
        kind, start = period
        rows = list(
            ParentReport.objects.filter(student__in=students, period_kind=kind, period_start=start)
            .select_related("student", "student__group")
            .prefetch_related("lines")
            .order_by("student__group__code", "student__last_name", "student__first_name")
        )
    status_filter = str(request.query_params.get("status") or "")
    shown = [r for r in rows if not status_filter or r.status == status_filter]
    calendar = school_calendar.load()
    config = school_calendar.report_settings_of(calendar.year)
    return Response(
        {
            "group": picked.code if picked else "all",
            "groups": [{"id": g.pk, "code": g.code} for g in groups],
            "periods": available,
            "period": {"code": f"{period[0]}:{period[1]}", "title": rows[0].title if rows else ""} if period else None,
            "rows": [report_row(r) for r in shown],
            "counts": {
                "total": len(rows),
                "draft": sum(1 for r in rows if r.status == ReportStatus.DRAFT),
                "checked": sum(1 for r in rows if r.status == ReportStatus.CHECKED),
                "exported": sum(1 for r in rows if r.status == ReportStatus.EXPORTED),
                "sent": sum(1 for r in rows if r.status == ReportStatus.SENT),
                "no_phone": sum(1 for r in rows if not reporting.parent_phones(r.student)),
            },
            "built_at": rows[0].built_at if rows else None,
            "cadence": reporting.cadence_words(config),
            "next_quarter_end": calendar.current_quarter().ends if calendar.current_quarter() else None,
            "may_write": rights.writes_reports(user.role),
            "may_build": rights.writes_reports(user.role),
            "statuses": [{"code": c, "title": t} for c, t in ReportStatus.choices],
        }
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def reports_build(request):
    """Собрать отчёты за период руками — по группе или по одному ученику.

    Делают четыре роли (решение владельца, 27.09.2026): куратор — по своим
    группам, Кымбат, Салтанат и администратор — по всем. Обычно отчёты
    собирает расписание; `student` — отчёт на одного ученика.
    """
    refusal = _writer(request)
    if refusal:
        return refusal
    calendar = school_calendar.load()
    period = _period_of(calendar, str(request.data.get("period") or ""))
    if period is None:
        return _bad("Такой четверти нет")
    kind, start, end, title, quarter = period
    students = visible_students(request.user).filter(is_active=True).select_related("exam", "group")
    picked = _group_param(request.data.get("group"))
    if picked is not None:
        if request.user.role == ROLE_CURATOR and picked.pk not in curated_group_ids(request.user):
            return _not_found()
        students = students.filter(group=picked)
    one = _int(request.data.get("student"))
    if one is not None:
        students = students.filter(pk=one)
        if not students.exists():
            return _not_found()
    rows = reporting.build_for_period(
        kind=kind, start=start, end=end, calendar=calendar, quarter=quarter, students=students, actor=request.user
    )
    if rows and one is None:
        reporting.notify_curators(rows, rows[0].title)
    return Response(
        {"built": len(rows), "title": rows[0].title if rows else title, "report": rows[0].pk if one and rows else None}
    )


def _period_of(calendar, code: str):
    """Период по коду: `qN` — четверть, `ГГГГ-ММ` или пусто — месяц."""
    if code.startswith("q"):
        start, end, title, quarter = calendar_period(calendar, code)
        if quarter is None:
            return None
        return ReportPeriod.QUARTER, start, end, title, quarter
    start, end, title, quarter = calendar_period(calendar, code or f"{today().year}-{today().month:02d}")
    return ReportPeriod.MONTH, start, end, title, None


def _each(request, ids: list[int]):
    """Отчёты из списка, которые видны и есть; чужие и пропавшие молча пропускаются."""
    for pk in ids:
        row = _report_for(request.user, pk)
        if row is not None:
            yield row


@extend_schema(responses={200: dict})
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@cached
def report(request, pk: int):
    """Отчёт целиком; PATCH — слово куратора."""
    refusal = _reader(request)
    if refusal:
        return refusal
    row = _report_for(request.user, pk)
    if row is None:
        return _not_found()
    if request.method == "PATCH":
        refusal = _writer(request)
        if refusal:
            return refusal
        if row.status == ReportStatus.SENT:
            return _bad("Отчёт уже отправлен родителям: слово не меняется")
        if reporting.set_word(row, actor=request.user, curator_word=str(request.data.get("curator_word") or "")):
            row.save(update_fields=["curator_word", "word_by", "word_at"])
    return Response(report_detail(row, request.user))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def report_check(request, pk: int):
    """«Проверено»: слово записано, статус «проверен»."""
    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    row = _report_for(request.user, pk)
    if row is None:
        return _not_found()
    word = request.data.get("curator_word")
    reporting.check(row, actor=request.user, curator_word=str(word) if word is not None else None)
    return Response(report_detail(row, request.user))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def report_refresh(request, pk: int):
    """«Обновить данные»: пересобрать снимок; статус откатывается только при изменении."""
    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    row = _report_for(request.user, pk)
    if row is None:
        return _not_found()
    calendar = school_calendar.load()
    quarter = None
    if row.period_kind == ReportPeriod.QUARTER:
        quarter = next((q for q in calendar.quarters if q.starts == row.period_start), None)
    before = row.fingerprint
    row = reporting.build_report(
        row.student,
        kind=row.period_kind,
        start=row.period_start,
        end=row.period_end,
        calendar=calendar,
        config=reporting.report_settings(calendar),
        quarter=quarter,
        actor=request.user,
    )
    return Response({"changed": before != row.fingerprint, **report_detail(row, request.user)})


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def report_pdf(request, pk: int):
    """PDF одного отчёта; скачивание ставит «выгружен». Черновик — 400."""
    from academics.pdf import render

    refusal = _reader(request)
    if refusal:
        return refusal
    row = _report_for(request.user, pk)
    if row is None:
        return _not_found()
    if request.user.role == ROLE_CURATOR or rights.edits_schedule(request.user.role):
        try:
            reporting.mark_exported(row, actor=request.user)
        except reporting.ReportRefused as error:
            return _bad(str(error))
    content = render(row, curator_name=_curator_name(row.student))
    return file_response(content=content, filename=reporting.file_stem(row) + ".pdf", content_type="application/pdf")


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def reports_zip(request):
    """ZIP по группе или по отмеченным — только проверенные; каждый помечается выгруженным."""
    from academics.pdf import render_zip

    refusal = _reader(request)
    if refusal:
        return refusal
    user = request.user
    students = visible_students(user).filter(is_active=True)
    picked = _group_param(request.query_params.get("group"))
    if picked is not None:
        if user.role == ROLE_CURATOR and picked.pk not in curated_group_ids(user):
            return _not_found()
        students = students.filter(group=picked)
    ids = [int(i) for i in str(request.query_params.get("ids") or "").split(",") if i.strip().isdigit()]
    rows = (
        ParentReport.objects.filter(student__in=students)
        .exclude(status=ReportStatus.DRAFT)
        .select_related("student", "student__group")
        .prefetch_related("lines")
    )
    if ids:
        rows = rows.filter(pk__in=ids)
    else:
        available = _periods_available(students)
        period = _pick_period(str(request.query_params.get("period") or ""), available)
        if period is None:
            return _not_found()
        rows = rows.filter(period_kind=period[0], period_start=period[1])
    rows = list(rows.order_by("student__group__code", "student__last_name"))
    if not rows:
        return _bad("Проверенных отчётов нет: в архив входят только проверенные")
    for row in rows:
        reporting.mark_exported(row, actor=user)
    curators = {}
    for row in rows:
        if row.student.group_id and row.student.group_id not in curators:
            curators[row.student.group_id] = _curator_name(row.student)
    content = render_zip(rows, curators=curators)
    group_code = picked.code if picked else "Все группы"
    return file_response(
        content=content, filename=reporting.zip_name(group_code, rows[0].title), content_type="application/zip"
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def report_sent(request, pk: int):
    """Отметка «отправлен родителям» — или снять её."""
    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    row = _report_for(request.user, pk)
    if row is None:
        return _not_found()
    try:
        reporting.mark_sent(row, actor=request.user, sent=bool(request.data.get("sent", True)))
    except reporting.ReportRefused as error:
        return _bad(str(error))
    return Response(report_detail(row, request.user))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def reports_check(request):
    """«Проверено» для всех отмеченных."""
    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    ids = [int(i) for i in (request.data.get("ids") or []) if str(i).isdigit()]
    done = 0
    for row in _each(request, ids):
        if row.status == ReportStatus.DRAFT:
            reporting.check(row, actor=request.user)
            done += 1
    return Response({"checked": done})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def reports_refresh(request):
    """«Обновить данные» для всех отмеченных: пересобрать снимки."""
    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    ids = [int(i) for i in (request.data.get("ids") or []) if str(i).isdigit()]
    calendar = school_calendar.load()
    config = reporting.report_settings(calendar)
    changed = 0
    total = 0
    for row in _each(request, ids):
        quarter = None
        if row.period_kind == ReportPeriod.QUARTER:
            quarter = next((q for q in calendar.quarters if q.starts == row.period_start), None)
        before = row.fingerprint
        fresh = reporting.build_report(
            row.student,
            kind=row.period_kind,
            start=row.period_start,
            end=row.period_end,
            calendar=calendar,
            config=config,
            quarter=quarter,
            actor=request.user,
        )
        total += 1
        changed += int(before != fresh.fingerprint)
    return Response({"refreshed": total, "changed": changed})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def reports_sent(request):
    """Отметить отправленными списком."""
    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    ids = [int(i) for i in (request.data.get("ids") or []) if str(i).isdigit()]
    done = 0
    skipped = []
    for row in _each(request, ids):
        try:
            reporting.mark_sent(row, actor=request.user, sent=True)
            done += 1
        except reporting.ReportRefused:
            skipped.append(row.student.full_name)
    return Response({"sent": done, "skipped": skipped})


def _unused():  # pragma: no cover
    return scale_of, http
