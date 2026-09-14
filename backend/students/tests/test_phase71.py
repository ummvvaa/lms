"""Фаза 71: импорт по реестру соответствий.

Реестр — одно место, где записано «какая колонка какое поле какого домена
заполняет и как её разбирать». Здесь проверяется не «импорт работает»,
а обещания владельцу:

* **каждая колонка таблицы Асем доезжает до своего поля** — по тесту
  на колонку, через реестр, а не через свои списки;
* **срок паспорта не теряется** без ссылки на паспорт;
* **GPA один раз** — в блоке «Поступление», из «Экзаменов» убран;
* **почта и пароли — текст**: с логином не сверяются, предупреждений нет;
* **домены выбираются**: невыбранный не пишется и виден в отчёте;
* **права**: администратор — любые домены, владелец — свои плюс то, что
  реестр отдал его таблице, куратор — 403;
* **документация совпадает с кодом**: таблица в `ADMISSION_IMPORT.md`
  собрана из реестра, и тест это сверяет.
"""

# ruff: noqa: F811 — фикстуры фазы 65 импортированы по имени
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from students import admission_import, import_registry
from students.models import AttemptSource, ExamAttempt, StudentCredential, StudentDocument
from students.tests.test_phase65 import (  # noqa: F401 — фикстуры и книга той же таблицы
    HEADER_19,
    admin,
    asem,
    boston,
    chicago,
    curator,
    klass,
    kymbat,
    stranger,
)
from students.tests.test_phase68_import import FULL, card_block, load, row19

ROOT = Path("/repo") if Path("/repo/docs").is_dir() else Path(__file__).resolve().parents[3]


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def book_of(klass, **cells):
    from students.tests.test_phase65 import book

    return book({"Chicago ": (HEADER_19, [row19(klass[0].full_name, **{**FULL, **cells})])})


# --- Реестр: каждая колонка → своё поле ---------------------------------------


def test_the_registry_covers_every_column_of_the_table():
    """Все девятнадцать заголовков таблицы Асем находятся в реестре — и ни один дважды."""
    found = import_registry.read_columns(HEADER_19)
    # «№» — служебный, остальные восемнадцать — колонки данных
    assert len(found) == len(HEADER_19) - 1
    assert import_registry.unknown_columns(HEADER_19, found) == []


