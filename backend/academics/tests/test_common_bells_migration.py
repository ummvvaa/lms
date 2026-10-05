"""Миграция разбирает запись «Общее» по данным (решение владельца, 05.10.2026).

Группы, жившие по общим звонкам, получают их своим расписанием — время их
уроков не меняется; если по «Общему» не жила ни одна группа, оно удаляется.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("academics", "0008_subject_title_en")]
AFTER = [("academics", "0009_no_common_bells")]


# Схема ходит назад и вперёд внутри транзакции теста (в PostgreSQL изменение
# таблиц откатывается вместе с данными): после теста база та же, что до него,
# и строки, посеянные миграциями других приложений, целы.
pytestmark = pytest.mark.django_db


@pytest.fixture
def old_schema(db):
    """База на шаг раньше миграции — до конца теста."""
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    return executor.loader.project_state(BEFORE).apps


def _forward():
    # строки теста проверяются сейчас, как при обычном сохранении: миграция
    # начинает с базы без отложенных проверок, как на бою
    connection.check_constraints()
    executor = MigrationExecutor(connection)
    executor.migrate(AFTER)
    return executor.loader.project_state(AFTER).apps


def _school(apps, *, own_for: tuple[str, ...]):
    """Год с «Общим» и расписанием «Звонки 11»; `own_for` — группы со своими звонками."""
    Year = apps.get_model("academics", "AcademicYear")
    BellSchedule = apps.get_model("academics", "BellSchedule")
    Bell = apps.get_model("academics", "Bell")
    StudyGroup = apps.get_model("students", "StudyGroup")
    year = Year.objects.create(
        title="2026–2027", starts=dt.date(2026, 9, 1), ends=dt.date(2027, 5, 25), is_current=True
    )
    common = BellSchedule.objects.create(year=year, title="Общее", is_default=True)
    own = BellSchedule.objects.create(year=year, title="Звонки 11")
    Bell.objects.create(year=year, schedule=common, number=1, starts=dt.time(8, 30), ends=dt.time(9, 15))
    Bell.objects.create(year=year, schedule=own, number=1, starts=dt.time(10, 15), ends=dt.time(10, 55))
    # звонок без расписания — остаток времён одной сетки на год
    Bell.objects.create(year=year, schedule=None, number=2, starts=dt.time(9, 25), ends=dt.time(10, 10))
    for code in ("KIOTO", "тест", "АРХИВ"):
        group = StudyGroup.objects.create(code=code, parallel=11, is_active=code != "АРХИВ")
        if code in own_for:
            own.groups.add(group)
    return year


def test_groups_that_lived_by_the_common_bells_keep_them_as_their_own(old_schema):
    _school(old_schema, own_for=("KIOTO",))
    apps = _forward()
    BellSchedule = apps.get_model("academics", "BellSchedule")
    common = BellSchedule.objects.get(title="Общее")
    # «тест» жила по общим звонкам — они стали её расписанием; неактивная группа не назначена
    assert sorted(common.groups.values_list("code", flat=True)) == ["тест"]
    assert sorted(common.bells.values_list("number", flat=True)) == [1, 2]
    assert sorted(BellSchedule.objects.get(title="Звонки 11").groups.values_list("code", flat=True)) == ["KIOTO"]
    assert not hasattr(common, "is_default")


def test_common_bells_nobody_lived_by_are_deleted(old_schema):
    _school(old_schema, own_for=("KIOTO", "тест"))
    apps = _forward()
    BellSchedule = apps.get_model("academics", "BellSchedule")
    Bell = apps.get_model("academics", "Bell")
    assert list(BellSchedule.objects.values_list("title", flat=True)) == ["Звонки 11"]
    assert Bell.objects.count() == 1 and Bell.objects.filter(schedule__isnull=True).count() == 0
