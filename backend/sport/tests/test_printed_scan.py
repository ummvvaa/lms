"""Отметка ученика по печатному QR: время занятия, место, запись.

Время замораживается на субботу 31.10.2026, 12:04 по Алматы — идёт теннис
12:00–13:00 для 10–11 классов. Место тенниса — точка в Алматы, радиус 200 м
по правилу школы; точки ученика считаются сдвигом на север.

Границы, которые легко сломать тихо:
* в радиусе и точно — засчитана; неточно или до двух радиусов — «на проверку»;
  дальше двух радиусов — отказ, отметки нет;
* место спрашивается, только когда занятие идёт и оно своё (или ученик — гость);
* координаты ученика не остаются ни в отметке, ни в журнале, ни в логах;
* прежний лист после «Выпустить новый QR» не отмечает, меняющийся код работает как был.
"""

from __future__ import annotations

import datetime as dt
import logging

import pytest
from rest_framework.test import APIClient

from core.models import AuditLog
from sport import printed, services
from sport.models import MarkStatus, Section, SectionMark, SectionMarkMethod
from sport.tests.conftest import DEGREE_M, LAT, LNG, SATURDAY, away, login, slot_of
from sport.tests.conftest import scan_printed as scan

pytestmark = pytest.mark.django_db


# --- Токен ------------------------------------------------------------------------------


def test_forged_print_token_is_refused(member, at):
    senior, _slot = member
    at(12, 4)
    token = printed.make_print_token(Section.objects.get(title="Теннис"))
    other = Section.objects.exclude(title="Теннис").first()
    # подпись тенниса под номером другой секции
    forged = f"p.{other.pk}." + token.split(".", 2)[2]
    answer = login(senior.user).post("/api/sport/scan/", {"token": forged, **away(0)}, format="json").json()
    assert answer["state"] == "replaced" and not SectionMark.objects.exists()


def test_old_sheet_stops_working_after_reissue(people, member, at):
    senior, _slot = member
    at(12, 4)
    court = Section.objects.get(title="Теннис")
    old = printed.make_print_token(court)
    answer = login(people["director_sport"]).post(f"/api/sport/sections/{court.pk}/reissue/")
    assert answer.status_code == 200 and answer.json()["qr_version"] == 2
    api = login(senior.user)
    assert api.post("/api/sport/scan/", {"token": old, **away(10)}, format="json").json()["state"] == "replaced"
    assert not SectionMark.objects.exists()
    court.refresh_from_db()
    assert scan(senior, court, away(10))["state"] == "marked"


# --- Место ------------------------------------------------------------------------------


def test_haversine_matches_known_distance():
    # Алматы — Астана по дуге большого круга: около 972 км
    value = printed.distance_m(43.238949, 76.889709, 51.169392, 71.449074)
    assert 965_000 < value < 980_000
    assert round(printed.distance_m(43.0, 76.0, 43.0 + 200 / DEGREE_M, 76.0)) == 200


def test_inside_radius_is_marked_and_keeps_only_distance(member, at):
    senior, slot = member
    at(12, 4)
    court = slot.section
    assert scan(senior, court)["state"] == "need_geo"
    assert not SectionMark.objects.exists()
    answer = scan(senior, court, away(120))
    assert answer["state"] == "marked" and answer["session"]["section"] == "Теннис"
    mark = SectionMark.objects.get(student=senior, slot=slot, date=SATURDAY)
    assert mark.method == SectionMarkMethod.PRINTED and mark.status == MarkStatus.CONFIRMED
    assert (mark.distance_m, mark.accuracy_m, mark.is_guest) == (120, 15, False)
    assert scan(senior, court)["state"] == "already"
    assert scan(senior, court, away(120))["state"] == "already"
    assert SectionMark.objects.count() == 1


@pytest.mark.parametrize(
    ("metres", "accuracy", "inaccurate"),
    [(40, 500, True), (310, 15, False), (399, 15, False)],
)
def test_poor_accuracy_or_edge_goes_to_review(member, at, metres, accuracy, inaccurate):
    senior, slot = member
    at(12, 4)
    answer = scan(senior, slot.section, away(metres, accuracy))
    assert answer["state"] == "review" and answer["inaccurate"] is inaccurate
    mark = SectionMark.objects.get(student=senior)
    assert mark.status == MarkStatus.PENDING and (mark.distance_m, mark.accuracy_m) == (metres, accuracy)
    # повторный скан с тем же местом отметку не множит и не засчитывает
    assert scan(senior, slot.section, away(metres, accuracy))["state"] == "review"
    assert SectionMark.objects.count() == 1


def test_clean_rescan_confirms_a_pending_mark(member, at):
    senior, slot = member
    at(12, 4)
    assert scan(senior, slot.section, away(40, 800))["state"] == "review"
    assert scan(senior, slot.section, away(40, 20))["state"] == "marked"
    mark = SectionMark.objects.get(student=senior)
    assert mark.status == MarkStatus.CONFIRMED and mark.accuracy_m == 20


def test_beyond_two_radiuses_is_refused(member, at):
    senior, slot = member
    at(12, 4)
    answer = scan(senior, slot.section, away(2300))
    assert answer["state"] == "far" and answer["distance"] == "2,3 км" and answer["inaccurate"] is False
    # дальше двух радиусов — отказ и при неточном месте: телефон просят определить его точнее
    answer = scan(senior, slot.section, away(450, 900))
    assert answer["state"] == "far" and answer["distance"] == "450 м" and answer["inaccurate"] is True
    assert not SectionMark.objects.exists()


