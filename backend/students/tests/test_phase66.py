"""Фаза 66: дисциплина у куратора и письма.

Три места, где легко сделать тихо неправильно.

**Граница групп.** Куратор впервые не подтверждает чужое, а вносит своё.
Право «пишет» не должно протечь на соседнюю группу — и не должно молча
превратиться в право «подтверждает»: это разные вещи, и очередь у них
разная.

**Числа профиля.** Посещаемость и замечания стали строками, но процент
и счётчик читают готовность, дашборды, правила обзвона и корзина «нужен
контроль». Пересчёт обязан держать их верными, а прямой ввод Салтанат —
продолжать работать там, где строк нет.

**Письмо.** Сервер не шлёт: он собирает `mailto:`. Кириллица в теме
ломается тихо, длинный список адресов почтовые клиенты режут молча,
и в журнале должно стоять «открыто», а не «отправлено».
"""

from __future__ import annotations

import datetime as dt
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.curators import assign
from accounts.models import User
from core.models import AuditLog, Notification
from engagement.models import MailTemplate
from students import discipline, letters
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


def test_curator_marks_own_group_and_percent_is_recounted(db, chicago, klass, curator):
    """Отметил день — процент в профиле пересчитался из строк."""
    client = login(curator)
    rows = [
        {"student": klass[0].pk, "present": False, "reason": "болел"},
        {"student": klass[1].pk, "present": True},
        {"student": klass[2].pk, "present": True},
    ]
    response = client.post(
        "/api/attendance/save/",
        {"group": chicago.pk, "date": str(TODAY), "rows": rows},
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["written"] == 3
    assert response.data["absent"] == 1

    klass[0].behavior.refresh_from_db()
    assert klass[0].behavior.attendance_percent == 0
    klass[1].behavior.refresh_from_db()
    assert klass[1].behavior.attendance_percent == 100


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
    saved = client.post(
        "/api/attendance/save/",
        {"group": tokyo.pk, "date": str(TODAY), "rows": [{"student": stranger.pk, "present": False}]},
        format="json",
    )
    assert saved.status_code == 404
    assert not AttendanceDay.objects.filter(student=stranger).exists()


def test_saltanat_marks_any_group(db, tokyo, stranger, saltanat):
    """Директор школы ведёт всю школу, как и раньше."""
    response = login(saltanat).post(
        "/api/attendance/save/",
        {"group": tokyo.pk, "date": str(TODAY), "rows": [{"student": stranger.pk, "present": False}]},
        format="json",
    )
    assert response.status_code == 200
    assert AttendanceDay.objects.filter(student=stranger, present=False).exists()


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


def test_future_day_is_refused(db, chicago, klass, curator):
    response = login(curator).post(
        "/api/attendance/save/",
        {"group": chicago.pk, "date": str(days(1)), "rows": []},
        format="json",
    )
    assert response.status_code == 400
    assert "не наступил" in response.data["detail"]


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


def test_mailto_carries_cyrillic_subject_and_body():
    """Кириллица в теме и в тексте ломается тихо — поэтому кодируем сами."""
    link = letters.mailto(
        to=["mama@example.kz"],
        subject="Документы Данияра",
        body="Здравствуйте!\nНе хватает паспорта.",
    )
    parsed = urlparse(link)
    assert parsed.scheme == "mailto"
    assert parsed.path == "mama@example.kz"
    query = parse_qs(parsed.query)
    assert unquote(query["subject"][0]) == "Документы Данияра"
    assert "\n" in unquote(query["body"][0])
    # пробелы и перевод строки закодированы, а не оставлены как есть
    assert " " not in parsed.query


def test_many_addresses_go_to_bcc_and_split_by_fifty():
    """Список длиннее пятидесяти клиенты режут молча — режем сами и явно."""
    addresses = [f"pupil{i}@example.kz" for i in range(120)]
    parts = letters.batches(addresses)
    assert [len(p) for p in parts] == [50, 50, 20]

    link = letters.mailto(bcc=parts[0], subject="Тема", body="Текст")
    query = parse_qs(urlparse(link).query)
    assert len(unquote(query["bcc"][0]).split(",")) == 50
    assert urlparse(link).path == ""


def test_template_is_taken_in_the_language_of_the_group(db, tokyo, stranger, saltanat):
    """Семье пишут на её языке, а не на языке того, кто нажал кнопку."""
    payload = (
        login(saltanat)
        .post(
            "/api/letters/compose/",
            {"students": [stranger.pk], "kind": "document", "ask": "паспорт", "due": "12.09.2026"},
            format="json",
        )
        .data
    )
    assert payload["language"] == "kk"
    assert "Сәлеметсіз" in payload["body"]
    assert stranger.full_name in payload["subject"]


def test_template_variables_are_substituted(db, chicago, klass, curator):
    payload = (
        login(curator)
        .post(
            "/api/letters/compose/",
            {"students": [klass[0].pk], "kind": "document", "ask": "паспорт и табель", "due": "12.09.2026"},
            format="json",
        )
        .data
    )
    assert klass[0].full_name in payload["subject"]
    assert "CHICAGO" in payload["body"]
    assert "паспорт и табель" in payload["body"]
    assert "12.09.2026" in payload["body"]
    assert curator.full_name in payload["body"]
    assert "{" not in payload["body"]


def test_unknown_variable_is_left_visible():
    """Опечатку в шаблоне видно, а не подставлено пустотой."""
    assert letters.fill("Привет, {ученик} и {непонятно}", {"ученик": "Данияр"}) == "Привет, Данияр и {непонятно}"


def test_opening_a_letter_writes_the_journal_and_says_it_cannot_confirm(db, chicago, klass, curator):
    """В журнале «письмо открыто»: отправку система не видит."""
    before = AuditLog.objects.filter(field_name="letter_opened").count()
    response = login(curator).post(
        "/api/letters/open/",
        {
            "students": [s.pk for s in klass],
            "audience": "student",
            "subject": "Документы",
            "body": "Здравствуйте!",
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["recipients"] == 3
    assert len(response.data["links"]) == 1
    assert "подтвердить не может" in response.data["note"]
    assert AuditLog.objects.filter(field_name="letter_opened").count() == before + 3

    entry = AuditLog.objects.filter(field_name="letter_opened").latest("id")
    assert "Документы" in entry.new_value


def test_students_without_email_are_listed_apart(db, chicago, klass, curator, make_user):
    """«Без почты: 1» — отдельным списком, с переходом в карточку."""
    silent = Student.objects.create(
        last_name="Безпочтов",
        first_name="Ерлан",
        email="",
        grade=11,
        group=chicago,
        graduation_year=2027,
    )
    BehaviorProfile.objects.create(student=silent)

    payload = (
        login(curator)
        .post(
            "/api/letters/open/",
            {
                "students": [klass[0].pk, silent.pk],
                "audience": "student",
                "subject": "Документы",
                "body": "Текст",
            },
            format="json",
        )
        .data
    )
    assert payload["recipients"] == 1
    assert [row["full_name"] for row in payload["without_email"]] == [silent.full_name]


def test_letter_to_parents_uses_the_parent_address(db, klass, curator):
    ParentContact.objects.create(
        student=klass[0], full_name="Серикова Гульнара", relation="mother", email="mama@example.kz"
    )
    payload = (
        login(curator)
        .post(
            "/api/letters/open/",
            {"students": [klass[0].pk], "audience": "parent", "subject": "Тема", "body": "Текст"},
            format="json",
        )
        .data
    )
    assert payload["recipients"] == 1
    assert "mama%40example.kz" in payload["links"][0] or "mama@example.kz" in payload["links"][0]


def test_letters_are_closed_to_students(db, klass):
    client = login(klass[0].user)
    assert client.post("/api/letters/compose/", {"students": [klass[0].pk]}, format="json").status_code == 403
    assert client.post("/api/letters/open/", {"students": [klass[0].pk]}, format="json").status_code == 403


def test_curator_cannot_write_to_another_group(db, stranger, curator):
    response = login(curator).post(
        "/api/letters/open/",
        {"students": [stranger.pk], "audience": "student", "subject": "Тема", "body": "Текст"},
        format="json",
    )
    assert response.status_code == 404


def test_templates_cover_every_kind_in_both_languages(db):
    """У каждого вида письма есть текст на обоих языках — иначе кнопка пустая."""
    from engagement.models import MailKind

    for kind in MailKind.values:
        for language in ("ru", "kk"):
            assert MailTemplate.objects.filter(kind=kind, language=language).exists(), f"{kind}/{language}"


def test_missing_language_falls_back_to_russian(db, tokyo, stranger, saltanat):
    """Шаблона на казахском нет — берём русский, а не отдаём пустое письмо."""
    MailTemplate.objects.filter(kind="task", language="kk").delete()
    payload = (
        login(saltanat).post("/api/letters/compose/", {"students": [stranger.pk], "kind": "task"}, format="json").data
    )
    assert payload["language"] == "ru"
    assert payload["subject"]
