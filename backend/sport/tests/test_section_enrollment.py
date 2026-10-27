"""Запись в секции: часы своей группы классов, лимит под блокировкой, одна секция на ученика.

Границы, которые легко сломать тихо:
* ученик видит только занятия своего класса и только свою запись;
* при закрытой записи выбора нет, но записанный без часа выбирает час своей секции;
* последнее место часа достаётся одному из двоих одновременно нажавших;
* выход закрывает запись, а не удаляет её: история остаётся, место освобождается;
* директор записывает и переводит и при закрытой записи; чужой директор, учитель и куратор — нет.
"""

from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections
from django.utils import timezone

from core.models import AuditLog
from sport import services
from sport.models import EnrollmentSource, Section, SectionEnrollment, SectionSlot
from sport.tests.conftest import login, slot_of
from students.models import Student

pytestmark = pytest.mark.django_db


def test_schedule_comes_with_the_migration():
    assert Section.objects.count() == 5
    assert SectionSlot.objects.count() == 14
    assert slot_of("Теннис", 5, 13, 10).capacity == 27
    assert slot_of("Шахматы", 2, 15, 8).ends == dt.time(17, 0)


def test_closed_enrollment_hides_the_choice(pupils):
    senior, _junior = pupils
    body = login(senior.user).get("/api/my/section/").json()
    assert body["open"] is False and body["enrollment"] is None and body["sections"] == []
    answer = login(senior.user).post("/api/my/section/enroll/", {"slot": slot_of("Теннис", 5, 12, 10).pk})
    assert answer.status_code == 400


def test_student_sees_only_slots_of_his_grade(pupils, open_enroll):
    senior, junior = pupils
    body = login(senior.user).get("/api/my/section/").json()
    grades = {(s["grade_from"], s["grade_to"]) for section in body["sections"] for s in section["slots"]}
    assert grades == {(10, 11)}
    body = login(junior.user).get("/api/my/section/").json()
    assert {(s["grade_from"], s["grade_to"]) for section in body["sections"] for s in section["slots"]} == {(8, 9)}
    # чужой группы час — отказ сервера, а не только скрытая кнопка
    answer = login(junior.user).post("/api/my/section/enroll/", {"slot": slot_of("Теннис", 5, 12, 10).pk})
    assert answer.status_code == 400


def test_one_section_per_student_and_leaving_keeps_history(pupils, open_enroll):
    senior, _junior = pupils
    api = login(senior.user)
    assert api.post("/api/my/section/enroll/", {"slot": slot_of("Теннис", 5, 12, 10).pk}).status_code == 200
    body = api.post("/api/my/section/enroll/", {"slot": slot_of("Футбол", 5, 12, 10).pk}).json()
    assert body["enrollment"]["section_title"] == "Футбол"
    assert SectionEnrollment.objects.filter(student=senior, ended_at__isnull=True).count() == 1
    assert SectionEnrollment.objects.filter(student=senior).count() == 2
    assert api.post("/api/my/section/leave/").json()["enrollment"] is None
    assert SectionEnrollment.objects.filter(student=senior).count() == 2
    assert AuditLog.objects.filter(student_id=senior.pk, field_name=services.EVENT).count() == 3


def test_full_slot_refuses(pupils, open_enroll):
    senior, _junior = pupils
    slot = slot_of("Теннис", 5, 12, 10)
    SectionSlot.objects.filter(pk=slot.pk).update(capacity=1)
    other = Student.objects.create(last_name="Ермеков", first_name="Алихан", group=senior.group, graduation_year=2028)
    services.enroll(student=other, slot=slot, actor=None)
    answer = login(senior.user).post("/api/my/section/enroll/", {"slot": slot.pk})
    assert answer.status_code == 400
    # и директору сверх лимита не записать
    with pytest.raises(services.Refused):
        services.enroll(student=senior, slot=slot, actor=None, by_director=True)


