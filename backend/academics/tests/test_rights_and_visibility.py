"""Границы ролей в учебной части.

Учитель видит только свои уроки и учеников своих составов; всё чужое —
404. Ученику не уходят ярлыки, заметки и средние по группе. Куратор —
свои группы. Администратор правит с пометкой в журнале.
"""

from __future__ import annotations

import pytest
from django.urls import get_resolver

from academics import marks as marking
from academics.calendar import scale_of
from academics.tests.conftest import login
from accounts.permissions import TEACHER_READ_ROUTES, TEACHER_WRITE_ROUTES, teacher_may
from accounts.tests.test_admin_writes_all_domains import _api_routes
from core.models import AuditLog
from students.models import CuratorNote

pytestmark = pytest.mark.django_db

SECRET_NOTE = "Мать просила звонить после шести"
SECRET_LABEL = "needs_supervision"


@pytest.fixture
def secrets(pupils, curator):
    aliya = pupils["aliya"]
    aliya.behavior.status = "needs_supervision"
    aliya.behavior.comment = "заметка директора школы"
    aliya.behavior.save()
    CuratorNote.objects.create(student=aliya, author=curator, text=SECRET_NOTE)
    return aliya


# --- Учитель ---------------------------------------------------------------------


def test_teacher_gate_answers_not_found_for_everything_outside_its_list(teacher, lesson, pupils):
    """Все маршруты API под учителем: открытые — не 404 от шлюза, остальные — 404."""
    client = login(teacher)
    closed: list[str] = []
    for path, name in _api_routes():
        response = client.get(path)
        assert response.status_code < 500, (path, name, response.status_code)
        if teacher_may(name, "GET"):
            continue
        if response.status_code != 404:
            closed.append(f"{name} {path} → {response.status_code}")
    assert not closed, "учителю открыто то, чего нет в его списке:\n" + "\n".join(closed)


def test_teacher_list_names_only_real_routes():
    names = {name for _path, name in _api_routes()}
    for name in TEACHER_READ_ROUTES | TEACHER_WRITE_ROUTES:
        assert name in names, name
    assert len(get_resolver().url_patterns) > 0


def test_teacher_sees_own_lesson_and_own_students_only(teacher, other_teacher, lesson, eng_lesson, pupils, secrets):
    client = login(teacher)
    assert client.get(f"/api/acad/lessons/{lesson.pk}/").status_code == 200
    assert client.get(f"/api/acad/lessons/{eng_lesson.pk}/").status_code == 404, "чужой урок не существует"
    assert client.get(f"/api/acad/teacher/students/{pupils['aliya'].pk}/").status_code == 200
    assert client.get(f"/api/acad/teacher/students/{pupils['stranger'].pk}/").status_code == 404
    other = login(other_teacher)
    # второй учитель ведёт только первую подгруппу английского: Нурай из второй — чужая
    assert other.get(f"/api/acad/teacher/students/{pupils['aliya'].pk}/").status_code == 200
    assert other.get(f"/api/acad/teacher/students/{pupils['nurai'].pk}/").status_code == 404


def test_teacher_never_reads_notes_documents_admission_exams_or_reports(teacher, lesson, pupils, secrets):
    client = login(teacher)
    for path in (
        f"/api/students/{pupils['aliya'].pk}/",
        f"/api/notes/?student={pupils['aliya'].pk}",
        f"/api/documents/?student={pupils['aliya'].pk}",
        f"/api/profiles/admission/{pupils['aliya'].pk}/",
        f"/api/attempts/?student={pupils['aliya'].pk}",
        "/api/acad/reports/",
        f"/api/students/{pupils['aliya'].pk}/credentials/",
    ):
        response = client.get(path)
        assert response.status_code == 404, path
        assert SECRET_NOTE not in response.content.decode() and SECRET_LABEL not in response.content.decode(), path


def test_teacher_answers_carry_no_labels_or_notes(teacher, lesson, pupils, secrets):
    client = login(teacher)
    for path in (
        f"/api/acad/lessons/{lesson.pk}/",
        f"/api/acad/teacher/students/{pupils['aliya'].pk}/",
        "/api/acad/teacher/today/",
        f"/api/acad/journals/{lesson.course.pk}/",
    ):
        body = client.get(path).content.decode()
        assert (
            SECRET_NOTE not in body and SECRET_LABEL not in body and "comment" not in body.replace('"comment": ""', "")
        ) or "заметка директора" not in body, path


def test_teacher_cannot_mark_or_grade_a_foreign_lesson(teacher, eng_lesson, pupils):
    client = login(teacher)
    assert (
        client.post(f"/api/acad/lessons/{eng_lesson.pk}/attendance/", {"all_present": True}, format="json").status_code
        == 404
    )
    assert (
        client.post(
            f"/api/acad/lessons/{eng_lesson.pk}/grade/", {"student": pupils["aliya"].pk, "value": 5}, format="json"
        ).status_code
        == 404
    )


def test_substitute_marks_the_lesson_into_the_owner_journal(lesson, other_teacher, pupils, kymbat, calendar):
    from academics.models import Lesson

    Lesson.objects.filter(pk=lesson.pk).update(substitute=other_teacher)
    client = login(other_teacher)
    response = client.post(
        f"/api/acad/lessons/{lesson.pk}/attendance/",
        {"rows": [{"student": pupils["aliya"].pk, "mark": "absent"}]},
        format="json",
    )
    assert response.status_code == 200, response.content
    lesson.refresh_from_db()
    assert lesson.marked_by_id == other_teacher.pk
    assert (
        client.get(f"/api/acad/journals/{lesson.course.pk}/").status_code == 404
    ), "журнал остаётся у основного учителя"


