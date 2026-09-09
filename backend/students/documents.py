"""Проверка документов ученика (фаза 62): очередь, решение, матрица сбора.

Документ проходит: загрузка → «ждёт проверки» и строка в очереди домена
«Документы» → подтверждение или отклонение с причиной → при отклонении
ученик загружает заново, прежний файл остаётся историей.

Очередь — та же, что у баллов (`suggestions`): строка домена `documents`
с одной правкой «проверка: ждёт → подтверждён». Подтверждение применяет
её обычным путём (запись в журнал, инвариант №9); отклонение ставит
документу статус и причину через тот же аудит. Второго кода очереди
для документов нет — иначе 409, замок и права разошлись бы с баллами.

Что считать «собрано» — здесь же, одним местом: матрица экрана
«Документы», столбец в таблице учеников, число на главной, корзина
«документы не собраны» и чек-лист ученика берут одно и то же.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from core.audit import apply_changes, record_event
from core.domains import ROLE_STUDENT, Source
from students.models import DocumentStatus, DocumentType, Student, StudentDocument
from students.portfolio import REQUIRED_DOCUMENTS

#: Состояния ячейки матрицы. «Нет» — файла не загружали ни разу.
STATES = ("none", "pending", "confirmed", "rejected", "expiring")

#: Собранным считается подтверждённый — в том числе с истекающим сроком:
#: файл есть и проверен, а срок — повод напомнить, не дыра в наборе.
COLLECTED = ("confirmed", "expiring")


def types() -> list[dict]:
    """Пять типов чек-листа с подписями — единственный список для всех экранов."""
    return [{"code": code, "title": DocumentType(code).label} for code in REQUIRED_DOCUMENTS]


def latest_by_type(students: QuerySet[Student]) -> dict[int, dict[str, StudentDocument]]:
    """Последний документ каждого типа у каждого ученика.

    История загрузок остаётся строками (отклонённый файл не удаляется),
    а состояние типа — по последней: перезагрузил после отклонения —
    и тип снова «ждёт проверки».
    """
    out: dict[int, dict[str, StudentDocument]] = {}
    rows = StudentDocument.objects.filter(student__in=students).order_by("student_id", "doc_type", "created_at", "id")
    for row in rows:
        out.setdefault(row.student_id, {})[row.doc_type] = row
    return out


def state_of(students: QuerySet[Student]) -> dict[int, dict]:
    """По каждому ученику: состояние каждого типа и сколько собрано."""
    from suggestions.models import Suggestion, SuggestionSource, SuggestionStatus

    latest = latest_by_type(students)
    # нерешённые строки очереди по документам — одним запросом, не по ячейке
    pending_rows = dict(
        Suggestion.objects.filter(
            source_type=SuggestionSource.DOCUMENT,
            status=SuggestionStatus.PENDING,
            changes__model_label="students.StudentDocument",
        ).values_list("changes__object_id", "pk")
    )
    out: dict[int, dict] = {}
    for student in students:
        mine = latest.get(student.pk, {})
        cells: dict[str, dict] = {}
        for code in REQUIRED_DOCUMENTS:
            row = mine.get(code)
            cells[code] = {
                "state": row.state if row else "none",
                "document": row.pk if row else None,
                # имя файла — как назвал ученик, иначе само имя файла: повторять тип незачем
                "file_name": (row.title or (Path(row.file.name).name if row.file else row.external_url)) if row else "",
                "content_type": row.content_type if row else "",
                # документ-ссылка (фаза 65): свой значок, предпросмотр открывает адрес
                "is_link": row.is_link if row else False,
                "external_url": row.external_url if row else "",
                "reject_reason": row.reject_reason if row else "",
                "expires_at": row.expires_at if row else None,
                # строка очереди — для кнопок «подтвердить / отклонить» в предпросмотре
                "suggestion": pending_rows.get(str(row.pk)) if row else None,
            }
        collected = sum(1 for cell in cells.values() if cell["state"] in COLLECTED)
        out[student.pk] = {
            "cells": cells,
            "collected": collected,
            "total": len(REQUIRED_DOCUMENTS),
            "missing": [code for code, cell in cells.items() if cell["state"] in ("none", "rejected")],
            "pending": any(cell["state"] == "pending" for cell in cells.values()),
            "expiring": any(cell["state"] == "expiring" for cell in cells.values()),
            "rejected": any(cell["state"] == "rejected" for cell in cells.values()),
        }
    return out


def counts(students: QuerySet[Student]) -> list[dict]:
    """Пять чисел «собрано / всего» по типам — верх экрана «Документы»."""
    state = state_of(students)
    total = len(state)
    return [
        {
            "code": code,
            "title": DocumentType(code).label,
            "collected": sum(1 for row in state.values() if row["cells"][code]["state"] in COLLECTED),
            "total": total,
        }
        for code in REQUIRED_DOCUMENTS
    ]


def filter_students(students: QuerySet[Student], code: str) -> QuerySet[Student]:
    """Фильтры экрана: не собраны, ждут проверки, истекает срок."""
    if code not in ("missing", "pending", "expiring"):
        return students
    state = state_of(students)
    keep = [
        pk
        for pk, row in state.items()
        if (code == "missing" and row["missing"])
        or (code == "pending" and row["pending"])
        or (code == "expiring" and row["expiring"])
    ]
    return students.filter(pk__in=keep)


# --- Очередь -------------------------------------------------------------------


def _change_kwargs(document: StudentDocument) -> dict:
    return {
        "student": document.student,
        "model_label": "students.StudentDocument",
        "object_id": str(document.pk),
        "field_name": "status",
        "old_value": DocumentStatus.PENDING,
        "new_value": DocumentStatus.CONFIRMED,
        "confidence": 1,
        "is_accepted": True,
    }


@transaction.atomic
def submit(document: StudentDocument, *, author):
    """Поставить документ в очередь проверки — при загрузке и при снятии подтверждения."""
    from suggestions.models import Suggestion, SuggestionChange, SuggestionSource, SuggestionStatus

    suggestion = Suggestion.objects.create(
        author=author if getattr(author, "pk", None) else None,
        role=ROLE_STUDENT,
        domain_code="documents",
        source_type=SuggestionSource.DOCUMENT,
        status=SuggestionStatus.PENDING,
    )
    SuggestionChange.objects.create(suggestion=suggestion, **_change_kwargs(document))
    return suggestion


def open_suggestion(document: StudentDocument):
    """Нерешённая строка очереди этого документа, если есть."""
    from suggestions.models import Suggestion, SuggestionSource, SuggestionStatus

    return (
        Suggestion.objects.filter(
            source_type=SuggestionSource.DOCUMENT,
            status=SuggestionStatus.PENDING,
            changes__object_id=str(document.pk),
            changes__model_label="students.StudentDocument",
        )
        .distinct()
        .first()
    )


def document_of(suggestion) -> StudentDocument | None:
    """Документ строки очереди — по её единственной правке."""
    change = suggestion.changes.filter(model_label="students.StudentDocument").first()
    if change is None or not change.object_id:
        return None
    return StudentDocument.objects.select_related("student", "student__group").filter(pk=change.object_id).first()


def after_decision(suggestion, *, actor) -> None:
    """Довести документ до состояния решения по строке очереди.

    Подтверждение уже записано применением правки (статус «подтверждён»).
    Здесь — снимок проверившего и, при отклонении, статус с причиной:
    ученик прочитает её у себя, имени проверившего не увидит.
    """
    from suggestions.models import SuggestionStatus

    document = document_of(suggestion)
    if document is None:
        return
    if suggestion.status == SuggestionStatus.REJECTED:
        apply_changes(
            document,
            {"status": DocumentStatus.REJECTED, "reject_reason": suggestion.reject_reason},
            actor=actor,
            source=Source.STUDENT_PROPOSAL,
            suggestion=suggestion,
        )
    document.reviewed_at = timezone.now()
    document.reviewed_by = actor if getattr(actor, "pk", None) else None
    document.save(update_fields=["reviewed_at", "reviewed_by"])


@transaction.atomic
def revoke(document: StudentDocument, *, actor):
    """Снять подтверждение: документ снова «ждёт проверки» и в очереди, с записью в журнал."""
    if document.status != DocumentStatus.CONFIRMED:
        raise ValueError("Снять подтверждение можно только с подтверждённого документа")
    apply_changes(
        document,
        {"status": DocumentStatus.PENDING, "reject_reason": ""},
        actor=actor,
        source=Source.MANUAL,
    )
    document.reviewed_at = None
    document.reviewed_by = None
    document.save(update_fields=["reviewed_at", "reviewed_by"])
    return submit(document, author=document.student.user)


# --- Напоминания задачей ---------------------------------------------------------


def remind(students: QuerySet[Student], *, actor, days: int = 7) -> list[dict]:
    """Каждому, у кого не хватает, — задача со списком именно его недостающих."""
    from roadmap.models import TaskCategory
    from roadmap.services import assign_to_students

    state = state_of(students)
    due = timezone.localdate() + dt.timedelta(days=days)
    made = []
    for student in students:
        missing = state[student.pk]["missing"]
        if not missing:
            continue
        titles = ", ".join(DocumentType(code).label for code in missing)
        assign_to_students(
            [student],
            title=f"Загрузить: {titles}",
            due_date=due,
            category=TaskCategory.DOCUMENTS,
            actor=actor,
        )
        record_event(student=student, code="document_reminder", text=titles, actor=actor)
        made.append({"student": student.pk, "missing": missing})
    return made


# --- Уведомления о сроке -----------------------------------------------------------


def send_expiry_notices(today: dt.date | None = None) -> int:
    """Куратору — за `DOCUMENT_NOTICE_DAYS` дней до срока подтверждённого документа."""
    from accounts.curators import curator_of
    from core.models import Notification
    from roadmap.reminders import _notify_once

    today = today or timezone.localdate()
    when = today + dt.timedelta(days=settings.CURATOR_RULES["DOCUMENT_NOTICE_DAYS"])
    sent = 0
    rows = StudentDocument.objects.filter(status=DocumentStatus.CONFIRMED, expires_at=when).select_related(
        "student", "student__group"
    )
    for row in rows:
        assignment = curator_of(row.student.group) if row.student.group_id else None
        if assignment is None:
            continue
        if _notify_once(
            assignment.curator,
            kind=Notification.Kind.DOCUMENT_EXPIRING,
            template="Через {days} дней истекает срок документа «{doc}» у {student}",
            link=f"/students/{row.student_id}?tab=documents",
            days=settings.CURATOR_RULES["DOCUMENT_NOTICE_DAYS"],
            doc=row.get_doc_type_display(),
            student=row.student.full_name,
        ):
            sent += 1
    return sent
