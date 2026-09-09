"""Ручки дисциплины и писем (фаза 66).

Дисциплину ведут двое: куратор — по своим группам, директор школы —
по всей школе. Право одно и то же, разная только граница, и держит её
общая выборка `core.scope` — второго списка групп здесь нет.

Писем сервер не шлёт. Ручка писем собирает `mailto:` и пишет в журнал
«письмо открыто»; отправку подтвердить нельзя, и так это и называется.
"""

from __future__ import annotations

import datetime as dt

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.curators import curated_group_ids
from core.domains import ROLE_ADMIN, ROLE_CURATOR, ROLE_STUDENT
from core.scope import visible_students
from students import discipline, letters
from students.models import BehaviorRemark, Student, StudyGroup

#: Кто ведёт дисциплину: владелец домена по всей школе, куратор — по своим
#: группам, администратор — как везде. Ученику закрыто наглухо
DISCIPLINE_ROLES = ("director_behavior", ROLE_CURATOR, ROLE_ADMIN)

STUDENT_REFUSAL = "Посещаемость и замечания ведёт школа"


def _forbidden(detail: str = STUDENT_REFUSAL) -> Response:
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


def _not_found() -> Response:
    return Response({"detail": "Не найдено"}, status=status.HTTP_404_NOT_FOUND)


def _date(raw) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def _group_for(user, raw) -> StudyGroup | None:
    """Группа, которую человек вправе вести. Чужая — как несуществующая.

    404, а не 403: по отказу не должно быть видно, какие ещё группы
    есть в школе.
    """
    group = None
    if str(raw or "").isdigit():
        group = StudyGroup.objects.filter(pk=int(raw)).first()
    if group is None:
        group = StudyGroup.objects.filter(code__iexact=str(raw or "").strip()).first()
    if group is None:
        return None
    role = getattr(user, "role", "")
    if role in ("director_behavior", ROLE_ADMIN):
        return group
    if role == ROLE_CURATOR and group.pk in curated_group_ids(user):
        return group
    return None


def _student_for(user, pk: int) -> Student | None:
    return visible_students(user).filter(pk=pk).first()


# --- Посещаемость ------------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_day(request):
    """Лист посещаемости группы за день: все присутствуют, пока не снято."""
    if request.user.role == ROLE_STUDENT:
        return _forbidden()
    if request.user.role not in DISCIPLINE_ROLES:
        return _forbidden("Посещаемость ведут куратор и директор школы")
    groups = _my_groups(request.user)
    raw = request.query_params.get("group")
    # экран открывается без выбранной группы: подставляем первую доступную,
    # иначе человек видит пустоту и должен догадаться выбрать
    group = _group_for(request.user, raw) if raw else (_group_for(request.user, groups[0]["id"]) if groups else None)
    if group is None:
        if raw:
            return _not_found()
        return Response(
            {
                "group": None,
                "group_code": "",
                "date": str(_date(request.query_params.get("date")) or dt.date.today()),
                "saved": False,
                "late": False,
                "rows": [],
                "absent": 0,
                "total": 0,
                "groups": groups,
            }
        )
    date = _date(request.query_params.get("date")) or dt.date.today()
    payload = discipline.day_sheet(group=group, date=date)
    payload["groups"] = _my_groups(request.user)
    return Response(payload)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def attendance_save(request):
    """Сохранить лист за день. Правка старше недели уходит в журнал отдельно."""
    if request.user.role == ROLE_STUDENT:
        return _forbidden()
    if request.user.role not in DISCIPLINE_ROLES:
        return _forbidden("Посещаемость ведут куратор и директор школы")
    group = _group_for(request.user, request.data.get("group"))
    if group is None:
        return _not_found()
    date = _date(request.data.get("date"))
    if date is None:
        return Response({"detail": "Не указана дата"}, status=status.HTTP_400_BAD_REQUEST)
    if date > dt.date.today():
        return Response({"detail": "День ещё не наступил"}, status=status.HTTP_400_BAD_REQUEST)
    rows = request.data.get("rows")
    if not isinstance(rows, list):
        return Response({"detail": "Не переданы отметки"}, status=status.HTTP_400_BAD_REQUEST)
    payload = discipline.save_day(group=group, date=date, rows=rows, actor=request.user)
    payload["groups"] = _my_groups(request.user)
    return Response(payload)


