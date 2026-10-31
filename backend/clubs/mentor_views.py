"""Кабинет ментора: ученики своего кружка, задание, отметка по QR, заметки об ученике.

Право роли — из реестра (`core.domains.CABINET_WRITERS`, `CABINET_READERS`),
граница «свой кружок» — `clubs.rights`: ментор видит только кружок, который
ведёт, и только записанных в него; администратор — все кружки и может всё,
что ментор. Чужой кружок — 404. Отметка существует, только пока администратор
её включил: до того ручки отметки отвечают «не найдено».
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Count
from django.http import FileResponse
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from clubs import payloads, rights, services
from clubs.models import ClubEnrollment, ClubHomework, ClubMark, ClubNote
from core.domains import ROLE_STUDENT, can_read_cabinet, can_write_cabinet
from sport.views import ScanThrottle
from students.models import Student

ENROLLMENT = "clubs.ClubEnrollment"
HOMEWORK = "clubs.ClubHomework"
MARK = "clubs.ClubMark"
NOTE = "clubs.ClubNote"
#: файл задания: до 20 МБ, документы, таблицы, презентации, картинки и архив
FILE_LIMIT = 20 * 1024 * 1024
FILE_TYPES = frozenset({"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "png", "jpg", "jpeg", "zip"})


def _role(request) -> str:
    return getattr(request.user, "role", "")


def _not_found() -> Response:
    return Response({"detail": _("Не найдено")}, status=status.HTTP_404_NOT_FOUND)


def _bad(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def _int(raw) -> int | None:
    return int(raw) if str(raw if raw is not None else "").isdigit() else None


def _date(raw) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def _club(request, pk, label: str, *, write: bool = False):
    """Кружок, который человек ведёт и где у роли есть право на эту запись; иначе `None` (404)."""
    role = _role(request)
    allowed = can_write_cabinet(role, label) if write else can_read_cabinet(role, label)
    if not allowed:
        return None
    club = rights.club_of(request.user, pk)
    if club is None or club.archived_at is not None:
        return None
    return club


def _members(club):
    return list(
        services.active_rows()
        .filter(club=club)
        .select_related("student", "student__group", "club")
        .order_by("student__last_name", "student__first_name")
    )


# --- Свои кружки и ученики ---------------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mine(request):
    """Кружки, которые ведёт человек: ментор — свои, администратор — все живые."""
    from clubs.models import Club

    if not can_read_cabinet(_role(request), ENROLLMENT):
        return _not_found()
    query = Club.objects.all() if _role(request) == "admin" else rights.mentored_clubs(request.user)
    counts = dict(services.active_rows().values("club_id").annotate(n=Count("id")).values_list("club_id", "n"))
    rows = query.prefetch_related("meetings", "parallels").order_by("order", "title")
    return Response({"clubs": [{**payloads.club_card(c), "enrolled": counts.get(c.pk, 0)} for c in rows]})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def students(request, pk: int):
    """Записанные сейчас: ФИО, группа, дата записи. Других учеников ментор не видит."""
    club = _club(request, pk, ENROLLMENT)
    if club is None:
        return _not_found()
    notes = dict(
        ClubNote.objects.filter(club=club).values("student_id").annotate(n=Count("id")).values_list("student_id", "n")
    )
    rows = [{**payloads.enrollment_row(row), "notes": notes.get(row.student_id, 0)} for row in _members(club)]
    return Response({"club": payloads.club_card(club), "rows": rows})


# --- Задание -------------------------------------------------------------------------------


def _upload(request):
    upload = request.FILES.get("file")
    if upload is None:
        return None
    ext = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
    if ext not in FILE_TYPES:
        raise services.Refused(_("Такой файл не подойдёт: PDF, Word, Excel, PowerPoint, картинка или ZIP"))
    if upload.size > FILE_LIMIT:
        raise services.Refused(_("Файл больше 20 МБ"))
    return upload


@extend_schema(request=None, responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def homework(request, pk: int):
    """Задания кружка (GET) и новое задание (POST: текст, срок, необязательный файл)."""
    club = _club(request, pk, HOMEWORK, write=request.method == "POST")
    if club is None:
        return _not_found()
    if request.method == "POST":
        due = _date(request.data.get("due"))
        if due is None:
            return _bad(_("Укажите срок"))
        try:
            row = services.publish_homework(
                club=club,
                text=str(request.data.get("text") or ""),
                due=due,
                upload=_upload(request),
                actor=request.user,
            )
        except services.Refused as error:
            return _bad(str(error))
        return Response(payloads.homework_row(row), status=status.HTTP_201_CREATED)
    rows = services.visible_homework(club).select_related("club", "created_by")
    return Response({"club": payloads.club_card(club), "rows": [payloads.homework_row(r) for r in rows]})


@extend_schema(request=None, responses={200: dict})
@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def homework_detail(request, pk: int, hw: int):
    """PATCH — поправить текст, срок или файл (`drop_file` — убрать файл); DELETE — снять задание."""
    club = _club(request, pk, HOMEWORK, write=True)
    row = ClubHomework.objects.filter(pk=hw, club=club).select_related("club").first() if club else None
    if row is None:
        return _not_found()
    if request.method == "DELETE":
        services.withdraw_homework(row, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
    due = _date(request.data.get("due")) if request.data.get("due") else None
    if request.data.get("due") and due is None:
        return _bad(_("Укажите срок"))
    try:
        row = services.edit_homework(
            row,
            text=request.data.get("text") if "text" in request.data else None,
            due=due,
            upload=_upload(request),
            drop_file=str(request.data.get("drop_file") or "").lower() in ("1", "true"),
            actor=request.user,
        )
    except services.Refused as error:
        return _bad(str(error))
    return Response(payloads.homework_row(row))


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def homework_file(request, hw: int):
    """Файл задания: ментору своего кружка, администратору и ученикам, которые сейчас в кружке."""
    row = ClubHomework.objects.filter(pk=hw).select_related("club").first()
    if row is None or not row.file or row.club.archived_at is not None:
        return _not_found()
    if _role(request) == ROLE_STUDENT:
        me = Student.objects.filter(user=request.user, is_active=True).first()
        allowed = me is not None and services.active_of(me, row.club) is not None
    else:
        allowed = can_read_cabinet(_role(request), HOMEWORK) and rights.leads(request.user, row.club)
    if not allowed:
        return _not_found()
    response = FileResponse(row.file.open("rb"), as_attachment=True, filename=row.file_name or "file")
    response["Cache-Control"] = "private, no-store"
    return response


# --- Отметка по QR ---------------------------------------------------------------------------


def _marking(request, pk, *, write: bool = False):
    club = _club(request, pk, MARK, write=write)
    if club is None or not club.marks_enabled:
        return None
    return club


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def session(request, pk: int):
    """«Пришли / Ещё нет» на встрече в дату (по умолчанию сегодня). Отметка выключена — 404."""
    club = _marking(request, pk)
    if club is None:
        return _not_found()
    now = services.local_now()
    day = _date(request.query_params.get("date")) or now.date()
    marks = {m.student_id: m for m in ClubMark.objects.filter(club=club, date=day)}
    rows = []
    for row in _members(club):
        mark = marks.get(row.student_id)
        rows.append(
            {
                **payloads.student_brief(row.student),
                "came": mark is not None,
                "method": mark.method if mark else "",
                "at": payloads.when(mark.marked_at) if mark else None,
            }
        )
    rows.sort(key=lambda s: (not s["came"], s["at"] or "", s["short_name"]))
    meeting = services.meeting_on(club, day)
    return Response(
        {
            "club": payloads.club_card(club),
            "date": day.isoformat(),
            "state": services.session_state(club, day, now),
            "time": services.time_words(meeting) if meeting else "",
            "came": sum(1 for s in rows if s["came"]),
            "students": rows,
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def session_token(request, pk: int):
    """Свежий токен QR на идущую встречу. Фронт перезапрашивает его, когда истекает срок."""
    club = _marking(request, pk, write=True)
    if club is None:
        return _not_found()
    now = services.local_now()
    state = services.session_state(club, now.date(), now)
    if state != "live":
        return Response({"state": state, "token": "", "ttl": services.sport.ttl(), "expires_in": 0})
    token, left = services.make_token(club, now.date())
    return Response({"state": state, "token": token, "ttl": services.sport.ttl(), "expires_in": left})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def session_mark(request, pk: int):
    """Отметить вручную пришедшего без телефона (POST) или снять ошибочную отметку (DELETE)."""
    club = _marking(request, pk, write=True)
    if club is None:
        return _not_found()
    student_id = _int(request.data.get("student") or request.query_params.get("student"))
    row = ClubEnrollment.objects.filter(club=club, student_id=student_id, ended_at__isnull=True).first()
    if row is None:
        return _not_found()
    day = _date(request.data.get("date") or request.query_params.get("date")) or services.local_now().date()
    if request.method == "DELETE":
        services.unmark(student=row.student, club=club, day=day)
        return Response(status=status.HTTP_204_NO_CONTENT)
    try:
        _mark, created = services.mark_manually(student=row.student, club=club, day=day, actor=request.user)
    except services.Refused as error:
        return _bad(str(error))
    return Response({"created": created}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ScanThrottle])
def scan(request):
    """Ученик отсканировал QR встречи. Не вошёл — свежий код ждёт входа в этом браузере, как у секций."""
    token = str(request.data.get("token") or "")
    found = services.read_token(token) if token else None
    if not request.user.is_authenticated:
        if found is None:
            return Response({"state": "stale"})
        services.scan_hold(request.session, *found)
        return Response({"state": "login", "hold_seconds": services.HOLD_SECONDS})
    me = Student.objects.filter(user=request.user, is_active=True).first() if _role(request) == ROLE_STUDENT else None
    if me is None:
        return Response({"detail": _("Отмечается на встрече ученик")}, status=status.HTTP_403_FORBIDDEN)
    held = services.take_hold(request.session)
    if found is None and not token:
        found = held
    if found is None:
        return Response({"state": "stale"})
    return Response(services.mark_by_scan(student=me, club_id=found[0], day=found[1]))


# --- Заметки ментора -----------------------------------------------------------------------


def _note_row(note: ClubNote) -> dict:
    return {
        "id": note.pk,
        "student": payloads.student_brief(note.student),
        "text": note.text,
        "created_at": payloads.when(note.created_at),
        "author": (note.author.full_name or note.author.email) if note.author_id else note.author_title,
    }


@extend_schema(request=None, responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def notes(request, pk: int):
    """Заметки об учениках кружка (`?student=` — одного). Читают только ментор кружка и администратор."""
    club = _club(request, pk, NOTE, write=request.method == "POST")
    if club is None or not rights.reads_notes(request.user, club):
        return _not_found()
    if request.method == "POST":
        row = ClubEnrollment.objects.filter(
            club=club, student_id=_int(request.data.get("student")), ended_at__isnull=True
        ).first()
        if row is None:
            return _not_found()
        try:
            note = services.add_note(
                club=club, student=row.student, text=str(request.data.get("text") or ""), actor=request.user
            )
        except services.Refused as error:
            return _bad(str(error))
        return Response(_note_row(note), status=status.HTTP_201_CREATED)
    query = ClubNote.objects.filter(club=club, student__archived_at__isnull=True).select_related(
        "student", "student__group", "author"
    )
    student_id = _int(request.query_params.get("student"))
    if student_id:
        query = query.filter(student_id=student_id)
    return Response({"club": payloads.club_card(club), "rows": [_note_row(n) for n in query]})


@extend_schema(request=None, responses={204: None})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def note(request, pk: int):
    """Убрать заметку в архив — свою или любую у администратора."""
    row = ClubNote.objects.filter(pk=pk).select_related("club").first()
    if row is None or not can_write_cabinet(_role(request), NOTE) or not rights.reads_notes(request.user, row.club):
        return _not_found()
    services.archive_note(row)
    return Response(status=status.HTTP_204_NO_CONTENT)
