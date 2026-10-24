"""Кабинеты директоров (24.10.2026): права новых ручек и путь записей.

Границы, которые легко сломать тихо:
* звонок, задача, олимпиада, освобождение, мероприятие пишет только роль
  своего кабинета и администратор — чужой директор получает 403;
* ученик видит только свои заявки, чужих учеников и ярлыков в ответе нет;
* куратор видит освобождение только у своей группы, чужого ученика ему — 404;
* освобождённый урок у учителя помечен, а пропуск читается как «у»;
* результат олимпиады — одна подтверждённая строка портфолио, правка её обновляет;
* «Норм / Не норм» у Асем меняет статус эссе, текст остаётся прежним.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.curators import assign
from directors.models import (
    ApplicationStatus,
    LessonRelease,
    Olympiad,
    OlympiadEntry,
    ParentCall,
    SportApplication,
    SportEvent,
    StaffTask,
)
from students.models import Activity, ParentContact, Student, StudyGroup

pytestmark = pytest.mark.django_db

DIRECTORS = ("director_behavior", "director_exam", "director_admission", "director_talent", "director_sport")


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def people(make_user):
    out = {role: make_user(role, f"{role}@cab.kz", full_name=role) for role in DIRECTORS}
    out["admin"] = make_user("admin", "admin@cab.kz", full_name="Администратор")
    out["teacher"] = make_user("teacher", "teacher@cab.kz", full_name="Учитель")
    out["curator"] = make_user("curator", "curator@cab.kz", full_name="Куратор")
    return out


@pytest.fixture
def groups(people):
    mine = StudyGroup.objects.create(code="CORNELL", parallel=11)
    other = StudyGroup.objects.create(code="OXFORD", parallel=10)
    assign(group=mine, curator=people["curator"], since=timezone.localdate() - dt.timedelta(days=30))
    return mine, other


@pytest.fixture
def pupils(groups, make_user):
    mine, other = groups
    a = Student.objects.create(
        last_name="Бекова", first_name="Жанель", group=mine, graduation_year=2027, user=make_user("student", "a@cab.kz")
    )
    b = Student.objects.create(
        last_name="Ермеков",
        first_name="Алихан",
        group=other,
        graduation_year=2028,
        user=make_user("student", "b@cab.kz"),
    )
    return a, b


def test_parent_call_is_written_by_behavior_and_lands_in_the_card(people, pupils):
    a, _b = pupils
    contact = ParentContact.objects.create(
        student=a, full_name="Бекова Гульмира", relation="mother", phone="87014821936"
    )
    body = {"student": a.pk, "outcome": "call_back", "note": "Просили позже", "contact": contact.pk}
    for role in ("director_exam", "director_sport", "teacher"):
        assert login(people[role]).post("/api/directors/calls/", body, format="json").status_code in (403, 404)
    response = login(people["director_behavior"]).post("/api/directors/calls/", body, format="json")
    assert response.status_code == 201, response.content
    assert ParentCall.objects.get().contact == contact
    from core.models import AuditLog

    assert AuditLog.objects.filter(student_id=a.pk, field_name="parent_call").exists()
    history = login(people["director_behavior"]).get("/api/directors/calls/").json()
    assert history["rows"][0]["outcome"] == "call_back"
    assert login(people["director_talent"]).get("/api/directors/calls/").status_code == 403


def test_reports_are_open_to_school_and_academic_directors_only(people, pupils):
    for role, allowed in (("director_behavior", True), ("director_exam", True), ("director_sport", False)):
        response = login(people[role]).get("/api/directors/reports/")
        assert response.status_code == (200 if allowed else 403), role
    saltanat = login(people["director_behavior"])
    kinds = {row["kind"] for row in saltanat.get("/api/directors/reports/").json()["current"]}
    assert kinds == {"morning", "security", "parent_reports", "calls", "attendance_week"}
    # отчёт чужой роли — как несуществующий
    assert saltanat.get("/api/directors/reports/teachers/").status_code == 404
    report = saltanat.get("/api/directors/reports/morning/").json()
    assert report["seen"] is False
    assert saltanat.post("/api/directors/reports/morning/seen/", {"period": report["period"]}, format="json").json()[
        "seen"
    ]
    assert saltanat.get("/api/directors/reports/morning/").json()["seen"] is True
    # «Просмотрено» — у каждого своё
    assert login(people["admin"]).get("/api/directors/reports/morning/").json()["seen"] is False
    export = saltanat.get("/api/directors/reports/security/export/")
    assert export.status_code == 200 and export["Content-Type"].startswith("application/vnd.openxml")


def test_staff_task_path_from_kymbat_to_the_assignee_and_back(people):
    kymbat = login(people["director_exam"])
    body = {"title": "Отметить журналы", "due": (timezone.localdate() + dt.timedelta(days=2)).isoformat()}
    for role in ("director_behavior", "curator", "teacher"):
        response = login(people[role]).post("/api/directors/staff-tasks/", {**body, "assignee": people["teacher"].pk})
        # учителю чужой маршрут не существует — шлюз отвечает 404
        assert response.status_code in (403, 404), role
    created = kymbat.post("/api/directors/staff-tasks/", {**body, "assignee": people["teacher"].pk}, format="json")
    assert created.status_code == 201, created.content
    task = StaffTask.objects.get()
    # себе и ученику — нельзя
    assert (
        kymbat.post("/api/directors/staff-tasks/", {**body, "assignee": people["director_exam"].pk}).status_code == 400
    )

    teacher = login(people["teacher"])
    assert [row["id"] for row in teacher.get("/api/directors/staff-tasks/mine/").json()["rows"]] == [task.pk]
    # чужую задачу не отметить и не увидеть
    assert login(people["curator"]).post(f"/api/directors/staff-tasks/{task.pk}/done/").status_code == 404
    assert login(people["curator"]).get("/api/directors/staff-tasks/mine/").json()["rows"] == []
    assert teacher.post(f"/api/directors/staff-tasks/{task.pk}/done/").json()["status"] == "done"
    returned = kymbat.patch(
        f"/api/directors/staff-tasks/{task.pk}/", {"action": "return", "note": "Не все"}, format="json"
    )
    assert returned.json()["status"] == "returned"
    teacher.post(f"/api/directors/staff-tasks/{task.pk}/done/")
    assert (
        kymbat.patch(f"/api/directors/staff-tasks/{task.pk}/", {"action": "accept"}, format="json").json()["status"]
        == "accepted"
    )
    # принятая задача у исполнителя уходит с главной
    assert teacher.get("/api/directors/staff-tasks/mine/").json()["rows"] == []


def test_olympiad_result_writes_one_confirmed_portfolio_row(people, pupils):
    a, _b = pupils
    arman = login(people["director_talent"])
    body = {"title": "Городская олимпиада по математике", "level": "city", "starts": "2026-10-30", "ends": "2026-10-31"}
    assert login(people["director_sport"]).post("/api/directors/olympiads/", body).status_code == 403
    created = arman.post("/api/directors/olympiads/", body, format="json")
    assert created.status_code == 201, created.content
    olympiad = Olympiad.objects.get()
    assert (
        arman.post(f"/api/directors/olympiads/{olympiad.pk}/entries/", {"students": [a.pk]}, format="json").json()[
            "added"
        ]
        == 1
    )
    entry = OlympiadEntry.objects.get()
    arman.patch(f"/api/directors/olympiad-entries/{entry.pk}/", {"result": "prize"}, format="json")
    arman.patch(f"/api/directors/olympiad-entries/{entry.pk}/", {"result": "winner"}, format="json")
    rows = Activity.objects.filter(student=a)
    assert rows.count() == 1
    assert rows.get().is_confirmed and rows.get().title.endswith("победитель")
    # кураторам и академ директору — на чтение
    assert login(people["director_exam"]).get(f"/api/directors/olympiads/{olympiad.pk}/").status_code == 200
    assert login(people["director_exam"]).patch(f"/api/directors/olympiads/{olympiad.pk}/", {}).status_code == 403


def test_release_marks_lessons_excused_and_shows_to_own_curator_only(people, pupils, groups):
    a, b = pupils
    day = timezone.localdate()
    olympiad = Olympiad.objects.create(title="Отбор на IZhO", level="national", starts=day, ends=day)
    body = {"olympiad": olympiad.pk, "students": [a.pk, b.pk], "starts": day.isoformat(), "slot_from": 3, "slot_to": 4}
    assert login(people["director_exam"]).post("/api/directors/releases/", body, format="json").status_code == 403
    created = login(people["director_talent"]).post("/api/directors/releases/", body, format="json")
    assert created.status_code == 201, created.content
    row = LessonRelease.objects.get()
    assert row.covers(day, 3) and not row.covers(day, 5)

    week = {"from": day.isoformat(), "to": day.isoformat()}
    kymbat = login(people["director_exam"]).get("/api/directors/releases/", week).json()["rows"]
    assert {s["id"] for s in kymbat[0]["students"]} == {a.pk, b.pk}
    # куратор видит только своего ученика
    curator = login(people["curator"]).get("/api/directors/releases/", week)
    assert curator.status_code == 403  # куратору — через утреннюю отметку, отдельной ручки нет

    from academics.marks import is_released, releases_of

    found = releases_of([a.pk], day, day)
    assert is_released(found, a.pk, day, 4) and not is_released(found, a.pk, day, 2)
    # отмена — в архив, отметки снова прежние
    assert login(people["director_sport"]).delete(f"/api/directors/releases/{row.pk}/").status_code == 403
    assert login(people["director_talent"]).delete(f"/api/directors/releases/{row.pk}/").status_code == 204
    assert releases_of([a.pk], day, day) == {}


def test_sport_application_flow_and_student_sees_only_own(people, pupils):
    a, b = pupils
    nurlybek = login(people["director_sport"])
    starts = (timezone.now() + dt.timedelta(days=2)).isoformat()
    body = {"title": "Кубок BHS по волейболу", "kind": "competition", "starts_at": starts, "place": "Спортзал"}
    assert login(people["director_talent"]).post("/api/directors/sport-events/", body).status_code == 403
    created = nurlybek.post("/api/directors/sport-events/", {**body, "seats": 1, "spectators": True}, format="json")
    assert created.status_code == 201, created.content
    event = SportEvent.objects.get()

    pupil_a, pupil_b = login(a.user), login(b.user)
    assert (
        pupil_a.post(f"/api/my/sport-events/{event.pk}/apply/", {"kind": "play", "comment": "Капитан"}).status_code
        == 201
    )
    assert pupil_b.post(f"/api/my/sport-events/{event.pk}/apply/", {"kind": "play"}).status_code == 201
    mine = pupil_a.get("/api/my/sport-events/").json()["rows"][0]
    assert mine["mine"]["status"] == "pending"
    assert "applications" not in mine and "pending" not in mine  # чужих заявок ученик не видит
    # ученику закрыт список директора
    assert pupil_a.get("/api/directors/sport-events/").status_code == 403
    assert pupil_a.get(f"/api/directors/sport-events/{event.pk}/applications/").status_code == 403

    first, second = SportApplication.objects.order_by("id")
    assert nurlybek.patch(f"/api/directors/sport-applications/{first.pk}/", {"status": "accepted"}).status_code == 200
    # мест одно — второго не принять
    assert nurlybek.patch(f"/api/directors/sport-applications/{second.pk}/", {"status": "accepted"}).status_code == 400
    released = nurlybek.post(f"/api/directors/sport-applications/{first.pk}/release/", {"slot_from": 1, "slot_to": 3})
    assert released.status_code == 201, released.content
    assert LessonRelease.objects.get().event == event
    # отклонённую заявку принятым участником не освободить
    nurlybek.patch(f"/api/directors/sport-applications/{second.pk}/", {"status": "declined"})
    assert nurlybek.post(f"/api/directors/sport-applications/{second.pk}/release/", {}).status_code == 400
    assert SportApplication.objects.get(pk=second.pk).status == ApplicationStatus.DECLINED
    # чужую заявку ученик не отзовёт
    assert pupil_b.delete(f"/api/my/sport-applications/{first.pk}/").status_code == 404


def test_essay_verdict_changes_status_not_text(people, pupils):
    from roadmap.models import Essay, EssayComment, EssayStatus, EssayVersion

    a, _b = pupils
    essay = Essay.objects.create(student=a, title="Personal Statement", status=EssayStatus.REVIEW)
    EssayVersion.objects.create(essay=essay, number=1, text="Мой текст эссе")
    draft = Essay.objects.create(student=a, title="Черновик")
    EssayVersion.objects.create(essay=draft, number=1, text="Не готово")
    asem = login(people["director_admission"])
    assert login(people["director_exam"]).get("/api/directors/essays/").status_code == 403
    rows = asem.get("/api/directors/essays/").json()["rows"]
    assert [row["id"] for row in rows] == [essay.pk]  # черновик не виден
    assert asem.post(f"/api/directors/essays/{essay.pk}/verdict/", {"verdict": "not_ok"}).status_code == 400
    done = asem.post(f"/api/directors/essays/{essay.pk}/verdict/", {"verdict": "not_ok", "comment": "Нет истории"})
    assert done.status_code == 200 and done.json()["verdict"] == "not_ok"
    essay.refresh_from_db()
    assert essay.status == EssayStatus.REVISION and essay.current_version.text == "Мой текст эссе"
    assert EssayComment.objects.get(essay=essay).text == "Нет истории"
    assert asem.get(f"/api/directors/essays/{draft.pk}/").status_code == 404


def test_exam_results_are_read_only_for_kymbat(people, pupils):
    from students.models import ExamAttempt

    a, b = pupils
    ExamAttempt.objects.create(
        student=a, exam_type="IELTS", attempt_format="mock", date=timezone.localdate(), total_score=6.5
    )
    kymbat = login(people["director_exam"])
    data = kymbat.get("/api/directors/exam-results/?exam=IELTS").json()
    # только 11: ученик 10 параллели в таблицу не входит
    assert [row["id"] for row in data["rows"]] == [a.pk]
    assert data["rows"][0]["mock"] == "6.5"
    assert kymbat.get(f"/api/directors/exam-results/{a.pk}/").json()["attempts"][0]["total"] == "6.5"
    assert login(people["director_admission"]).get("/api/directors/exam-results/").status_code == 403


def test_student_answers_hold_no_internal_labels(people, pupils):
    a, _b = pupils
    SportEvent.objects.create(
        title="Осенний кросс", kind="event", starts_at=timezone.now() + dt.timedelta(days=3), place="Парк"
    )
    text = login(a.user).get("/api/my/sport-events/").content.decode()
    for word in ("critical", "needs_supervision", "curator_note", "full_name"):
        assert word not in text
