"""Перевод на следующий год: предпросмотр, выпуск в архив, запрет повтора.

8→9, 9→10, 10→11 — та же группа, параллель растёт, у новых 11 появляется
поступление. 11 — выпуск: ученики и группа в архиве, вход закрыт, данные
на месте. Второй перевод в том же учебном году — отказ.
"""

from __future__ import annotations

import datetime as dt

import pytest
from rest_framework.test import APIClient

from accounts.models import CuratorAssignment, Role, User
from core.models import AuditLog
from core.parallels import has_admission
from students.enrollment import _make_profiles
from students.models import Student, StudyGroup, YearTransfer
from students.year_transfer import school_year


def test_school_year_runs_september_to_august():
    assert school_year(dt.date(2027, 6, 15)) == "2026/2027"
    assert school_year(dt.date(2027, 8, 31)) == "2026/2027"
    assert school_year(dt.date(2027, 9, 1)) == "2027/2028"


@pytest.fixture
def school(db, make_user):
    groups = {
        parallel: StudyGroup.objects.create(code=code, parallel=parallel)
        for parallel, code in ((8, "OSLO"), (9, "LISBON"), (10, "PRAGUE"), (11, "CHICAGO"))
    }
    students = {}
    for parallel, group in groups.items():
        user = make_user(Role.STUDENT, f"p{parallel}@example.kz")
        student = Student.objects.create(
            last_name=f"Ученик{parallel}",
            first_name="Тест",
            email=user.email,
            group=group,
            graduation_year=2027,
            user=user,
        )
        _make_profiles(student)
        students[parallel] = student
    return {"groups": groups, "students": students}


def admin_client(make_user) -> tuple[APIClient, User]:
    admin = make_user(Role.ADMIN, "admin.transfer@example.kz", full_name="Администратор Школы")
    api = APIClient()
    api.force_login(admin)
    return api, admin


def test_preview_then_transfer_then_refuse_the_second(school, make_user):
    api, admin = admin_client(make_user)
    curator = make_user(Role.CURATOR, "curator.transfer@example.kz")
    CuratorAssignment.objects.create(curator=curator, group=school["groups"][11], since=dt.date(2026, 9, 1))

    plan = api.get("/api/year-transfer/").json()
    assert plan["done"] is None
    assert plan["students_moved"] == 3 and plan["students_graduated"] == 1
    assert plan["confirm"] == "4"
    assert [row["to"] for row in plan["moves"]] == [None, 11, 10, 9]

    # без набранного числа — отказ, ничего не тронуто
    assert api.post("/api/year-transfer/", {"confirm": "3"}, format="json").status_code == 400
    assert not YearTransfer.objects.exists()

    done = api.post("/api/year-transfer/", {"confirm": "4"}, format="json")
    assert done.status_code == 200, done.content
    body = done.json()
    assert body["students_moved"] == 3 and body["students_graduated"] == 1

    # параллели выросли, год выпуска прежний, у бывших 10 появилось поступление
    for parallel, code in ((9, "OSLO"), (10, "LISBON"), (11, "PRAGUE")):
        assert StudyGroup.objects.get(code=code).parallel == parallel
    prague = Student.objects.get(pk=school["students"][10].pk)
    assert has_admission(prague)
    assert prague.graduation_year == 2027

    # выпускники: в архиве, вход закрыт, данные на месте
    graduate = Student.all_objects.get(pk=school["students"][11].pk)
    assert graduate.archived_at is not None
    assert StudyGroup.all_objects.get(code="CHICAGO").archived_at is not None
    assert not Student.objects.filter(pk=graduate.pk).exists()
    assert User.objects.get(pk=graduate.user_id).is_active is False
    assert graduate.admission.pk  # профили остались в базе
    assert not CuratorAssignment.objects.filter(group__code="CHICAGO", until__isnull=True).exists()
    login = APIClient().post("/api/auth/login/", {"login": "p11@example.kz", "password": "pass12345"}, format="json")
    assert login.status_code in (401, 403)

    # город выпускной группы свободен для новой восьмой
    assert api.post("/api/groups/", {"code": "CHICAGO", "parallel": 8}, format="json").status_code == 201

    # журнал: событие у каждого ученика и сводка школы
    assert AuditLog.objects.filter(field_name="year_transfer", student_id=graduate.pk).exists()
    assert AuditLog.objects.filter(field_name="year_transfer", model_label="students.StudyGroup", actor=admin).exists()

    again = api.get("/api/year-transfer/").json()
    assert again["done"] is not None
    refused = api.post("/api/year-transfer/", {"confirm": again["confirm"]}, format="json")
    assert refused.status_code == 400
    assert "уже выполнен" in refused.json()["detail"]
    assert StudyGroup.objects.get(code="PRAGUE").parallel == 11


def test_only_the_admin_transfers(school, make_user):
    for role in (Role.DIRECTOR_EXAM, Role.CURATOR, Role.DIRECTOR_BEHAVIOR):
        api = APIClient()
        api.force_login(make_user(role, f"{role}.transfer@example.kz"))
        assert api.get("/api/year-transfer/").status_code == 403
        assert api.post("/api/year-transfer/", {"confirm": "4"}, format="json").status_code == 403


def test_archived_student_loses_the_session(school):
    """Вход закрыт для любого ученика в архиве — не только выпускника."""
    from core.archive import archive

    student = school["students"][9]
    api = APIClient()
    api.force_login(student.user)
    assert api.get("/api/auth/me/").status_code == 200
    archive(student)
    assert api.get("/api/auth/me/").status_code in (401, 403)
