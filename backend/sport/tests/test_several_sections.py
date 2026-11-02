"""Несколько секций у ученика (02.11.2026): предел — правило школы, часы не пересекаются.

Границы, которые легко сломать тихо:
* запись в другую секцию прежнюю не закрывает, а в ту же — второй записи не даёт;
* два часа, совпадающие по дню и времени, не записать ни ученику, ни директору;
* предел из «Правил школы»: ученик упирается, директор проходит, подтвердив;
* выход и посещение — по каждой записи отдельно, QR засчитывается в секцию своего кода;
* перевод в другую секцию закрывает прежнюю запись и открывает новую одним шагом;
* кружок предупреждает о пересечении с любой из секций ученика.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from core import school_rules
from sport import services
from sport.models import EnrollmentSource, SectionEnrollment, SectionMark
from sport.tests.conftest import login, slot_of

pytestmark = pytest.mark.django_db


def _saturday_tennis():
    return slot_of("Теннис", 5, 12, 10)


def _friday_chess():
    return slot_of("Шахматы", 4, 17, 10)


def test_two_sections_at_different_hours(pupils, open_enroll):
    senior, _junior = pupils
    api = login(senior.user)
    assert api.post("/api/my/section/enroll/", {"slot": _saturday_tennis().pk}).status_code == 200
    body = api.post("/api/my/section/enroll/", {"slot": _friday_chess().pk}).json()
    assert [r["section_title"] for r in body["enrollments"]] == ["Теннис", "Шахматы"]
    assert SectionEnrollment.objects.filter(student=senior, ended_at__isnull=True).count() == 2
    # выход — из одной секции, вторая остаётся
    body = api.post("/api/my/section/leave/", {"section": _saturday_tennis().section_id}).json()
    assert [r["section_title"] for r in body["enrollments"]] == ["Шахматы"]
    # выйти, не сказав откуда, при двух записях нельзя — но при одной сервер понимает и так
    services.enroll(student=senior, slot=_saturday_tennis(), actor=None)
    assert api.post("/api/my/section/leave/").status_code == 400


def test_second_enrollment_in_same_section_is_refused_by_the_database(pupils):
    senior, _junior = pupils
    services.enroll(student=senior, slot=_saturday_tennis(), actor=None, by_director=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        SectionEnrollment.objects.create(
            student=senior, section=_saturday_tennis().section, slot=None, source=EnrollmentSource.DIRECTOR
        )
    # тот же путь через сервис — перевод часа, строка одна
    services.enroll(student=senior, slot=slot_of("Теннис", 5, 13, 10), actor=None, by_director=True)
    rows = SectionEnrollment.objects.filter(student=senior, ended_at__isnull=True)
    assert rows.count() == 1 and rows.get().slot.starts == dt.time(13, 0)


def test_overlapping_hours_are_refused_to_student_and_director(people, pupils, open_enroll):
    senior, _junior = pupils
    services.enroll(student=senior, slot=_saturday_tennis(), actor=None)
    # футбол в субботу 12:00 совпадает с теннисом минута в минуту
    football = slot_of("Футбол", 5, 12, 10)
    answer = login(senior.user).post("/api/my/section/enroll/", {"slot": football.pk})
    assert answer.status_code == 400 and "Теннис" in answer.json()["detail"]
    answer = login(people["director_sport"]).post(
        "/api/sport/enrollments/", {"student": senior.pk, "slot": football.pk, "force": True}, format="json"
    )
    assert answer.status_code == 400
    # час, касающийся границей, — не пересечение: 13:00–14:00 после 12:00–13:00
    volleyball = slot_of("Волейбол", 5, 13, 10)
    assert login(senior.user).post("/api/my/section/enroll/", {"slot": volleyball.pk}).status_code == 200
    # ученик видит, почему час закрыт
    body = login(senior.user).get("/api/my/section/").json()
    clash = next(s for sec in body["sections"] if sec["title"] == "Футбол" for s in sec["slots"])
    assert clash["clash"].startswith("Теннис")


def test_limit_from_school_rules_stops_student_and_warns_director(people, pupils, open_enroll):
    senior, _junior = pupils
    admin = people["admin"]
    school_rules.set_value(school_rules.SPORT_SECTIONS_MAX, 1, actor=admin)
    services.enroll(student=senior, slot=_saturday_tennis(), actor=None)
    answer = login(senior.user).post("/api/my/section/enroll/", {"slot": _friday_chess().pk})
    assert answer.status_code == 400
    director = login(people["director_sport"])
    payload = {"student": senior.pk, "slot": _friday_chess().pk}
    answer = director.post("/api/sport/enrollments/", payload, format="json")
    assert answer.status_code == 409 and answer.json()["warnings"]
    assert SectionEnrollment.objects.filter(student=senior, ended_at__isnull=True).count() == 1
    answer = director.post("/api/sport/enrollments/", {**payload, "force": True}, format="json")
    assert answer.status_code == 201
    assert SectionEnrollment.objects.filter(student=senior, ended_at__isnull=True).count() == 2
    # по умолчанию — две секции
    school_rules.reset(school_rules.SPORT_SECTIONS_MAX, actor=admin)
    assert services.sections_max() == 2


def test_transfer_to_other_section_closes_old_and_opens_new(people, pupils):
    senior, _junior = pupils
    row = services.enroll(student=senior, slot=_saturday_tennis(), actor=None, by_director=True)
    api = login(people["director_sport"])
    answer = api.patch(f"/api/sport/enrollments/{row.pk}/", {"slot": _friday_chess().pk}, format="json")
    assert answer.status_code == 200 and answer.json()["section_title"] == "Шахматы"
    row.refresh_from_db()
    assert row.ended_at is not None and row.ended_by == people["director_sport"]
    active = SectionEnrollment.objects.get(student=senior, ended_at__isnull=True)
    assert active.section.title == "Шахматы"


def test_failed_transfer_keeps_the_old_enrollment(people, pupils):
    senior, _junior = pupils
    tennis = services.enroll(student=senior, slot=_saturday_tennis(), actor=None, by_director=True)
    chess = services.enroll(student=senior, slot=_friday_chess(), actor=None, by_director=True)
    # шахматы → футбол в субботу 12:00 совпадают с теннисом: отказ, шахматы на месте
    api = login(people["director_sport"])
    answer = api.patch(f"/api/sport/enrollments/{chess.pk}/", {"slot": slot_of("Футбол", 5, 12, 10).pk}, format="json")
    assert answer.status_code == 400
    chess.refresh_from_db()
    tennis.refresh_from_db()
    assert chess.ended_at is None and tennis.ended_at is None


def test_percent_and_scan_go_by_each_enrollment(pupils, monkeypatch):
    senior, _junior = pupils
    tennis = _saturday_tennis()
    chess = _friday_chess()
    services.enroll(student=senior, slot=tennis, actor=None, by_director=True)
    services.enroll(student=senior, slot=chess, actor=None, by_director=True)
    SectionEnrollment.objects.filter(student=senior).update(
        enrolled_at=timezone.make_aware(dt.datetime(2026, 10, 1)),
        slot_set_at=timezone.make_aware(dt.datetime(2026, 10, 1)),
    )
    # шахматы идут в пятницу 30.10, 17:00 — отметка по коду шахмат идёт в шахматы
    during = timezone.make_aware(dt.datetime(2026, 10, 30, 17, 20))
    answer = services.mark_by_scan(student=senior, slot_id=chess.pk, day=during.date(), now=during)
    assert answer["state"] == "marked"
    assert SectionMark.objects.get(student=senior).slot_id == chess.pk
    rows = services.active_list(senior)
    after = timezone.make_aware(dt.datetime(2026, 11, 1, 9, 0))
    monkeypatch.setattr(services, "local_now", lambda: timezone.localtime(after))
    pct = services.month_percents(rows, "2026-10")
    by_section = {row.section.title: pct[row.pk] for row in rows}
    # шахматы: пять пятниц октября, одна отметка; теннис: пять суббот, ни одной
    assert by_section == {"Шахматы": 20, "Теннис": 0}


def test_curator_and_lists_see_every_section(people, pupils):
    senior, _junior = pupils
    services.enroll(student=senior, slot=_saturday_tennis(), actor=None, by_director=True)
    services.enroll(student=senior, slot=_friday_chess(), actor=None, by_director=True)
    curator = login(people["curator"])
    card = curator.get(f"/api/sport/students/{senior.pk}/section/").json()
    assert [r["section"] for r in card["rows"]] == ["Теннис", "Шахматы"]
    column = curator.get("/api/sport/students/sections/").json()["rows"][str(senior.pk)]
    assert [r["section"] for r in column] == ["Теннис", "Шахматы"]
    hits = login(people["director_sport"]).get("/api/sport/students/?q=Абдрахман").json()["rows"]
    assert [s["section_title"] for s in hits[0]["sections"]] == ["Теннис", "Шахматы"]


def test_club_overlap_checks_every_section_hour(pupils, make_user):
    from clubs import services as clubs
    from clubs.models import Club, ClubMeeting

    senior, _junior = pupils
    services.enroll(student=senior, slot=_saturday_tennis(), actor=None, by_director=True)
    services.enroll(student=senior, slot=_friday_chess(), actor=None, by_director=True)
    club = Club.objects.create(title="Дебаты", mentor_name="Ментор")
    ClubMeeting.objects.create(club=club, weekday=4, starts=dt.time(17, 30), ends=dt.time(18, 30))
    found = clubs.sport_overlaps(senior, club)
    assert len(found) == 1 and "Шахматы" in found[0]


def test_migration_keeps_every_enrollment_and_mark(pupils):
    """Миграция только снимает «одна запись на ученика» и добавляет флаг гостя: строки на месте."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    senior, junior = pupils
    services.enroll(student=senior, slot=_saturday_tennis(), actor=None, by_director=True)
    services.enroll(student=junior, slot=slot_of("Теннис", 3, 17, 8), actor=None, by_director=True)
    SectionMark.objects.create(student=senior, slot=_saturday_tennis(), date=dt.date(2026, 10, 31), method="qr")
    before = (SectionEnrollment.objects.count(), SectionMark.objects.count())
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    executor = MigrationExecutor(connection)
    executor.migrate([("sport", "0001_sections_and_tickets")])
    executor.loader.build_graph()
    executor.migrate([("sport", "0002_several_sections_and_guests")])
    assert (SectionEnrollment.objects.count(), SectionMark.objects.count()) == before
    assert SectionMark.objects.filter(is_guest=False).count() == before[1]
