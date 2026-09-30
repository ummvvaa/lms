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
from academics.models import (
    DraftState,
    ParentReport,
    ReportPeriod,
    ReportReview,
    ReportSection,
    ReportStatus,
    ReportTemplate,
    ReviewKind,
)
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
        "template": report.template,
        "template_title": report.get_template_display(),
        "language": report.language,
        "draft_state": report.draft_state,
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


def _school_detail(report: ParentReport) -> dict:
    """Отчёт по шаблону школы: данные снимка, тексты, отзывы, пометки куратору."""
    from academics import school_reports

    lines = list(report.lines.all())

    def rows(section: str) -> list[dict]:
        return [
            {"code": line.code, "title": line.title, "value": line.value, "note": line.note}
            for line in lines
            if line.section == section
        ]

    return {
        "attendance": rows(ReportSection.ATTENDANCE),
        "grades": rows(ReportSection.GRADES),
        "ielts": rows(ReportSection.IELTS),
        "sat": rows(ReportSection.SAT),
        "profile": rows(ReportSection.PROFILE),
        "texts": {"mock_comment": report.mock_comment, "character": report.character, "summary": report.summary},
        "reviews": [
            {
                "id": row.pk,
                "kind": row.kind,
                "kind_title": row.get_kind_display(),
                "teacher": row.teacher_name,
                "subject": row.subject_title,
                "text": row.text,
                "by_ai": row.by_ai,
                "removable": row.kind == ReviewKind.SUBJECT,
            }
            for row in report.reviews.all()
        ],
        "gaps": school_reports.gaps(report),
        "draft": {
            "state": report.draft_state,
            "title": report.get_draft_state_display(),
            "note": report.draft_note,
            "at": report.drafted_at,
        },
        # какие тексты есть у варианта: у первого — общий отзыв, у второго — пробник и итоги
        "fields": ["character"] if report.template == ReportTemplate.REVIEW else ["mock_comment", "summary"],
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
        # раздел выключен в настройках отчётов — слово не печатается и не правится
        "word_on": reporting.word_on(report),
        "curator": curator,
        "message": reporting.message_text(report, user_name(user) if user.role == ROLE_CURATOR else curator),
        "may_write": rights.writes_reports(user.role),
        "file_name": reporting.file_stem(report) + ".pdf",
        # стандартный — только PDF; шаблоны школы — PDF и Word из одного docx
        "formats": ["pdf"] if report.template == ReportTemplate.STANDARD else ["pdf", "docx"],
        "school": _school_detail(report) if report.template != ReportTemplate.STANDARD else None,
        # вид и язык видны сверху черновика и переключаются (30.09.2026)
        "language_title": report.get_language_display(),
        "texts_edited": report.texts_edited_at is not None,
        "checked_by": user_name(report.checked_by) if report.checked_by_id else "",
        "sent_by": user_name(report.sent_by) if report.sent_by_id else "",
        # кто написал слово и когда — видно в отчёте (решение владельца, 27.09.2026)
        "word_by": user_name(report.word_by) if report.word_by_id else "",
        "word_at": report.word_at,
    }


LANGUAGE_SHORT = {"ru": "рус", "kk": "қаз"}


def period_code(template: str, language: str, kind: str, start, end) -> str:
    return f"{template}:{language}:{kind}:{start}:{end}"


def period_label(template: str, language: str, title: str) -> str:
    """«сентябрь 2026» у стандартного, «Вариант 2 · қаз · 02.09–18.09.2026» у шаблонов."""
    if template == ReportTemplate.STANDARD:
        return title
    variant = "Вариант 1" if template == ReportTemplate.REVIEW else "Вариант 2"
    return f"{variant} · {LANGUAGE_SHORT.get(language, language)} · {title}"


