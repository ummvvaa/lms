"""Ручки секций и билетов (27.10.2026).

Право — из реестра (`core.domains.CABINET_WRITERS`, `CABINET_READERS`),
граница учеников — `core.scope`. Администратор получает всё, что директор
спорта, во всех блоках (решение владельца). Чужой ученик и чужая запись
отвечают 404: по 403 было бы видно, что запись есть.
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.domains import ROLE_STUDENT, can_read_cabinet, can_write_cabinet
from core.exports import Column, workbook_of_sheets
from core.scope import visible_students
from sport import services
from sport.models import (
    MarkMethod,
    Section,
    SectionEnrollment,
    SectionMark,
    SectionSlot,
    Weekday,
)
from students.models import Student

SECTION = "sport.Section"
ENROLLMENT = "sport.SectionEnrollment"


def _forbid(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


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


def _role(request) -> str:
    return getattr(request.user, "role", "")


def _when(value) -> str | None:
    return timezone.localtime(value).isoformat() if value else None


def _writer(request, label: str = SECTION) -> bool:
    return can_write_cabinet(_role(request), label)


def _no_rights() -> Response:
    return _forbid(_("Секции ведёт директор спорта"))


def _brief(student) -> dict:
    return {
        "id": student.pk,
        "full_name": student.full_name,
        "short_name": f"{student.last_name} {student.first_name}".strip(),
        "group": student.group.code if student.group_id else "",
        "grade": services.grade_of(student),
    }


def _slot_dict(slot: SectionSlot, taken: int | None = None) -> dict:
    out = {
        "id": slot.pk,
        "section": slot.section_id,
        "weekday": slot.weekday,
        "day": slot.get_weekday_display(),
        "day_short": services.short_day(slot.weekday),
        "starts": f"{slot.starts:%H:%M}",
        "ends": f"{slot.ends:%H:%M}",
        "grade_from": slot.grade_from,
        "grade_to": slot.grade_to,
        "room": slot.room,
        "capacity": slot.capacity,
    }
    if taken is not None:
        out["taken"] = taken
        out["free"] = max(slot.capacity - taken, 0)
    return out


def _settings_dict() -> dict:
    until = services.enroll_until()
    return {"enroll_until": _when(until), "open": services.is_open()}


def _enrollment_dict(row: SectionEnrollment, pct=None) -> dict:
    return {
        "id": row.pk,
        "student": _brief(row.student),
        "section": row.section_id,
        "section_title": row.section.title,
        "slot": row.slot_id,
        "slot_title": services.slot_words(row.slot) if row.slot_id else "",
        "enrolled_at": _when(row.enrolled_at),
        "source": row.source,
        "source_title": row.get_source_display(),
        "slot_set_by_director": bool(row.slot_set_by_id),
        "percent": pct,
    }


# --- Секции и настройка записи ---------------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sections(request):
    """Секции со слотами, числом записанных и «N без часа» — экран «Секции» директора."""
    if not _writer(request):
        return _no_rights()
    rows = list(Section.objects.select_related("sport_type").prefetch_related("slots"))
    slots = [slot for section in rows for slot in section.slots.all() if slot.archived_at is None]
    taken = services.taken_map(slots)
    active = services.active_enrollments()
    counts = dict(active.values("section_id").annotate(n=Count("id")).values_list("section_id", "n"))
    no_hour = dict(
        active.filter(slot__isnull=True).values("section_id").annotate(n=Count("id")).values_list("section_id", "n")
    )
    out = []
    for section in rows:
        own = [slot for slot in slots if slot.section_id == section.pk]
        out.append(
            {
                "id": section.pk,
                "title": section.title,
                "sport_type": section.sport_type_id,
                "address": section.address,
                "enrolled": counts.get(section.pk, 0),
                "no_hour": no_hour.get(section.pk, 0),
                "capacity": sum(slot.capacity for slot in own),
                "slots": [_slot_dict(slot, taken.get(slot.pk, 0)) for slot in own],
            }
        )
    return Response({"settings": _settings_dict(), "rows": out, "weekdays": Weekday.choices})


@extend_schema(responses={200: dict})
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def section(request, pk: int):
    """Карточка секции: занятия с записанными, строка «без часа». PATCH — адрес и занятия."""
    if not _writer(request):
        return _no_rights()
    row = Section.objects.filter(pk=pk).first()
    if row is None:
        return _not_found()
    if request.method == "PATCH":
        try:
            _save_section(row, request.data, actor=request.user)
        except services.Refused as error:
            return _bad(str(error))
    slots = list(row.slots.all())
    enrollments = list(
        services.active_enrollments()
        .filter(section=row)
        .select_related("student", "student__group", "section", "slot")
        .order_by("enrolled_at", "id")
    )
    pct = services.month_percents(enrollments)
    taken = services.taken_map(slots)
    return Response(
        {
            "id": row.pk,
            "title": row.title,
            "address": row.address,
            "slots": [
                {
                    **_slot_dict(slot, taken.get(slot.pk, 0)),
                    "students": [
                        _enrollment_dict(e, pct.get(e.student_id)) for e in enrollments if e.slot_id == slot.pk
                    ],
                }
                for slot in slots
            ],
            "no_hour": [_enrollment_dict(e) for e in enrollments if e.slot_id is None],
        }
    )


def _clock(raw) -> dt.time | None:
    try:
        return dt.time.fromisoformat(str(raw))
    except ValueError:
        return None


def _slot_fields(data) -> dict:
    weekday = _int(data.get("weekday"))
    starts, ends = _clock(data.get("starts")), _clock(data.get("ends"))
    grade_from, grade_to = _int(data.get("grade_from")), _int(data.get("grade_to"))
    capacity = _int(data.get("capacity"))
    if weekday is None or weekday not in Weekday.values:
        raise services.Refused(_("Выберите день недели"))
    if starts is None or ends is None or ends <= starts:
        raise services.Refused(_("Конец занятия должен быть позже начала"))
    if grade_from is None or grade_to is None or not 8 <= grade_from <= grade_to <= 11:
        raise services.Refused(_("Классы — от 8 до 11"))
    if not capacity:
        raise services.Refused(_("Укажите лимит мест"))
    return {
        "weekday": weekday,
        "starts": starts,
        "ends": ends,
        "grade_from": grade_from,
        "grade_to": grade_to,
        "room": str(data.get("room") or "").strip()[:80],
        "capacity": min(capacity, 999),
    }


def _save_section(row: Section, data, *, actor) -> None:
    """Адрес и занятия одним сохранением. Занятие, которого нет в списке, убирается.

    Записанных на убранное занятие переводят в час из `moves` (`{id: куда}`)
    или оставляют «без часа» — тогда ученик видит плашку «Выбери время».
    """
    from django.db import transaction

    address = str(data.get("address") if "address" in data else row.address).strip()
    if not address:
        raise services.Refused(_("Укажите адрес площадки"))
    given = data.get("slots")
    moves = data.get("moves") or {}
    with transaction.atomic():
        row.address = address[:250]
        row.save(update_fields=["address"])
        if given is None:
            return
        keep: list[int] = []
        created: dict[str, SectionSlot] = {}
        for item in given:
            fields = _slot_fields(item)
            slot_id = _int(item.get("id"))
            if slot_id:
                slot = row.slots.filter(pk=slot_id).first()
                if slot is None:
                    raise services.Refused(_("Такого занятия нет"))
                for key, value in fields.items():
                    setattr(slot, key, value)
                slot.save()
                keep.append(slot.pk)
            else:
                slot = SectionSlot.objects.create(section=row, **fields)
                keep.append(slot.pk)
                if item.get("key"):
                    created[str(item["key"])] = slot
        for slot in row.slots.exclude(pk__in=keep):
            target_raw = moves.get(str(slot.pk))
            target = created.get(str(target_raw)) or (
                row.slots.filter(pk=_int(target_raw)).first() if _int(target_raw) else None
            )
            services.remove_slot(slot, move_to=target, actor=actor)


@extend_schema(responses={200: dict})
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def enroll_settings(request):
    """«Запись открыта до»: пусто — закрыта. Ведут директор спорта и администратор."""
    if not _writer(request):
        return _no_rights()
    if request.method == "PATCH":
        raw = request.data.get("enroll_until")
        value = parse_datetime(str(raw)) if raw else None
        if raw and value is None:
            return _bad(_("Укажите дату и время"))
        if value is not None and timezone.is_naive(value):
            value = timezone.make_aware(value)
        services.set_enroll_until(value, actor=request.user)
    return Response(_settings_dict())


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sections_export(request):
    """Excel: лист на секцию — час, ученик, класс, когда записался и откуда."""
    if not _writer(request):
        return _no_rights()
    rows = list(
        services.active_enrollments()
        .select_related("student", "student__group", "section", "slot")
        .order_by("section__order", "slot__weekday", "slot__starts", "student__last_name")
    )
    columns = [
        Column(_("Час"), lambda e: services.slot_words(e.slot) if e.slot_id else _("час не выбран"), 18),
        Column(_("Ученик"), lambda e: e.student.full_name, 30),
        Column(_("Группа"), lambda e: e.student.group.code if e.student.group_id else "", 10),
        Column(_("Класс"), lambda e: services.grade_of(e.student), 8),
        Column(_("Записался"), lambda e: timezone.localtime(e.enrolled_at).date(), 12),
        Column(_("Откуда запись"), lambda e: e.get_source_display(), 18),
    ]
    sheets = [
        (section.title, columns, [e for e in rows if e.section_id == section.pk]) for section in Section.objects.all()
    ]
    # пустой лист в предпросмотре — секция без записанных, искать в нём нечего
    sheets = [sheet for sheet in sheets if sheet[2]]
    return workbook_of_sheets(filename=_("Секции.xlsx"), sheets=sheets, request=request)


# --- Записи: директор записывает, переводит, назначает час, убирает --------------------------


def _visible_student(request, raw):
    pk = _int(raw)
    return visible_students(request.user).filter(pk=pk).select_related("group").first() if pk else None


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_search(request):
    """Поиск ученика, чтобы записать его самому — и при закрытой записи."""
    if not _writer(request, ENROLLMENT):
        return _no_rights()
    query = str(request.query_params.get("q") or "").strip()
    if len(query) < 2:
        return Response({"rows": []})
    found = Student.objects.filter(is_active=True).select_related("group")
    for word in query.split()[:3]:
        found = found.filter(
            Q(last_name__icontains=word) | Q(first_name__icontains=word) | Q(group__code__icontains=word)
        )
    found = list(found.order_by("last_name", "first_name")[:20])
    current = {
        e.student_id: e
        for e in SectionEnrollment.objects.filter(student__in=found, ended_at__isnull=True).select_related(
            "section", "slot"
        )
    }
    out = []
    for student in found:
        row = current.get(student.pk)
        out.append(
            {
                **_brief(student),
                "section": row.section.title if row else "",
                "slot": services.slot_words(row.slot) if row and row.slot_id else "",
            }
        )
    return Response({"rows": out})


@extend_schema(request=None, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def enrollments(request):
    """Директор записывает ученика на час — и при закрытой записи; другая секция закрывает прежнюю запись."""
    if not _writer(request, ENROLLMENT):
        return _no_rights()
    student = _visible_student(request, request.data.get("student"))
    if student is None:
        return _not_found()
    slot = SectionSlot.objects.filter(pk=_int(request.data.get("slot"))).first()
    if slot is None:
        return _bad(_("Выберите час занятия"))
    try:
        row = services.enroll(student=student, slot=slot, actor=request.user, by_director=True)
    except services.Refused as error:
        return _bad(str(error))
    return Response(_enrollment_dict(row), status=status.HTTP_201_CREATED)


@extend_schema(request=None, responses={200: dict})
@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def enrollment(request, pk: int):
    """PATCH `slot` — перевести в другой час или назначить час; DELETE — убрать из секции."""
    if not _writer(request, ENROLLMENT):
        return _no_rights()
    row = (
        SectionEnrollment.objects.filter(pk=pk, ended_at__isnull=True)
        .select_related("student", "student__group", "section", "slot")
        .first()
    )
    if row is None:
        return _not_found()
    try:
        if request.method == "DELETE":
            services.leave(student=row.student, actor=request.user, by_director=True)
            return Response(status=status.HTTP_204_NO_CONTENT)
        slot = SectionSlot.objects.filter(pk=_int(request.data.get("slot")), section=row.section).first()
        if slot is None:
            return _bad(_("Выберите час этой секции"))
        row = services.enroll(student=row.student, slot=slot, actor=request.user, by_director=True)
    except services.Refused as error:
        return _bad(str(error))
    return Response(_enrollment_dict(row))


# --- Ученик: «Моя секция» ------------------------------------------------------------------


def _me_student(request):
    if _role(request) != ROLE_STUDENT:
        return None
    return Student.objects.filter(user=request.user, is_active=True).select_related("group").first()


def _marks_of(student, row: SectionEnrollment | None, limit: int = 8) -> list[dict]:
    """Последние занятия своего часа: был (QR или вручную) или не был."""
    if row is None or row.slot_id is None:
        return []
    today = services.local_now().date()
    since = max(timezone.localtime(row.slot_set_at or row.enrolled_at).date(), today - dt.timedelta(days=120))
    dates = services.held_dates(row.slot, since, today)[-limit:]
    marks = {m.date: m for m in SectionMark.objects.filter(student=student, slot=row.slot, date__in=dates)}
    out = []
    for day in reversed(dates):
        mark = marks.get(day)
        out.append(
            {
                "date": day.isoformat(),
                "came": mark is not None,
                "method": mark.method if mark else "",
                "at": _when(mark.marked_at) if mark and mark.method == MarkMethod.QR else None,
            }
        )
    return out


def _my_payload(student) -> dict:
    row = services.active_of(student)
    settings_data = _settings_dict()
    options: list[dict] = []
    # выбор показывается при открытой записи, а записанному без часа — часы своей секции всегда
    if row is not None and row.slot_id is None:
        slots = list(services.slots_for(student, row.section))
    elif settings_data["open"]:
        slots = list(services.slots_for(student))
    else:
        slots = []
    taken = services.taken_map(slots)
    by_section: dict[int, dict] = {}
    for slot in slots:
        entry = by_section.setdefault(
            slot.section_id,
            {"id": slot.section_id, "title": slot.section.title, "address": slot.section.address, "slots": []},
        )
        entry["slots"].append(_slot_dict(slot, taken.get(slot.pk, 0)))
    options = list(by_section.values())
    mine = None
    if row is not None:
        marks = _marks_of(student, row)
        last = services.local_now().date()
        mine = {
            "id": row.pk,
            "section": row.section_id,
            "section_title": row.section.title,
            "address": row.section.address,
            "slot": _slot_dict(row.slot) if row.slot_id else None,
            "source": row.source,
            "next_at": _when(services.next_session(row.slot)) if row.slot_id else None,
            "percent": services.percent(row, dt.date(2000, 1, 1), last),
            "marks": marks,
            "came": sum(1 for m in marks if m["came"]),
        }
    return {
        **settings_data,
        "grade": services.grade_of(student),
        "enrollment": mine,
        "sections": options,
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_section(request):
    """Своя секция, ближайшее занятие, свои отметки; при открытой записи — часы своей группы классов."""
    me = _me_student(request)
    if me is None:
        return _forbid(_("Раздел — у ученика"))
    return Response(_my_payload(me))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_enroll(request):
    """Записаться на час, сменить секцию или час; записанный без часа выбирает час и при закрытой записи."""
    me = _me_student(request)
    if me is None:
        return _forbid(_("Записывается ученик"))
    slot = SectionSlot.objects.filter(pk=_int(request.data.get("slot"))).first()
    if slot is None:
        return _bad(_("Выберите час занятия"))
    try:
        services.enroll(student=me, slot=slot, actor=request.user)
    except services.Refused as error:
        return _bad(str(error))
    return Response(_my_payload(me))


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_leave(request):
    me = _me_student(request)
    if me is None:
        return _forbid(_("Выходит из секции ученик"))
    try:
        services.leave(student=me, actor=request.user)
    except services.Refused as error:
        return _bad(str(error))
    return Response(_my_payload(me))


# --- Секция ученика у куратора и директора спорта ------------------------------------------


def _student_section(student) -> dict:
    row = services.active_of(student)
    if row is None:
        return {"enrolled": False}
    pct = services.month_percents([row]).get(student.pk)
    return {
        "enrolled": True,
        "section": row.section.title,
        "address": row.section.address,
        "slot": services.slot_words(row.slot) if row.slot_id else "",
        "slot_day": row.slot.get_weekday_display() if row.slot_id else "",
        "percent": pct,
        "below": services.below_threshold(pct),
        "marks": _marks_of(student, row, limit=4),
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_section(request, pk: int):
    """Блок «Секция» в карточке ученика — только чтение. Куратор — свои группы, чужой — 404."""
    if not can_read_cabinet(_role(request), ENROLLMENT):
        return _no_rights()
    student = _visible_student(request, pk)
    if student is None:
        return _not_found()
    return Response(_student_section(student))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def students_sections(request):
    """Колонки «Секция» и «Посещение секции» в списке учеников: по группе или по всем видимым."""
    if not can_read_cabinet(_role(request), ENROLLMENT):
        return _no_rights()
    students = visible_students(request.user).filter(is_active=True)
    group = _int(request.query_params.get("group"))
    if group:
        students = students.filter(group_id=group)
    rows = list(
        SectionEnrollment.objects.filter(student__in=students, ended_at__isnull=True).select_related("section", "slot")
    )
    pct = services.month_percents(rows)
    by_student = {
        row.student_id: {
            "section": row.section.title,
            "slot": services.slot_words(row.slot) if row.slot_id else "",
            "percent": pct.get(row.student_id),
            "below": services.below_threshold(pct.get(row.student_id)),
        }
        for row in rows
    }
    return Response({"rows": {str(k): v for k, v in by_student.items()}})