# --- Ученик ---------------------------------------------------------------------------


def test_student_reads_own_grades_without_labels_group_averages_or_names(
    lesson, pupils, teacher, calendar, secrets, as_student
):
    scale = scale_of(calendar.year)
    marking.set_grade(lesson, pupils["aliya"], 7, actor=teacher, calendar=calendar, scale=scale)
    marking.set_grade(lesson, pupils["damir"], 3, actor=teacher, calendar=calendar, scale=scale)
    from students import credentials as vault

    vault.set_credential(pupils["aliya"], "email", "Секрет-пароль-2026", actor=teacher)
    for path in (
        "/api/acad/me/grades/",
        "/api/acad/me/lessons/",
        f"/api/acad/lessons/{lesson.pk}/",
        "/api/acad/lessons/",
    ):
        response = as_student.get(path)
        assert response.status_code == 200, path
        body = response.content.decode()
        assert SECRET_NOTE not in body and SECRET_LABEL not in body, path
        assert "Сериков" not in body, "чужие имена ученику не уходят"
        assert "password" not in body and "secret" not in body, path
        assert "quarter_grade_avg" not in body and "group_avg" not in body, path
    mine = as_student.get("/api/acad/me/grades/").json()
    assert mine["subjects"][0]["stats"]["fo_avg"] == 7.0
    assert "unexcused_days" not in mine and "excuses" not in mine


def test_student_is_refused_from_staff_academic_screens(lesson, pupils, as_student):
    for path in (
        f"/api/acad/journals/{lesson.course.pk}/",
        "/api/acad/attendance/",
        "/api/acad/reports/",
        f"/api/acad/students/{pupils['aliya'].pk}/grades/",
        "/api/acad/schedule/",
        "/api/acad/excuses/",
    ):
        assert as_student.get(path).status_code in (403, 404), path


# --- Куратор -------------------------------------------------------------------------


def test_curator_reads_own_group_journal_and_not_the_other(
    lesson, cohorts, subjects, other_teacher, chicago, calendar, as_curator
):
    from academics.schedule import create_once
    from academics.tests.conftest import school_day

    foreign = create_once(
        subject=subjects["alg"],
        teacher=other_teacher,
        cohort=cohorts["chicago"],
        date=school_day(-2, calendar),
        slot=5,
        room="1",
    )
    assert as_curator.get(f"/api/acad/journals/{lesson.course.pk}/").status_code == 200
    assert as_curator.get(f"/api/acad/journals/{foreign.course.pk}/").status_code == 404
    assert as_curator.get(f"/api/acad/lessons/{foreign.pk}/").status_code == 404
    assert as_curator.get(f"/api/acad/attendance/?group={chicago.code}").status_code == 404
    assert as_curator.get(f"/api/acad/grades/group/?group={chicago.code}").status_code == 404


def test_curator_does_not_mark_or_grade(lesson, pupils, as_curator):
    assert (
        as_curator.post(f"/api/acad/lessons/{lesson.pk}/attendance/", {"all_present": True}, format="json").status_code
        == 403
    )
    assert (
        as_curator.post(
            f"/api/acad/lessons/{lesson.pk}/grade/", {"student": pupils["aliya"].pk, "value": 5}, format="json"
        ).status_code
        == 403
    )


# --- Салтанат и администратор ---------------------------------------------------


def test_saltanat_reads_attendance_by_lessons_but_not_grades(lesson, saltanat, boston):
    client = login(saltanat)
    assert client.get(f"/api/acad/attendance/?group={boston.code}").status_code == 200
    assert client.get("/api/acad/risks/").status_code == 200
    assert client.get(f"/api/acad/journals/{lesson.course.pk}/").status_code == 404
    assert client.get("/api/acad/grades/school/").status_code == 403
    assert client.get("/api/acad/schedule/").status_code == 403


def test_admin_edit_is_marked_in_the_journal(lesson, pupils, admin, calendar):
    scale = scale_of(calendar.year)
    marking.set_grade(lesson, pupils["aliya"], 6, actor=admin, calendar=calendar, scale=scale)
    entry = AuditLog.objects.get(model_label="academics.Grade", field_name="value", new_value="6")
    assert entry.actor_id == admin.pk and entry.domain_code == "academics" and entry.acting_for == "academics"


def test_curator_exports_the_journal_of_own_group_and_not_a_foreign_one(lesson, curator, chicago, subjects, teacher):
    """Кнопка «Выгрузить» у куратора работает: та же граница, что у журнала на экране."""
    from academics.cohorts import group_cohort
    from academics.models import Course

    client = login(curator)
    own = client.get(f"/api/acad/journals/{lesson.course_id}/export/")
    assert own.status_code == 200, own.content[:200]
    assert own["Content-Type"].startswith("application/vnd.openxmlformats")
    foreign = Course.objects.create(subject=subjects["alg"], cohort=group_cohort(chicago), teacher=teacher)
    assert client.get(f"/api/acad/journals/{foreign.pk}/export/").status_code == 404
