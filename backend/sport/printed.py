"""Печатный QR секции с проверкой места (решение владельца, 05.11.2026).

Меняющийся код на экране директора остаётся как был. Печатный код вешают
на площадке один раз: в нём постоянная ссылка с подписью секции, а от
«сфотографировал и переслал другу» защищает геолокация — отметка
засчитывается, только если ученик рядом с местом секции и только пока
идёт занятие.

Токен — «p.секция.выпуск.подпись» той же солью, что у меняющегося кода
(`services.TOKEN_SALT`). Буква в начале отличает его от токена занятия
(«занятие.дата.окно.подпись»): один не читается как другой. «Выпустить
новый QR» прибавляет номер выпуска — прежний лист перестаёт работать сразу.

Координаты ученика нужны один раз — посчитать расстояние. В базу и в журнал
идут только расстояние до точки секции и точность телефона.
"""

from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _

from core import school_rules
from core.domains import Source
from sport import services
from sport.models import MarkStatus, Section, SectionMark, SectionMarkMethod, SectionSlot

#: первая часть токена печатного кода
PRINT_PREFIX = "p"
#: модель секции в журнале и поля: место и выпуск печатного кода
SECTION_LABEL = "sport.Section"
LOCATION_FIELD = "location"
QR_FIELD = "qr_version"
#: средний радиус Земли, м — для формулы гаверсинуса
EARTH_M = 6_371_008.8
#: дальше стольких радиусов — отказ; между одним и этим числом — «на проверку»
FAR_RADIUSES = 2
#: потолок точности, которую есть смысл хранить: хуже — это уже «место неизвестно»
ACCURACY_CAP = 1_000_000


# --- Место секции ------------------------------------------------------------------------


def default_radius() -> int:
    return int(school_rules.value(school_rules.SPORT_GEO_RADIUS))


def radius_of(section: Section) -> int:
    """Радиус отметки секции: свой, а без него — правило школы."""
    return int(section.radius_m or default_radius())


def point_words(section: Section) -> str:
    """«43.238949, 76.889709» — так же, как координаты копируются из карт. Места нет — пусто."""
    if not section.has_location:
        return ""
    return f"{section.latitude.normalize():f}, {section.longitude.normalize():f}"


def _location_words(section: Section) -> str:
    """Место словами для журнала: точка и радиус — свой или по правилу школы."""
    if not section.has_location:
        return ""
    radius = (
        _("{n} м").format(n=section.radius_m)
        if section.radius_m
        else _("{n} м по правилу школы").format(n=default_radius())
    )
    return f"{point_words(section)} · {radius}"


