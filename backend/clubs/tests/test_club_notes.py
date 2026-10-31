"""Заметки ментора: видят только ментор этого кружка и администратор — больше никто и никогда."""

from __future__ import annotations

import pytest

from clubs import rights, services
from clubs.tests.conftest import login
from core.domains import ROLE_ADMIN, ROLE_MENTOR

pytestmark = pytest.mark.django_db

SECRET = "есть потенциал, сделал прототип"


@pytest.fixture
def noted(mentor, pupils, lab):
    senior, _junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    services.add_note(club=lab, student=senior, text=SECRET, actor=mentor)
    return senior


def test_readers_are_listed_in_one_place():
    assert rights.NOTE_READERS == (ROLE_MENTOR, ROLE_ADMIN)


def test_mentor_and_admin_read_notes(mentor, people, noted, lab):
    for user in (mentor, people["admin"]):
        rows = login(user).get(f"/api/clubs/{lab.pk}/notes/?student={noted.pk}").json()["rows"]
        assert [r["text"] for r in rows] == [SECRET]


def test_note_never_reaches_curator_directors_student_or_other_mentor(people, other_mentor, noted, lab):
    readers = [user for role, user in people.items() if role != "admin"] + [other_mentor, noted.user]
    for user in readers:
        api = login(user)
        assert api.get(f"/api/clubs/{lab.pk}/notes/").status_code in (403, 404), user.role
        for path in (
            f"/api/students/{noted.pk}/",
            f"/api/curator/students/{noted.pk}/",
            f"/api/clubs/students/{noted.pk}/",
            "/api/my/clubs/",
        ):
            assert SECRET not in api.get(path).content.decode(), (user.role, path)


def test_mentor_writes_notes_only_about_own_members(mentor, pupils, lab):
    _senior, junior = pupils
    api = login(mentor)
    assert api.post(f"/api/clubs/{lab.pk}/notes/", {"student": junior.pk, "text": "x"}).status_code == 404


def test_note_goes_to_archive_not_away(mentor, noted, lab):
    from clubs.models import ClubNote

    api = login(mentor)
    note_id = api.get(f"/api/clubs/{lab.pk}/notes/").json()["rows"][0]["id"]
    assert api.delete(f"/api/clubs/notes/{note_id}/").status_code == 204
    assert not ClubNote.objects.filter(pk=note_id).exists() and ClubNote.all_objects.filter(pk=note_id).exists()
