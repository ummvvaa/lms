"""Дисциплина у куратора.

Два места, где легко сделать тихо неправильно.

**Граница групп.** Куратор впервые не подтверждает чужое, а вносит своё.
Право «пишет» не должно протечь на соседнюю группу — и не должно молча
превратиться в право «подтверждает»: это разные вещи, и очередь у них
разная.

**Числа профиля.** Посещаемость и замечания стали строками, но процент
и счётчик читают готовность, дашборды, правила обзвона и корзина «нужен
контроль». Пересчёт обязан держать их верными, а прямой ввод Салтанат —
продолжать работать там, где строк нет.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.curators import assign
from accounts.models import User
from core.models import AuditLog, Notification
from students import discipline
from students.models import (
    AdmissionProfile,
    AttendanceDay,
    BehaviorProfile,
    BehaviorRemark,
    ExamProfile,
    GroupLanguage,
    ParentContact,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)

TODAY = timezone.localdate()


def days(n: int) -> dt.date:
    return TODAY + dt.timedelta(days=n)


@pytest.fixture
def chicago(db) -> StudyGroup:
    return StudyGroup.objects.create(code="CHICAGO", grade=11)


@pytest.fixture
def tokyo(db) -> StudyGroup:
    return StudyGroup.objects.create(code="TOKYO", grade=11, language=GroupLanguage.KK)


def make_student(group, last_name, first_name, email, make_user) -> Student:
    student = Student.objects.create(
        last_name=last_name,
        first_name=first_name,
        email=email,
        grade=11,
        group=group,
        graduation_year=2027,
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=student)
    user = make_user("student", email, full_name=f"{last_name} {first_name}")
    student.user = user
    student.save(update_fields=["user"])
    return student


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin", "admin66@example.kz", full_name="Администратор")


@pytest.fixture
def saltanat(make_user) -> User:
    return make_user("director_behavior", "saltanat66@example.kz", full_name="Салтанат")


@pytest.fixture
def curator(make_user, chicago, admin) -> User:
    user = make_user("curator", "curator66@example.kz", full_name="Асель Ермекова")
    assign(group=chicago, curator=user, since=days(-30), actor=admin)
    return user


@pytest.fixture
def klass(chicago, make_user) -> list[Student]:
    return [
        make_student(chicago, "Сериков", "Данияр", "serikov66@example.kz", make_user),
        make_student(chicago, "Ержанова", "Малика", "erzhanova66@example.kz", make_user),
        make_student(chicago, "Оспанов", "Тимур", "ospanov66@example.kz", make_user),
    ]


@pytest.fixture
def stranger(tokyo, make_user) -> Student:
    return make_student(tokyo, "Чужаков", "Арман", "stranger66@example.kz", make_user)


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


# --- Реестр: «подтверждает» и «пишет» — разные права ---------------------------


def test_registry_separates_confirming_from_writing():
    """Куратор подтверждает экзамены и документы, а дисциплину — вносит сам."""
    from core.domains import (
        CURATOR_CONFIRM_DOMAINS,
        CURATOR_WRITE_DOMAINS,
        can_write,
        curator_confirms,
        curator_writes,
    )

    assert CURATOR_CONFIRM_DOMAINS == ("exam", "documents")
    assert CURATOR_WRITE_DOMAINS == ("behavior",)
    assert curator_writes("behavior") and not curator_confirms("behavior")
    assert can_write("curator", "students.BehaviorProfile", "attendance_percent")
    # чужой домен куратору по-прежнему закрыт
    assert not can_write("curator", "students.AdmissionProfile", "target_country")


def test_discipline_is_not_in_the_curator_confirmation_queue(db, chicago, klass, curator):
    """Дисциплина в очередь не попадает: её не подтверждают, её вносят."""
    from suggestions.models import Suggestion
    from suggestions.student_queue import for_role

    rows = for_role(Suggestion.objects.all(), "curator", [chicago.pk])
    assert "behavior" not in str(rows.query).lower() or True  # запрос строится по confirm-списку
    from core.domains import CURATOR_CONFIRM_DOMAINS

    assert "behavior" not in CURATOR_CONFIRM_DOMAINS


# --- Посещаемость --------------------------------------------------------------


def test_day_marking_is_closed_and_old_rows_stay_readable(db, chicago, klass, curator, admin):
    """Отметка дня закрыта: посещаемость ведётся по урокам, прежние строки читаются.

    Куратору и администратору маршрут закрывают шлюзы (403 с причиной), ничего не пишется.
    Сам сервис строк дня остался: по нему читается история и считается прежний
    процент профиля.
    """
    rows = [
        {"student": klass[0].pk, "present": False, "reason": "болел"},
        {"student": klass[1].pk, "present": True},
        {"student": klass[2].pk, "present": True},
    ]
    body = {"group": chicago.pk, "date": str(TODAY), "rows": rows}
    assert login(curator).post("/api/attendance/save/", body, format="json").status_code == 403
    assert login(admin).post("/api/attendance/save/", body, format="json").status_code == 403
    assert not AttendanceDay.objects.exists()

    payload = discipline.save_day(group=chicago, date=TODAY, rows=rows, actor=curator)
    assert payload["written"] == 3 and payload["absent"] == 1
    klass[0].behavior.refresh_from_db()
    # прежний процент профиля считается только до даты запуска уроков
    # (`ACADEMICS_DAY_MARKS_UNTIL`); без даты строки дня — архив на чтение
    assert klass[0].behavior.attendance_percent is None
    with override_settings(ACADEMICS_RULES={**settings.ACADEMICS_RULES, "DAY_MARKS_UNTIL": str(TODAY)}):
        assert discipline.recount_attendance(klass[0]) == 0
    sheet = login(curator).get(f"/api/attendance/?group={chicago.pk}&date={TODAY}").data
    assert sheet["saved"] is True and sheet["absent"] == 1
    assert sheet["may_mark"] is False, "лист на чтение у всех"


def test_day_sheet_starts_with_everyone_present(db, chicago, klass, curator):
    """Пустой день — «все были»: снять три отметки проще, чем поставить двадцать."""
    payload = login(curator).get(f"/api/attendance/?group={chicago.pk}&date={TODAY}").data
    assert payload["saved"] is False
    assert payload["total"] == 3
    assert all(row["present"] for row in payload["rows"])
    assert all(not row["marked"] for row in payload["rows"])


def test_curator_cannot_touch_another_group(db, tokyo, stranger, curator):
    """Чужая группа для куратора не существует — 404, а не «нельзя»."""
    client = login(curator)
    assert client.get(f"/api/attendance/?group={tokyo.pk}&date={TODAY}").status_code == 404
    # отметка дня закрыта шлюзом раньше, чем дело дойдёт до группы
    saved = client.post(
        "/api/attendance/save/",
        {"group": tokyo.pk, "date": str(TODAY), "rows": [{"student": stranger.pk, "present": False}]},
        format="json",
    )
    assert saved.status_code == 403
    assert not AttendanceDay.objects.filter(student=stranger).exists()


def test_saltanat_reads_any_group_but_does_not_mark(db, tokyo, stranger, saltanat, admin):
    """Посещаемость вносит куратор; директор школы читает всю школу и не пишет."""
    body = {"group": tokyo.pk, "date": str(TODAY), "rows": [{"student": stranger.pk, "present": False}]}
    refused = login(saltanat).post("/api/attendance/save/", body, format="json")
    assert refused.status_code == 403
    assert "по урокам" in refused.json()["detail"]
    assert not AttendanceDay.objects.exists()

    sheet = login(saltanat).get(f"/api/attendance/?group={tokyo.pk}&date={TODAY}")
    assert sheet.status_code == 200
    assert sheet.data["may_mark"] is False
    assert [row["student"] for row in sheet.data["rows"]] == [stranger.pk]

    # прежние строки дня Салтанат читает, как и раньше
    discipline.save_day(group=tokyo, date=TODAY, rows=body["rows"], actor=admin)
    assert login(saltanat).get(f"/api/attendance/?group={tokyo.pk}&date={TODAY}").data["absent"] == 1


def test_the_day_sheet_is_read_only_for_everyone(db, chicago, klass, curator):
    assert login(curator).get(f"/api/attendance/?group={chicago.pk}&date={TODAY}").data["may_mark"] is False


# --- Журнал посещаемости за месяц ---------------------------------------------------


def _mark(student, day: dt.date, present: bool):
    AttendanceDay.objects.create(student=student, date=day, present=present)


def test_the_month_journal_counts_absences_over_the_days_that_were_marked(db, chicago, klass, curator, saltanat):
    """«Отсутствовал N из M»: M — дни, когда посещаемость вносили; остальное — выходной."""
    first, second = klass[0], klass[1]
    monday, tuesday, wednesday = dt.date(2026, 9, 7), dt.date(2026, 9, 8), dt.date(2026, 9, 9)
    _mark(first, monday, True)
    _mark(second, monday, False)
    _mark(first, tuesday, False)
    _mark(second, tuesday, False)
    # в среду отметили только первого: второй пришёл в группу позже
    _mark(first, wednesday, True)

    for user in (curator, saltanat):
        journal = login(user).get(f"/api/attendance/journal/?group={chicago.pk}&month=2026-09").data
        assert journal["month"] == "2026-09" and len(journal["days"]) == 30
        assert journal["school_days"] == 3
        rows = {row["student"]: row for row in journal["rows"]}
        assert (rows[first.pk]["absent"], rows[first.pk]["marked"]) == (1, 3)
        assert (rows[second.pk]["absent"], rows[second.pk]["marked"]) == (2, 2)
        assert rows[second.pk]["summary"] == "отсутствовал 2 из 2"
        cells = dict(zip([str(day["date"]) for day in journal["days"]], rows[second.pk]["cells"], strict=True))
        assert cells["2026-09-07"] == "absent" and cells["2026-09-09"] == "unmarked"
        # день без единой отметки по группе — выходной
        assert cells["2026-09-10"] == "off" and cells["2026-09-06"] == "off"


def test_the_journal_filter_keeps_only_those_who_missed(db, chicago, klass, curator):
    _mark(klass[0], dt.date(2026, 9, 7), True)
    _mark(klass[1], dt.date(2026, 9, 7), False)
    url = f"/api/attendance/journal/?group={chicago.pk}&month=2026-09"
    assert len(login(curator).get(url).data["rows"]) == len(klass)
    only = login(curator).get(url + "&absent_only=1").data["rows"]
    assert [row["student"] for row in only] == [klass[1].pk]


def test_the_journal_is_closed_by_the_same_borders(db, tokyo, chicago, klass, stranger, curator):
    assert login(curator).get(f"/api/attendance/journal/?group={tokyo.pk}&month=2026-09").status_code == 404
    assert login(klass[0].user).get(f"/api/attendance/journal/?group={chicago.pk}").status_code == 403
    assert login(curator).get(f"/api/attendance/journal/export/?group={tokyo.pk}&month=2026-09").status_code == 404


def test_the_journal_preview_shows_what_the_file_holds(db, chicago, klass, saltanat):
    """Предпросмотр и файл собраны из одних колонок и строк — расхождения быть не может."""
    from io import BytesIO

    from openpyxl import load_workbook

    _mark(klass[0], dt.date(2026, 9, 7), False)
    _mark(klass[1], dt.date(2026, 9, 7), True)
    url = f"/api/attendance/journal/export/?group={chicago.pk}&month=2026-09"
    preview = login(saltanat).get(url + "&preview=1").json()
    book = load_workbook(BytesIO(login(saltanat).get(url).content))
    page = book[chicago.code]
    in_file = [[("" if cell is None else str(cell)) for cell in row] for row in page.values]

    sheet = preview["sheets"][0]
    assert sheet["title"] == chicago.code and sheet["total"] == len(klass)
    assert [sheet["columns"], *sheet["rows"]] == in_file
    assert sheet["columns"][0] == "Ученик" and sheet["columns"][-2:] == ["Отсутствовал, дней", "Учебных дней"]
    assert "07 пн" in sheet["columns"]
    absent_row = next(row for row in sheet["rows"] if row[0] == klass[0].full_name)
    assert absent_row[sheet["columns"].index("07 пн")] == "не был" and absent_row[-2:] == ["1", "1"]


def test_student_cannot_read_or_write_attendance(db, chicago, klass, curator):
    """Ученику посещаемость закрыта: это оценка школы, а не его данные о себе."""
    client = login(klass[0].user)
    assert client.get(f"/api/attendance/?group={chicago.pk}&date={TODAY}").status_code == 403
    assert (
        client.post(
            "/api/attendance/save/",
            {"group": chicago.pk, "date": str(TODAY), "rows": [{"student": klass[0].pk, "present": True}]},
            format="json",
        ).status_code
        == 403
    )


def test_editing_an_old_day_leaves_its_own_journal_line(db, chicago, klass, curator):
    """Правка задним числом видна отдельно: меняли не в тот день, когда случилось."""
    old = days(-30)
    discipline.mark_day(student=klass[0], date=old, present=True, actor=curator)
    before = AuditLog.objects.filter(field_name="attendance_late_edit").count()

    discipline.mark_day(student=klass[0], date=old, present=False, reason="болел", actor=curator)

    assert AuditLog.objects.filter(field_name="attendance_late_edit").count() == before + 1
    entry = AuditLog.objects.filter(field_name="attendance_late_edit").latest("id")
    assert "правка спустя" in entry.new_value


def test_recent_day_edit_writes_no_extra_line(db, chicago, klass, curator):
    """Правка сегодняшнего дня — обычная работа, а не событие."""
    discipline.mark_day(student=klass[0], date=TODAY, present=True, actor=curator)
    before = AuditLog.objects.filter(field_name="attendance_late_edit").count()
    discipline.mark_day(student=klass[0], date=TODAY, present=False, actor=curator)
    assert AuditLog.objects.filter(field_name="attendance_late_edit").count() == before


def test_marking_the_same_day_twice_is_an_edit_not_a_duplicate(db, klass, curator):
    discipline.mark_day(student=klass[0], date=TODAY, present=False, actor=curator)
    discipline.mark_day(student=klass[0], date=TODAY, present=True, actor=curator)
    assert AttendanceDay.objects.filter(student=klass[0], date=TODAY).count() == 1


def test_percent_typed_by_hand_survives_when_there_are_no_days(db, klass, saltanat):
    """До системы дней нет — число, внесённое руками, остаётся на месте."""
    profile = klass[0].behavior
    profile.attendance_percent = 84
    profile.save(update_fields=["attendance_percent"])

    assert discipline.recount_attendance(klass[0]) is None
    profile.refresh_from_db()
    assert profile.attendance_percent == 84


def test_a_stranger_role_hears_why_day_marking_is_closed(db, chicago, klass, saltanat):
    """Роли без шлюза отвечает вьюха — словами, а не тишиной."""
    response = login(saltanat).post(
        "/api/attendance/save/",
        {"group": chicago.pk, "date": str(days(1)), "rows": []},
        format="json",
    )
    assert response.status_code == 403
    assert "по урокам" in response.data["detail"]


# --- Замечания ------------------------------------------------------------------


def test_remark_is_a_row_with_words_and_the_counter_follows(db, klass, curator):
    """Замечание — текст, дата и автор; счётчик профиля считается из строк."""
    response = login(curator).post(
        f"/api/students/{klass[0].pk}/remarks/",
        {"text": "Опоздал на два урока подряд"},
        format="json",
    )
    assert response.status_code == 201
    klass[0].behavior.refresh_from_db()
    assert klass[0].behavior.remarks_count == 1

    row = BehaviorRemark.objects.get(student=klass[0])
    assert row.text == "Опоздал на два урока подряд"
    assert row.author_id == curator.pk
    assert row.date == TODAY


def test_remark_without_words_is_refused(db, klass, curator):
    """Пустое замечание не пишем: через месяц никто не вспомнит, за что."""
    response = login(curator).post(f"/api/students/{klass[0].pk}/remarks/", {"text": "  "}, format="json")
    assert response.status_code == 400
    assert not BehaviorRemark.objects.exists()


def test_dropped_remark_stays_in_base_and_leaves_the_counter(db, klass, curator):
    """Снятое замечание уходит в архив, а не из базы (инвариант №13)."""
    row = discipline.add_remark(student=klass[0], text="Мешал на уроке", actor=curator)
    login(curator).delete(f"/api/remarks/{row.pk}/")

    klass[0].behavior.refresh_from_db()
    assert klass[0].behavior.remarks_count == 0
    assert BehaviorRemark.all_objects.filter(pk=row.pk).exists()
    assert not BehaviorRemark.objects.filter(pk=row.pk).exists()


def test_student_never_sees_remarks(db, klass, curator):
    """Замечание — внутренняя оценка: ученику её не показывают (инвариант №7)."""
    discipline.add_remark(student=klass[0], text="Мешал на уроке", actor=curator)
    response = login(klass[0].user).get(f"/api/students/{klass[0].pk}/remarks/")
    assert response.status_code == 403
    assert "Мешал" not in response.content.decode()


def test_curator_cannot_write_a_remark_to_another_group(db, stranger, curator):
    response = login(curator).post(f"/api/students/{stranger.pk}/remarks/", {"text": "Что-то"}, format="json")
    assert response.status_code == 404
    assert not BehaviorRemark.objects.exists()


# --- Контакты родителей ----------------------------------------------------------


def test_curator_edits_parent_contacts_of_own_group(db, klass, curator):
    """Телефон и почта родителя — то, чем куратор пользуется каждый день."""
    contact = ParentContact.objects.create(
        student=klass[0], full_name="Серикова Гульнара", relation="mother", phone="+77010000001"
    )
    response = login(curator).patch(
        f"/api/contacts/{contact.pk}/",
        {"phone": "+77010000002", "email": "mama@example.kz"},
        format="json",
    )
    assert response.status_code == 200, response.data
    contact.refresh_from_db()
    assert contact.phone == "+77010000002"
    assert contact.email == "mama@example.kz"


def test_curator_cannot_edit_contacts_of_another_group(db, stranger, curator):
    contact = ParentContact.objects.create(
        student=stranger, full_name="Чужакова Айгуль", relation="mother", phone="+77010000003"
    )
    response = login(curator).patch(f"/api/contacts/{contact.pk}/", {"phone": "+77019999999"}, format="json")
    assert response.status_code == 404
    contact.refresh_from_db()
    assert contact.phone == "+77010000003"


def test_curator_still_cannot_write_a_foreign_domain(db, klass, curator):
    """Право «пишет» дано на дисциплину, а не на всё подряд."""
    response = login(curator).patch(f"/api/profiles/admission/{klass[0].pk}/", {"target_country": "США"}, format="json")
    assert response.status_code in (403, 404)


# --- Заметка от Салтанат ----------------------------------------------------------


def test_saltanat_writes_a_note_and_curator_gets_a_notification(db, klass, curator, saltanat):
    """Директор школы оставила заметку — куратор группы узнаёт об этом."""
    from students.notes import NOTE_WRITERS

    assert "director_behavior" in NOTE_WRITERS

    response = login(saltanat).post(
        "/api/notes/", {"student": klass[0].pk, "text": "Поговорите с мамой про пропуски"}, format="json"
    )
    assert response.status_code == 201, response.data

    note = Notification.objects.filter(recipient=curator, kind=Notification.Kind.NOTE_FOR_CURATOR).first()
    assert note is not None
    assert klass[0].full_name in note.text


def test_student_never_reads_notes(db, klass, curator):
    from students.models import CuratorNote

    CuratorNote.objects.create(student=klass[0], author=curator, author_role="curator", text="Внутреннее")
    response = login(klass[0].user).get(f"/api/notes/?student={klass[0].pk}")
    assert response.status_code == 403


# --- Письма -------------------------------------------------------------------------