def test_moved_from_bot_chooses_hour_even_when_closed(pupils, tennis):
    senior, _junior = pupils
    services.import_enrollment(student=senior, section=tennis, slot=None, enrolled_at=timezone.now())
    api = login(senior.user)
    body = api.get("/api/my/section/").json()
    assert body["open"] is False
    assert [s["title"] for s in body["sections"]] == ["Теннис"]
    assert len(body["sections"][0]["slots"]) == 3
    # чужую секцию при закрытой записи не выбрать
    assert api.post("/api/my/section/enroll/", {"slot": slot_of("Футбол", 5, 12, 10).pk}).status_code == 400
    body = api.post("/api/my/section/enroll/", {"slot": slot_of("Теннис", 5, 13, 10).pk}).json()
    assert body["enrollment"]["slot"]["starts"] == "13:00"
    row = SectionEnrollment.objects.get(student=senior, ended_at__isnull=True)
    assert row.source == EnrollmentSource.BOT and row.slot_set_by is None
    # час выбран — запись закрыта, выйти нельзя
    assert api.post("/api/my/section/leave/").status_code == 400


def test_student_answer_has_no_other_students(pupils, open_enroll):
    senior, junior = pupils
    services.enroll(student=junior, slot=slot_of("Теннис", 3, 17, 8), actor=None)
    services.enroll(student=senior, slot=slot_of("Теннис", 5, 12, 10), actor=None)
    text = login(senior.user).get("/api/my/section/").content.decode()
    assert "Бекова" not in text and "Жанель" not in text


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_last_place_goes_to_one_of_two(groups):
    mine, _other = groups
    services.set_enroll_until(timezone.now() + dt.timedelta(days=1), actor=None)
    slot = slot_of("Волейбол", 5, 12, 10)
    SectionSlot.objects.filter(pk=slot.pk).update(capacity=1)
    racers = [
        Student.objects.create(last_name=f"Гонщик{n}", first_name="Тест", group=mine, graduation_year=2028)
        for n in range(2)
    ]

    def press(pk):
        close_old_connections()
        try:
            services.enroll(student=Student.objects.get(pk=pk), slot=slot, actor=None)
            return True
        except services.Refused:
            return False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(press, [r.pk for r in racers]))
    assert sorted(outcomes) == [False, True]
    assert SectionEnrollment.objects.filter(slot=slot, ended_at__isnull=True).count() == 1


def test_director_enrolls_moves_assigns_and_removes_when_closed(people, pupils, tennis):
    senior, _junior = pupils
    api = login(people["director_sport"])
    answer = api.post("/api/sport/enrollments/", {"student": senior.pk, "slot": slot_of("Теннис", 5, 12, 10).pk})
    assert answer.status_code == 201
    row_id = answer.json()["id"]
    moved = api.patch(f"/api/sport/enrollments/{row_id}/", {"slot": slot_of("Теннис", 5, 14, 10).pk}, format="json")
    assert moved.status_code == 200 and moved.json()["slot_title"].endswith("14:00–15:00")
    # перевод — только в часы своей секции и своей группы классов
    assert (
        api.patch(f"/api/sport/enrollments/{row_id}/", {"slot": slot_of("Футбол", 5, 12, 10).pk}, format="json")
    ).status_code == 400
    assert (
        api.patch(f"/api/sport/enrollments/{row_id}/", {"slot": slot_of("Теннис", 3, 17, 8).pk}, format="json")
    ).status_code == 400
    assert api.delete(f"/api/sport/enrollments/{row_id}/").status_code == 204
    assert SectionEnrollment.objects.get(pk=row_id).ended_at is not None


def test_director_assigns_hour_to_moved_student(people, pupils, tennis):
    senior, _junior = pupils
    row, _created = services.import_enrollment(student=senior, section=tennis, slot=None, enrolled_at=timezone.now())
    body = login(people["director_sport"]).get(f"/api/sport/sections/{tennis.pk}/").json()
    assert [r["student"]["id"] for r in body["no_hour"]] == [senior.pk]
    login(people["director_sport"]).patch(
        f"/api/sport/enrollments/{row.pk}/", {"slot": slot_of("Теннис", 5, 12, 10).pk}, format="json"
    )
    row.refresh_from_db()
    assert row.slot_id and row.slot_set_by == people["director_sport"]


