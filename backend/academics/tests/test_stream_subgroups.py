"""Подгруппы потока в расписании: каждому — только свой английский.

Английский идёт подгруппами по уровню, собранными из нескольких групп
параллели (EEP-8-1 из четырёх групп). Пока у подгруппы не задан состав,
урок стоит в неделе каждой группы потока; с составом — только у групп,
чьи ученики в ней учатся, а ученику — только его подгруппа.
"""

from __future__ import annotations

import pytest

from academics import calendar as school_calendar
from academics.cohorts import make_stream
from academics.models import Cohort, CohortKind, CohortMembership
from academics.schedule import create_once
from academics.tests.conftest import days, login, school_day

pytestmark = pytest.mark.django_db


@pytest.fixture
def english(year, subjects, other_teacher, cohorts, pupils):
    """Поток BOSTON + CHICAGO и две подгруппы английского в одно время.

    В ENG-1 — Дамир из BOSTON, в ENG-2 — Ерлан из CHICAGO, ENG-3 пока пустая.
    """
    stream = make_stream(name="ENG", parts=[cohorts["boston"], cohorts["chicago"]])
    made = {}
    for name in ("ENG-1", "ENG-2", "ENG-3"):
        made[name] = Cohort.objects.create(kind=CohortKind.SUBGROUP, stream=stream, subject=subjects["eng"], name=name)
    CohortMembership.objects.create(cohort=made["ENG-1"], student=pupils["damir"], since=days(-60))
    CohortMembership.objects.create(cohort=made["ENG-2"], student=pupils["stranger"], since=days(-60))
    day = school_day(1, school_calendar.load(year))
    lessons = {
        name: create_once(
            subject=subjects["eng"], teacher=other_teacher, cohort=cohort, date=day, slot=3, room=f"30{i}"
        )
        for i, (name, cohort) in enumerate(made.items(), start=1)
    }
    return {"day": day, "lessons": lessons}


def _week(client, day, **params):
    response = client.get("/api/acad/schedule/", {"from": day.isoformat(), **params})
    assert response.status_code == 200, response.content
    return {row["cohort"]["name"] for row in response.json()["lessons"] if row["cohort"]["name"].startswith("ENG")}


def test_week_of_a_group_shows_only_subgroups_with_its_students(english, kymbat):
    client = login(kymbat)
    # пустая ENG-3 стоит у обеих групп: до загрузки состава урок не пропадает
    assert _week(client, english["day"], view="group", key="BOSTON") == {"ENG-1", "ENG-3"}
    assert _week(client, english["day"], view="group", key="CHICAGO") == {"ENG-2", "ENG-3"}


def test_student_sees_only_own_subgroup(english, pupils, make_user):
    from accounts.models import Role

    user = make_user(Role.STUDENT, "damir.stream@example.kz")
    pupils["damir"].user = user
    pupils["damir"].save(update_fields=["user"])
    day = english["day"]
    response = login(user).get("/api/acad/lessons/", {"from": day.isoformat(), "to": day.isoformat()})
    assert response.status_code == 200, response.content
    names = {row["cohort"]["name"] for row in response.json()["lessons"] if row["cohort"]["name"].startswith("ENG")}
    assert names == {"ENG-1"}


def test_curator_of_a_group_sees_only_its_subgroups(english, curator):
    day = english["day"]
    response = login(curator).get("/api/acad/lessons/", {"from": day.isoformat(), "to": day.isoformat()})
    assert response.status_code == 200, response.content
    names = {row["cohort"]["name"] for row in response.json()["lessons"] if row["cohort"]["name"].startswith("ENG")}
    assert names == {"ENG-1", "ENG-3"}
