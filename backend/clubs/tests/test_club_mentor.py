"""Кабинет ментора: только свой кружок и его ученики, задание с журналом, шлюз по всем маршрутам."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.permissions import MENTOR_READ_ROUTES, MENTOR_WRITE_ROUTES, mentor_may
from accounts.tests.test_admin_writes_all_domains import _api_routes
from clubs import services
from clubs.models import ClubHomework
from clubs.tests.conftest import login
from core.models import AuditLog
from core.scope import visible_students

pytestmark = pytest.mark.django_db


def test_mentor_gate_answers_not_found_for_everything_outside_its_list(mentor, pupils, lab):
    client = login(mentor)
    opened: list[str] = []
    for path, name in _api_routes():
        response = client.get(path)
        assert response.status_code < 500, (path, name, response.status_code)
        if mentor_may(name, "GET"):
            continue
        if response.status_code != 404:
            opened.append(f"{name} {path} → {response.status_code}")
    assert not opened, "ментору открыто то, чего нет в его списке:\n" + "\n".join(opened)


def test_mentor_list_names_only_real_routes():
    names = {name for _path, name in _api_routes()}
    for name in MENTOR_READ_ROUTES | MENTOR_WRITE_ROUTES:
        assert name in names, name


def test_mentor_sees_only_students_of_own_club(mentor, other_mentor, pupils, lab, robots):
    senior, junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    services.enroll(student=junior, club=robots, actor=None)
    assert list(visible_students(mentor)) == [senior]
    api = login(mentor)
    assert [c["title"] for c in api.get("/api/clubs/mine/").json()["clubs"]] == ["AI Startup Lab"]
    rows = api.get(f"/api/clubs/{lab.pk}/students/").json()["rows"]
    assert [r["student"]["full_name"] for r in rows] == [senior.full_name]
    assert rows[0]["student"]["group"] == "TOKYO" and rows[0]["enrolled_at"]
    assert api.get(f"/api/clubs/{robots.pk}/students/").status_code == 404, "чужой кружок не существует"
    assert api.get(f"/api/students/{junior.pk}/").status_code == 404
    services.leave(student=senior, club=lab, actor=None)
    assert not visible_students(mentor).exists(), "вышедший пропадает у ментора"


def test_admin_does_everything_the_mentor_does(people, pupils, lab):
    senior, _junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    api = login(people["admin"])
    assert api.get(f"/api/clubs/{lab.pk}/students/").status_code == 200
    made = api.post(f"/api/clubs/{lab.pk}/homework/", {"text": "Прототип", "due": "2026-11-09"})
    assert made.status_code == 201
    assert api.post(f"/api/clubs/{lab.pk}/notes/", {"student": senior.pk, "text": "ок"}).status_code == 201
    assert len(api.get("/api/clubs/mine/").json()["clubs"]) == 2


def test_homework_publish_edit_withdraw_is_journaled_and_reaches_students(mentor, pupils, lab):
    senior, junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    api = login(mentor)
    upload = SimpleUploadedFile("план.pdf", b"%PDF-1.4 test", content_type="application/pdf")
    made = api.post(
        f"/api/clubs/{lab.pk}/homework/", {"text": "Собрать прототип бота", "due": "2026-11-09", "file": upload}
    )
    assert made.status_code == 201, made.content
    hw = made.json()
    assert hw["has_file"] and hw["file_name"] == "план.pdf"
    card = next(c for c in login(senior.user).get("/api/my/clubs/").json()["clubs"] if c["id"] == lab.pk)
    assert [h["text"] for h in card["homework"]] == ["Собрать прототип бота"]
    # файл: ученик кружка — да, ученик не из кружка и чужой ментор — нет
    assert login(senior.user).get(f"/api/clubs/homework/{hw['id']}/file/").status_code == 200
    assert login(junior.user).get(f"/api/clubs/homework/{hw['id']}/file/").status_code == 404

    edited = api.patch(f"/api/clubs/{lab.pk}/homework/{hw['id']}/", {"due": "2026-11-12"}, format="json")
    assert edited.status_code == 200 and edited.json()["due"] == "2026-11-12"
    assert api.delete(f"/api/clubs/{lab.pk}/homework/{hw['id']}/").status_code == 204
    assert not ClubHomework.objects.filter(pk=hw["id"]).exists(), "снятое — в архиве"
    card = next(c for c in login(senior.user).get("/api/my/clubs/").json()["clubs"] if c["id"] == lab.pk)
    assert card["homework"] == []
    fields = list(
        AuditLog.objects.filter(model_label="clubs.ClubHomework", object_id=str(hw["id"]))
        .order_by("pk")
        .values_list("field_name", flat=True)
    )
    assert fields == ["published", "edited", "withdrawn"]


def test_homework_refuses_empty_text_and_strange_files(mentor, lab):
    api = login(mentor)
    assert api.post(f"/api/clubs/{lab.pk}/homework/", {"text": " ", "due": "2026-11-09"}).status_code == 400
    assert api.post(f"/api/clubs/{lab.pk}/homework/", {"text": "x"}).status_code == 400
    bad = SimpleUploadedFile("run.exe", b"MZ", content_type="application/octet-stream")
    assert (
        api.post(f"/api/clubs/{lab.pk}/homework/", {"text": "x", "due": "2026-11-09", "file": bad}).status_code == 400
    )


def test_other_mentor_cannot_touch_my_homework(mentor, other_mentor, lab):
    row = services.publish_homework(club=lab, text="Задание", due=dt.date(2026, 11, 9), actor=mentor)
    api = login(other_mentor)
    assert api.get(f"/api/clubs/{lab.pk}/homework/").status_code == 404
    assert api.delete(f"/api/clubs/{lab.pk}/homework/{row.pk}/").status_code == 404
    assert ClubHomework.objects.filter(pk=row.pk).exists()