def _my_groups(user) -> list[dict]:
    """Группы, доступные человеку: куратору — свои, директору — все."""
    role = getattr(user, "role", "")
    query = StudyGroup.objects.filter(is_active=True)
    if role == ROLE_CURATOR:
        query = query.filter(pk__in=curated_group_ids(user))
    return [{"id": g.pk, "code": g.code, "grade": g.grade, "language": g.language} for g in query.order_by("code")]


# --- Замечания ---------------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def remarks(request, pk: int):
    """Замечания ученика: список и запись новой строки словами."""
    if request.user.role == ROLE_STUDENT:
        return _forbidden("Замечания ученику не показываются")
    student = _student_for(request.user, pk)
    if student is None:
        return _not_found()
    if request.method == "GET":
        return Response(
            {
                "rows": discipline.remarks_of(student),
                "may_write": discipline.may_write(request.user, student),
            }
        )
    if not discipline.may_write(request.user, student):
        return _forbidden("Замечание записывают куратор группы и директор школы")
    try:
        row = discipline.add_remark(
            student=student,
            text=str(request.data.get("text") or ""),
            date=_date(request.data.get("date")),
            actor=request.user,
        )
    except ValueError as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"id": row.pk, "rows": discipline.remarks_of(student)}, status=status.HTTP_201_CREATED)


@extend_schema(responses={200: dict})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remark_drop(request, pk: int):
    """Убрать замечание в архив: написанное о ребёнке не удаляется насовсем."""
    if request.user.role == ROLE_STUDENT:
        return _forbidden("Замечания ученику не показываются")
    row = BehaviorRemark.objects.select_related("student").filter(pk=pk).first()
    if row is None or _student_for(request.user, row.student_id) is None:
        return _not_found()
    if not discipline.may_write(request.user, row.student):
        return _forbidden("Замечание снимают куратор группы и директор школы")
    discipline.drop_remark(row, actor=request.user)
    return Response({"rows": discipline.remarks_of(row.student)})


# --- Письма -------------------------------------------------------------------


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def letter_compose(request):
    """Заготовка письма: тема и текст из шаблона на языке группы.

    Ничего не отправляет и ничего не пишет: это ещё черновик, который
    человек будет править.
    """
    if request.user.role == ROLE_STUDENT:
        return _forbidden("Письма пишет школа")
    ids = [int(i) for i in (request.data.get("students") or []) if str(i).isdigit()]
    students = list(visible_students(request.user).filter(pk__in=ids).select_related("group"))
    if not students:
        return _not_found()

    group = students[0].group
    language = group.language if group is not None else "ru"
    first = students[0]
    values = {
        "ученик": first.full_name if len(students) == 1 else "ученик",
        "группа": group.code if group is not None else "",
        "просим": str(request.data.get("ask") or ""),
        "срок": str(request.data.get("due") or ""),
        "куратор": request.user.full_name or request.user.email,
    }
    draft = letters.compose(kind=str(request.data.get("kind") or "free"), language=language, values=values)
    to, without = _addresses(students, str(request.data.get("audience") or "student"))
    return Response(
        {
            **draft,
            "language": draft.get("language", language),
            "recipients": to,
            "without_email": without,
            "batches": [len(b) for b in letters.batches(to)],
            "limit": letters.ADDRESS_LIMIT,
        }
    )


