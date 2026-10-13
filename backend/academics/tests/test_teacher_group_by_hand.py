"""Группа учителю по предмету руками, без импорта (решение владельца, 13.10.2026).

В карточке учителя у предмета без журналов — «Добавить группу»: журнала
нет — заводится пустой, уроки придут с расписанием; журнал без учителя —
назначается; журнал другого учителя — передаётся с даты, как «Сменить
учителя». Предмет журнала дописывается в предметы учителя.
"""

from __future__ import annotations

import pytest

from academics.models import Course, Lesson, TeacherProfile
from academics.schedule import create_once
from academics.tests.conftest import login, school_day
from accounts.models import Role

pytestmark = pytest.mark.django_db


@pytest.fixture
def newcomer(make_user, subjects):
    """Учитель с предметом в карточке и без единого журнала."""
    user = make_user(Role.TEACHER, "newcomer.acad@example.kz", full_name="Динмухаммед Новый")
    TeacherProfile.objects.create(user=user, room="102").subjects.set([subjects["alg"]])
    return user


def test_options_list_groups_with_cohorts_and_who_keeps_the_journal(
    newcomer, teacher, lesson, cohorts, subjects, kymbat
):
    response = login(kymbat).get(f"/api/acad/teachers/{newcomer.pk}/courses/?subject={subjects['eng'].pk}")
    assert response.status_code == 200
    boston = next(g for g in response.json()["groups"] if g["code"] == "BOSTON")
    names = [c["name"] for c in boston["cohorts"]]
    assert names[0] == "BOSTON" and cohorts["eng1"].name in names and cohorts["eng2"].name in names
    # по алгебре вся BOSTON уже у Гульнары — окно покажет, кто ведёт
    response = login(kymbat).get(f"/api/acad/teachers/{newcomer.pk}/courses/?subject={subjects['alg'].pk}")
    boston = next(g for g in response.json()["groups"] if g["code"] == "BOSTON")
    whole = boston["cohorts"][0]
    assert whole["course"]["teacher"] == "Сапарова Гульнара" and whole["course"]["mine"] is False


def test_new_journal_is_created_empty_and_the_subject_lands_in_the_profile(newcomer, cohorts, subjects, kymbat):
    client = login(kymbat)
    response = client.post(
        f"/api/acad/teachers/{newcomer.pk}/courses/",
        {"subject": subjects["eng"].pk, "cohort": cohorts["chicago"].pk},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["transferred"] is False
    course = Course.objects.get(subject=subjects["eng"], cohort=cohorts["chicago"])
    assert course.teacher == newcomer and not Lesson.objects.filter(course=course).exists()
    assert newcomer.teacher_profile.subjects.filter(pk=subjects["eng"].pk).exists()
    # журнал виден в карточке учителя, второй раз — отказ словами
    detail = client.get(f"/api/acad/teachers/{newcomer.pk}/").json()
    assert [c["id"] for c in detail["courses"]] == [course.pk]
    response = client.post(
        f"/api/acad/teachers/{newcomer.pk}/courses/",
        {"subject": subjects["eng"].pk, "cohort": cohorts["chicago"].pk},
        format="json",
    )
    assert response.status_code == 400 and "уже ведёт" in response.json()["detail"]


def test_journal_of_another_teacher_is_transferred_from_the_date(
    newcomer, teacher, lesson, cohorts, subjects, calendar, admin
):
    future = create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(3, calendar),
        slot=1,
        room="204",
    )
    response = login(admin).post(
        f"/api/acad/teachers/{newcomer.pk}/courses/",
        {"subject": subjects["alg"].pk, "cohort": cohorts["boston"].pk, "since": school_day(1, calendar).isoformat()},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["transferred"] is True
    course = Course.objects.get(subject=subjects["alg"], cohort=cohorts["boston"])
    assert course.teacher == newcomer
    lesson.refresh_from_db()
    future.refresh_from_db()
    assert lesson.teacher == teacher and future.teacher == newcomer


def test_refusals(newcomer, teacher, cohorts, subjects, kymbat, curator):
    client = login(kymbat)
    base = f"/api/acad/teachers/{newcomer.pk}/courses/"
    assert client.post(base, {"subject": 0, "cohort": cohorts["boston"].pk}, format="json").status_code == 400
    assert client.post(base, {"subject": subjects["alg"].pk, "cohort": 0}, format="json").status_code == 400
    # подгруппа английского — не состав для алгебры
    assert (
        client.post(base, {"subject": subjects["alg"].pk, "cohort": cohorts["eng1"].pk}, format="json").status_code
        == 400
    )
    assert client.get(f"/api/acad/teachers/0/courses/?subject={subjects['alg'].pk}").status_code == 404
    assert login(curator).get(f"{base}?subject={subjects['alg'].pk}").status_code in (403, 404)
    assert login(teacher).post(
        base, {"subject": subjects["alg"].pk, "cohort": cohorts["boston"].pk}, format="json"
    ).status_code in (403, 404)
