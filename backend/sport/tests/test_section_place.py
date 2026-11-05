"""Место секции для печатного QR: координаты и радиус задаёт только администратор.

Границы, которые легко сломать тихо:
* директор спорта координат не видит и не правит — ему приходит только признак «место задано»;
* адрес и занятия директор правит как раньше, место при этом не трогается;
* куратор, учитель и ученик формы секции не видят вовсе;
* команда `set_section_locations` ищет секцию по точному названию и ничего не создаёт.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.management import call_command

from core.models import AuditLog
from sport.models import Section
from sport.tests.conftest import LAT, LNG, login

pytestmark = pytest.mark.django_db


def test_only_admin_sees_and_sets_the_place(people, tennis):
    url = f"/api/sport/sections/{tennis.pk}/"
    admin, director = login(people["admin"]), login(people["director_sport"])
    assert admin.get(url).json()["location"] == {"point": "", "radius_m": None, "default_radius_m": 200}
    body = director.get(url).json()
    assert "location" not in body and body["has_location"] is False

    refused = director.patch(url, {"location": {"point": "43.23, 76.94", "radius_m": 150}}, format="json")
    assert refused.status_code == 403
    tennis.refresh_from_db()
    assert not tennis.has_location

    saved = admin.patch(url, {"location": {"point": "43.238949, 76.889709", "radius_m": 150}}, format="json")
    assert saved.status_code == 200
    assert saved.json()["location"] == {"point": "43.238949, 76.889709", "radius_m": 150, "default_radius_m": 200}
    body = director.get(url).json()
    assert "location" not in body and body["has_location"] is True
    assert "43.238949" not in str(body)
    sections = director.get("/api/sport/sections/").json()["rows"]
    assert next(row for row in sections if row["id"] == tennis.pk)["has_location"] is True
    assert "43.238949" not in str(sections)
    entry = AuditLog.objects.get(model_label="sport.Section", field_name="location")
    assert entry.old_value == "" and entry.new_value == "43.238949, 76.889709 · 150 м"
    assert entry.actor == people["admin"]

    # директор правит адрес и занятия как раньше — место при этом не трогается
    assert director.patch(url, {"address": "Новый адрес, 1"}, format="json").status_code == 200
    tennis.refresh_from_db()
    assert tennis.has_location and tennis.radius_m == 150

    # пустая точка убирает место — печатный код перестаёт работать
    assert admin.patch(url, {"location": {"point": "", "radius_m": None}}, format="json").status_code == 200
    tennis.refresh_from_db()
    assert not tennis.has_location and tennis.radius_m is None


def test_place_is_closed_to_curator_teacher_and_student(people, pupils, tennis):
    senior, _junior = pupils
    url = f"/api/sport/sections/{tennis.pk}/"
    for user in (people["curator"], people["teacher"], people["director_exam"], senior.user):
        api = login(user)
        assert api.get(url).status_code in (403, 404), user.role
        answer = api.patch(url, {"location": {"point": "43.23, 76.94"}}, format="json")
        assert answer.status_code in (403, 404), user.role
    tennis.refresh_from_db()
    assert not tennis.has_location


@pytest.mark.parametrize(
    "point",
    ["43.23", "сорок три, семьдесят шесть", "143.2, 76.9", "43.2, 276.9", "43.2, 76.9, 12"],
)
def test_bad_place_is_refused_with_a_reason(people, tennis, point):
    answer = login(people["admin"]).patch(
        f"/api/sport/sections/{tennis.pk}/", {"location": {"point": point}}, format="json"
    )
    assert answer.status_code == 400 and answer.json()["detail"]
    tennis.refresh_from_db()
    assert not tennis.has_location


def test_radius_must_fit_the_school_rule_bounds(people, tennis):
    admin = login(people["admin"])
    url = f"/api/sport/sections/{tennis.pk}/"
    for radius in (5, 50_000, "много"):
        answer = admin.patch(url, {"location": {"point": "43.23 76.94", "radius_m": radius}}, format="json")
        assert answer.status_code == 400, radius
    assert admin.patch(url, {"location": {"point": "43.23; 76.94", "radius_m": ""}}, format="json").status_code == 200
    tennis.refresh_from_db()
    assert (tennis.latitude, tennis.longitude, tennis.radius_m) == (Decimal("43.23"), Decimal("76.94"), None)


# --- Команда set_section_locations ------------------------------------------------------


def test_command_sets_places_and_lists_the_missing(tmp_path, capsys):
    file = tmp_path / "places.csv"
    file.write_text(
        "название секции; широта; долгота; радиус\n"
        "Теннис; 43.238949; 76.889709; 150\n"
        "Волейбол; 43,2565; 76,9285;\n"
        "Керлинг; 43.2; 76.9; 100\n"
        "Футбол; 143.2; 76.9; 100\n",
        encoding="utf-8",
    )
    before = Section.all_objects.count()
    call_command("set_section_locations", str(file), "--dry-run")
    assert not Section.objects.filter(latitude__isnull=False).exists()
    assert "ничего не изменено" in capsys.readouterr().out

    call_command("set_section_locations", str(file))
    out = capsys.readouterr().out
    tennis = Section.objects.get(title="Теннис")
    assert (tennis.latitude, tennis.longitude, tennis.radius_m) == (LAT, LNG, 150)
    # дробная часть через запятую, радиус не указан — действует правило школы
    volleyball = Section.objects.get(title="Волейбол")
    assert (volleyball.latitude, volleyball.longitude, volleyball.radius_m) == (
        Decimal("43.2565"),
        Decimal("76.9285"),
        None,
    )
    # ненайденная секция — в списке, ничего не создано; строка с ошибкой названа
    assert "не найдены" in out and "Керлинг" in out
    assert Section.all_objects.count() == before
    assert not Section.objects.get(title="Футбол").has_location and "Широта" in out
    assert AuditLog.objects.filter(model_label="sport.Section", field_name="location", source="import").count() == 2

    # повторный запуск ничего не меняет и не пишет в журнал второй раз
    logged = AuditLog.objects.filter(field_name="location").count()
    call_command("set_section_locations", str(file))
    assert "Без изменений" in capsys.readouterr().out
    assert AuditLog.objects.filter(field_name="location").count() == logged