def test_enroll_until_is_set_by_sport_director_and_logged(people):
    api = login(people["director_sport"])
    until = (timezone.now() + dt.timedelta(days=10)).isoformat()
    body = api.patch("/api/sport/settings/", {"enroll_until": until}, format="json").json()
    assert body["open"] is True
    assert api.patch("/api/sport/settings/", {"enroll_until": None}, format="json").json()["open"] is False
    assert AuditLog.objects.filter(model_label="sport.SectionSettings").count() == 2
    for role in ("director_exam", "teacher", "curator"):
        answer = login(people[role]).patch("/api/sport/settings/", {"enroll_until": until}, format="json")
        assert answer.status_code in (403, 404)


def test_removed_slot_moves_students_or_leaves_them_without_hour(people, pupils, tennis):
    senior, _junior = pupils
    first, second, third = (slot_of("Теннис", 5, hour, 10) for hour in (12, 13, 14))
    services.enroll(student=senior, slot=first, actor=None, by_director=True)
    slots = [
        {
            "id": s.pk,
            "weekday": s.weekday,
            "starts": f"{s.starts:%H:%M}",
            "ends": f"{s.ends:%H:%M}",
            "grade_from": s.grade_from,
            "grade_to": s.grade_to,
            "capacity": s.capacity,
        }
        for s in tennis.slots.exclude(pk=first.pk)
    ]
    api = login(people["director_sport"])
    answer = api.patch(
        f"/api/sport/sections/{tennis.pk}/",
        {"address": tennis.address, "slots": slots, "moves": {str(first.pk): second.pk}},
        format="json",
    )
    assert answer.status_code == 200
    assert SectionEnrollment.objects.get(student=senior, ended_at__isnull=True).slot_id == second.pk
    assert SectionSlot.all_objects.get(pk=first.pk).archived_at is not None
    # без перевода — «без часа»
    slots = [s for s in slots if s["id"] != second.pk]
    api.patch(f"/api/sport/sections/{tennis.pk}/", {"slots": slots}, format="json")
    assert SectionEnrollment.objects.get(student=senior, ended_at__isnull=True).slot_id is None
    assert third.pk in [s["id"] for s in api.get(f"/api/sport/sections/{tennis.pk}/").json()["slots"]]


@pytest.mark.parametrize("role", ["director_behavior", "director_exam", "director_talent", "teacher", "curator"])
def test_strangers_do_not_run_sections(people, pupils, tennis, role):
    senior, _junior = pupils
    api = login(people[role])
    # учителю шлюз маршрутов отвечает 404 — этих разделов для него нет
    refused = 404 if role == "teacher" else 403
    assert api.get("/api/sport/sections/").status_code == refused
    assert api.get(f"/api/sport/sections/{tennis.pk}/").status_code == refused
    assert api.get("/api/sport/sections/export/").status_code == refused
    assert api.get("/api/sport/students/?q=Абд").status_code == refused
    assert api.post("/api/sport/enrollments/", {"student": senior.pk, "slot": 1}).status_code == refused


def test_curator_reads_section_of_own_group_only(people, pupils):
    senior, junior = pupils
    services.enroll(student=senior, slot=slot_of("Теннис", 5, 12, 10), actor=None, by_director=True)
    services.enroll(student=junior, slot=slot_of("Теннис", 3, 17, 8), actor=None, by_director=True)
    api = login(people["curator"])
    assert api.get(f"/api/sport/students/{senior.pk}/section/").json()["section"] == "Теннис"
    assert api.get(f"/api/sport/students/{junior.pk}/section/").status_code == 404
    rows = api.get("/api/sport/students/sections/").json()["rows"]
    assert set(rows) == {str(senior.pk)}
    # остальные директора секцию ученика не читают
    assert login(people["director_exam"]).get(f"/api/sport/students/{senior.pk}/section/").status_code == 403
    assert login(people["teacher"]).get("/api/sport/students/sections/").status_code == 404


def test_excel_has_a_sheet_per_section(people, pupils):
    senior, _junior = pupils
    services.enroll(student=senior, slot=slot_of("ММА", 5, 12, 10), actor=None, by_director=True)
    body = login(people["director_sport"]).get("/api/sport/sections/export/?preview=1").json()
    titles = [sheet["title"] for sheet in body["sheets"]]
    assert titles == ["ММА"]
