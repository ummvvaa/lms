"""«Ученики секций» (02.11.2026): рабочий список записей у директора спорта и администратора.

Границы, которые легко сломать тихо:
* в списке только ученики с действующей записью: убрали отовсюду — ушёл, история осталась;
* фильтры собираются вместе, Excel — ровно то, что на экране;
* массовое действие сначала даёт итог с причинами, потом выполняет — частичный
  отказ не откатывает остальных, каждое изменение в журнале с автором;
* куратор, другой директор, учитель и ученик раздела не видят.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from core.models import AuditLog
from sport import services
from sport.models import SectionEnrollment, SectionMark
from sport.tests.conftest import login, slot_of
from students.models import Student

pytestmark = pytest.mark.django_db


@pytest.fixture
def roster(people, pupils, tennis):
    """Абдрахман — теннис и шахматы, Бекова — теннис 8–9, Ермеков — теннис без часа."""
    senior, junior = pupils
    services.enroll(student=senior, slot=slot_of("Теннис", 5, 12, 10), actor=None, by_director=True)
    services.enroll(student=senior, slot=slot_of("Шахматы", 4, 17, 10), actor=None, by_director=True)
    services.enroll(student=junior, slot=slot_of("Теннис", 3, 17, 8), actor=None, by_director=True)
    third = Student.objects.create(last_name="Ермеков", first_name="Алихан", group=senior.group, graduation_year=2028)
    services.import_enrollment(student=third, section=tennis, slot=None, enrolled_at=timezone.now())
    return senior, junior, third


def _ids(body):
    return [row["student"]["id"] for row in body["rows"]]


def test_list_shows_only_students_with_an_enrollment(people, roster):
    senior, junior, third = roster
    nobody = Student.objects.create(last_name="Жоқ", first_name="Секция", group=senior.group, graduation_year=2028)
    api = login(people["director_sport"])
    body = api.get("/api/sport/roster/").json()
    assert set(_ids(body)) == {senior.pk, junior.pk, third.pk} and nobody.pk not in _ids(body)
    assert body["shown"] == body["total"] == 3
    row = next(r for r in body["rows"] if r["student"]["id"] == senior.pk)
    assert [e["section_title"] for e in row["enrollments"]] == ["Теннис", "Шахматы"]
    # убрали из всех секций — из списка ушёл, записи с датой выхода остались
    for item in row["enrollments"]:
        assert api.delete(f"/api/sport/enrollments/{item['id']}/").status_code == 204
    body = api.get("/api/sport/roster/").json()
    assert senior.pk not in _ids(body) and body["total"] == 2
    assert SectionEnrollment.objects.filter(student=senior, ended_at__isnull=False).count() == 2
    history = api.get(f"/api/sport/roster/{senior.pk}/history/").json()
    assert len(history["enrollments"]) == 2 and all(e["ended_at"] for e in history["enrollments"])
    assert any("вышел" in e["text"] for e in history["events"])


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("q=абдрах", {"senior"}),
        ("parallel=9", {"junior"}),
        ("section={chess}", {"senior"}),
        ("weekday=3", {"junior"}),
        ("hour=12:00", {"senior"}),
        ("section={tennis}&weekday=5&hour=12:00", {"senior"}),
        ("no_hour=1", {"third"}),
        ("several=1", {"senior"}),
        ("group={group}&several=1", {"senior"}),
    ],
)
def test_filters_go_together(people, roster, tennis, query, expected):
    senior, junior, third = roster
    names = {senior.pk: "senior", junior.pk: "junior", third.pk: "third"}
    chess = slot_of("Шахматы", 4, 17, 10).section_id
    text = query.format(chess=chess, tennis=tennis.pk, group=senior.group_id)
    body = login(people["director_sport"]).get(f"/api/sport/roster/?{text}").json()
    assert {names[i] for i in _ids(body)} == expected
    assert body["total"] == 3


def test_below_and_never_filters(people, roster, monkeypatch):
    senior, junior, _third = roster
    # все записаны с 1 октября; сейчас — 2 ноября, октябрь прошёл целиком
    SectionEnrollment.objects.update(
        enrolled_at=timezone.make_aware(dt.datetime(2026, 10, 1)),
        slot_set_at=timezone.make_aware(dt.datetime(2026, 10, 1)),
    )
    now = timezone.make_aware(dt.datetime(2026, 11, 2, 10, 0))
    monkeypatch.setattr(services, "local_now", lambda: timezone.localtime(now))
    tennis_9 = slot_of("Теннис", 3, 17, 8)
    for day in (1, 8, 15, 22, 29):
        SectionMark.objects.create(student=junior, slot=tennis_9, date=dt.date(2026, 10, day), method="qr")
    api = login(people["director_sport"])
    assert set(_ids(api.get("/api/sport/roster/?month=2026-10&below=1").json())) == {senior.pk}
    assert set(_ids(api.get("/api/sport/roster/?month=2026-10&never=1").json())) == {senior.pk}
    row = next(r for r in api.get("/api/sport/roster/?month=2026-10").json()["rows"] if r["student"]["id"] == junior.pk)
    assert row["enrollments"][0]["percent"] == 100 and row["last_mark"]["date"] == "2026-10-29"


def test_export_is_what_the_filters_show(people, roster):
    api = login(people["director_sport"])
    body = api.get("/api/sport/roster/export/?several=1&preview=1").json()
    sheet = body["sheets"][0]
    # строка на запись: у Абдрахмана — две
    assert len(sheet["rows"]) == 2


def test_bulk_assign_hour_reports_partial_refusal_then_applies(people, roster, tennis):
    senior, junior, third = roster
    api = login(people["director_sport"])
    outsider = Student.objects.create(last_name="Шахматов", first_name="Нұр", group=senior.group, graduation_year=2028)
    services.enroll(student=outsider, slot=slot_of("Шахматы", 4, 17, 10), actor=None, by_director=True)
    payload = {
        "action": "assign_hour",
        "students": [senior.pk, junior.pk, third.pk, outsider.pk],
        "slot": slot_of("Теннис", 5, 13, 10).pk,
    }
    preview = api.post("/api/sport/roster/bulk/", payload, format="json").json()
    assert preview["ok"] == 1 and preview["failed"] == 3 and preview["applied"] is False
    reasons = {row["student"]["id"]: row["reason"] for row in preview["rows"]}
    assert reasons[third.pk] == ""
    assert "уже назначен" in reasons[senior.pk] and "уже назначен" in reasons[junior.pk]
    assert "Не записан" in reasons[outsider.pk]
    # итог ничего не записал
    assert SectionEnrollment.objects.get(student=third, ended_at__isnull=True).slot_id is None
    done = api.post("/api/sport/roster/bulk/", {**payload, "apply": True}, format="json").json()
    assert done["ok"] == 1 and done["applied"] is True
    row = SectionEnrollment.objects.get(student=third, ended_at__isnull=True)
    assert row.slot.starts == dt.time(13, 0) and row.slot_set_by == people["director_sport"]
    event = AuditLog.objects.filter(student_id=third.pk, field_name=services.EVENT).latest("created_at")
    assert event.actor == people["director_sport"]


def test_bulk_move_counts_the_hour_limit_as_it_goes(people, roster, tennis):
    senior, _junior, third = roster
    target = slot_of("Теннис", 5, 14, 10)
    type(target).objects.filter(pk=target.pk).update(capacity=1)
    api = login(people["director_sport"])
    preview = api.post(
        "/api/sport/roster/bulk/",
        {"action": "move_hour", "students": [senior.pk, third.pk], "slot": target.pk},
        format="json",
    ).json()
    assert preview["ok"] == 2
    # первому место есть, второму — сверх лимита: предупреждение, а не отказ
    assert [bool(row["warnings"]) for row in preview["rows"]] == [False, True]


def test_bulk_remove_closes_only_that_section(people, roster, tennis):
    senior, junior, _third = roster
    api = login(people["director_sport"])
    done = api.post(
        "/api/sport/roster/bulk/",
        {"action": "remove", "students": [senior.pk, junior.pk], "section": tennis.pk, "apply": True},
        format="json",
    ).json()
    assert done["ok"] == 2
    assert [r.section.title for r in services.active_list(senior)] == ["Шахматы"]
    assert services.active_list(junior) == []


@pytest.mark.parametrize("role", ["director_exam", "curator", "teacher"])
def test_strangers_have_no_roster(people, roster, role):
    senior, _junior, _third = roster
    api = login(people[role])
    for path in ("/api/sport/roster/", "/api/sport/roster/export/", f"/api/sport/roster/{senior.pk}/history/"):
        assert api.get(path).status_code in (403, 404)
    answer = api.post("/api/sport/roster/bulk/", {"action": "remove", "students": [senior.pk], "section": 1})
    assert answer.status_code in (403, 404)


def test_student_has_no_roster(roster):
    senior, _junior, _third = roster
    assert login(senior.user).get("/api/sport/roster/").status_code in (403, 404)


def test_admin_runs_the_roster_like_the_director(people, roster):
    body = login(people["admin"]).get("/api/sport/roster/").json()
    assert body["total"] == 3