def test_common_app_email_wins_over_personal_email():
    """Порядок реестра разводит «Электронный адрес Common app» и «Электронный адрес»."""
    found = import_registry.read_columns(HEADER_19)
    assert HEADER_19[found["common_app_email"]].strip().lower().endswith("common app")
    assert HEADER_19[found["email"]] == "Электронный адрес"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("cell", "value", "getter"),
    [
        ("phone", "8 707 389 63 73", lambda s: s.admission.student_phone == "+77073896373"),
        ("email", "lichnaya@gmail.com", lambda s: s.admission.personal_email == "lichnaya@gmail.com"),
        ("common_app_email", "ca@commonapp.org", lambda s: s.admission.common_app_email == "ca@commonapp.org"),
        ("drive", "https://drive.google.com/x", lambda s: s.admission.drive_folder_url == "https://drive.google.com/x"),
        ("expiry", "2030-01-16", lambda s: s.admission.passport_expires_at == dt.date(2030, 1, 16)),
        ("gpa", "4.9", lambda s: s.exam.gpa == Decimal("4.9")),
    ],
)
def test_each_profile_column_reaches_its_field(klass, asem, cell, value, getter):
    """Колонка → поле профиля: телефон, две почты, папка, срок паспорта, GPA."""
    load(klass, asem, **{cell: value})
    student = klass[0]
    student.refresh_from_db()
    student.admission.refresh_from_db()
    student.exam.refresh_from_db()
    assert getter(student)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("cell", "exam", "slot", "score"),
    [
        ("ielts1", "IELTS", 1, "6.5"),
        ("ielts2", "IELTS", 2, "7.0"),
        ("ielts3", "IELTS", 3, "7.5"),
        ("sat1", "SAT", 1, "1310"),
        ("sat2", "SAT", 2, "1380"),
        ("sat3", "SAT", 3, "1430"),
    ],
)
def test_each_score_column_becomes_its_attempt(klass, asem, cell, exam, slot, score):
    """Колонка балла → попытка: место в таблице и есть номер попытки."""
    load(klass, asem, **{cell: score})
    rows = list(
        ExamAttempt.objects.filter(student=klass[0], exam_type=exam, source=AttemptSource.ADMISSION_IMPORT).order_by(
            "created_at", "id"
        )
    )
    assert rows[slot - 1].total_score == Decimal(score)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("cell", "doc_type"),
    [("passport", "passport"), ("transcript", "transcript"), ("recommendation", "recommendation")],
)
def test_each_link_column_becomes_its_document(klass, asem, cell, doc_type):
    load(klass, asem, **{cell: f"https://drive.google.com/{doc_type}"})
    assert StudentDocument.objects.filter(
        student=klass[0], doc_type=doc_type, external_url=f"https://drive.google.com/{doc_type}"
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(("cell", "kind"), [("email_password", "email"), ("common_app_password", "common_app")])
def test_each_password_column_reaches_the_store(klass, asem, cell, kind):
    load(klass, asem, **{cell: "Secret-1234"})
    assert StudentCredential.objects.filter(student=klass[0], kind=kind).exists()


# --- Три ошибки ---------------------------------------------------------------


@pytest.mark.django_db
def test_passport_expiry_survives_without_a_passport_link(klass, asem, curator):
    """Срок паспорта — поле профиля: без ссылки он раньше терялся вовсе."""
    load(klass, asem, passport="", expiry="16.01.2030")
    student = klass[0]
    student.admission.refresh_from_db()

    assert student.admission.passport_expires_at == dt.date(2030, 1, 16)
    assert not StudentDocument.objects.filter(student=student, doc_type="passport").exists()
    # и в блоке он виден — тоже без ссылки
    assert card_block(curator, student)["passport_expires_at"] == "2030-01-16"


@pytest.mark.django_db
def test_a_passport_link_that_comes_later_takes_the_stored_expiry(klass, asem):
    """Появилась ссылка — документ создаётся и берёт срок из поля профиля."""
    load(klass, asem, passport="", expiry="16.01.2030")
    load(klass, asem, passport="https://drive.google.com/passport", expiry="")

    document = StudentDocument.objects.get(student=klass[0], doc_type="passport")
    assert document.expires_at == dt.date(2030, 1, 16)


def test_gpa_is_shown_once_in_the_admission_block():
    """GPA остался у Кымбат в реестре, но блок «Экзамены» его не рисует."""
    from core import domains

    spec = domains.spec_of_field("students.ExamProfile", "gpa")
    assert spec is not None and spec.card == "none"
    assert domains.domain_of_field("students.ExamProfile", "gpa").code == "exam"


@pytest.mark.django_db
def test_the_block_carries_gpa_and_says_who_edits_it(klass, asem, kymbat, curator):
    load(klass, asem, gpa="4.7")
    student = klass[0]

    block = login(asem).get(f"/api/students/{student.pk}/").json()["admission_block"]
    assert block["gpa"] == 4.7
    # правит владелец домена экзаменов, не владелец блока
    assert block["may_edit_gpa"] is False
    by_kymbat = login(kymbat).get(f"/api/students/{student.pk}/").json()["admission_block"]
    assert by_kymbat["may_edit_gpa"] is True


@pytest.mark.django_db
def test_personal_email_is_written_as_is_without_any_check(klass, asem, curator):
    """Почта из таблицы — текст: логин не тронут, предупреждений нет."""
    student = klass[0]
    login_before = student.email
    record = load(klass, asem, email="lichnaya.pochta@gmail.com")

    student.refresh_from_db()
    student.admission.refresh_from_db()
    assert student.email == login_before
    assert student.admission.personal_email == "lichnaya.pochta@gmail.com"
    assert "не совпадает" not in record.report
    assert "заведите вход" not in record.report
    assert card_block(curator, student)["email"] == "lichnaya.pochta@gmail.com"


# --- Выбор доменов ---------------------------------------------------------------


@pytest.mark.django_db
def test_unselected_domain_is_not_written_and_is_reported(klass, admin):
    """Домен не выбран — колонка не пишется, и отчёт говорит об этом словами."""
    record = admission_import.apply(book_of(klass, gpa="4.9"), actor=admin, domains=["admission"])
    student = klass[0]
    student.exam.refresh_from_db()

    assert student.exam.gpa is None
    assert not ExamAttempt.objects.filter(student=student).exists()
    assert not StudentDocument.objects.filter(student=student).exists()
    # а своё — записано
    student.admission.refresh_from_db()
    assert student.admission.student_phone == "+77073896373"
    lines = [row["text"] for row in admission_import.report_rows(record)]
    assert any("колонка «Средний GPA» пропущена: домен «Экзамены» не выбран" == line for line in lines)
    assert record.domains == "admission"


@pytest.mark.django_db
def test_all_found_domains_are_selected_by_default(klass, asem):
    """Без выбора — все домены, для которых в файле нашлись колонки."""
    sheets = admission_import.parse(book_of(klass))
    assert admission_import.found_domains(sheets) == ["admission", "documents", "exam"]


@pytest.mark.django_db
def test_an_unknown_column_is_reported_not_rejected(klass, asem):
    header = [*HEADER_19, "Любимый цвет"]
    from students.tests.test_phase65 import book

    uploaded = book({"Chicago ": (header, [[*row19(klass[0].full_name, **FULL), "синий"]])})
    record = admission_import.apply(uploaded, actor=asem)

    assert record.students_updated == 1
    assert any("«Любимый цвет» не распознана" in row["text"] for row in admission_import.report_rows(record))


@pytest.mark.django_db
def test_the_report_counts_written_values_by_domain(klass, asem):
    record = load(klass, asem)
    lines = [row for row in admission_import.report_rows(record) if row["kind"] == "домен"]
    titles = {line["text"].split(":")[0] for line in lines}
    assert titles == {"Поступление", "Документы", "Экзамены"}
    assert all("записано значений — " in line["text"] for line in lines)


# --- Права -------------------------------------------------------------------------


def test_writable_domains_by_role(admin, asem, kymbat, curator):
    """Администратор — любые; Асем — свои и экзамены по исключению; куратор — ничего."""
    from core.domains import DOMAINS

    assert import_registry.writable_domains(admin) == set(DOMAINS)
    assert import_registry.writable_domains(asem) == {"admission", "documents", "exam"}
    assert import_registry.writable_domains(kymbat) == {"exam"}
    assert import_registry.writable_domains(curator) == set()


@pytest.mark.django_db
def test_the_owner_may_not_pick_a_domain_that_is_not_theirs(klass, asem):
    """Асем выбирает «Дисциплина» — отказ словами, ничего не записано."""
    answer = login(asem).post(
        "/api/admission-imports/apply/",
        {"file": book_of(klass), "domains": '["admission", "behavior"]'},
        format="multipart",
    )
    assert answer.status_code == 403
    assert "не принадлежит" in answer.json()["detail"]
    klass[0].admission.refresh_from_db()
    assert klass[0].admission.student_phone == ""


@pytest.mark.django_db
def test_the_curator_does_not_run_the_import_at_all(klass, curator):
    answer = login(curator).post("/api/admission-imports/apply/", {"file": book_of(klass)}, format="multipart")
    assert answer.status_code == 403


@pytest.mark.django_db
def test_the_admin_writes_any_domain(klass, admin):
    answer = login(admin).post(
        "/api/admission-imports/apply/",
        {"file": book_of(klass), "domains": '["admission", "exam", "documents"]'},
        format="multipart",
    )
    assert answer.status_code == 201, answer.content
    assert answer.json()["domains"] == ["admission", "exam", "documents"]


@pytest.mark.django_db
def test_preview_tells_which_found_domains_are_writable(klass, asem):
    answer = login(asem).post("/api/admission-imports/preview/", {"file": book_of(klass)}, format="multipart")
    assert answer.status_code == 200
    body = answer.json()
    assert body["domains"] == ["admission", "documents", "exam"]
    assert body["writable_domains"] == ["admission", "documents", "exam"]


# --- Повтор без дублей ---------------------------------------------------------


@pytest.mark.django_db
def test_a_second_import_updates_and_does_not_duplicate(klass, asem):
    load(klass, asem)
    load(klass, asem, ielts2="7.5", expiry="01.02.2031")
    student = klass[0]

    assert ExamAttempt.objects.filter(student=student, source=AttemptSource.ADMISSION_IMPORT).count() == 6
    assert StudentDocument.objects.filter(student=student).count() == 3
    assert StudentCredential.objects.filter(student=student).count() == 2
    student.admission.refresh_from_db()
    assert student.admission.passport_expires_at == dt.date(2031, 2, 1)


# --- Документация совпадает с кодом ----------------------------------------------


def test_the_doc_table_matches_the_registry():
    """Таблица соответствий в `ADMISSION_IMPORT.md` собрана из реестра — построчно."""
    text = (ROOT / "docs" / "ADMISSION_IMPORT.md").read_text(encoding="utf-8")
    for row in import_registry.as_rows():
        line = f"| {row['title']} | {row['aliases']} | {row['domain']} | {row['kind']} | {row['destination']} |"
        assert line in text, f"в документации нет строки реестра: {line}"