def _periods_available(students) -> list[dict]:
    rows = (
        ParentReport.objects.filter(student__in=students)
        .values("template", "language", "period_kind", "period_start", "period_end", "title")
        .distinct()
        .order_by("-period_start", "template", "language")
    )
    seen: list[dict] = []
    codes: set[str] = set()
    for row in rows:
        end = row["period_end"]
        # у месяца и четверти конец задан началом: один код на период
        if row["period_kind"] != ReportPeriod.CUSTOM:
            end = ""
        code = period_code(row["template"], row["language"], row["period_kind"], row["period_start"], end)
        if code in codes:
            continue
        codes.add(code)
        seen.append(
            {
                "code": code,
                "title": period_label(row["template"], row["language"], row["title"]),
                "kind": row["period_kind"],
                "template": row["template"],
            }
        )
    return seen


def _pick_period(raw: str, available: list[dict]) -> dict | None:
    """Период из кода; старый код «вид:начало» — стандартный отчёт на русском."""
    code = raw or (available[0]["code"] if available else "")
    if not code:
        return None
    parts = code.split(":")
    if len(parts) == 2:
        parts = [ReportTemplate.STANDARD, "ru", parts[0], parts[1], ""]
    if len(parts) != 5:
        return None
    template, language, kind, start, end = parts
    return {"template": template, "language": language, "kind": kind, "start": start, "end": end}


def _in_period(rows, period: dict):
    rows = rows.filter(
        template=period["template"],
        language=period["language"],
        period_kind=period["kind"],
        period_start=period["start"],
    )
    if period["end"]:
        rows = rows.filter(period_end=period["end"])
    return rows


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
        rows = list(
            _in_period(ParentReport.objects.filter(student__in=students), period)
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
            "groups": [
                {"id": g.pk, "code": g.code, "language": g.language, "language_title": g.get_language_display()}
                for g in groups
            ],
            "periods": available,
            "period": (
                {
                    "code": period_code(
                        period["template"], period["language"], period["kind"], period["start"], period["end"]
                    ),
                    "title": period_label(period["template"], period["language"], rows[0].title) if rows else "",
                    "template": period["template"],
                }
                if period
                else None
            ),
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
            "templates": [{"code": c, "title": t} for c, t in ReportTemplate.choices],
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
    template = str(request.data.get("template") or ReportTemplate.STANDARD)
    if template not in ReportTemplate.values:
        return _bad("Такого вида отчёта нет")
    language = str(request.data.get("language") or "")
    if language and language not in ("ru", "kk"):
        return _bad("Язык отчёта — русский или казахский")
    if template == ReportTemplate.STANDARD:
        period = _period_of(calendar, str(request.data.get("period") or ""))
        if period is None:
            return _bad("Такой четверти нет")
    else:
        period = _custom_period(request.data.get("date_from"), request.data.get("date_to"))
        if isinstance(period, str):
            return _bad(period)
    kind, start, end, title, quarter = period
    students = visible_students(request.user).filter(is_active=True).select_related("exam", "group", "sport")
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
        kind=kind,
        start=start,
        end=end,
        calendar=calendar,
        quarter=quarter,
        students=students,
        actor=request.user,
        template=template,
        language=language,
    )
    if template != ReportTemplate.STANDARD:
        from academics.report_drafts import request_draft

        # черновик текстов — один раз на отчёт; дальше «Написать заново» руками
        for row in rows:
            if row.draft_state == DraftState.NONE:
                request_draft(row, actor=request.user)
    if rows and one is None:
        reporting.notify_curators(rows, rows[0].title)
    return Response(
        {
            "built": len(rows),
            "title": rows[0].title if rows else title,
            "report": rows[0].pk if one and rows else None,
            "period": (
                period_code(template, rows[0].language, kind, start, end if kind == ReportPeriod.CUSTOM else "")
                if rows
                else ""
            ),
        }
    )


