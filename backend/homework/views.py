"""API сдачи ДЗ: задание урока, загрузка файлов, сдача, проверка, сводка.

Файлы идут с устройства прямо в хранилище по подписанной ссылке
(`homework.storage`): сервер выдаёт ссылку, потом проверяет, что пришло
(размер, тип по первым байтам), и только тогда файл считается загруженным.
Отдаётся файл короткой подписанной ссылкой после проверки прав; чужой файл —
404, как и чужое задание.

Видимость учеников — одно правило `core.scope`: учитель — свои составы,
куратор — свои группы, руководители — вся школа.
"""

from __future__ import annotations

import datetime as dt

from django.core import signing
from django.http import FileResponse, Http404, StreamingHttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import BaseParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from academics.models import Lesson
from academics.payloads import person, student_brief, user_name
from core.domains import ROLE_ADMIN, ROLE_CURATOR, ROLE_STUDENT
from core.scope import visible_students
from homework import files as hwfiles
from homework import services
from homework.models import Assignment, FileKind, FileState, HomeworkFile, LatePolicy, Submission
from homework.storage import LocalStorage, StorageError, backend, new_key

#: сколько последних дней заданий показывать в списках
LIST_DAYS = 120


def _forbid(detail: str) -> Response:
    return Response({"detail": detail}, status=http.HTTP_403_FORBIDDEN)


def _not_found() -> Response:
    return Response({"detail": "Не найдено"}, status=http.HTTP_404_NOT_FOUND)


def _bad(detail: str) -> Response:
    return Response({"detail": detail}, status=http.HTTP_400_BAD_REQUEST)


