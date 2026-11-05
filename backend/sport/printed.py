"""Место секции для отметки по печатному QR (решение владельца, 05.11.2026).

Печатный код вешают на площадке один раз, а от «сфотографировал и переслал
другу» защищает геолокация: отметка засчитывается только рядом с местом
секции. Место — точка (широта, долгота) и радиус; радиус по умолчанию —
правило школы, у секции можно задать свой. Задаёт место администратор.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.translation import gettext as _

from core import school_rules
from core.domains import Source
from sport import services
from sport.models import Section

#: модель секции в журнале и поле места
SECTION_LABEL = "sport.Section"
LOCATION_FIELD = "location"


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