def _custom_period(raw_from, raw_to):
    """Период «с — по» отчёта по шаблону школы или текст отказа."""
    import datetime as dt

    try:
        start = dt.date.fromisoformat(str(raw_from or ""))
        end = dt.date.fromisoformat(str(raw_to or ""))
    except ValueError:
        return "Укажите период: дату «с» и дату «по»"
    if end < start:
        return "Дата «по» раньше даты «с»"
    if (end - start).days > 366:
        return "Период длиннее года — выберите короче"
    return ReportPeriod.CUSTOM, start, end, reporting.span_title(start, end), None


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
            return _bad("Отчёт уже отправлен родителям: тексты не меняются")
        if "curator_word" in request.data and reporting.set_word(
            row, actor=request.user, curator_word=str(request.data.get("curator_word") or "")
        ):
            row.save(update_fields=["curator_word", "word_by", "word_at"])
        if row.template != ReportTemplate.STANDARD:
            _save_texts(row, request.data, request.user)
    return Response(report_detail(row, request.user))


#: предел текста в отчёте — абзацы куратора, а не сочинение
TEXT_LIMIT = 4000


def _save_texts(report: ParentReport, data, actor) -> None:
    """Тексты отчёта по шаблону школы: поля отчёта и отзывы учителей."""
    from core.audit import record_event

    changed = []
    for name in ("mock_comment", "character", "summary"):
        if name in data:
            value = str(data.get(name) or "").strip()[:TEXT_LIMIT]
            if value != getattr(report, name):
                setattr(report, name, value)
                changed.append(name)
    if changed:
        report.save(update_fields=changed)
    reviews = data.get("reviews")
    if isinstance(reviews, list):
        own = {row.pk: row for row in report.reviews.all()}
        for item in reviews:
            if not isinstance(item, dict) or _int(item.get("id")) not in own:
                continue
            row = own[_int(item.get("id"))]
            value = str(item.get("text") or "").strip()[:TEXT_LIMIT]
            if value != row.text:
                row.text = value
                row.by_ai = False
                row.save(update_fields=["text", "by_ai"])
                changed.append(f"review:{row.pk}")
    if changed:
        from django.utils import timezone

        report.texts_edited_at = timezone.now()
        report.save(update_fields=["texts_edited_at"])
        record_event(student=report.student, code="report_texts", text=f"за {report.title}", actor=actor)


@extend_schema(request=None, responses={200: dict})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@cached
def report_review(request, pk: int, review_id: int):
    """Убрать блок отзыва учителя другого предмета; три постоянных блока не убираются."""
    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    row = _report_for(request.user, pk)
    if row is None:
        return _not_found()
    if row.status == ReportStatus.SENT:
        return _bad("Отчёт уже отправлен родителям: тексты не меняются")
    review = ReportReview.objects.filter(report=row, pk=review_id).first()
    if review is None:
        return _not_found()
    if review.kind != ReviewKind.SUBJECT:
        return _bad("Постоянный блок не убирается — оставьте его пустым, и он не попадёт в файл")
    review.delete()
    return Response(report_detail(row, request.user))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def report_draft(request, pk: int):
    """«Написать заново»: ИИ пишет тексты по данным отчёта, правка куратора заменяется."""
    from academics.report_drafts import request_draft

    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    row = _report_for(request.user, pk)
    if row is None:
        return _not_found()
    if row.template == ReportTemplate.STANDARD:
        return _bad("У стандартного отчёта черновика нет")
    if row.status == ReportStatus.SENT:
        return _bad("Отчёт уже отправлен родителям: тексты не меняются")
    request_draft(row, actor=request.user, overwrite=True)
    row.refresh_from_db()
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
    """«Обновить данные»: заново посещаемость, оценки, комментарии и пробники за период.

    Снимок пересобирается всегда; статус откатывается только при изменении.
    У шаблона школы тексты пишутся заново по свежим данным — но правку
    куратора без спроса не затирает: ответ `needs_confirm`, и экран
    спрашивает «Перезаписать мои правки?»; `overwrite` — ответ «да».
    """
    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    row = _report_for(request.user, pk)
    if row is None:
        return _not_found()
    before = row.fingerprint
    row = _rebuild(row, request.user)
    overwrite = str(request.data.get("overwrite") or "").lower() in ("1", "true")
    needs_confirm = False
    redrafting = False
    if row.template != ReportTemplate.STANDARD and row.status != ReportStatus.SENT:
        from academics.report_drafts import request_draft

        if row.texts_edited_at is not None and not overwrite:
            needs_confirm = True
        else:
            request_draft(row, actor=request.user, overwrite=True)
            redrafting = True
        row.refresh_from_db()
    return Response(
        {
            "changed": before != row.fingerprint,
            "needs_confirm": needs_confirm,
            "redrafting": redrafting,
            **report_detail(row, request.user),
        }
    )