def _int(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _student(user):
    return getattr(user, "student", None) if getattr(user, "role", "") == ROLE_STUDENT else None


# --- Представление ------------------------------------------------------------------


def file_dict(row: HomeworkFile) -> dict:
    return {
        "id": row.pk,
        "name": row.name,
        "kind": row.kind,
        "content_type": row.content_type,
        "size": row.size,
        "photos": row.photos,
        "state": row.state,
    }


def _ready_files(rows) -> list[dict]:
    return [file_dict(row) for row in rows if row.state == FileState.READY and row.archived_at is None]


def _lesson_brief(lesson: Lesson) -> dict:
    cohort = lesson.course.cohort
    return {
        "id": lesson.pk,
        "date": lesson.date,
        "slot": lesson.slot,
        "subject": lesson.course.subject.title,
        "cohort": cohort.name,
        "cohort_kind": cohort.kind,
        "teacher": person(lesson.substitute or lesson.teacher),
        "course": lesson.course_id,
    }


def assignment_dict(row: Assignment) -> dict:
    return {
        "id": row.pk,
        "lesson": _lesson_brief(row.lesson),
        "text": row.lesson.homework,
        "requires_submission": row.requires_submission,
        "due_at": row.due_at,
        "late_policy": row.late_policy,
        "late_policy_title": row.get_late_policy_display(),
        "files": _ready_files(row.files.all()),
    }


def submission_dict(row: Submission, *, for_student: bool) -> dict:
    out = {
        "id": row.pk,
        "text": row.text,
        "link": row.link,
        "comment": row.comment,
        "submitted_at": row.submitted_at,
        "late_minutes": row.late_minutes,
        "checked_at": row.checked_at,
        "grade": row.grade,
        "teacher_comment": row.teacher_comment,
        "files": _ready_files(row.files.all()),
    }
    if not for_student:
        out["student"] = student_brief(row.student)
        out["checked_by"] = user_name(row.checked_by) if row.checked_by_id else ""
    return out


# --- Учитель: задание урока --------------------------------------------------------


def _lesson(pk: int) -> Lesson | None:
    return (
        Lesson.objects.select_related("course", "course__subject", "course__cohort", "course__teacher")
        .filter(pk=pk)
        .first()
    )


def _parse_due(raw) -> dt.datetime | None:
    if not raw:
        return None
    try:
        value = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError as error:
        raise services.HomeworkRefused("Срок не читается") from error
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def lesson_payload(lesson: Lesson, user) -> dict:
    row = services.assignment_of(lesson)
    cohort = lesson.course.cohort
    count = len(services.recipients(lesson))
    return {
        "lesson": lesson.pk,
        "assignment": row.pk if row else None,
        "requires_submission": bool(row and row.requires_submission),
        "due_at": row.due_at if row else None,
        "late_policy": row.late_policy if row else LatePolicy.ACCEPT,
        "files": _ready_files(row.files.all()) if row else [],
        "options": services.due_options(lesson),
        "recipients": {"count": count, "cohort": cohort.name, "kind": cohort.kind},
        "policies": [{"code": c, "title": t} for c, t in LatePolicy.choices],
        "may_edit": services.may_set(user, lesson),
        "limits": hwfiles.limits(),
    }


@extend_schema(request=None, responses={200: dict})
@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def lesson_assignment(request, pk: int):
    """ДЗ урока: нужна ли сдача, срок, «после срока», файлы учителя. Ученику — 404."""
    lesson = _lesson(pk)
    user = request.user
    if lesson is None or user.role == ROLE_STUDENT:
        return _not_found()
    if not (services.may_check(user, lesson) or services.teaches(user, lesson)):
        return _not_found()
    if request.method == "PUT":
        if not services.may_set(user, lesson):
            return _forbid("ДЗ задаёт учитель, который ведёт урок")
        try:
            services.save_assignment(
                lesson,
                requires_submission=bool(request.data.get("requires_submission")),
                due_at=_parse_due(request.data.get("due_at")),
                late_policy=str(request.data.get("late_policy") or LatePolicy.ACCEPT),
                actor=user,
            )
        except services.HomeworkRefused as error:
            return _bad(str(error))
    return Response(lesson_payload(lesson, user))


# --- Загрузка файлов ------------------------------------------------------------------


def _upload_target(request):
    """Куда грузится файл: задание урока (учитель) или своя сдача (ученик)."""
    user = request.user
    student = _student(user)
    if student is not None:
        assignment = (
            Assignment.objects.select_related("lesson", "lesson__course", "lesson__course__cohort")
            .filter(pk=_int(request.data.get("assignment")), requires_submission=True)
            .first()
        )
        if assignment is None or not services.is_recipient(student.pk, assignment.lesson):
            return None, None
        submission = services.draft_of(assignment, student)
        services.may_change(submission)
        return None, submission
    lesson = _lesson(_int(request.data.get("lesson")) or 0)
    if lesson is None or not services.may_set(user, lesson):
        return None, None
    return services.ensure_assignment(lesson, user), None


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_start(request):
    """Начать загрузку: строка файла и подписанная ссылка (или ссылки частей)."""
    name = str(request.data.get("name") or "файл").strip()[:250] or "файл"
    size = _int(request.data.get("size")) or 0
    declared = str(request.data.get("content_type") or "")[:120]
    try:
        assignment, submission = _upload_target(request)
    except services.HomeworkRefused as error:
        return _bad(str(error))
    if assignment is None and submission is None:
        return _not_found()
    owner = assignment.files if assignment is not None else submission.files
    try:
        hwfiles.check_count(owner.filter(archived_at__isnull=True).count())
        hwfiles.check_size(name, size, declared)
    except hwfiles.FileRejected as error:
        return _bad(str(error))
    key = new_key("teacher" if assignment is not None else "student")
    store = backend()
    try:
        plan = store.start_upload(key, size)
    except StorageError as error:
        return _bad(str(error))
    photos = _int(request.data.get("photos"))
    row = HomeworkFile.objects.create(
        assignment=assignment,
        submission=submission,
        key=key,
        name=name,
        content_type=declared,
        size=size,
        photos=photos if photos and photos > 0 else None,
        upload_id=plan.get("upload_id", ""),
        uploaded_by=request.user,
        order=owner.count(),
    )
    return Response({"file": row.pk, **plan})


def _own_file(user, pk: int) -> HomeworkFile | None:
    """Файл, который человек загрузил сам, — для завершения и удаления."""
    return (
        HomeworkFile.objects.select_related("assignment__lesson", "submission__assignment__lesson")
        .filter(pk=pk, uploaded_by=user)
        .first()
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_complete(request, pk: int):
    """Загрузка закончена: собрать части, проверить размер и тип по первым байтам."""
    row = _own_file(request.user, pk)
    if row is None or row.state != FileState.UPLOADING:
        return _not_found()
    store = backend()
    parts = request.data.get("parts") or []
    try:
        store.complete(row.key, row.upload_id, parts if isinstance(parts, list) else [])
    except Exception:
        store.abort(row.key, row.upload_id)
        row.delete()
        return _bad("Файл не собрался из частей — загрузите его ещё раз")
    size = store.size(row.key)
    try:
        found = hwfiles.refine(hwfiles.sniff(store.head(row.key, hwfiles.HEAD_BYTES)), row.name)
        hwfiles.check_size(row.name, size, found.content_type)
    except hwfiles.FileRejected as error:
        store.delete(row.key)
        row.delete()
        return _bad(str(error))
    row.size = size
    row.content_type = found.content_type
    row.kind = found.kind
    row.state = FileState.READY
    row.upload_id = ""
    row.save(update_fields=["size", "content_type", "kind", "state", "upload_id"])
    return Response(file_dict(row))


@extend_schema(request=None, responses={200: dict})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def file_drop(request, pk: int):
    """Убрать свой файл: учитель — из задания, ученик — из работы до срока."""
    from core.archive import archive

    row = _own_file(request.user, pk)
    if row is None or row.archived_at is not None:
        return _not_found()
    if row.submission_id is not None:
        try:
            services.may_change(row.submission)
        except services.HomeworkRefused as error:
            return _bad(str(error))
    if row.state == FileState.UPLOADING:
        backend().abort(row.key, row.upload_id)
        row.delete()
    else:
        archive(row, actor=request.user)
    return Response({"dropped": pk})


def may_read_file(user, row: HomeworkFile) -> bool:
    """Файл задания — учитель и ученики состава; файл работы — её автор и проверяющие."""
    student = _student(user)
    if row.assignment_id is not None:
        lesson = row.assignment.lesson
        if student is not None:
            return services.is_recipient(student.pk, lesson)
        return services.may_check(user, lesson) or services.teaches(user, lesson)
    submission = row.submission
    if student is not None:
        return submission.student_id == student.pk
    return services.may_check(user, submission.assignment.lesson)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def file_link(request, pk: int):
    """Короткая подписанная ссылка на файл — после проверки прав; чужой файл — 404."""
    row = (
        HomeworkFile.objects.select_related(
            "assignment__lesson__course__cohort", "submission__assignment__lesson__course", "submission__student"
        )
        .filter(pk=pk, state=FileState.READY)
        .first()
    )
    if row is None:
        return _not_found()
    if not may_read_file(request.user, row):
        return _not_found()
    inline = request.query_params.get("download") != "1" and row.kind != FileKind.OTHER
    url = backend().link(row.key, name=row.name, content_type=row.content_type, inline=inline)
    return Response({"url": url, **file_dict(row)})


class RawParser(BaseParser):
    """Тело запроса как есть — файл, загружаемый в локальное хранилище."""

    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        return stream


@extend_schema(request=None, responses={200: None})
@api_view(["GET", "PUT"])
@permission_classes([AllowAny])
@parser_classes([RawParser])
def local_file(request, token: str):
    """Локальное хранилище разработки: подписанный адрес загрузки и скачивания.

    Подпись — единственный пропуск, как у ссылки бакета: выдаёт её сервер
    после проверки прав, живёт она минуты.
    """
    from homework.storage import LINK_SECONDS, UPLOAD_SECONDS

    store = backend()
    if not isinstance(store, LocalStorage):
        raise Http404
    action = "put" if request.method == "PUT" else "get"
    try:
        key = LocalStorage.read_token(token, action, UPLOAD_SECONDS if action == "put" else LINK_SECONDS)
    except signing.BadSignature as error:
        raise Http404 from error
    if action == "put":
        if not HomeworkFile.objects.filter(key=key, state=FileState.UPLOADING).exists():
            raise Http404
        try:
            store.write(key, iter(lambda: request.stream.read(1024 * 1024), b""))
        except StorageError as error:
            return _bad(str(error))
        return Response({"ok": True})
    data = signing.loads(token, salt="homework.local")
    from core.exports import _disposition

    target = store.path(key)
    if not target.is_file():
        raise Http404
    response = FileResponse(target.open("rb"), content_type=data.get("t") or "application/octet-stream")
    disposition = _disposition(data.get("n") or "файл", data.get("t") or "")
    response["Content-Disposition"] = disposition.replace("attachment", "inline", 1) if data.get("i") else disposition
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# --- Ученик ------------------------------------------------------------------------


def student_assignments(student) -> list[Assignment]:
    """Задания со сдачей, которые получил ученик: его составы на дату урока."""
    from academics.cohorts import cohorts_of_student
    from academics.schedule import for_student

    since = timezone.localdate() - dt.timedelta(days=LIST_DAYS)
    rows = list(
        Assignment.objects.filter(
            requires_submission=True,
            lesson__course__cohort_id__in=cohorts_of_student(student.pk),
            lesson__date__gte=since,
            lesson__archived_at__isnull=True,
        )
        .exclude(lesson__status="cancelled")
        .select_related(
            "lesson", "lesson__course", "lesson__course__subject", "lesson__course__cohort", "lesson__teacher"
        )
        .prefetch_related("files")
    )
    lessons = {lesson.pk for lesson in for_student([row.lesson for row in rows], student.pk)}
    return [row for row in rows if row.lesson_id in lessons]


def _student_row(assignment: Assignment, submission: Submission | None, now) -> dict:
    return {
        **assignment_dict(assignment),
        "state": services.student_state(assignment, submission, now),
        "past_due": services.is_past_due(assignment, now),
        "submission": submission_dict(submission, for_student=True) if submission else None,
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_list(request):
    """«Домашние задания» ученика: к сдаче, на проверке, проверено, не сдано."""
    student = _student(request.user)
    if student is None:
        return _forbid("Экран ученика")
    rows = student_assignments(student)
    mine = {
        row.assignment_id: row
        for row in Submission.objects.filter(student=student, assignment__in=rows).prefetch_related("files")
    }
    now = timezone.now()
    items = [_student_row(row, mine.get(row.pk), now) for row in rows]
    order = {services.TODO: 0, services.REVIEW: 1, services.CHECKED: 2, services.MISSED: 3}
    far = dt.datetime.max.replace(tzinfo=dt.UTC)
    items.sort(key=lambda item: (order[item["state"]], item["due_at"] or far))
    counts = {state: sum(1 for item in items if item["state"] == state) for state in order}
    return Response({"items": items, "counts": counts, "limits": hwfiles.limits(), "now": now})


def _my_assignment(student, pk: int) -> Assignment | None:
    return next((row for row in student_assignments(student) if row.pk == pk), None)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_detail(request, pk: int):
    """Задание ученика со своей работой. Чужое — 404."""
    student = _student(request.user)
    if student is None:
        return _forbid("Экран ученика")
    row = _my_assignment(student, pk)
    if row is None:
        return _not_found()
    return Response(_detail_payload(student, row))


def _detail_payload(student, row: Assignment) -> dict:
    submission = Submission.objects.filter(assignment=row, student=student).prefetch_related("files").first()
    now = timezone.now()
    payload = _student_row(row, submission, now)
    try:
        if submission is not None:
            services.may_change(submission, now)
        elif services.is_past_due(row, now) and row.late_policy == LatePolicy.CLOSE:
            raise services.HomeworkRefused("Срок прошёл, учитель не принимает работы после срока")
        payload["may_change"] = True
        payload["change_note"] = ""
    except services.HomeworkRefused as error:
        payload["may_change"] = False
        payload["change_note"] = str(error)
    payload["limits"] = hwfiles.limits()
    return payload


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_submit(request, pk: int):
    """«Сдать работу»: файлы уже загружены, здесь — текст, ссылка и комментарий учителю."""
    student = _student(request.user)
    if student is None:
        return _forbid("Экран ученика")
    row = _my_assignment(student, pk)
    if row is None:
        return _not_found()
    try:
        services.submit(
            row,
            student,
            text=str(request.data.get("text") or ""),
            link=str(request.data.get("link") or ""),
            comment=str(request.data.get("comment") or ""),
        )
    except services.HomeworkRefused as error:
        return _bad(str(error))
    return Response(_detail_payload(student, row))


# --- Учитель: проверка ------------------------------------------------------------------


def _checkable(user):
    """Задания со сдачей, которые человек проверяет: свои уроки; Кымбат и администратор — все."""
    from django.db.models import Q

    rows = Assignment.objects.filter(requires_submission=True, lesson__archived_at__isnull=True).exclude(
        lesson__status="cancelled"
    )
    if user.role not in (ROLE_ADMIN, services.EXAM_DIRECTOR):
        rows = rows.filter(Q(lesson__teacher=user) | Q(lesson__substitute=user) | Q(lesson__course__teacher=user))
    return rows.select_related(
        "lesson", "lesson__course", "lesson__course__subject", "lesson__course__cohort", "lesson__teacher"
    )


def _review_row(row: Assignment, now) -> dict:
    ids = services.recipients(row.lesson)
    subs = [s for s in row.submissions.all() if s.student_id in set(ids) and s.is_submitted]
    unchecked = sum(1 for s in subs if not s.is_checked)
    if unchecked:
        tab = "unchecked"
    elif not services.is_past_due(row, now):
        tab = "running"
    else:
        tab = "checked"
    return {
        **assignment_dict(row),
        "total": len(ids),
        "submitted": len(subs),
        "unchecked": unchecked,
        "tab": tab,
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def review_list(request):
    """«Проверка ДЗ»: задания со сдачей по своим урокам, три вкладки."""
    if request.user.role == ROLE_STUDENT:
        return _forbid("Экран учителя")
    since = timezone.localdate() - dt.timedelta(days=LIST_DAYS)
    rows = _checkable(request.user).filter(lesson__date__gte=since).prefetch_related("submissions", "files")
    now = timezone.now()
    items = [_review_row(row, now) for row in rows]
    far = dt.datetime.max.replace(tzinfo=dt.UTC)
    items.sort(key=lambda item: (item["due_at"] or far), reverse=True)
    counts = {tab: sum(1 for item in items if item["tab"] == tab) for tab in ("unchecked", "running", "checked")}
    return Response({"items": items, "counts": counts})


def _checkable_assignment(user, pk: int) -> Assignment | None:
    return _checkable(user).filter(pk=pk).first() if user.role != ROLE_STUDENT else None


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def review_detail(request, pk: int):
    """Задание на проверке: ученики — не проверено, проверено, не сдали; «н» в день урока."""
    from academics.marks import marks_map
    from students.models import Student

    row = _checkable_assignment(request.user, pk)
    if row is None:
        return _not_found()
    ids = services.recipients(row.lesson)
    students = {s.pk: s for s in Student.objects.filter(pk__in=ids).select_related("group")}
    subs = {
        s.student_id: s
        for s in row.submissions.filter(student_id__in=ids).prefetch_related("files").select_related("checked_by")
    }
    marks = marks_map([row.lesson], ids) if row.lesson.is_marked else {}
    out = []
    for sid in ids:
        student = students.get(sid)
        if student is None:
            continue
        sub = subs.get(sid)
        state = "missed"
        if sub is not None and sub.is_checked:
            state = "checked"
        elif sub is not None and sub.is_submitted:
            state = "unchecked"
        out.append(
            {
                "student": student_brief(student),
                "state": state,
                "absent": marks.get((row.lesson_id, sid)) in ("absent", "excused"),
                "submission": submission_dict(sub, for_student=False) if sub and sub.is_submitted else None,
            }
        )
    order = {"unchecked": 0, "checked": 1, "missed": 2}
    out.sort(key=lambda item: (order[item["state"]], item["student"]["full_name"]))
    return Response(
        {
            **_review_row(row, timezone.now()),
            "students": out,
            "may_check": services.may_check(request.user, row.lesson),
        }
    )


def _checkable_submission(user, pk: int) -> Submission | None:
    if user.role == ROLE_STUDENT:
        return None
    row = (
        Submission.objects.select_related(
            "assignment", "assignment__lesson", "assignment__lesson__course", "student", "student__group"
        )
        .filter(pk=pk, submitted_at__isnull=False)
        .first()
    )
    if row is None or not services.may_check(user, row.assignment.lesson):
        return None
    return row


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_check(request, pk: int):
    """«Проверено»: оценка 1–10 или без оценки и комментарий. Окна в 7 дней нет."""
    row = _checkable_submission(request.user, pk)
    if row is None:
        return _not_found()
    raw = request.data.get("grade")
    try:
        services.check(
            row,
            grade=_int(raw) if raw not in (None, "") else None,
            comment=str(request.data.get("comment") or ""),
            actor=request.user,
        )
    except services.HomeworkRefused as error:
        return _bad(str(error))
    return Response(submission_dict(row, for_student=False))


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def review_zip(request, pk: int):
    """«Скачать всё»: файлы работы одним архивом без сжатия, потоком из хранилища."""
    import zipfile

    row = _checkable_submission(request.user, pk)
    if row is None:
        return _not_found()
    store = backend()
    rows = [f for f in row.files.all() if f.state == FileState.READY]

    class Sink:
        def __init__(self) -> None:
            self.chunks: list[bytes] = []

        def write(self, data: bytes) -> int:
            self.chunks.append(bytes(data))
            return len(data)

        def flush(self) -> None:
            return None

    def stream():
        sink = Sink()
        with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED) as archive:
            used: set[str] = set()
            for item in rows:
                name = item.name
                counter = 2
                while name in used:
                    name = f"{counter}-{item.name}"
                    counter += 1
                used.add(name)
                source = store.open(item.key)
                with archive.open(name, "w", force_zip64=True) as target:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        target.write(chunk)
                        yield from sink.chunks
                        sink.chunks.clear()
                source.close()
            text = "\n\n".join(part for part in (row.text, row.link, row.comment) if part)
            if text:
                archive.writestr("ответ.txt", text)
        yield from sink.chunks

    from core.exports import _disposition

    subject = row.assignment.lesson.course.subject.short_title
    name = f"{row.student.last_name} {row.student.first_name} — {subject} {row.assignment.lesson.date:%d.%m}.zip"
    response = StreamingHttpResponse(stream(), content_type="application/zip")
    response["Content-Disposition"] = _disposition(name, "application/zip")
    response["Cache-Control"] = "private, no-store"
    return response


# --- Куратор и руководители: кто не сдаёт -----------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def overview(request):
    """Выполнение ДЗ по ученикам за четверть: куратор — свои группы, руководители — школа."""
    from students.models import StudyGroup

    user = request.user
    if user.role == ROLE_STUDENT:
        return _forbid("Экран сотрудника")
    students = visible_students(user).filter(is_active=True).select_related("group")
    code = str(request.query_params.get("group") or "")
    if code:
        group = StudyGroup.objects.filter(code=code).first()
        if group is None:
            return _not_found()
        students = students.filter(group=group)
    students = list(students.order_by("group__code", "last_name", "first_name"))
    start, end = services.current_period()
    stats = services.completion([s.pk for s in students], start, end)
    rows = [{**student_brief(s), **stats[s.pk].as_dict()} for s in students]
    rows = [row for row in rows if row["total"]]
    rows.sort(key=lambda row: (row["pct"] if row["pct"] is not None else 101, row["full_name"]))
    groups = sorted({s.group.code for s in students if s.group_id})
    if user.role == ROLE_CURATOR:
        from accounts.curators import curated_group_ids

        groups = sorted(StudyGroup.objects.filter(pk__in=curated_group_ids(user)).values_list("code", flat=True))
    from core import school_rules

    values = school_rules.values()
    return Response(
        {
            "period": {"start": start, "end": end},
            "rows": rows,
            "groups": groups,
            # кто «не сдаёт ДЗ вовремя» — пороги школы, а не числа в экране
            "behind": {
                "pct": values[school_rules.HOMEWORK_BEHIND_PCT],
                "missed": values[school_rules.HOMEWORK_BEHIND_MISSED],
            },
        }
    )
