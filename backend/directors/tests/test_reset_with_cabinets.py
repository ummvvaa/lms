"""Полное обнуление на базе с записями кабинетов директоров (24.10.2026).

Олимпиада держит предмет, мероприятие — вид спорта ссылкой PROTECT: `reset_data --all`
падал на справочниках (`ProtectedError`), и за ним не запускался весь прогон.
"""

from __future__ import annotations

import datetime as dt
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from directories.models import OlympiadSubject, SportType
from directors import services
from directors.models import LessonRelease, Olympiad, ParentCall, SportApplication, SportEvent, StaffTask
from students.models import Student

pytestmark = pytest.mark.django_db


def test_reset_all_goes_through_olympiads_and_events(settings, student, make_user):
    settings.DEBUG = True
    arman = make_user("director_talent", "arman.reset@example.kz")
    kymbat = make_user("director_exam", "kymbat.reset@example.kz")
    teacher = make_user("teacher", "teacher.reset@example.kz")
    today = timezone.localdate()
    olympiad = Olympiad.objects.create(
        title="Городская",
        subject=OlympiadSubject.objects.create(name="Математика"),
        level="city",
        starts=today,
        ends=today,
    )
    services.add_entries(olympiad, [student])
    services.set_result(olympiad.entries.get(), "prize", actor=arman)
    services.release(
        students=[student], starts=today, ends=today, slot_from=None, slot_to=None, olympiad=olympiad, actor=arman
    )
    event = SportEvent.objects.create(
        title="Кубок",
        kind="competition",
        sport_type=SportType.objects.create(name="Волейбол"),
        starts_at=timezone.now() + dt.timedelta(days=2),
        place="Спортзал",
    )
    services.apply(event=event, student=student, kind="play")
    services.record_call(student=student, outcome="reached", actor=arman)
    services.set_task(title="Журналы", due=today, assignee=teacher, actor=kymbat)

    call_command("reset_data", "--all", confirm="УДАЛИТЬ ДАННЫЕ", stdout=StringIO())

    assert Student.all_objects.count() == 0
    for model in (Olympiad, LessonRelease, SportEvent, ParentCall, StaffTask):
        assert model.all_objects.count() == 0, model.__name__
    assert SportApplication.objects.count() == 0
    assert OlympiadSubject.objects.count() == 0 and SportType.objects.count() == 0