def _rebuild(row: ParentReport, actor) -> ParentReport:
    """Пересобрать снимок отчёта за его период, вид и язык."""
    calendar = school_calendar.load()
    quarter = None
    if row.period_kind == ReportPeriod.QUARTER:
        quarter = next((q for q in calendar.quarters if q.starts == row.period_start), None)
    from academics import cache

    # отдельный кэш: отметки и оценки читаются заново, а не из того, что уже
    # прочитал этот запрос
    with cache.scope():
        return reporting.build_report(
            row.student,
            kind=row.period_kind,
            start=row.period_start,
            end=row.period_end,
            calendar=calendar,
            config=reporting.report_settings(calendar),
            quarter=quarter,
            actor=actor,
            template=row.template,
            language=row.language,
        )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def report_switch(request, pk: int):
    """Другой вид или язык того же отчёта: тот же ученик и период, черновик собирается заново.

    Прежний отчёт остаётся как был. Стандартный отчёт — месяц или четверть:
    период «с — по» переводится в четверть, если совпал с ней, иначе в месяц
    начала периода. Стандартный — только на русском.
    """
    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    row = _report_for(request.user, pk)
    if row is None:
        return _not_found()
    template = str(request.data.get("template") or row.template)
    if template not in ReportTemplate.values:
        return _bad("Такого вида отчёта нет")
    language = str(request.data.get("language") or row.language)
    if language not in ("ru", "kk"):
        return _bad("Язык отчёта — русский или казахский")
    calendar = school_calendar.load()
    quarter = None
    if template == ReportTemplate.STANDARD:
        language = "ru"
        quarter = next(
            (q for q in calendar.quarters if q.starts == row.period_start and q.ends == row.period_end), None
        )
        if quarter is not None:
            kind, start, end = ReportPeriod.QUARTER, quarter.starts, quarter.ends
        else:
            kind, start, end, _title, _q = _period_of(calendar, f"{row.period_start:%Y-%m}")
    else:
        kind, start, end = ReportPeriod.CUSTOM, row.period_start, row.period_end
    fresh = reporting.build_report(
        row.student,
        kind=kind,
        start=start,
        end=end,
        calendar=calendar,
        config=reporting.report_settings(calendar),
        quarter=quarter,
        actor=request.user,
        template=template,
        language=language,
    )
    if template != ReportTemplate.STANDARD and fresh.draft_state == DraftState.NONE:
        from academics.report_drafts import request_draft

        request_draft(fresh, actor=request.user)
        fresh.refresh_from_db()
    return Response(
        {
            "report": fresh.pk,
            "period": period_code(template, language, kind, start, end if kind == ReportPeriod.CUSTOM else ""),
            **report_detail(fresh, request.user),
        }
    )


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@cached
def report_pdf(request, pk: int):
    """Файл одного отчёта (`?type=pdf|docx`); скачивание ставит «выгружен». Черновик — 400.

    Не `?format=`: этот параметр DRF забирает себе под выбор ответа и отвечает 404.
    """
    from academics.report_files import FORMATS, PDF, FileRefused, render

    refusal = _reader(request)
    if refusal:
        return refusal
    row = _report_for(request.user, pk)
    if row is None:
        return _not_found()
    file_format = str(request.query_params.get("type") or PDF)
    if file_format not in FORMATS:
        return _bad("Формат — PDF или Word")
    # выгружает куратор или Кымбат с администратором — черновик им не отдаётся
    marks = request.user.role == ROLE_CURATOR or rights.edits_schedule(request.user.role)
    if marks and row.status == ReportStatus.DRAFT:
        return _bad("Сначала проверьте отчёт: черновик не выгружается")
    try:
        content, name, content_type = render(row, file_format)
    except FileRefused as error:
        return _bad(str(error))
    if marks:
        reporting.mark_exported(row, actor=request.user)
    return file_response(content=content, filename=name, content_type=content_type)


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
        rows = _in_period(rows, period)
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
    """«Обновить данные» для всех отмеченных: снимки заново, тексты ИИ — где куратор их не правил."""
    refusal = _reader(request) or _writer(request)
    if refusal:
        return refusal
    from academics.report_drafts import request_draft

    ids = [int(i) for i in (request.data.get("ids") or []) if str(i).isdigit()]
    changed = 0
    total = 0
    kept = 0
    for row in _each(request, ids):
        before = row.fingerprint
        fresh = _rebuild(row, request.user)
        total += 1
        changed += int(before != fresh.fingerprint)
        if fresh.template != ReportTemplate.STANDARD and fresh.status != ReportStatus.SENT:
            if fresh.texts_edited_at is not None:
                kept += 1
            else:
                request_draft(fresh, actor=request.user, overwrite=True)
    return Response({"refreshed": total, "changed": changed, "kept": kept})


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


