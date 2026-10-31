"""Ученик в кружках: запись сразу, выход с историей, окно записи, параллель, пункт меню, главная."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from clubs import services
from clubs.models import ClubEnrollment, ClubParallel
from clubs.tests.conftest import login
from core.models import AuditLog
from sport import services as sport
from sport.tests.conftest import slot_of

pytestmark = pytest.mark.django_db


def _card(body, title):
    return next(card for card in body["clubs"] if card["title"] == title)


def test_student_sees_both_clubs_and_enrolls_at_once(pupils, lab):
    senior, _junior = pupils
    api = login(senior.user)
    body = api.get("/api/my/clubs/").json()
    assert {card["title"] for card in body["clubs"]} == {"AI Startup Lab", "Робототехника"}
    assert _card(body, "AI Startup Lab")["can_enroll"] and not _card(body, "AI Startup Lab")["enrolled"]
    after = api.post(f"/api/my/clubs/{lab.pk}/enroll/").json()
    card = _card(after, "AI Startup Lab")
    assert card["enrolled"] and card["enrolled_at"] and after["warnings"] == []
    # повторное нажатие — та же запись, без второй строки
    api.post(f"/api/my/clubs/{lab.pk}/enroll/")
    assert ClubEnrollment.objects.filter(student=senior, club=lab).count() == 1


def test_student_can_be_in_several_clubs(pupils, lab, robots):
    senior, _junior = pupils
    api = login(senior.user)
    api.post(f"/api/my/clubs/{lab.pk}/enroll/")
    body = api.post(f"/api/my/clubs/{robots.pk}/enroll/").json()
    assert all(card["enrolled"] for card in body["clubs"])


def test_leave_keeps_history_and_enroll_again_adds_a_row(pupils, lab):
    senior, _junior = pupils
    api = login(senior.user)
    api.post(f"/api/my/clubs/{lab.pk}/enroll/")
    body = api.post(f"/api/my/clubs/{lab.pk}/leave/").json()
    assert not _card(body, "AI Startup Lab")["enrolled"]
    closed = ClubEnrollment.objects.get(student=senior, club=lab)
    assert closed.ended_at is not None, "строка не удаляется — у неё дата выхода"
    api.post(f"/api/my/clubs/{lab.pk}/enroll/")
    rows = ClubEnrollment.objects.filter(student=senior, club=lab)
    assert rows.count() == 2 and rows.filter(ended_at__isnull=True).count() == 1
    events = AuditLog.objects.filter(student_id=senior.pk, field_name="club").values_list("new_value", flat=True)
    assert list(events) == [
        "Кружок: записан — AI Startup Lab",
        "Кружок: вышел — AI Startup Lab",
        "Кружок: записан — AI Startup Lab",
    ]


def test_closed_window_hides_the_button_but_keeps_members_who_may_leave(pupils, lab):
    senior, junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    lab.enroll_until = timezone.now() - dt.timedelta(minutes=1)
    lab.save(update_fields=["enroll_until"])
    newcomer = login(junior.user)
    card = _card(newcomer.get("/api/my/clubs/").json(), "AI Startup Lab")
    assert card["open"] is False and card["can_enroll"] is False
    assert newcomer.post(f"/api/my/clubs/{lab.pk}/enroll/").status_code == 400
    member = login(senior.user)
    assert _card(member.get("/api/my/clubs/").json(), "AI Startup Lab")["enrolled"], "записанный остаётся"
    assert member.post(f"/api/my/clubs/{lab.pk}/leave/").status_code == 200, "выйти можно и при закрытой"


def test_club_of_another_parallel_is_not_offered(pupils, lab, robots):
    senior, junior = pupils  # 10 и 9 параллель
    ClubParallel.objects.filter(club=lab).exclude(parallel=10).delete()
    junior_api = login(junior.user)
    assert "AI Startup Lab" not in {c["title"] for c in junior_api.get("/api/my/clubs/").json()["clubs"]}
    assert junior_api.post(f"/api/my/clubs/{lab.pk}/enroll/").status_code == 404


def test_menu_item_only_when_a_club_is_open_for_the_parallel(pupils, lab, robots):
    from core.parallels import student_paths

    senior, junior = pupils
    assert "/clubs" in student_paths(senior) and "/clubs" in student_paths(junior)
    ClubParallel.objects.filter(parallel=9).delete()
    assert "/clubs" not in student_paths(junior), "кружков для 9 нет — пункта нет"
    assert "/clubs" in student_paths(senior)
    assert "/clubs" not in login(junior.user).get("/api/auth/me/").json()["sections"]


def test_overlap_with_own_sport_section_warns_but_enrolls(pupils, robots, make_user):
    """Вторник 15:00–18:00 у робототехники, у ученика 9 параллели теннис по средам — без пересечения;
    волейбол во вторник 16:00 — с пересечением."""
    _senior, junior = pupils
    from sport.models import SectionSlot

    tuesday = SectionSlot.objects.filter(weekday=1, parallel_from__lte=9, parallel_to__gte=9).first()
    if tuesday is None:
        tuesday = SectionSlot.objects.create(
            section=slot_of("Теннис", 3, 17, 8).section,
            weekday=1,
            starts=dt.time(16, 0),
            ends=dt.time(17, 0),
            parallel_from=8,
            parallel_to=9,
            capacity=20,
        )
    sport.enroll(student=junior, slot=tuesday, actor=None, by_director=True)
    api = login(junior.user)
    preview = _card(api.get("/api/my/clubs/").json(), "Робототехника")
    assert preview["overlaps"], "предупреждение видно до записи"
    body = api.post(f"/api/my/clubs/{robots.pk}/enroll/").json()
    assert body["warnings"] and "Робототехника" in body["warnings"][0]
    assert _card(body, "Робототехника")["enrolled"], "записан всё равно"


def test_today_line_on_meeting_days_only(pupils, lab, monkeypatch):
    senior, _junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    monday = timezone.make_aware(dt.datetime(2026, 11, 2, 9, 0))
    monkeypatch.setattr(services, "local_now", lambda: timezone.localtime(monday))
    assert login(senior.user).get("/api/my/clubs/").json()["today"] == [
        {"id": lab.pk, "title": "AI Startup Lab", "time": "15:00–18:00"}
    ]
    sunday = monday - dt.timedelta(days=1)
    monkeypatch.setattr(services, "local_now", lambda: timezone.localtime(sunday))
    assert login(senior.user).get("/api/my/clubs/").json()["today"] == []


def test_staff_have_no_student_club_routes(people):
    for role, user in people.items():
        assert login(user).get("/api/my/clubs/").status_code in (403, 404), role


def test_student_answer_carries_no_internal_labels(pupils, lab):
    senior, _junior = pupils
    services.enroll(student=senior, club=lab, actor=None)
    raw = login(senior.user).get("/api/my/clubs/").content.decode()
    for word in ("critical", "needs_supervision", "notes", 'mentor":', "is_fictional"):
        assert word not in raw, word