def test_section_radius_overrides_the_school_rule(member, at, set_rules):
    senior, slot = member
    at(12, 4)
    court = slot.section
    set_rules(sport_geo_radius=100)
    assert printed.radius_of(court) == 100
    assert scan(senior, court, away(150))["state"] == "review"
    SectionMark.objects.all().delete()
    printed.set_location(court, point=(LAT, LNG), radius_m=400, actor=None)
    court.refresh_from_db()
    assert printed.radius_of(court) == 400
    assert scan(senior, court, away(350))["state"] == "marked"


def test_bad_coordinates_ask_for_the_place_again(member, at):
    senior, slot = member
    at(12, 4)
    for position in (
        {"latitude": "abc", "longitude": 76.9, "accuracy": 10},
        {"latitude": 143.2, "longitude": 76.9, "accuracy": 10},
        {"latitude": 43.2, "longitude": 76.9},
        {"latitude": 43.2, "longitude": 76.9, "accuracy": -5},
        {"latitude": float("nan"), "longitude": 76.9, "accuracy": 5},
    ):
        body = {"token": printed.make_print_token(slot.section), **position}
        raw = login(senior.user).post("/api/sport/scan/", body, format="multipart")
        assert raw.json()["state"] == "need_geo", position
    assert not SectionMark.objects.exists()


def test_student_coordinates_are_not_kept_anywhere(member, at, caplog):
    senior, slot = member
    at(12, 4)
    position = away(137, 23)
    with caplog.at_level(logging.DEBUG):
        assert scan(senior, slot.section, position)["state"] == "marked"
    latitude = f"{position['latitude']:.4f}"
    assert latitude not in caplog.text
    mark = SectionMark.objects.get(student=senior)
    # у отметки — только расстояние и точность; полей широты и долготы у неё нет
    names = {field.name for field in SectionMark._meta.get_fields()}
    assert not names & {"latitude", "longitude", "lat", "lng", "position", "point"}
    assert latitude not in " ".join(str(value) for value in mark.__dict__.values())
    assert not AuditLog.objects.filter(new_value__contains=latitude).exists()


# --- Время и запись ---------------------------------------------------------------------


def test_outside_session_time_is_refused_before_asking_the_place(member, at):
    senior, slot = member
    court = slot.section
    at(11, 40)
    assert scan(senior, court)["state"] == "no_session"
    assert scan(senior, court, away(5))["state"] == "no_session"
    at(15, 30)
    assert scan(senior, court, away(5))["state"] == "no_session"
    at(12, 4, day=SATURDAY + dt.timedelta(days=1))
    assert scan(senior, court, away(5))["state"] == "no_session"
    # занятие закончено директором раньше — отметки закрыты
    at(12, 4)
    services.end_session(slot, actor=None, day=SATURDAY)
    assert scan(senior, court, away(5))["state"] == "no_session"
    assert not SectionMark.objects.exists()


def test_guest_by_printed_code(pupils, court, at):
    """Не записан в секцию — гостевая отметка на идущем занятии, как по меняющемуся коду."""
    senior, _junior = pupils
    at(12, 4)
    assert scan(senior, court, away(30))["state"] == "guest"
    mark = SectionMark.objects.get(student=senior)
    assert mark.is_guest and mark.slot == slot_of("Теннис", 5, 12, 10) and mark.method == SectionMarkMethod.PRINTED
    assert scan(senior, court, away(30))["state"] == "guest_already"


def test_enrolled_at_another_hour_is_not_yours(pupils, court, at):
    senior, _junior = pupils
    services.enroll(student=senior, slot=slot_of("Теннис", 5, 13, 10), actor=None, by_director=True)
    at(12, 4)
    answer = scan(senior, court, away(10))
    assert answer["state"] == "foreign" and answer["mine"]["starts"] == "13:00"
    assert not SectionMark.objects.exists()
    at(13, 4)
    assert scan(senior, court, away(10))["state"] == "marked"


def test_not_logged_in_is_asked_to_log_in_and_token_survives(member, at):
    senior, slot = member
    at(12, 4)
    api = APIClient()
    token = printed.make_print_token(slot.section)
    answer = api.post("/api/sport/scan/", {"token": token}, format="json").json()
    assert answer == {"state": "login", "geo": True}
    api.force_login(senior.user)
    assert api.post("/api/sport/scan/", {"token": token, **away(20)}, format="json").json()["state"] == "marked"


def test_staff_cannot_mark_by_printed_code(people, member, at):
    _senior, slot = member
    at(12, 4)
    token = printed.make_print_token(slot.section)
    for role in ("director_sport", "curator", "teacher"):
        answer = login(people[role]).post("/api/sport/scan/", {"token": token, **away(5)}, format="json")
        # учителя и куратора не пускает шлюз маршрутов (404), директора — сама ручка (403)
        assert answer.status_code in (403, 404), role
    assert not SectionMark.objects.exists()


def test_changing_code_still_works_and_confirms_a_pending_mark(member, at):
    senior, slot = member
    at(12, 4)
    assert scan(senior, slot.section, away(350))["state"] == "review"
    token = services.make_token(slot, SATURDAY)[0]
    api = login(senior.user)
    assert api.post("/api/sport/scan/", {"token": token}, format="json").json()["state"] == "marked"
    mark = SectionMark.objects.get(student=senior)
    assert mark.status == MarkStatus.CONFIRMED and mark.method == SectionMarkMethod.QR
    assert api.post("/api/sport/scan/", {"token": token}, format="json").json()["state"] == "already"