def _export_rows(request):
    """Отчёты для архива: отмеченные или вся группа за период — только проверенные и видимые."""
    user = request.user
    students = visible_students(user).filter(is_active=True)
    picked = _group_param(request.data.get("group"))
    if picked is not None:
        if user.role == ROLE_CURATOR and picked.pk not in curated_group_ids(user):
            return None, picked
        students = students.filter(group=picked)
    rows = ParentReport.objects.filter(student__in=students).exclude(status=ReportStatus.DRAFT)
    ids = [int(i) for i in (request.data.get("ids") or []) if str(i).isdigit()]
    if ids:
        rows = rows.filter(pk__in=ids)
    else:
        period = _pick_period(str(request.data.get("period") or ""), _periods_available(students))
        if period is None:
            return [], picked
        rows = _in_period(rows, period)
    return list(rows.order_by("student__group__code", "student__last_name")), picked


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@cached
def reports_export(request):
    """Заказать архив отчётов в PDF или Word: собирается в очереди, экран ждёт номер задания."""
    from academics.report_files import FORMATS, start_export

    refusal = _reader(request)
    if refusal:
        return refusal
    file_format = str(request.data.get("format") or "pdf")
    if file_format not in FORMATS:
        return _bad("Формат — PDF или Word")
    rows, picked = _export_rows(request)
    if rows is None:
        return _not_found()
    if not rows:
        return _bad("Проверенных отчётов нет: в архив входят только проверенные")
    group_code = picked.code if picked else (rows[0].student.group.code if rows[0].student.group_id else "")
    name = reporting.zip_name(group_code or "Все группы", rows[0].title)
    job = start_export(user=request.user, ids=[row.pk for row in rows], file_format=file_format, zip_name=name)
    return Response({"job": job, "total": len(rows)})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_export_state(request, job: str):
    """Сколько готово; чужое задание — 404."""
    from academics.report_files import export_state

    state = export_state(job, request.user)
    if state is None:
        return _not_found()
    return Response({key: state.get(key) for key in ("state", "done", "total", "name", "error")})


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_export_file(request, job: str):
    """Готовый архив — тому, кто заказал."""
    from academics.report_files import export_file

    found = export_file(job, request.user)
    if found is None:
        return _not_found()
    payload, name = found
    return file_response(content=payload, filename=name, content_type="application/zip")


def _unused():  # pragma: no cover
    return scale_of, http
