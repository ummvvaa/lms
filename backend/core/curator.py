"""Кабинет куратора: главная, ученики, карточка, задачи, выгрузка (фаза 61).

Всё считает сервер. Числа на главной, чипы над таблицей и блок «что
требует внимания» в карточке берутся из одного места (`students.attention`):
три экрана, каждый со своей арифметикой, разошлись бы в первый месяц.

Границу «свои группы — чужие» держит `core.scope`, а список открытых
куратору маршрутов — шлюз в `accounts.permissions` (фаза 60). Чужой
ученик сюда не доходит: его нет в выборке, и ответ — 404, а не 403.

Очередь подтверждений здесь не дублируется: она живёт в
`/api/suggestions/from-students/` с теми же действиями, что у директоров.
Отсюда отдаются только первые строки для главной.
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.curators import curated_group_ids
from core.domains import ROLE_CURATOR
from students import attention
from students.models import DocumentType, Student, StudyGroup
from students.portfolio import REQUIRED_DOCUMENTS

#: Сколько строк показываем на главной, не открывая раздел.
HOME_QUEUE, HOME_TASKS, HOME_JOURNAL = 5, 4, 5


def _deny(request):
    """Кабинет куратора — только куратору. Директор ходит своим кабинетом."""
    if request.user.role != ROLE_CURATOR:
        return Response({"detail": "Это кабинет куратора"}, status=http.HTTP_403_FORBIDDEN)
    return None


def _groups(request) -> list[int]:
    """Группы, по которым сейчас смотрит куратор.

    Без параметра — все его группы; с параметром `group` — одна, и только
    если она действительно его. Чужой код группы не сужает выборку до
    чужих учеников, а отдаёт пусто: подсказывать, что такая группа есть,
    незачем.
    """
    mine = curated_group_ids(request.user)
    code = str(request.query_params.get("group") or "").strip()
    if not code or code == "all":
        return mine
    picked = StudyGroup.objects.filter(code__iexact=code, pk__in=mine).values_list("pk", flat=True)
    return list(picked)


def _students(request):
    return attention.active_students(_groups(request)).select_related("group", "exam", "behavior")


def _group_rows(user) -> list[dict]:
    """Свои группы с числом учеников — шапка кабинета и экран «Мои группы»."""
    from accounts.curators import active_assignments

    rows = []
    for row in active_assignments().filter(curator=user).select_related("group").order_by("group__code"):
        rows.append(
            {
                "id": row.group_id,
                "code": row.group.code,
                "grade": row.group.grade,
                "students": row.group.students.filter(is_active=True).count(),
                "since": row.since,
            }
        )
    return rows


def _student_row(student: Student, state: dict) -> dict:
    """Строка таблицы учеников: только то, что куратор читает."""
    behavior = getattr(student, "behavior", None)
    return {
        "id": student.pk,
        "full_name": student.full_name,
        "group": student.group.code if student.group_id else "",
        "grade": student.grade,
        "ielts_current": state["ielts_current"],
        "ielts_target": state["ielts_target"],
        "sat_current": state["sat_current"],
        "sat_target": state["sat_target"],
        "last_mock_date": state["last_mock_date"],
        "last_mock_exam": state["last_mock_exam"],
        "days_without_mock": state["days_without_mock"],
        # внутренний ярлык: куратор его читает, ученику он не отдаётся никогда
        "status": getattr(behavior, "status", "") or "",
        "status_title": behavior.get_status_display() if behavior and behavior.status else "",
        "documents_collected": state["documents_collected"],
        "documents_total": state["documents_total"],
        "buckets": state["buckets"],
    }


def _tasks_of(students, *, only_open: bool = False):
    from roadmap.models import Task, TaskStatus

    rows = Task.objects.filter(student__in=students).select_related("student", "student__group")
    if only_open:
        rows = rows.exclude(status__in=TaskStatus.closed())
    return rows


def _task_row(task) -> dict:
    return {
        "id": task.pk,
        "student": task.student_id,
        "student_name": task.student.full_name,
        "group": task.student.group.code if task.student.group_id else "",
        "title": task.title,
        "status": task.status,
        "status_title": task.get_status_display(),
        "due_date": task.effective_due_date,
        "is_overdue": task.is_overdue,
        "origin": task.origin,
        "origin_title": task.origin_title,
        "created_at": task.created_at,
    }


def _journal(students, limit: int = HOME_JOURNAL) -> list[dict]:
    """Последние действия по своим ученикам — кто что подтвердил и поправил.

    Читается из общего журнала (`AuditLog`), второго источника у истории
    нет. Полный экран журнала с фильтрами — фаза 62.
    """
    from core.models import AuditLog

    ids = list(students.values_list("pk", flat=True))
    rows = AuditLog.objects.filter(student_id__in=ids).select_related("actor").order_by("-created_at")[:limit]

    from core.labels import field_title, value_title

    out = []
    for row in rows:
        who = row.actor
        out.append(
            {
                "id": row.pk,
                "who": (who.full_name or who.email) if who else (row.actor_title or "система"),
                "what": field_title(row.model_label, row.field_name),
                "value": value_title(row.model_label, row.field_name, row.new_value) or row.new_value,
                "student_group": row.student_group,
                "at": row.created_at,
            }
        )
    return out


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def overview(request):
    """Главная куратора: приветствие, четыре числа, очередь, задачи, корзины."""
    denied = _deny(request)
    if denied:
        return denied

    from suggestions.student_queue import queue_payload

    groups = _groups(request)
    students = _students(request)
    state = attention.state_of(students)
    queue = queue_payload(ROLE_CURATOR, groups)
    tasks = _tasks_of(students, only_open=True)
    today = timezone.localdate()
    soon = [t for t in tasks if t.effective_due_date and t.effective_due_date <= today + dt.timedelta(days=2)]
    overdue = [t for t in tasks if t.is_overdue]
    counts = attention.counts(students)
    by_code = {row["code"]: row["count"] for row in counts}

    return Response(
        {
            "role": ROLE_CURATOR,
            "title": "Кабинет куратора",
            "owner": (request.user.full_name or request.user.email) + " · куратор",
            "groups": _group_rows(request.user),
            "students_total": students.count(),
            "queue_total": len(queue),
            "tasks_due": len(soon),
            # четыре числа-кнопки, как в прототипе: очередь, без цели, документы
            # не собраны, истекает срок (фаза 62). «Пробника не было» и «просроченные
            # задачи» остаются в корзинах и на экране задач
            "numbers": [
                {"code": "queue", "label": "ждут подтверждения", "value": len(queue), "tone": "brand", "to": "/queue"},
                {
                    "code": "nogoal",
                    "label": "без цели по экзаменам",
                    "value": by_code.get("nogoal", 0),
                    "tone": "warn",
                    "to": "/students?bucket=nogoal",
                },
                {
                    "code": "docs",
                    "label": "документы не собраны",
                    "value": by_code.get("docs", 0),
                    "tone": "risk",
                    "to": "/documents?f=missing",
                },
                {
                    "code": "expiring",
                    "label": "истекает срок документа",
                    "value": sum(1 for row in state.values() if row["documents_expiring"]),
                    "tone": "indigo",
                    "to": "/documents?f=expiring",
                },
            ],
            "tasks_overdue": len(overdue),
            "queue": queue[:HOME_QUEUE],
            "tasks": [_task_row(t) for t in sorted(tasks, key=lambda t: (t.effective_due_date or today))[:HOME_TASKS]],
            "buckets": counts,
            "journal": _journal(students),
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def students_list(request):
    """Таблица учеников: чтение, корзины и внутренняя метка."""
    denied = _deny(request)
    if denied:
        return denied

    students = _students(request)
    bucket = str(request.query_params.get("bucket") or "").strip()
    if bucket:
        students = attention.filter_by(students, bucket)
    search = str(request.query_params.get("search") or "").strip()
    if search:
        students = students.filter(Q(last_name__icontains=search) | Q(first_name__icontains=search))

    state = attention.state_of(students)
    rows = [_student_row(student, state[student.pk]) for student in students]
    return Response(
        {
            "results": rows,
            "buckets": attention.counts(_students(request)),
            "groups": _group_rows(request.user),
        }
    )


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def students_export(request):
    """Та же таблица книгой XLSX — общим кодом выгрузки (`core.exports`)."""
    denied = _deny(request)
    if denied:
        return denied

    from core.exports import Column, workbook_response

    students = _students(request)
    bucket = str(request.query_params.get("bucket") or "").strip()
    if bucket:
        students = attention.filter_by(students, bucket)
    state = attention.state_of(students)
    rows = [_student_row(student, state[student.pk]) for student in students]

    def pair(current_key: str, target_key: str):
        def read(row):
            current = row[current_key]
            target = row[target_key]
            return f"{current if current is not None else '—'} → {target if target is not None else 'нет цели'}"

        return read

    columns = (
        Column("Ученик", lambda row: row["full_name"], 30),
        Column("Группа", lambda row: row["group"], 12),
        Column("Класс", lambda row: row["grade"], 8),
        Column("IELTS", pair("ielts_current", "ielts_target"), 16),
        Column("SAT", pair("sat_current", "sat_target"), 16),
        Column("Последний пробник", lambda row: row["last_mock_date"], 20),
        Column("Документы", lambda row: f"{row['documents_collected']} / {row['documents_total']}", 14),
        Column("Статус", lambda row: row["status_title"], 18),
    )
    stamp = timezone.localdate().strftime("%Y-%m-%d")
    code = str(request.query_params.get("group") or "все-группы").strip()
    return workbook_response(
        filename=f"ученики-{code}-{stamp}.xlsx",
        sheet="Ученики",
        columns=columns,
        rows=rows,
    )


def _own_student(request, pk: int) -> Student:
    """Ученик своей группы или 404 — существования чужого куратор не узнаёт."""
    from core.scope import visible_students

    student = (
        visible_students(request.user)
        .filter(pk=pk)
        .select_related("group", "exam", "behavior", "admission", "talent", "sport")
        .first()
    )
    if student is None:
        raise NotFound("Ученика нет в ваших группах")
    return student


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_card(request, pk: int):
    """Карточка ученика: пять вкладок одним ответом.

    Собирается из тех же служб, что и остальные экраны: портфолио —
    `students.portfolio`, корзины — `students.attention`, очередь —
    `suggestions.student_queue`. Своих правил подсчёта здесь нет.
    """
    denied = _deny(request)
    if denied:
        return denied

    from students import portfolio
    from suggestions.student_queue import queue_payload

    student = _own_student(request, pk)
    state = attention.state_of(Student.objects.filter(pk=student.pk))[student.pk]
    mine = [row for row in queue_payload(ROLE_CURATOR, curated_group_ids(request.user)) if row["student"] == student.pk]

    from students.models import IELTS_SECTIONS, ExamAttempt, ExamType

    mock_rows = list(
        ExamAttempt.objects.filter(student=student, attempt_format="mock")
        .select_related("mock_import", "mock_import__uploaded_by")
        .order_by("date")
    )

    def _sections(row) -> dict:
        return {name: float(getattr(row, name)) if getattr(row, name) is not None else None for name in IELTS_SECTIONS}

    mocks = [
        {
            "id": row.pk,
            "exam": row.exam_type,
            "date": row.date,
            "score": float(row.total_score) if row.total_score is not None else None,
            "source": row.source,
            "source_title": row.get_source_display(),
            # чей это пробник и кто его залил — видно у каждой строки (фаза 63)
            "sections": _sections(row) if row.exam_type == ExamType.IELTS else {},
            "mock_import": row.mock_import_id,
            "teacher": row.mock_import.teacher if row.mock_import_id else "",
            "uploaded_by": (
                (row.mock_import.uploaded_by.full_name or row.mock_import.uploaded_by.email)
                if row.mock_import_id and row.mock_import.uploaded_by_id
                else ""
            ),
        }
        for row in mock_rows
    ]

    # секции последнего пробника IELTS и динамика по каждой (фаза 63):
    # отдельных целей по секциям нет — все четыре меряются общей целью
    ielts_mocks = [row for row in mock_rows if row.exam_type == ExamType.IELTS and row.listening is not None]
    sections_block = {
        "target": state["ielts_target"],
        "last_date": ielts_mocks[-1].date if ielts_mocks else None,
        "last": _sections(ielts_mocks[-1]) if ielts_mocks else {},
        # искра рисуется от двух точек: по одной линию не проводят
        "trend": (
            {
                name: [float(getattr(row, name)) for row in ielts_mocks if getattr(row, name) is not None]
                for name in IELTS_SECTIONS
            }
            if len(ielts_mocks) > 1
            else {}
        ),
    }

    from universities.models import StudentUniversity

    unis = [
        {
            "id": row.pk,
            "program": row.program.name if row.program_id else "",
            "university": row.program.university.name if row.program_id else "",
            "tier": row.tier,
            "tier_title": row.get_tier_display() if row.tier else "",
            "deadline": row.admission_round.deadline if row.admission_round_id else None,
        }
        for row in StudentUniversity.objects.filter(student=student)
        .select_related("program__university", "admission_round")
        .order_by("program__university__name")
    ]

    from students.models import ParentContact

    contacts = [
        {
            "id": row.pk,
            "full_name": row.full_name,
            "relation_title": row.get_relation_display(),
            "phone": row.phone,
            "email": row.email,
        }
        for row in ParentContact.objects.filter(student=student).order_by("-is_primary", "full_name")
    ]

    from students import documents
    from students.models import CuratorNote

    doc_state = documents.state_of(Student.objects.filter(pk=student.pk))[student.pk]
    doc_cells = [
        {"code": code, "title": DocumentType(code).label, **doc_state["cells"][code]} for code in REQUIRED_DOCUMENTS
    ]
    portfolio_state = portfolio.state(student)
    behavior = getattr(student, "behavior", None)

    # блок «Поступление» (фаза 65): данные Асем, GPA из экзаменов и признак
    # «пароли есть / нет». Самих паролей здесь нет — их отдаёт только показ
    from core.domains import DOMAINS

    # дисциплина (фаза 66): дни и замечания словами — ими куратор
    # разговаривает с родителем, числа профиля для этого не годятся
    from students import credentials, discipline
    from students.models import AttemptSource, CredentialKind, ExamAttempt

    behavior_block = {
        "attendance_percent": getattr(behavior, "attendance_percent", None),
        "remarks_count": getattr(behavior, "remarks_count", 0),
        "may_write": discipline.may_write(request.user, student),
        "days": discipline.attendance_history(student, limit=30),
        "remarks": discipline.remarks_of(student),
        "owner": DOMAINS["behavior"].owner_name,
    }

    admission = getattr(student, "admission", None)
    exam_profile = getattr(student, "exam", None)
    present = credentials.state(student)
    imported = [
        {
            "id": row.pk,
            "exam": row.exam_type,
            "score": float(row.total_score) if row.total_score is not None else None,
            "date": row.date,
            "date_unknown": row.date_unknown,
            "source_title": row.get_source_display(),
        }
        for row in ExamAttempt.objects.filter(student=student, source=AttemptSource.ADMISSION_IMPORT).order_by(
            "exam_type", "created_at"
        )
    ]
    admission_block = {
        "student_phone": getattr(admission, "student_phone", "") or "",
        "email": student.email,
        "common_app_email": getattr(admission, "common_app_email", "") or "",
        "drive_folder_url": getattr(admission, "drive_folder_url", "") or "",
        "gpa": float(exam_profile.gpa) if getattr(exam_profile, "gpa", None) is not None else None,
        "owner": DOMAINS["admission"].owner_name,
        "may_reveal": credentials.may_view(request.user, student),
        "may_edit_credentials": credentials.may_edit(request.user, student),
        "credentials": [
            {"kind": kind, "title": CredentialKind(kind).label, "present": present[kind]}
            for kind in CredentialKind.values
        ],
        "imported_attempts": imported,
    }
    return Response(
        {
            "id": student.pk,
            "full_name": student.full_name,
            "grade": student.grade,
            "group": student.group.code if student.group_id else "",
            "email": student.email,
            "curator": request.user.full_name or request.user.email,
            "status": getattr(behavior, "status", "") or "",
            "status_title": behavior.get_status_display() if behavior and behavior.status else "",
            "exams": {
                "ielts_current": state["ielts_current"],
                "ielts_target": state["ielts_target"],
                "ielts_exam_date": state["ielts_exam_date"],
                "sat_current": state["sat_current"],
                "sat_target": state["sat_target"],
                "sat_exam_date": state["sat_exam_date"],
                "last_mock_date": state["last_mock_date"],
                "mocks_total": len(mocks),
            },
            "mocks": mocks,
            "sections": sections_block,
            "universities": unis,
            "portfolio": {
                "percent": portfolio_state["percent"],
                "sections": portfolio_state["sections"],
                "activities": portfolio_state.get("counts", {}),
            },
            "contacts": contacts,
            "admission": admission_block,
            "behavior": behavior_block,
            "buckets": [
                {"code": b.code, "title": b.title, "tone": b.tone}
                for b in attention.BUCKETS
                if b.code in state["buckets"]
            ],
            "queue": mine,
            "tasks": [_task_row(t) for t in _tasks_of(Student.objects.filter(pk=student.pk)).order_by("-created_at")],
            "documents": {
                "collected": doc_state["collected"],
                "total": doc_state["total"],
                "missing": doc_state["missing"],
                "rows": doc_cells,
            },
            "notes_total": CuratorNote.objects.filter(student=student).count(),
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def tasks(request):
    """Задачи ученикам: список с фильтром и постановка одному или группе."""
    denied = _deny(request)
    if denied:
        return denied

    from roadmap.models import TaskStatus
    from roadmap.services import assign_to_students

    students = _students(request)
    if request.method == "GET":
        rows = _tasks_of(students).order_by("-created_at")
        chosen = str(request.query_params.get("filter") or "open").strip()
        rows = list(rows)
        kept = {
            "open": [t for t in rows if t.status not in TaskStatus.closed()],
            "late": [t for t in rows if t.is_overdue],
            "done": [t for t in rows if t.status == TaskStatus.DONE],
            "cancelled": [t for t in rows if t.status == TaskStatus.CANCELLED],
            "all": rows,
        }
        counts = {name: len(value) for name, value in kept.items()}
        return Response({"results": [_task_row(t) for t in kept.get(chosen, kept["open"])], "counts": counts})

    title = str(request.data.get("title") or "").strip()
    if not title:
        return Response({"detail": "Напишите, что сделать"}, status=http.HTTP_400_BAD_REQUEST)

    due_raw = str(request.data.get("due_date") or "").strip()
    due = None
    if due_raw:
        try:
            due = dt.date.fromisoformat(due_raw)
        except ValueError:
            return Response({"detail": "Срок непонятен — нужна дата"}, status=http.HTTP_400_BAD_REQUEST)

    group_code = str(request.data.get("group") or "").strip()
    if group_code:
        # всей группе — по задаче на каждого: закрывает её каждый сам
        targets = students.filter(group__code__iexact=group_code)
    else:
        targets = students.filter(pk=request.data.get("student"))
    targets = list(targets)
    if not targets:
        return Response(
            {"detail": "Некому ставить задачу — проверьте ученика или группу"}, status=http.HTTP_404_NOT_FOUND
        )

    made = assign_to_students(
        targets,
        title=title,
        due_date=due,
        category=str(request.data.get("category") or ""),
        actor=request.user,
    )
    return Response({"created": len(made), "students": [t.student_id for t in made]}, status=http.HTTP_201_CREATED)


@extend_schema(responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def task_status(request, pk: int):
    """Закрыть, отменить или вернуть задачу — тем же кодом, что у ученика."""
    denied = _deny(request)
    if denied:
        return denied

    from roadmap.models import Task, TaskStatus
    from roadmap.services import complete

    task = Task.objects.filter(pk=pk, student__in=_students(request)).select_related("student__group").first()
    if task is None:
        raise NotFound("Задачи нет в ваших группах")

    wanted = str(request.data.get("status") or "").strip()
    allowed = {TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.TODO}
    if wanted not in allowed:
        return Response({"detail": "Задачу можно закрыть, отменить или вернуть"}, status=http.HTTP_400_BAD_REQUEST)
    return Response(_task_row(complete(task, status=wanted, actor=request.user)))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def profile(request):
    """Профиль куратора: группы, что подтверждает, что читает."""
    denied = _deny(request)
    if denied:
        return denied

    from core.domains import CURATOR_CONFIRM_DOMAINS, CURATOR_DOMAINS, CURATOR_WRITE_DOMAINS, DOMAINS

    return Response(
        {
            "full_name": request.user.full_name,
            "email": request.user.email,
            "role_title": "Куратор",
            "groups": _group_rows(request.user),
            "confirms": [DOMAINS[code].title for code in CURATOR_CONFIRM_DOMAINS if code in DOMAINS],
            # дисциплину куратор ведёт сам по своим группам (фаза 66)
            "writes": [DOMAINS[code].title for code in CURATOR_WRITE_DOMAINS if code in DOMAINS],
            "reads": [d.title for d in DOMAINS.values() if d.code not in CURATOR_DOMAINS],
        }
    )


# --- Документы (фаза 62) ------------------------------------------------------------


def _documents_rows(request):
    """Строки матрицы по текущим группам и фильтру экрана."""
    from students import documents

    students = _students(request)
    picked = str(request.query_params.get("f") or "").strip()
    shown = documents.filter_students(students, picked) if picked else students
    state = documents.state_of(shown)
    rows = [
        {
            "id": student.pk,
            "full_name": student.full_name,
            "group": student.group.code if student.group_id else "",
            "collected": state[student.pk]["collected"],
            "total": state[student.pk]["total"],
            "cells": [{"code": code, **state[student.pk]["cells"][code]} for code in REQUIRED_DOCUMENTS],
        }
        for student in shown
    ]
    return students, rows


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def documents_matrix(request):
    """Экран «Документы»: пять чисел, фильтры, матрица ученик × тип."""
    denied = _deny(request)
    if denied:
        return denied

    from students import documents

    students, rows = _documents_rows(request)
    everything = documents.state_of(students)
    return Response(
        {
            "types": documents.types(),
            "counts": documents.counts(students),
            "results": rows,
            "groups": _group_rows(request.user),
            # сколько задач уйдёт по «напомнить всем» — модалка называет число
            "missing_students": sum(1 for row in everything.values() if row["missing"]),
            "filters": {
                "missing": sum(1 for row in everything.values() if row["missing"]),
                "pending": sum(1 for row in everything.values() if row["pending"]),
                "expiring": sum(1 for row in everything.values() if row["expiring"]),
            },
        }
    )


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def documents_export(request):
    """Матрица книгой XLSX — тем же кодом, что таблица учеников."""
    denied = _deny(request)
    if denied:
        return denied

    from core.exports import Column, workbook_response

    _students_all, rows = _documents_rows(request)
    titles = {
        "none": "нет",
        "pending": "ждёт",
        "confirmed": "подтверждён",
        "rejected": "отклонён",
        "expiring": "истекает",
    }

    def cell(index: int):
        return lambda row: titles.get(row["cells"][index]["state"], "")

    columns = [Column("Ученик", lambda row: row["full_name"], 30), Column("Группа", lambda row: row["group"], 12)]
    for index, code in enumerate(REQUIRED_DOCUMENTS):
        columns.append(Column(DocumentType(code).label, cell(index), 18))
    columns.append(Column("Собрано", lambda row: f"{row['collected']} / {row['total']}", 12))
    stamp = timezone.localdate().strftime("%Y-%m-%d")
    code = str(request.query_params.get("group") or "все-группы").strip()
    return workbook_response(filename=f"документы-{code}-{stamp}.xlsx", sheet="Документы", columns=columns, rows=rows)


@extend_schema(responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def documents_remind(request):
    """«Напомнить всем, у кого не хватает»: по задаче каждому со списком его недостающих."""
    denied = _deny(request)
    if denied:
        return denied

    from students import documents

    students = _students(request)
    picked = request.data.get("student")
    if picked:
        students = students.filter(pk=picked)
        if not students.exists():
            raise NotFound("Ученика нет в ваших группах")
    made = documents.remind(students, actor=request.user)
    return Response({"created": len(made), "students": made})


@extend_schema(responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def document_revoke(request, pk: int):
    """Снять подтверждение: документ снова в очереди, запись в журнале."""
    denied = _deny(request)
    if denied:
        return denied

    from students import documents
    from students.models import StudentDocument

    row = StudentDocument.objects.filter(pk=pk, student__in=_students(request)).select_related("student").first()
    if row is None:
        raise NotFound("Документа нет в ваших группах")
    try:
        documents.revoke(row, actor=request.user)
    except ValueError as error:
        return Response({"detail": str(error)}, status=http.HTTP_400_BAD_REQUEST)
    return Response({"status": row.status, "state": row.state})


# --- Звонок родителям и передача владельцу домена (фаза 62) -------------------------


@extend_schema(responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def parent_call(request, pk: int):
    """Итог звонка: с текстом — заметка «Звонок родителям: …» и журнал, без — только журнал."""
    denied = _deny(request)
    if denied:
        return denied

    from core.audit import record_event
    from students.models import CuratorNote

    student = _own_student(request, pk)
    text = str(request.data.get("text") or "").strip()
    if text:
        CuratorNote.objects.create(
            student=student,
            author=request.user,
            author_role=request.user.role,
            text=f"Звонок родителям: {text}",
        )
    record_event(student=student, code="parent_call", text=text or "без записи", actor=request.user)
    return Response({"noted": bool(text)})


@extend_schema(responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def escalate_student(request, pk: int):
    """Передать вопрос по ученику владельцу домена — Кымбат или Асем — с комментарием."""
    denied = _deny(request)
    if denied:
        return denied

    from suggestions.followups import EscalationRefused
    from suggestions.followups import escalate_student as hand_over

    student = _own_student(request, pk)
    domain = str(request.data.get("domain") or "exam").strip()
    try:
        sent = hand_over(
            student, actor=request.user, domain_code=domain, comment=str(request.data.get("comment") or "")
        )
    except EscalationRefused as error:
        return Response({"detail": str(error)}, status=http.HTTP_400_BAD_REQUEST)
    return Response({"sent": sent})


# --- Журнал (фаза 62) ---------------------------------------------------------------


def _journal_rows(request, limit: int = 300) -> list[dict]:
    """Действия по своим группам — свои, владельцев доменов, директора школы.

    Группа берётся из снимка записи (фаза 60): ученик, переведённый
    в другую группу, не уносит с собой историю прежнего куратора.
    """
    from core.models import AuditLog

    codes = [StudyGroup.objects.filter(pk=pk).values_list("code", flat=True).first() for pk in _groups(request)]
    rows = (
        AuditLog.objects.filter(student_group__in=[c for c in codes if c])
        .select_related("actor")
        .order_by("-created_at")[:limit]
    )
    from core.domains import ROLE_TITLES
    from core.labels import field_title, value_title

    students = {
        s.pk: s.full_name for s in Student.all_objects.filter(pk__in={r.student_id for r in rows if r.student_id})
    }
    return [
        {
            "id": row.pk,
            "at": row.created_at,
            "who": (row.actor.full_name or row.actor.email) if row.actor else (row.actor_title or "система"),
            "role": ROLE_TITLES.get(row.actor_role, ""),
            "student": students.get(row.student_id, ""),
            "student_id": row.student_id,
            "group": row.student_group,
            "what": field_title(row.model_label, row.field_name),
            "was": value_title(row.model_label, row.field_name, row.old_value) or row.old_value,
            "now": value_title(row.model_label, row.field_name, row.new_value) or row.new_value,
        }
        for row in rows
    ]


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def journal(request):
    denied = _deny(request)
    if denied:
        return denied
    return Response({"results": _journal_rows(request), "groups": _group_rows(request.user)})


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def journal_export(request):
    denied = _deny(request)
    if denied:
        return denied

    from core.exports import Column, workbook_response

    columns = (
        Column("Когда", lambda row: row["at"], 20),
        Column("Кто", lambda row: row["who"], 24),
        Column("Роль", lambda row: row["role"], 18),
        Column("Ученик", lambda row: row["student"], 28),
        Column("Группа", lambda row: row["group"], 10),
        Column("Что", lambda row: row["what"], 28),
        Column("Было", lambda row: row["was"], 20),
        Column("Стало", lambda row: row["now"], 28),
    )
    stamp = timezone.localdate().strftime("%Y-%m-%d")
    return workbook_response(
        filename=f"журнал-{stamp}.xlsx", sheet="Журнал", columns=columns, rows=_journal_rows(request, limit=2000)
    )