def parse_point(raw) -> tuple[Decimal, Decimal] | None:
    """Широта и долгота из строки «43.23, 76.94». Пусто — `None` (место убирают).

    Разделитель — запятая, точка с запятой или пробел; дробная часть — через точку.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    parts = [part for part in text.replace(";", " ").replace(",", " ").split() if part]
    if len(parts) != 2:
        raise services.Refused(_("Координаты — два числа через запятую: широта, долгота. Например: 43.23, 76.94"))
    try:
        latitude, longitude = (Decimal(part) for part in parts)
    except InvalidOperation as error:
        raise services.Refused(
            _("Координаты — два числа через запятую: широта, долгота. Например: 43.23, 76.94")
        ) from error
    return check_point(latitude, longitude)


def check_point(latitude: Decimal, longitude: Decimal) -> tuple[Decimal, Decimal]:
    if not latitude.is_finite() or not longitude.is_finite():
        raise services.Refused(_("Координаты — два числа через запятую: широта, долгота. Например: 43.23, 76.94"))
    if not -90 <= latitude <= 90:
        raise services.Refused(_("Широта — от −90 до 90"))
    if not -180 <= longitude <= 180:
        raise services.Refused(_("Долгота — от −180 до 180"))
    return round(latitude, 6), round(longitude, 6)


def check_radius(raw) -> int | None:
    """Свой радиус секции в границах правила школы; пусто — по правилу."""
    if raw in (None, ""):
        return None
    rule = school_rules.rule_of(school_rules.SPORT_GEO_RADIUS)
    try:
        value = int(str(raw).strip())
    except ValueError as error:
        raise services.Refused(_("Радиус — целое число метров")) from error
    if not rule.minimum <= value <= rule.maximum:
        raise services.Refused(_("Радиус — от {low} до {high} м").format(low=int(rule.minimum), high=int(rule.maximum)))
    return value


@transaction.atomic
def set_location(
    section: Section, *, point: tuple[Decimal, Decimal] | None, radius_m: int | None, actor, source: str = Source.MANUAL
) -> bool:
    """Задать или убрать место секции. Правка — в журнал, было → стало. Ответ — менялось ли что-то."""
    from core.models import AuditLog

    row = Section.all_objects.select_for_update().get(pk=section.pk)
    old = _location_words(row)
    row.latitude, row.longitude = point if point is not None else (None, None)
    row.radius_m = radius_m if point is not None else None
    new = _location_words(row)
    if old == new:
        return False
    row.save(update_fields=["latitude", "longitude", "radius_m"])
    section.latitude, section.longitude, section.radius_m = row.latitude, row.longitude, row.radius_m
    AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_role=getattr(actor, "role", "") or "",
        model_label=SECTION_LABEL,
        object_id=str(row.pk),
        field_name=LOCATION_FIELD,
        domain_code="sport",
        old_value=old,
        new_value=new,
        source=source,
    )
    return True


# --- Токен печатного кода ------------------------------------------------------------------


def make_print_token(section: Section) -> str:
    """Постоянный токен секции: «p.секция.выпуск.подпись». От времени не зависит."""
    return services._signer().sign(f"{PRINT_PREFIX}.{section.pk}.{section.qr_version}")


def is_print_token(token) -> bool:
    return str(token or "").startswith(f"{PRINT_PREFIX}.")


def read_print_token(token) -> Section | None:
    """Секция действующего печатного кода. Подделанный, прежнего выпуска, секция в архиве — `None`."""
    try:
        raw = services._signer().unsign(str(token or ""))
        prefix, section_id, version = raw.split(".")
        if prefix != PRINT_PREFIX:
            return None
        section_value, version_value = int(section_id), int(version)
    except (signing.BadSignature, ValueError):
        return None
    return Section.objects.filter(pk=section_value, qr_version=version_value).first()


def print_url(section: Section) -> str:
    """Ссылка печатного кода — та же страница отметки, что у меняющегося: `/s/<токен>`."""
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/s/{make_print_token(section)}"


@transaction.atomic
def reissue(section: Section, *, actor) -> Section:
    """«Выпустить новый QR»: прежний лист перестаёт работать сразу. Пишется в журнал изменений."""
    from core.models import AuditLog

    Section.all_objects.filter(pk=section.pk).update(qr_version=F("qr_version") + 1)
    old = section.qr_version
    section.refresh_from_db(fields=["qr_version"])
    AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_role=getattr(actor, "role", "") or "",
        model_label=SECTION_LABEL,
        object_id=str(section.pk),
        field_name=QR_FIELD,
        domain_code="sport",
        old_value=str(old),
        new_value=str(section.qr_version),
        source=Source.MANUAL,
    )
    return section


# --- Расстояние -----------------------------------------------------------------------------


def distance_m(lat_a: float, lng_a: float, lat_b: float, lng_b: float) -> float:
    """Расстояние между двумя точками по формуле гаверсинуса, м."""
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = phi_b - phi_a
    d_lambda = math.radians(lng_b - lng_a)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_M * math.asin(min(1.0, math.sqrt(h)))


def read_position(data) -> tuple[float, float, float] | None:
    """Широта, долгота и точность из запроса. Нет или мусор — `None`: страница спросит место заново."""
    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        accuracy = float(data.get("accuracy"))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (latitude, longitude, accuracy)):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180 and accuracy >= 0):
        return None
    return latitude, longitude, accuracy


def distance_words(metres: int) -> str:
    """«350 м» или «2,3 км» — как ученик прочитает на телефоне."""
    if metres < 1000:
        return _("{n} м").format(n=metres)
    return _("{n} км").format(n=f"{metres / 1000:.1f}".replace(".", ","))


# --- Отметка ------------------------------------------------------------------------------


def _live_slots(section: Section, now: dt.datetime) -> list[SectionSlot]:
    """Занятия секции, которые идут сейчас: от начала до конца часа, не законченные раньше."""
    day = now.date()
    slots = SectionSlot.objects.filter(section=section, weekday=day.weekday()).select_related("section")
    return [
        slot for slot in slots.order_by("starts", "parallel_from") if services.session_state(slot, day, now) == "live"
    ]


def _place(section: Section) -> dict:
    return {"section": section.title, "address": section.address}


def mark_by_print(
    *, student, section: Section, position: tuple[float, float, float] | None, now: dt.datetime | None = None
) -> dict:
    """Отметка по печатному коду. Ответ — состояние для экрана телефона, а не исключение.

    Сначала время (идёт ли занятие секции), потом запись (свой час, гость,
    «не твоё занятие»), потом место. Без координат отвечает `need_geo` —
    и только когда всё остальное сошлось: спрашивать место у того, чьё
    занятие не идёт, незачем.

    Место: в радиусе и с точностью не хуже радиуса — отметка засчитана;
    точность хуже радиуса или до двух радиусов — «на проверку»; дальше —
    отказ. Повторный чистый скан засчитывает отметку, ждавшую проверки.
    """
    now = now or services.local_now()
    day = now.date()
    if not section.has_location:
        return {"state": "replaced"}
    live = _live_slots(section, now)
    if not live:
        return {"state": "no_session", "place": _place(section)}
    grade = services.student_parallel(student)
    fitting = next((slot for slot in live if slot.fits(grade)), live[0])
    mine = services.active_in(student, section)
    if mine is not None and mine.slot_id is None:
        return {"state": "no_hour", "session": services._slot_brief(fitting)}
    if mine is not None:
        slot = next((item for item in live if item.pk == mine.slot_id), None)
        if slot is None:
            return {
                "state": "foreign",
                "session": services._slot_brief(fitting),
                "mine": services._slot_brief(mine.slot),
            }
    else:
        # не записан в эту секцию — гость, как по меняющемуся коду
        slot = fitting
    session = services._slot_brief(slot)
    row = SectionMark.objects.filter(student=student, slot=slot, date=day).first()
    if row is not None and row.status == MarkStatus.CONFIRMED:
        return _answer("guest_already" if row.is_guest else "already", session, row)
    if row is not None and row.status == MarkStatus.REJECTED:
        return {"state": "rejected", "session": session}
    if position is None:
        return {"state": "need_geo", "session": session}

    latitude, longitude, accuracy = position
    radius = radius_of(section)
    distance = round(distance_m(latitude, longitude, float(section.latitude), float(section.longitude)))
    inaccurate = accuracy > radius
    if distance > FAR_RADIUSES * radius:
        return {
            "state": "far",
            "session": session,
            "distance": distance_words(distance),
            "inaccurate": inaccurate,
        }
    status = MarkStatus.PENDING if inaccurate or distance > radius else MarkStatus.CONFIRMED
    measured = {"distance_m": distance, "accuracy_m": min(math.ceil(accuracy), ACCURACY_CAP)}
    with transaction.atomic():
        row, created = SectionMark.objects.get_or_create(
            student=student,
            slot=slot,
            date=day,
            defaults={
                "method": SectionMarkMethod.PRINTED,
                "marked_at": timezone.now(),
                "is_guest": mine is None,
                "status": status,
                **measured,
            },
        )
        if not created and row.status == MarkStatus.PENDING and status == MarkStatus.CONFIRMED:
            # ждала проверки, а теперь ученик на месте и телефон видит его точно — проверять нечего
            for key, value in measured.items():
                setattr(row, key, value)
            row.status = MarkStatus.CONFIRMED
            row.method = SectionMarkMethod.PRINTED
            row.save(update_fields=["status", "method", *measured])
            created = True
    if row.status == MarkStatus.REJECTED:
        return {"state": "rejected", "session": session}
    if row.status == MarkStatus.PENDING:
        return {
            **_answer("review", session, row),
            "guest": row.is_guest,
            "distance": distance_words(distance),
            "inaccurate": inaccurate,
        }
    if row.is_guest:
        return _answer("guest" if created else "guest_already", session, row)
    return _answer("marked" if created else "already", session, row)


def _answer(state: str, session: dict, row: SectionMark) -> dict:
    return {"state": state, "session": session, "marked_at": timezone.localtime(row.marked_at).isoformat()}


# --- «На проверку» --------------------------------------------------------------------------


def why_pending(mark: SectionMark) -> str:
    """Почему отметка ждёт проверки — одной строкой для директора."""
    radius = radius_of(mark.slot.section)
    if mark.accuracy_m is not None and mark.accuracy_m > radius:
        return _("место определено неточно: ±{accuracy}, радиус {radius} м").format(
            accuracy=distance_words(mark.accuracy_m), radius=radius
        )
    return _("за радиусом: {distance} от места, радиус {radius} м").format(
        distance=distance_words(mark.distance_m or 0), radius=radius
    )


@transaction.atomic
def review(mark_id: int, *, confirm: bool, actor) -> SectionMark:
    """Директор решает по отметке «на проверку»: засчитать или отклонить. Второй раз — отказ."""
    row = (
        SectionMark.objects.select_for_update(of=("self",))
        .select_related("slot", "slot__section", "student")
        .filter(pk=mark_id)
        .first()
    )
    if row is None:
        raise services.Refused(_("Отметки нет"))
    if row.status != MarkStatus.PENDING:
        raise services.Refused(_("Отметка уже проверена"))
    row.status = MarkStatus.CONFIRMED if confirm else MarkStatus.REJECTED
    row.reviewed_by = actor if getattr(actor, "pk", None) else None
    row.reviewed_by_title = services._title(actor)
    row.reviewed_at = timezone.now()
    row.save(update_fields=["status", "reviewed_by", "reviewed_by_title", "reviewed_at"])
    return row
