"""Ручки дисциплины и писем (фаза 66).

Дисциплину ведут двое: куратор — по своим группам, директор школы —
по всей школе. Право одно и то же, разная только граница, и держит её
общая выборка `core.scope` — второго списка групп здесь нет.

Писем сервер не шлёт. Ручка писем собирает `mailto:` и пишет в журнал
«письмо открыто»; отправку подтвердить нельзя, и так это и называется.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.curators import curated_group_ids
from core.domains import ROLE_ADMIN, ROLE_CURATOR, ROLE_STUDENT
from core.scope import visible_students
from students import discipline
from students.models import BehaviorRemark, Student, StudyGroup

#: Кто ведёт дисциплину: владелец домена по всей школе, куратор — по своим
#: группам, администратор — как везде. Ученику закрыто наглухо
DISCIPLINE_ROLES = ("director_behavior", ROLE_CURATOR, ROLE_ADMIN)

STUDENT_REFUSAL = gettext_lazy("Посещаемость и замечания ведёт школа")


def _forbidden(detail: str = STUDENT_REFUSAL) -> Response:
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


def _not_found() -> Response:
    return Response({"detail": _("Не найдено")}, status=status.HTTP_404_NOT_FOUND)


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
        return _forbidden(_("Посещаемость ведут куратор и директор школы"))
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
                "date": str(_date(request.query_params.get("date")) or timezone.localdate()),
                "saved": False,
                "late": False,
                "rows": [],
                "absent": 0,
                "total": 0,
                "groups": groups,
            }
        )
    date = _date(request.query_params.get("date")) or timezone.localdate()
    # отметку утром ставит куратор своей группы и только за сегодня; остальные читают.
    # Открытый куратором лист за сегодня записывает «в школе» всем без отметки
    # (решение владельца, 19.10.2026): день отмечен и без нажатий
    may_mark = request.user.role == ROLE_CURATOR and date == timezone.localdate()
    if may_mark:
        payload = discipline.open_day(group=group, date=date, actor=request.user)
    else:
        payload = discipline.day_sheet(group=group, date=date)
    payload["groups"] = _my_groups(request.user)
    payload["may_mark"] = may_mark
    return Response(payload)


def _month(raw) -> dt.date:
    """Месяц журнала из `ГГГГ-ММ`; мусор и пусто — текущий месяц."""
    try:
        year, month = str(raw or "").split("-")[:2]
        return dt.date(int(year), int(month), 1)
    except (ValueError, TypeError):
        return timezone.localdate().replace(day=1)


def _journal_or_refusal(request):
    if request.user.role == ROLE_STUDENT:
        return None, _forbidden()
    if request.user.role not in DISCIPLINE_ROLES:
        return None, _forbidden(_("Посещаемость ведут куратор и директор школы"))
    groups = _my_groups(request.user)
    raw = request.query_params.get("group")
    group = _group_for(request.user, raw) if raw else (_group_for(request.user, groups[0]["id"]) if groups else None)
    if group is None:
        return None, (_not_found() if raw else Response({"group": None, "rows": [], "days": [], "groups": groups}))
    payload = discipline.month_journal(
        group=group,
        month=_month(request.query_params.get("month")),
        absent_only=str(request.query_params.get("absent_only") or "").lower() in ("1", "true"),
    )
    payload["groups"] = groups
    return payload, None


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_journal(request):
    """Журнал группы за месяц: ученики × дни, итог «отсутствовал N из M»."""
    payload, refusal = _journal_or_refusal(request)
    return refusal if refusal is not None else Response(payload)


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_journal_export(request):
    """Тот же журнал книгой XLSX; с `?preview=1` — таблицей для предпросмотра."""
    from core.exports import Column, workbook_response

    payload, refusal = _journal_or_refusal(request)
    if refusal is not None:
        return refusal
    if payload.get("group") is None:
        return _not_found()
    words = payload["words"]
    columns = [Column(_("Ученик"), lambda row: row["full_name"], 30)]
    for index, day in enumerate(payload["days"]):
        title = f"{day['day']:02d} {day['weekday']}"
        columns.append(Column(title, (lambda i: lambda row: words[row["cells"][i]])(index), 10))
    columns.append(Column(_("Отсутствовал, дней"), lambda row: row["absent"], 18))
    columns.append(Column(_("Учебных дней"), lambda row: row["marked"], 14))
    return workbook_response(
        filename=_("посещаемость-{group}-{month}.xlsx").format(group=payload["group_code"], month=payload["month"]),
        sheet=payload["group_code"],
        columns=columns,
        rows=payload["rows"],
        request=request,
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def attendance_save(request):
    """Отметка куратора утром: только куратор, только своя группа, только сегодня.

    С отметками учителей не связана (решение владельца, 19.10.2026).
    Администратору маршрут закрывает шлюз с причиной; директор школы
    лист читает.
    """
    if request.user.role == ROLE_STUDENT:
        return _forbidden()
    if request.user.role != ROLE_CURATOR:
        return _forbidden(_("Отметку утром ставит куратор своей группы"))
    group = _group_for(request.user, request.data.get("group"))
    if group is None:
        return _not_found()
    date = _date(request.data.get("date"))
    if date is None:
        return Response({"detail": _("Не указана дата")}, status=status.HTTP_400_BAD_REQUEST)
    if date != timezone.localdate():
        return Response(
            {"detail": _("Отмечать можно только сегодняшний день — поправить тоже сегодня")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    rows = request.data.get("rows")
    if not isinstance(rows, list):
        return Response({"detail": _("Не переданы отметки")}, status=status.HTTP_400_BAD_REQUEST)
    payload = discipline.save_day(group=group, date=date, rows=rows, actor=request.user)
    payload["groups"] = _my_groups(request.user)
    payload["may_mark"] = True
    return Response(payload)


def _today_group_or_refusal(request):
    """Группа и сегодняшняя дата для записи куратора; иначе — ответ с отказом."""
    if request.user.role == ROLE_STUDENT:
        return None, None, _forbidden()
    if request.user.role != ROLE_CURATOR:
        return None, None, _forbidden(_("Отметку утром ставит куратор своей группы"))
    group = _group_for(request.user, request.data.get("group"))
    if group is None:
        return None, None, _not_found()
    date = _date(request.data.get("date")) or timezone.localdate()
    if date != timezone.localdate():
        return (
            None,
            None,
            Response(
                {"detail": _("Отмечать можно только сегодняшний день — поправить тоже сегодня")},
                status=status.HTTP_400_BAD_REQUEST,
            ),
        )
    return group, date, None


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def attendance_mark(request):
    """Одна отметка сразу при нажатии: в школе, нет или опоздал, с комментарием у двух последних."""
    group, date, refusal = _today_group_or_refusal(request)
    if refusal is not None:
        return refusal
    student = Student.objects.filter(pk=request.data.get("student"), group=group, is_active=True).first()
    if student is None:
        return _not_found()
    mark = str(request.data.get("mark") or "").strip().lower()
    if mark not in discipline.MARKS:
        return Response({"detail": _("Отметка — в школе, нет или опоздал")}, status=status.HTTP_400_BAD_REQUEST)
    payload = discipline.mark_one(
        group=group,
        student=student,
        date=date,
        mark=mark,
        reason=str(request.data.get("reason") or "").strip(),
        actor=request.user,
    )
    return Response(payload)


# --- Отсутствующие — отчёт для службы безопасности ---------------------------


#: кто читает отчёт: куратор — свои группы, директор школы и администратор — все
ABSENCE_READERS = ("director_behavior", ROLE_CURATOR, ROLE_ADMIN)


def _period(request) -> tuple[dt.date, dt.date]:
    """Период отчёта из `from` и `to`; без них — с начала месяца по сегодня."""
    today = timezone.localdate()
    since = _date(request.query_params.get("from")) or today.replace(day=1)
    until = _date(request.query_params.get("to")) or today
    if until < since:
        since, until = until, since
    return since, until


def _absences_or_refusal(request):
    if request.user.role == ROLE_STUDENT:
        return None, _forbidden()
    if request.user.role not in ABSENCE_READERS:
        return None, _forbidden(_("Отчёт об отсутствующих читают куратор, директор школы и администратор"))
    groups = _my_groups(request.user)
    raw = request.query_params.get("group")
    if raw:
        picked = _group_for(request.user, raw)
        if picked is None:
            return None, _not_found()
        chosen = [picked.pk]
    else:
        chosen = [g["id"] for g in groups]
    since, until = _period(request)
    return {
        "from": since,
        "to": until,
        "group": raw or "",
        "groups": groups,
        "rows": discipline.absences(groups=chosen, since=since, until=until),
    }, None


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_absences(request):
    """Кого не было по отметке куратора: по дням и группам за период."""
    payload, refusal = _absences_or_refusal(request)
    return refusal if refusal is not None else Response(payload)


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_absences_export(request):
    """Тот же отчёт книгой XLSX — для службы безопасности."""
    from core.exports import Column, workbook_response

    payload, refusal = _absences_or_refusal(request)
    if refusal is not None:
        return refusal

    def names(mark: str):
        def read(row):
            return "; ".join(
                f"{s['full_name']} ({s['reason']})" if s["reason"] else s["full_name"]
                for s in row["students"]
                if s["mark"] == mark
            )

        return read

    columns = (
        Column(_("Дата"), lambda row: f"{row['date']:%d.%m.%Y}", 12),
        Column(_("День"), lambda row: row["weekday"], 6),
        Column(_("Группа"), lambda row: row["group_code"], 12),
        Column(_("Кого не было"), names("absent"), 60),
        Column(_("Сколько"), lambda row: row["count"], 8),
        Column(_("Кто опоздал"), names("late"), 40),
        Column(_("Опозданий"), lambda row: row["late_count"], 10),
    )
    return workbook_response(
        filename=_("отсутствующие-{since}-{until}.xlsx").format(since=payload["from"], until=payload["to"]),
        sheet=_("Отсутствующие"),
        columns=columns,
        rows=payload["rows"],
        request=request,
    )


def _my_groups(user) -> list[dict]:
    """Группы, доступные человеку: куратору — свои, директору — все."""
    role = getattr(user, "role", "")
    query = StudyGroup.objects.filter(is_active=True)
    if role == ROLE_CURATOR:
        query = query.filter(pk__in=curated_group_ids(user))
    return [{"id": g.pk, "code": g.code, "language": g.language} for g in query.order_by("code")]


# --- Аналитика по отметкам куратора --------------------------------------------


def _stats_or_refusal(request):
    """Период и группы аналитики: период — код из календаря школы или свои даты."""
    from academics import calendar as school_calendar

    if request.user.role == ROLE_STUDENT:
        return None, _forbidden()
    if request.user.role not in ABSENCE_READERS:
        return None, _forbidden(_("Аналитику по отметкам читают куратор, директор школы и администратор"))
    groups = _my_groups(request.user)
    raw = request.query_params.get("group")
    if raw and raw != "all":
        picked = _group_for(request.user, raw)
        if picked is None:
            return None, _not_found()
        chosen = [picked.pk]
    else:
        chosen = [g["id"] for g in groups]
    calendar = school_calendar.load()
    code = str(request.query_params.get("period") or "").strip()
    custom_from = _date(request.query_params.get("from"))
    custom_to = _date(request.query_params.get("to"))
    if code == "custom" or (not code and custom_from and custom_to):
        since, until = custom_from or timezone.localdate().replace(day=1), custom_to or timezone.localdate()
        if until < since:
            since, until = until, since
        code, title = "custom", _("свой период")
    else:
        since, until, title = school_calendar.period_bounds(calendar, code or "week")
        code = code or "week"
    report = discipline.stats(groups=chosen, since=since, until=until)
    return {
        "group": raw if raw and raw != "all" else "all",
        "groups": groups,
        "period": {"code": code, "from": since, "to": until, "title": title},
        "periods": [*school_calendar.period_choices(calendar), {"code": "custom", "title": _("Свой")}],
        "words": {mark: discipline.mark_label(mark) for mark in discipline.MARKS},
        **report,
    }, None


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_stats(request):
    """Аналитика по отметкам куратора: по ученикам и итого за период."""
    payload, refusal = _stats_or_refusal(request)
    return refusal if refusal is not None else Response(payload)


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_stats_export(request):
    """Та же таблица книгой XLSX; даты «нет» и «опоздал» — с комментарием куратора."""
    from core.exports import Column, workbook_response

    payload, refusal = _stats_or_refusal(request)
    if refusal is not None:
        return refusal

    def dates(mark: str):
        def read(row):
            return "; ".join(
                f"{d['date']:%d.%m}" + (f" ({d['reason']})" if d["reason"] else "")
                for d in row["dates"]
                if d["mark"] == mark
            )

        return read

    columns = (
        Column(_("Ученик"), lambda row: row["full_name"], 30),
        Column(_("Группа"), lambda row: row["group"], 12),
        Column(_("Дней отмечено"), lambda row: row["days"], 12),
        Column(_("Был"), lambda row: row["present"], 8),
        Column(_("Не был"), lambda row: row["absent"], 8),
        Column(_("Опоздал"), lambda row: row["late"], 10),
        Column(_("Процент"), lambda row: row["percent"], 10),
        Column(_("Не был — даты"), dates("absent"), 40),
        Column(_("Опоздал — даты"), dates("late"), 40),
    )
    period = payload["period"]
    return workbook_response(
        filename=_("посещаемость-куратора-{since}-{until}.xlsx").format(since=period["from"], until=period["to"]),
        sheet=_("Отметки куратора"),
        columns=columns,
        rows=payload["rows"],
        request=request,
    )


# --- Замечания ---------------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def remarks(request, pk: int):
    """Замечания ученика: список и запись новой строки словами."""
    if request.user.role == ROLE_STUDENT:
        return _forbidden(_("Замечания ученику не показываются"))
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
        return _forbidden(_("Замечание записывают куратор группы и директор школы"))
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
        return _forbidden(_("Замечания ученику не показываются"))
    row = BehaviorRemark.objects.select_related("student").filter(pk=pk).first()
    if row is None or _student_for(request.user, row.student_id) is None:
        return _not_found()
    if not discipline.may_write(request.user, row.student):
        return _forbidden(_("Замечание снимают куратор группы и директор школы"))
    discipline.drop_remark(row, actor=request.user)
    return Response({"rows": discipline.remarks_of(row.student)})
