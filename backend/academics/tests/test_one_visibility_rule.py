"""Одно правило видимости на всю платформу и на помощника (решение владельца, 30.09.2026).

Руководители — администратор и пять директоров — видят всю школу, куратор —
свои группы, учитель — учеников своих составов и состав урока на замене
только в день урока. Кнопки помощника берут границу из той же функции,
что и экраны: `core.scope`.
"""

from __future__ import annotations

import pytest

from academics.schedule import create_once, substitute
from academics.tests.conftest import days, login, make_student, school_day
from accounts.models import Role
from core.scope import visible_ids, visible_students
from students.models import AdmissionProfile, StudyGroup

pytestmark = pytest.mark.django_db

LEADERS = (
    Role.ADMIN,
    Role.DIRECTOR_BEHAVIOR,
    Role.DIRECTOR_ADMISSION,
    Role.DIRECTOR_EXAM,
    Role.DIRECTOR_TALENT,
    Role.DIRECTOR_SPORT,
)


@pytest.fixture
def junior(db):
    """Ученик 9 класса: у руководителей он есть, в поступлении — нет."""
    group = StudyGroup.objects.create(code="LISBON", parallel=9)
    return make_student(group, "Девятиклассов", "Ерлан", "junior.scope@example.kz")


def ask(user, **body) -> str:
    answer = login(user).post("/api/assistant/ask/", body, format="json").json()
    return "\n".join([answer["message"]["text"], *answer["message"]["lines"]])


@pytest.mark.parametrize("role", LEADERS)
def test_leaders_see_the_whole_school(role, make_user, pupils, junior):
    leader = make_user(role, f"{role}.scope@example.kz")
    everyone = {*[s.pk for s in pupils.values()], junior.pk}
    assert set(visible_students(leader).values_list("id", flat=True)) == everyone
    assert set(visible_ids(leader)) == everyone
    assert login(leader).get(f"/api/students/{junior.pk}/").status_code == 200


def test_curator_sees_only_own_groups(curator, as_curator, pupils, junior):
    own = {pupils[name].pk for name in ("aliya", "damir", "nurai")}
    assert set(visible_ids(curator)) == own
    assert as_curator.get(f"/api/students/{pupils['stranger'].pk}/").status_code == 404
    assert as_curator.get(f"/api/students/{junior.pk}/").status_code == 404
    rows = as_curator.get("/api/students/").json()
    rows = rows["results"] if isinstance(rows, dict) else rows
    assert {row["id"] for row in rows} == own


def test_teacher_sees_own_cohorts_and_a_substitution_only_on_its_day(
    teacher, other_teacher, as_teacher, marked_journal, pupils, subjects, cohorts, calendar
):
    own = {pupils[name].pk for name in ("aliya", "damir", "nurai")}
    stranger = pupils["stranger"].pk
    assert set(visible_ids(teacher)) == own
    assert as_teacher.get(f"/api/acad/teacher/students/{stranger}/").status_code == 404
    assert as_teacher.get(f"/api/acad/teacher/students/{pupils['aliya'].pk}/").status_code == 200

    # замена завтра: сегодня состав чужой группы учителю не виден
    tomorrow = create_once(
        subject=subjects["eng"],
        teacher=other_teacher,
        cohort=cohorts["chicago"],
        date=school_day(1, calendar),
        slot=9,
        room="305",
    )
    substitute(tomorrow, teacher=teacher, reason="курсы")
    assert stranger not in visible_ids(teacher)

    # замена сегодня: состав виден в день урока — иначе заменяющему нечего отмечать
    today = create_once(
        subject=subjects["eng"], teacher=other_teacher, cohort=cohorts["chicago"], date=days(0), slot=10, room="305"
    )
    substitute(today, teacher=teacher, reason="болеет")
    assert stranger in visible_ids(teacher)


def test_assistant_buttons_keep_the_same_border_for_every_role(
    admin, saltanat, curator, teacher, marked_journal, pupils
):
    """Дамир (BOSTON) и Чужестранцев (CHICAGO) не были на уроках: кто кого видит в кнопках."""
    for leader in (admin, saltanat):
        text = ask(leader, command="out_of_sight")
        assert "Сериков Дамир" in text and "Чужестранцев Ерлан" in text, leader.role
    curator_text = ask(curator, command="out_of_sight")
    assert "Сериков Дамир" in curator_text and "Чужестранцев" not in curator_text
    teacher_text = ask(teacher, command="lagging")
    assert "Сериков Дамир" in teacher_text and "Чужестранцев" not in teacher_text


def test_a_foreign_pick_does_not_widen_the_border(curator, marked_journal, pupils):
    """Экран прислал чужого ученика — кнопка его не видит, а своих — видит."""
    text = ask(curator, command="out_of_sight", students=[pupils["stranger"].pk])
    assert "Чужестранцев" not in text


def test_admission_buttons_count_only_graduates(make_user, pupils, junior):
    """Асем видит всех, но «без Common App» и сроки — только 11: граница домена."""
    AdmissionProfile.objects.filter(student__in=[pupils["aliya"], junior]).update(has_common_app=False)
    asem = make_user(Role.DIRECTOR_ADMISSION, "asem.scope@example.kz")
    text = ask(asem, command="no_common_app")
    assert "Ахметова Алия" in text
    assert "Девятиклассов" not in text
