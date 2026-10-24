"""Ручки кабинетов директоров (24.10.2026).

Право — из реестра (`core.domains.CABINET_WRITERS`, `CABINET_READERS`,
`SCHOOL_REPORT_READERS`), граница учеников — `core.scope`. Чужой ученик
и чужая запись отвечают 404: по 403 было бы видно, что запись есть.
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.domains import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    SCHOOL_REPORT_READERS,
    STAFF_TASK_ASSIGNEES,
    can_read_cabinet,
    can_write_cabinet,
)
from core.exports import Column, workbook_of_sheets, workbook_response
from core.scope import visible_students
from directors import reports, results, services
from directors.models import (
    ApplicationKind,
    ApplicationStatus,
    LessonRelease,
    Olympiad,
    OlympiadEntry,
    OlympiadLevel,
    ParentCall,
    SportApplication,
    SportEvent,
    SportEventKind,
    StaffTask,
    StaffTaskStatus,
)
from students.models import Student


def _forbid(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


def _not_found() -> Response:
    return Response({"detail": _("Не найдено")}, status=status.HTTP_404_NOT_FOUND)


def _bad(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def _date(raw) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def _int(raw) -> int | None:
    return int(raw) if str(raw or "").isdigit() else None


def _role(request) -> str:
    return getattr(request.user, "role", "")


def _student(request, raw):
    pk = _int(raw)
    return visible_students(request.user).filter(pk=pk).select_related("group").first() if pk else None


def _brief(student) -> dict:
    return {
        "id": student.pk,
        "full_name": student.full_name,
        "short_name": f"{student.last_name} {student.first_name}".strip(),
        "group": student.group.code if student.group_id else "",
        "parallel": student.group.parallel if student.group_id else None,
    }


def _when(value) -> str | None:
    return timezone.localtime(value).isoformat() if value else None


# --- Звонки родителям ---------------------------------------------------------------

CALL = "directors.ParentCall"


def _call_dict(row: ParentCall) -> dict:
    return {
        "id": row.pk,
        "student": _brief(row.student),
        "contact": (
            {"id": row.contact_id, "name": row.contact.full_name, "relation": row.contact.get_relation_display()}
            if row.contact_id
            else None
        ),
        "outcome": row.outcome,
        "outcome_title": row.get_outcome_display(),
        "note": row.note,
        "rule": row.rule,
        "by": row.called_by_title,
        "at": _when(row.called_at),
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def calls_today(request):
    """«Позвонить сегодня»: список по включённым правилам обзвона и итог звонка за сегодня."""
    from core.cabinets import call_list
    from engagement.models import CallRule

    if _role(request) not in ("director_behavior", ROLE_ADMIN):
        return _forbid(_("Обзвон ведёт директор школы"))
    rows = call_list(limit=200)
    today = timezone.localdate()
    done = {}
    for call in ParentCall.objects.filter(called_at__date=today).order_by("called_at"):
        done[call.student_id] = {"outcome": call.outcome, "outcome_title": call.get_outcome_display()}
    from students.models import ParentContact

    contacts = {}
    for contact in ParentContact.objects.filter(student__in=[r["student_id"] for r in rows]).exclude(phone=""):
        contacts.setdefault(contact.student_id, contact)
    week = timezone.now() - dt.timedelta(days=7)
    calls_week = ParentCall.objects.filter(called_at__gte=week)
    rules = [
        {
            "id": rule.pk,
            "code": rule.code,
            "reason": rule.reason,
            "condition_title": rule.get_condition_display(),
            "urgency_title": rule.get_urgency_display(),
            "is_active": rule.is_active,
        }
        for rule in CallRule.objects.all()
    ]
    return Response(
        {
            "rows": [
                {
                    **row,
                    "contact_id": contacts[row["student_id"]].pk if row["student_id"] in contacts else None,
                    "parent": contacts[row["student_id"]].full_name if row["student_id"] in contacts else "",
                    "today": done.get(row["student_id"]),
                }
                for row in rows
            ],
            "week": {
                "total": calls_week.count(),
                "reached": calls_week.filter(outcome="reached").count(),
                "later": calls_week.exclude(outcome="reached").count(),
            },
            "rules": rules,
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def calls(request):
    """История звонков (GET) и итог звонка (POST): дозвонились, не ответили, перезвонить и текст."""
    role = _role(request)
    if request.method == "POST":
        if not can_write_cabinet(role, CALL):
            return _forbid(_("Звонки записывают директор школы и кураторы"))
        student = _student(request, request.data.get("student"))
        if student is None:
            return _not_found()
        contact = None
        if _int(request.data.get("contact")):
            contact = student.contacts.filter(pk=_int(request.data.get("contact"))).first()
        try:
            row = services.record_call(
                student=student,
                outcome=str(request.data.get("outcome") or ""),
                note=str(request.data.get("note") or ""),
                contact=contact,
                rule=str(request.data.get("rule") or ""),
                actor=request.user,
            )
        except services.Refused as error:
            return _bad(str(error))
        return Response(_call_dict(row), status=status.HTTP_201_CREATED)
    if not can_read_cabinet(role, CALL):
        return _forbid(_("Историю звонков читают директор школы и кураторы"))
    rows = _calls_query(request)
    return Response({"rows": [_call_dict(r) for r in rows[:300]], "total": rows.count()})


def _calls_query(request):
    days = _int(request.query_params.get("days")) or 30
    rows = (
        ParentCall.objects.filter(
            student__in=visible_students(request.user), called_at__gte=timezone.now() - dt.timedelta(days=days)
        )
        .select_related("student", "student__group", "contact")
        .order_by("-called_at")
    )
    student = _int(request.query_params.get("student"))
    return rows.filter(student_id=student) if student else rows


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def calls_export(request):
    if not can_read_cabinet(_role(request), CALL):
        return _forbid(_("Историю звонков читают директор школы и кураторы"))
    report = reports.calls()
    return workbook_response(
        filename=_("Звонки родителям.xlsx"),
        sheet=_("Звонки"),
        columns=report.columns,
        rows=list(_calls_query(request)),
        request=request,
    )


# --- Отчёты одного места ----------------------------------------------------------------


def _report_kinds(request) -> tuple[str, ...]:
    role = _role(request)
    if role == ROLE_ADMIN:
        return tuple(reports.BUILDERS)
    return SCHOOL_REPORT_READERS.get(role, ())


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_list(request):
    """Отчёты роли: текущий период каждого вида с цифрами и прежние периоды строками."""
    kinds = _report_kinds(request)
    if not kinds:
        return _forbid(_("Отчёты — у директора школы и академического директора"))
    seen = reports.seen_keys(request.user)
    current = []
    archive = []
    for kind in kinds:
        report = reports.build(kind)
        current.append({**report.payload(seen=(kind, report.period) in seen), "topic": reports.TOPICS[kind]})
        for period in reports.recent_periods(kind)[1:]:
            archive.append(
                {
                    "kind": kind,
                    "title": report.title if kind != "parent_reports" else str(_("Отчёты родителям")),
                    "source": report.source,
                    "period": period,
                    "topic": reports.TOPICS[kind],
                    "seen": (kind, period) in seen,
                }
            )
    return Response({"current": current, "archive": archive})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_detail(request, kind: str):
    if kind not in _report_kinds(request):
        return _not_found()
    report = reports.build(kind, str(request.query_params.get("period") or ""))
    seen = (kind, report.period) in reports.seen_keys(request.user)
    out = {**report.payload(seen=seen), "topic": reports.TOPICS[kind]}
    if kind == "teachers":
        # строки учителей с id: «Поставить задачу» на экране открывает окно на этого учителя
        out["teachers"] = report.rows
    return Response(out)


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_export(request, kind: str):
    if kind not in _report_kinds(request):
        return _not_found()
    report = reports.build(kind, str(request.query_params.get("period") or ""))
    lines = [Column(_("Показатель"), lambda r: r[0], 34), Column(_("Значение"), lambda r: r[1], 24)]
    sheets = [(_("Итоги"), lines, report.lines)]
    if report.rows:
        sheets.append((_("Подробно"), report.columns, report.rows))
    return workbook_of_sheets(filename=f"{report.title} {report.period}.xlsx", sheets=sheets, request=request)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def report_seen(request, kind: str):
    if kind not in _report_kinds(request):
        return _not_found()
    period = str(request.data.get("period") or "") or reports.build(kind).period
    reports.mark_seen(request.user, kind, period)
    return Response({"kind": kind, "period": period, "seen": True})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_groups(request):
    """Отчёты родителям по группам за месяц: «Открыть» ведёт на экран отчётов группы."""
    if "parent_reports" not in _report_kinds(request):
        return _forbid(_("Отчёты — у директора школы и академического директора"))
    month = reports._parse_month(str(request.query_params.get("month") or "")) or timezone.localdate().replace(day=1)
    return Response({"month": f"{month:%Y-%m}", "rows": reports.parent_report_groups(month)})


# --- Задачи сотрудникам ------------------------------------------------------------------

TASK = "directors.StaffTask"


def _task_dict(task: StaffTask, today: dt.date) -> dict:
    from core.domains import ROLE_TITLES

    return {
        "id": task.pk,
        "title": task.title,
        "due": task.due,
        "status": task.status,
        "status_title": task.get_status_display(),
        "late": services.is_late(task, today),
        "days_late": (today - task.due).days if services.is_late(task, today) else 0,
        "assignee": {
            "id": task.assignee_id,
            "name": task.assignee.full_name or task.assignee.email,
            "role": task.assignee.role,
            "role_title": str(ROLE_TITLES.get(task.assignee.role, "")),
        },
        "author": task.author_title,
        "return_note": task.return_note,
        "done_at": _when(task.done_at),
        "reminded_at": _when(task.reminded_at),
        "created_at": _when(task.created_at),
    }


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def staff_tasks(request):
    """Задачи, поставленные сотрудникам: список с фильтрами и «Поставить»."""
    from accounts.models import User

    if not can_write_cabinet(_role(request), TASK):
        return _forbid(_("Задачи сотрудникам ставит академический директор"))
    if request.method == "POST":
        assignee = User.objects.filter(pk=_int(request.data.get("assignee"))).first()
        due = _date(request.data.get("due"))
        if due is None:
            return _bad(_("Укажите срок"))
        try:
            task = services.set_task(
                title=str(request.data.get("title") or ""), due=due, assignee=assignee, actor=request.user
            )
        except services.Refused as error:
            return _bad(str(error))
        return Response(_task_dict(task, timezone.localdate()), status=status.HTTP_201_CREATED)
    today = timezone.localdate()
    rows = list(StaffTask.objects.select_related("assignee").order_by("due", "id"))
    month = today.replace(day=1)
    return Response(
        {
            "rows": [_task_dict(t, today) for t in rows],
            "month": {
                "set": sum(1 for t in rows if t.created_at.date() >= month),
                "accepted": sum(1 for t in rows if t.accepted_at and t.accepted_at.date() >= month),
                "returned": sum(1 for t in rows if t.status == StaffTaskStatus.RETURNED),
            },
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_task_people(request):
    """Кому можно поставить задачу: учителя, кураторы, директора — с ролью."""
    from accounts.models import User
    from core.domains import ROLE_TITLES

    if not can_write_cabinet(_role(request), TASK):
        return _forbid(_("Задачи сотрудникам ставит академический директор"))
    people = (
        User.objects.filter(is_active=True, role__in=STAFF_TASK_ASSIGNEES)
        .exclude(pk=request.user.pk)
        .order_by("role", "full_name")
    )
    return Response(
        {
            "rows": [
                {
                    "id": u.pk,
                    "name": u.full_name or u.email,
                    "role": u.role,
                    "role_title": str(ROLE_TITLES.get(u.role, "")),
                }
                for u in people
            ]
        }
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def staff_task(request, pk: int):
    """Приёмка, возврат, напоминание, правка срока и текста; удаление — в архив."""
    from core.archive import archive

    if not can_write_cabinet(_role(request), TASK):
        return _forbid(_("Задачи сотрудникам ставит академический директор"))
    task = StaffTask.objects.select_related("assignee").filter(pk=pk).first()
    if task is None:
        return _not_found()
    if request.method == "DELETE":
        archive(task, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
    action = str(request.data.get("action") or "")
    try:
        if action == "accept":
            services.accept(task)
        elif action == "return":
            services.send_back(task, str(request.data.get("note") or ""))
        elif action == "remind":
            services.remind(task, actor=request.user)
        else:
            if "title" in request.data and str(request.data["title"]).strip():
                task.title = str(request.data["title"]).strip()[:300]
            if _date(request.data.get("due")):
                task.due = _date(request.data.get("due"))
            task.save(update_fields=["title", "due", "updated_at"])
    except services.Refused as error:
        return _bad(str(error))
    return Response(_task_dict(task, timezone.localdate()))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_staff_tasks(request):
    """Задачи, поставленные мне: открытые и возвращённые сверху, выполненные — до приёмки."""
    if _role(request) not in STAFF_TASK_ASSIGNEES:
        return Response({"rows": []})
    today = timezone.localdate()
    rows = StaffTask.objects.filter(
        assignee=request.user, status__in=(StaffTaskStatus.OPEN, StaffTaskStatus.RETURNED, StaffTaskStatus.DONE)
    ).select_related("assignee")
    return Response({"rows": [_task_dict(t, today) for t in rows.order_by("status", "due")]})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_staff_task_done(request, pk: int):
    task = StaffTask.objects.filter(pk=pk, assignee=request.user).select_related("assignee").first()
    if task is None:
        return _not_found()
    try:
        services.mark_done(task)
    except services.Refused as error:
        return _bad(str(error))
    return Response(_task_dict(task, timezone.localdate()))


# --- Результаты экзаменов ---------------------------------------------------------------

EXAM_READERS = ("director_exam", ROLE_ADMIN)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exam_results(request):
    if _role(request) not in EXAM_READERS:
        return _forbid(_("Результаты экзаменов читает академический директор"))
    exam = str(request.query_params.get("exam") or "IELTS").upper()
    return Response(results.rows(exam, group=str(request.query_params.get("group") or "")))


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exam_results_export(request):
    if _role(request) not in EXAM_READERS:
        return _forbid(_("Результаты экзаменов читает академический директор"))
    exam = str(request.query_params.get("exam") or "IELTS").upper()
    data = results.rows(exam, group=str(request.query_params.get("group") or ""))
    columns = [
        Column(_("Ученик"), lambda r: r["full_name"], 30),
        Column(_("Группа"), lambda r: r["group"], 10),
        Column(_("Последний Mock Test"), lambda r: r["mock"], 18),
        Column(_("Секции"), lambda r: r["sections"], 22),
        Column(_("Официальный"), lambda r: r["official"], 14),
        Column(_("Цель"), lambda r: r["goal"], 8),
        Column(_("До цели"), lambda r: r["gap"], 10),
    ]
    return workbook_response(
        filename=_("Результаты экзаменов {exam}.xlsx").format(exam=data["exam"]),
        sheet=data["exam"],
        columns=columns,
        rows=data["rows"],
        request=request,
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exam_results_student(request, pk: int):
    if _role(request) not in EXAM_READERS:
        return _forbid(_("Результаты экзаменов читает академический директор"))
    student = _student(request, pk)
    if student is None:
        return _not_found()
    return Response({"student": _brief(student), "attempts": results.history(student)})


# --- Эссе учеников у Асем ---------------------------------------------------------------

ESSAY = "roadmap.Essay.verdict"


def _essays():
    from core.parallels import admission_q
    from roadmap.models import Essay, EssayStatus

    return (
        Essay.objects.filter(
            admission_q("student__"),
            student__is_active=True,
            status__in=(EssayStatus.REVIEW, EssayStatus.DONE, EssayStatus.REVISION),
            versions__isnull=False,
        )
        .distinct()
        .select_related("student", "student__group", "doc_type", "program__university")
    )


def _essay_dict(essay) -> dict:
    from roadmap.models import EssayStatus

    version = essay.current_version
    last = essay.comments.order_by("-created_at").first()
    verdict = {EssayStatus.DONE: "ok", EssayStatus.REVISION: "not_ok"}.get(essay.status, "")
    return {
        "id": essay.pk,
        "title": essay.title,
        "kind": essay.doc_type.name if essay.doc_type_id else essay.get_essay_type_display(),
        "program": (f"{essay.program.university.name} · {essay.program.name}" if essay.program_id else ""),
        "student": _brief(essay.student),
        "words": version.word_count if version else 0,
        "word_limit": essay.word_limit or (essay.doc_type.default_word_limit if essay.doc_type_id else None),
        "submitted_at": _when(version.created_at if version else essay.updated_at),
        "verdict": verdict,
        "comment": last.text if last is not None else "",
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def essay_review(request):
    """Законченные эссе 11 класса: ученик отправил на проверку. Ждут решения — сверху."""
    if not can_write_cabinet(_role(request), ESSAY):
        return _forbid(_("Эссе учеников проверяет директор по поступлению"))
    rows = [_essay_dict(e) for e in _essays().prefetch_related("versions", "comments")]
    rows.sort(key=lambda r: (r["verdict"] != "", r["submitted_at"] or ""), reverse=False)
    pending = [r for r in rows if not r["verdict"]]
    pending.sort(key=lambda r: r["submitted_at"] or "", reverse=True)
    rest = [r for r in rows if r["verdict"]]
    rest.sort(key=lambda r: r["submitted_at"] or "", reverse=True)
    return Response(
        {"rows": pending + rest, "groups": sorted({r["student"]["group"] for r in rows if r["student"]["group"]})}
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def essay_review_detail(request, pk: int):
    if not can_write_cabinet(_role(request), ESSAY):
        return _forbid(_("Эссе учеников проверяет директор по поступлению"))
    essay = _essays().filter(pk=pk).first()
    if essay is None:
        return _not_found()
    version = essay.current_version
    return Response(
        {
            **_essay_dict(essay),
            "text": version.text if version else "",
            "comments": [
                {"text": c.text, "at": _when(c.created_at), "author": (c.author.full_name if c.author_id else "")}
                for c in essay.comments.select_related("author").order_by("created_at")
            ],
        }
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def essay_review_verdict(request, pk: int):
    if not can_write_cabinet(_role(request), ESSAY):
        return _forbid(_("Эссе учеников проверяет директор по поступлению"))
    essay = _essays().filter(pk=pk).first()
    if essay is None:
        return _not_found()
    verdict = str(request.data.get("verdict") or "")
    if verdict not in ("ok", "not_ok"):
        return _bad(_("Выберите: норм или не норм"))
    try:
        services.essay_verdict(
            essay, ok=verdict == "ok", comment=str(request.data.get("comment") or ""), actor=request.user
        )
    except services.Refused as error:
        return _bad(str(error))
    return Response(_essay_dict(_essays().get(pk=pk)))


# --- Олимпиады ---------------------------------------------------------------------------

OLYMPIAD = "directors.Olympiad"


def _olympiad_dict(row: Olympiad, entries=None) -> dict:
    out = {
        "id": row.pk,
        "title": row.title,
        "subject": row.subject_id,
        "subject_title": row.subject.name if row.subject_id else "",
        "level": row.level,
        "level_title": row.get_level_display(),
        "place": row.place,
        "starts": row.starts,
        "ends": row.ends,
        "participants": getattr(row, "participants", None),
        "pending": getattr(row, "waiting", None),
    }
    if entries is not None:
        released = services.released_map([e.student_id for e in entries], row.starts, row.ends)
        out["entries"] = [
            {
                "id": e.pk,
                "student": _brief(e.student),
                "result": e.result,
                "result_title": e.get_result_display(),
                "released": bool(services.released_on(released, e.student_id, row.starts)),
            }
            for e in entries
        ]
    return out


def _olympiad_fields(data, row: Olympiad | None = None) -> tuple[dict | None, str]:
    title = str(data.get("title") or (row.title if row else "")).strip()
    level = str(data.get("level") or (row.level if row else ""))
    starts = _date(data.get("starts")) or (row.starts if row else None)
    ends = _date(data.get("ends")) or starts
    if not title:
        return None, _("Напишите название олимпиады")
    if level not in OlympiadLevel.values:
        return None, _("Выберите уровень")
    if starts is None or ends < starts:
        return None, _("Проверьте даты")
    fields = {"title": title[:250], "level": level, "starts": starts, "ends": ends}
    if "place" in data:
        fields["place"] = str(data.get("place") or "").strip()[:200]
    if "subject" in data:
        fields["subject_id"] = _int(data.get("subject"))
    return fields, ""


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def olympiads(request):
    role = _role(request)
    if request.method == "POST":
        if not can_write_cabinet(role, OLYMPIAD):
            return _forbid(_("Олимпиады ведёт директор талантов"))
        fields, error = _olympiad_fields(request.data)
        if fields is None:
            return _bad(error)
        row = Olympiad.objects.create(**fields, created_by=request.user)
        return Response(_olympiad_dict(row, []), status=status.HTTP_201_CREATED)
    if not can_read_cabinet(role, OLYMPIAD):
        return _forbid(_("Олимпиады ведёт директор талантов"))
    rows = Olympiad.objects.select_related("subject").annotate(
        participants=Count("entries", filter=Q(entries__archived_at__isnull=True), distinct=True),
        waiting=Count("entries", filter=Q(entries__archived_at__isnull=True, entries__result="pending"), distinct=True),
    )
    return Response(
        {
            "rows": [_olympiad_dict(r) for r in rows.order_by("starts", "id")],
            "levels": [{"value": v, "label": str(label)} for v, label in OlympiadLevel.choices],
        }
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def olympiad(request, pk: int):
    from core.archive import archive

    role = _role(request)
    row = Olympiad.objects.select_related("subject").filter(pk=pk).first()
    if row is None or not can_read_cabinet(role, OLYMPIAD):
        return _not_found()
    if request.method != "GET" and not can_write_cabinet(role, OLYMPIAD):
        return _forbid(_("Олимпиады ведёт директор талантов"))
    if request.method == "DELETE":
        archive(row, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == "PATCH":
        fields, error = _olympiad_fields(request.data, row)
        if fields is None:
            return _bad(error)
        for key, value in fields.items():
            setattr(row, key, value)
        row.save()
    entries = list(
        row.entries.filter(student__in=visible_students(request.user)).select_related("student", "student__group")
    )
    return Response(_olympiad_dict(row, entries))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def olympiad_entries(request, pk: int):
    if not can_write_cabinet(_role(request), "directors.OlympiadEntry"):
        return _forbid(_("Участников олимпиады отмечает директор талантов"))
    row = Olympiad.objects.filter(pk=pk).first()
    if row is None:
        return _not_found()
    ids = [i for i in (_int(x) for x in request.data.get("students") or []) if i]
    students = list(visible_students(request.user).filter(pk__in=ids, is_active=True))
    if not students:
        return _bad(_("Отметьте учеников"))
    return Response({"added": services.add_entries(row, students)}, status=status.HTTP_201_CREATED)


@extend_schema(request=None, responses={200: dict})
@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def olympiad_entry(request, pk: int):
    if not can_write_cabinet(_role(request), "directors.OlympiadEntry"):
        return _forbid(_("Участников олимпиады отмечает директор талантов"))
    entry = OlympiadEntry.objects.select_related("olympiad", "student", "student__group").filter(pk=pk).first()
    if entry is None:
        return _not_found()
    if request.method == "DELETE":
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    try:
        services.set_result(entry, str(request.data.get("result") or ""), actor=request.user)
    except services.Refused as error:
        return _bad(str(error))
    return Response({"id": entry.pk, "result": entry.result, "result_title": entry.get_result_display()})


# --- Освобождения ------------------------------------------------------------------------

RELEASE = "directors.LessonRelease"


def _release_dict(row: LessonRelease, visible: set[int] | None = None) -> dict:
    students = [s for s in row.students.all() if visible is None or s.pk in visible]
    return {
        "id": row.pk,
        "reason": row.reason,
        "kind": "olympiad" if row.olympiad_id else "sport",
        "olympiad": row.olympiad_id,
        "event": row.event_id,
        "starts": row.starts,
        "ends": row.ends,
        "all_day": row.all_day,
        "slot_from": row.slot_from,
        "slot_to": row.slot_to,
        "span": services.span_text(row),
        "label": services.release_label(row),
        "by": row.created_by_title,
        "students": [_brief(s) for s in sorted(students, key=lambda s: (s.last_name, s.first_name))],
    }


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def releases(request):
    """Освобождения недели (GET `?from=&to=`) и новое освобождение по олимпиаде (POST)."""
    role = _role(request)
    if request.method == "POST":
        if role not in ("director_talent", ROLE_ADMIN):
            return _forbid(_("Освобождения по олимпиадам ставит директор талантов"))
        olympiad = Olympiad.objects.filter(pk=_int(request.data.get("olympiad"))).first()
        if olympiad is None:
            return _bad(_("Выберите олимпиаду"))
        ids = [i for i in (_int(x) for x in request.data.get("students") or []) if i]
        students = visible_students(request.user).filter(pk__in=ids, is_active=True)
        try:
            row = services.release(
                students=students,
                starts=_date(request.data.get("starts")) or olympiad.starts,
                ends=_date(request.data.get("ends")) or _date(request.data.get("starts")) or olympiad.ends,
                slot_from=_int(request.data.get("slot_from")),
                slot_to=_int(request.data.get("slot_to")),
                olympiad=olympiad,
                actor=request.user,
            )
        except services.Refused as error:
            return _bad(str(error))
        return Response(_release_dict(row), status=status.HTTP_201_CREATED)
    if not can_read_cabinet(role, RELEASE):
        return _forbid(_("Освобождения видят руководители школы и кураторы"))
    start = _date(request.query_params.get("from")) or timezone.localdate()
    end = _date(request.query_params.get("to")) or start + dt.timedelta(days=6)
    visible = set(visible_students(request.user).values_list("pk", flat=True))
    rows = [_release_dict(row, visible) for row in services.releases_between(start, end).order_by("starts", "id")]
    return Response({"from": start, "to": end, "rows": [r for r in rows if r["students"]]})


@extend_schema(request=None, responses={204: None})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def release(request, pk: int):
    row = LessonRelease.objects.select_related("olympiad", "event").filter(pk=pk).first()
    if row is None:
        return _not_found()
    role = _role(request)
    owner = "director_talent" if row.olympiad_id else "director_sport"
    if role not in (owner, ROLE_ADMIN):
        return _forbid(_("Освобождение отменяет тот, кто его поставил"))
    services.cancel_release(row, actor=request.user)
    return Response(status=status.HTTP_204_NO_CONTENT)


# --- Спортивные мероприятия -----------------------------------------------------------------

EVENT = "directors.SportEvent"


def _event_dict(row: SportEvent, *, me=None) -> dict:
    apps = list(row.applications.all())
    play = [a for a in apps if a.kind == ApplicationKind.PLAY]
    out = {
        "id": row.pk,
        "title": row.title,
        "kind": row.kind,
        "kind_title": row.get_kind_display(),
        "sport_type": row.sport_type_id,
        "sport_title": row.sport_type.name if row.sport_type_id else "",
        "starts_at": _when(row.starts_at),
        "place": row.place,
        "seats": row.seats,
        "spectators": row.spectators,
        "past": row.starts_at < timezone.now(),
        "accepted": sum(1 for a in play if a.status == ApplicationStatus.ACCEPTED),
        "seats_left": (
            max(row.seats - sum(1 for a in play if a.status == ApplicationStatus.ACCEPTED), 0)
            if row.seats is not None
            else None
        ),
    }
    if me is None:
        out["pending"] = sum(1 for a in play if a.status == ApplicationStatus.PENDING)
        out["applications"] = len(play)
        out["watchers"] = sum(1 for a in apps if a.kind == ApplicationKind.WATCH)
    else:
        mine = next((a for a in apps if a.student_id == me.pk), None)
        out["mine"] = _application_dict(mine, student_view=True) if mine else None
    return out


def _application_dict(row: SportApplication, *, student_view: bool = False) -> dict:
    out = {
        "id": row.pk,
        "kind": row.kind,
        "kind_title": row.get_kind_display(),
        "comment": row.comment,
        "status": row.status,
        "status_title": row.get_status_display(),
        "created_at": _when(row.created_at),
    }
    if not student_view:
        out["student"] = _brief(row.student)
        found = services.release_of(row)
        out["release"] = services.span_text(found) if found else ""
    return out


def _event_fields(data, row: SportEvent | None = None) -> tuple[dict | None, str]:
    from django.utils.dateparse import parse_datetime

    title = str(data.get("title") or (row.title if row else "")).strip()
    kind = str(data.get("kind") or (row.kind if row else ""))
    raw = data.get("starts_at")
    starts_at = parse_datetime(str(raw)) if raw else (row.starts_at if row else None)
    if starts_at is not None and timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at)
    place = str(data.get("place") if "place" in data else (row.place if row else "")).strip()
    if not title:
        return None, _("Напишите название")
    if kind not in SportEventKind.values:
        return None, _("Выберите тип")
    if starts_at is None:
        return None, _("Укажите дату и время")
    if not place:
        return None, _("Укажите место")
    fields = {"title": title[:250], "kind": kind, "starts_at": starts_at, "place": place[:200]}
    if "sport_type" in data:
        fields["sport_type_id"] = _int(data.get("sport_type"))
    if "seats" in data:
        fields["seats"] = _int(data.get("seats"))
    if "spectators" in data:
        fields["spectators"] = bool(data.get("spectators"))
    return fields, ""


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def sport_events(request):
    role = _role(request)
    if request.method == "POST":
        if not can_write_cabinet(role, EVENT):
            return _forbid(_("Мероприятия добавляет директор спорта"))
        fields, error = _event_fields(request.data)
        if fields is None:
            return _bad(error)
        row = SportEvent.objects.create(**fields, created_by=request.user)
        return Response(_event_dict(row), status=status.HTTP_201_CREATED)
    if role == ROLE_STUDENT or not can_read_cabinet(role, EVENT):
        return _forbid(_("Мероприятия ведёт директор спорта"))
    rows = SportEvent.objects.select_related("sport_type").prefetch_related("applications").order_by("starts_at")
    return Response({"rows": [_event_dict(r) for r in rows]})


@extend_schema(request=None, responses={200: dict})
@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def sport_event(request, pk: int):
    from core.archive import archive

    if not can_write_cabinet(_role(request), EVENT):
        return _forbid(_("Мероприятия ведёт директор спорта"))
    row = SportEvent.objects.select_related("sport_type").filter(pk=pk).first()
    if row is None:
        return _not_found()
    if request.method == "DELETE":
        archive(row, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
    fields, error = _event_fields(request.data, row)
    if fields is None:
        return _bad(error)
    for key, value in fields.items():
        setattr(row, key, value)
    row.save()
    return Response(_event_dict(row))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sport_event_applications(request, pk: int):
    if not can_write_cabinet(_role(request), "directors.SportApplication"):
        return _forbid(_("Заявки решает директор спорта"))
    row = SportEvent.objects.filter(pk=pk).first()
    if row is None:
        return _not_found()
    apps = row.applications.select_related("student", "student__group").order_by("status", "-created_at")
    return Response({"event": _event_dict(row), "rows": [_application_dict(a) for a in apps]})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sport_applications(request):
    """Новые заявки на все мероприятия — блок главной директора спорта."""
    if not can_write_cabinet(_role(request), "directors.SportApplication"):
        return _forbid(_("Заявки решает директор спорта"))
    apps = (
        SportApplication.objects.filter(status=ApplicationStatus.PENDING, event__starts_at__gte=timezone.now())
        .select_related("student", "student__group", "event")
        .order_by("-created_at")
    )
    return Response(
        {"rows": [{**_application_dict(a), "event": {"id": a.event_id, "title": a.event.title}} for a in apps]}
    )


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sport_event_export(request, pk: int):
    if not can_write_cabinet(_role(request), "directors.SportApplication"):
        return _forbid(_("Заявки решает директор спорта"))
    row = SportEvent.objects.filter(pk=pk).first()
    if row is None:
        return _not_found()
    apps = list(row.applications.select_related("student", "student__group").order_by("kind", "student__last_name"))
    columns = [
        Column(_("Ученик"), lambda a: a.student.full_name, 30),
        Column(_("Группа"), lambda a: a.student.group.code if a.student.group_id else "", 10),
        Column(_("Заявка"), lambda a: a.get_kind_display(), 16),
        Column(_("Статус"), lambda a: a.get_status_display(), 14),
        Column(_("Комментарий"), lambda a: a.comment, 40),
    ]
    return workbook_response(filename=f"{row.title}.xlsx", sheet=row.title, columns=columns, rows=apps, request=request)


@extend_schema(request=None, responses={200: dict})
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def sport_application(request, pk: int):
    if not can_write_cabinet(_role(request), "directors.SportApplication"):
        return _forbid(_("Заявки решает директор спорта"))
    row = SportApplication.objects.select_related("event", "student", "student__group").filter(pk=pk).first()
    if row is None:
        return _not_found()
    try:
        services.decide(row, str(request.data.get("status") or ""), actor=request.user)
    except services.Refused as error:
        return _bad(str(error))
    return Response(_application_dict(row))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sport_application_release(request, pk: int):
    if _role(request) not in ("director_sport", ROLE_ADMIN):
        return _forbid(_("Освобождение участнику ставит директор спорта"))
    row = SportApplication.objects.select_related("event", "student").filter(pk=pk).first()
    if row is None:
        return _not_found()
    try:
        services.release_player(
            row,
            slot_from=_int(request.data.get("slot_from")),
            slot_to=_int(request.data.get("slot_to")),
            actor=request.user,
        )
    except services.Refused as error:
        return _bad(str(error))
    return Response(_application_dict(row), status=status.HTTP_201_CREATED)


# --- Ученик: «Спорт» -----------------------------------------------------------------------


def _me_student(request):

    if _role(request) != ROLE_STUDENT:
        return None
    return Student.objects.filter(user=request.user, is_active=True).first()


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_sport(request):
    """Мероприятия школы и свои заявки — у ученика видны только его заявки."""
    me = _me_student(request)
    if me is None:
        return _forbid(_("Раздел — у ученика"))
    since = timezone.now() - dt.timedelta(days=30)
    rows = (
        SportEvent.objects.filter(starts_at__gte=since)
        .select_related("sport_type")
        .prefetch_related("applications")
        .order_by("starts_at")
    )
    return Response({"rows": [_event_dict(r, me=me) for r in rows]})


@extend_schema(request=None, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_sport_apply(request, pk: int):
    me = _me_student(request)
    if me is None:
        return _forbid(_("Заявку подаёт ученик"))
    event = SportEvent.objects.filter(pk=pk).first()
    if event is None:
        return _not_found()
    try:
        row = services.apply(
            event=event,
            student=me,
            kind=str(request.data.get("kind") or ""),
            comment=str(request.data.get("comment") or ""),
        )
    except services.Refused as error:
        return _bad(str(error))
    return Response(_application_dict(row, student_view=True), status=status.HTTP_201_CREATED)


@extend_schema(request=None, responses={204: None})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def my_sport_application(request, pk: int):
    me = _me_student(request)
    row = SportApplication.objects.filter(pk=pk, student=me).first() if me else None
    if row is None:
        return _not_found()
    try:
        services.withdraw(row)
    except services.Refused as error:
        return _bad(str(error))
    return Response(status=status.HTTP_204_NO_CONTENT)


# --- Утренние отметки кураторов по школе (директор школы, на чтение) ------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def morning(request):
    """Утренние отметки всех групп за день: кто отметил и когда, кого нет, кто опоздал, кто освобождён."""
    if _role(request) not in ("director_behavior", ROLE_ADMIN):
        return _forbid(_("Утренние отметки по школе читает директор школы"))
    return Response(reports.morning_overview(_date(request.query_params.get("date"))))