def _addresses(students, audience: str) -> tuple[list[str], list[dict]]:
    """Адреса и те, у кого их нет: список «без почты» показывается рядом."""
    from students.models import ParentContact

    to: list[str] = []
    without: list[dict] = []
    parents = {}
    if audience == "parent":
        for contact in ParentContact.objects.filter(student__in=students).exclude(email="").order_by("-is_primary"):
            parents.setdefault(contact.student_id, contact.email)
    for student in students:
        address = parents.get(student.pk, "") if audience == "parent" else (student.email or "")
        if address:
            to.append(address)
        else:
            without.append({"student": student.pk, "full_name": student.full_name})
    return to, without


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def letter_open(request):
    """Собрать `mailto:` и записать в журнал, что письмо открыли.

    Одно письмо — до `ADDRESS_LIMIT` адресов в скрытой копии; больше
    отдаётся частями, и человек открывает их кнопкой «следующие».
    """
    if request.user.role == ROLE_STUDENT:
        return _forbidden("Письма пишет школа")
    ids = [int(i) for i in (request.data.get("students") or []) if str(i).isdigit()]
    students = list(visible_students(request.user).filter(pk__in=ids).select_related("group"))
    if not students:
        return _not_found()

    subject = str(request.data.get("subject") or "").strip()
    body = str(request.data.get("body") or "")
    to, without = _addresses(students, str(request.data.get("audience") or "student"))
    if not to:
        return Response({"detail": "Не у кого из выбранных нет почты"}, status=status.HTTP_400_BAD_REQUEST)

    parts = letters.batches(to)
    links = [
        # один адресат — обычное письмо; много — в скрытую копию, чтобы
        # родители не увидели адреса друг друга
        (
            letters.mailto(to=part, subject=subject, body=body)
            if len(part) == 1
            else letters.mailto(bcc=part, subject=subject, body=body)
        )
        for part in parts
    ]
    letters.note_opened(students=students, subject=subject, recipients=len(to), actor=request.user)
    return Response(
        {
            "links": links,
            "recipients": len(to),
            "without_email": without,
            "note": "Письмо открыто в почте. Отправку система не видит и подтвердить не может",
        }
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def letter_template_save(request, pk: int):
    """Правка шаблона письма. Формулировки школы ведёт администратор.

    Директору шаблон виден на чтение: он им пользуется, но переписывать
    школьные формулировки поодиночке — верный способ получить пять разных
    писем об одном и том же.
    """
    from engagement.models import MailTemplate

    if request.user.role != ROLE_ADMIN:
        return _forbidden("Шаблоны писем ведёт администратор")
    row = MailTemplate.objects.filter(pk=pk).first()
    if row is None:
        return _not_found()
    subject = str(request.data.get("subject", row.subject)).strip()
    body = str(request.data.get("body", row.body))
    if not subject or not body.strip():
        return Response({"detail": "Тема и текст не могут быть пустыми"}, status=status.HTTP_400_BAD_REQUEST)
    row.subject = subject[:200]
    row.body = body
    if "is_active" in request.data:
        row.is_active = bool(request.data["is_active"])
    row.save(update_fields=["subject", "body", "is_active", "updated_at"])
    return Response({"id": row.pk, "subject": row.subject, "body": row.body, "is_active": row.is_active})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def letter_templates(request):
    """Шаблоны для экрана администратора и для подсказки в модалке."""
    from engagement.models import MailKind, MailTemplate

    if request.user.role == ROLE_STUDENT:
        return _forbidden("Письма пишет школа")
    rows = MailTemplate.objects.all()
    return Response(
        {
            "kinds": [{"code": code, "title": title} for code, title in MailKind.choices],
            "variables": list(letters.VARIABLES),
            "may_edit": request.user.role == ROLE_ADMIN,
            "rows": [
                {
                    "id": row.pk,
                    "kind": row.kind,
                    "kind_title": row.get_kind_display(),
                    "language": row.language,
                    "language_title": row.get_language_display(),
                    "subject": row.subject,
                    "body": row.body,
                    "is_active": row.is_active,
                }
                for row in rows
            ],
        }
    )
