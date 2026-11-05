"""Печатный QR секции: постоянный токен, лист A4 для печати и новый выпуск кода.

Границы, которые легко сломать тихо:
* печатный токен не зависит от времени и не читается как токен занятия — и наоборот;
* после «Выпустить новый QR» прежний токен не читается, выпуск записан в журнал изменений;
* лист печатают директор спорта и администратор; без места секции листа нет, и ответ говорит, к кому идти.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.models import AuditLog
from sport import printed, services
from sport.tests.conftest import LAT, LNG, SATURDAY, login, slot_of

pytestmark = pytest.mark.django_db


def test_print_token_is_permanent_and_of_another_kind(court, at):
    """Печатный токен не зависит от времени и не читается как токен занятия — и наоборот."""
    at(12, 4)
    token = printed.make_print_token(court)
    assert token.startswith("p.") and printed.read_print_token(token) == court
    at(12, 4, day=SATURDAY + dt.timedelta(days=200))
    assert printed.make_print_token(court) == token and printed.read_print_token(token) == court
    assert services.read_token(token) is None
    session_token = services.make_token(slot_of("Теннис", 5, 12, 10), SATURDAY)[0]
    assert not printed.is_print_token(session_token) and printed.read_print_token(session_token) is None


def test_reissue_kills_the_old_token_and_is_logged(people, court):
    old = printed.make_print_token(court)
    answer = login(people["director_sport"]).post(f"/api/sport/sections/{court.pk}/reissue/")
    assert answer.status_code == 200 and answer.json()["qr_version"] == 2
    court.refresh_from_db()
    assert printed.read_print_token(old) is None
    assert printed.read_print_token(printed.make_print_token(court)) == court
    entry = AuditLog.objects.get(model_label="sport.Section", field_name="qr_version")
    assert (entry.old_value, entry.new_value, entry.actor) == ("1", "2", people["director_sport"])


def test_sheet_is_printed_by_director_and_admin_only(people, pupils, tennis):
    senior, _junior = pupils
    url = f"/api/sport/sections/{tennis.pk}/print/"
    # места нет — кнопка объясняет, к кому идти
    refused = login(people["director_sport"]).get(url)
    assert refused.status_code == 400 and "обратитесь к администратору" in refused.json()["detail"]
    assert login(people["director_sport"]).post(f"/api/sport/sections/{tennis.pk}/reissue/").status_code == 400
    printed.set_location(tennis, point=(LAT, LNG), radius_m=None, actor=None)
    for role in ("director_sport", "admin"):
        answer = login(people[role]).get(url)
        assert answer.status_code == 200 and answer["Content-Type"] == "application/pdf", role
        assert answer.content.startswith(b"%PDF-")
        assert "attachment" in answer["Content-Disposition"]
    closed = [people["curator"], people["teacher"], people["director_exam"], senior.user]
    for user in closed:
        api = login(user)
        assert api.get(url).status_code in (403, 404), user.role
        assert api.post(f"/api/sport/sections/{tennis.pk}/reissue/").status_code in (403, 404), user.role
    tennis.refresh_from_db()
    assert tennis.qr_version == 1


def test_session_shows_the_same_permanent_code_as_the_sheet(people, court, at):
    """На экране «Занятие и QR» — тот же код, что на листе; после нового выпуска — новый; без места кода нет."""
    at(12, 10)
    api = login(people["director_sport"])
    slot = slot_of("Теннис", 5, 12, 10)
    row = next(item for item in api.get("/api/sport/sessions/today/").json()["rows"] if item["id"] == slot.pk)
    assert row["has_location"] is True and row["qr_url"] == printed.print_url(court)
    assert api.get(f"/api/sport/sessions/{slot.pk}/").json()["qr_url"] == printed.print_url(court)
    old = row["qr_url"]
    api.post(f"/api/sport/sections/{court.pk}/reissue/")
    court.refresh_from_db()
    fresh = api.get(f"/api/sport/sessions/{slot.pk}/").json()["qr_url"]
    assert fresh == printed.print_url(court) and fresh != old
    # у секции без места кода на экране нет — отметка только вручную
    other = next(item for item in api.get("/api/sport/sessions/today/").json()["rows"] if item["title"] != "Теннис")
    assert other["has_location"] is False and other["qr_url"] == ""


def test_sheet_code_carries_the_section_link(court, settings):
    from sport import poster

    settings.FRONTEND_BASE_URL = "https://lms.example.kz/"
    url = printed.print_url(court)
    assert url == f"https://lms.example.kz/s/{printed.make_print_token(court)}"
    matrix = poster._matrix(url)
    assert len(matrix) == len(matrix[0]) and len(matrix) >= 29
    lines = poster.schedule_lines(court)
    assert "Суббота · 12:00–13:00 · параллели 10–11" in lines and len(lines) == 4
