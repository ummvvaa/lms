"""Фаза 68: каждая колонка таблицы Асем доезжает до карточки.

Импорт из фазы 65 раскладывает таблицу по четырём местам: профиль
поступления, домен экзаменов, документы, хранилище паролей. Здесь
проверяется не «импорт работает», а обещание владельцу: **каждая
колонка видна в карточке** — по колонке на проверку, через тот же
ответ, что читает экран куратора.

Отдельно три свойства, без которых импорт опасен: одна загрузка пишет
во все домены одной транзакцией; права после неё не меняются; повторная
загрузка обновляет, а не дублирует.
"""

# ruff: noqa: F811 — фикстуры фазы 65 импортированы по имени, и параметры тестов их «переопределяют»
from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from students import admission_import
from students.models import AttemptSource, ExamAttempt, StudentCredential, StudentDocument
from students.tests.test_phase65 import (  # noqa: F401 — фикстуры и книга той же таблицы
    HEADER_18,
    HEADER_19,
    admin,
    asem,
    book,
    boston,
    chicago,
    curator,
    klass,
    row18,
    stranger,
)


def row19(name: str, **cells) -> list:
    """Строка листа с почтой Common App — она стоит между двумя паролями."""
    base = row18(name, **cells)
    return base[:5] + [cells.get("common_app_email", "")] + base[5:]


FULL = {
    "phone": "8 707 389 63 73",
    "email_password": "Pass-Email-1",
    "common_app_password": "Pass-CA-2",
    "common_app_email": "serikov.ca@commonapp.org",
    "drive": "https://drive.google.com/drive/folders/serikov",
    "passport": "https://drive.google.com/file/d/passport-serikov",
    "expiry": "2028-05-01",
    "gpa": "4.7",
    "ielts1": "6.5",
    "ielts2": "7.0",
    "ielts3": "7.5",
    "sat1": "1310",
    "sat2": "1380",
    "sat3": "1430.0",
    "transcript": "https://drive.google.com/file/d/transcript-serikov",
    "recommendation": "https://drive.google.com/file/d/recommendation-serikov",
}


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def load(klass, asem, **overrides):
    """Загрузить лист BOSTON-вида (19 колонок) на первого ученика группы."""
    # почта по умолчанию — реестровая: несовпадение проверяется отдельно
    cells = {**FULL, "email": klass[0].email, **overrides}
    uploaded = book({"Chicago ": (HEADER_19, [row19(klass[0].full_name, **cells)])})
    return admission_import.apply(uploaded, actor=asem)


def card_block(curator, student) -> dict:
    return login(curator).get(f"/api/curator/students/{student.pk}/").json()["admission"]


# --- Колонка → карточка ---------------------------------------------------------


@pytest.mark.django_db
def test_phone_reaches_the_card(klass, asem, curator):
    load(klass, asem)
    assert card_block(curator, klass[0])["student_phone"] == "+77073896373"


@pytest.mark.django_db
def test_table_email_is_compared_but_the_registry_email_stays(klass, asem, curator):
    """Почта из таблицы сверяется с реестром и не переписывает вход ученика."""
    before = klass[0].email
    record = load(klass, asem, email="other@example.kz")
    klass[0].refresh_from_db()
    assert klass[0].email == before
    assert card_block(curator, klass[0])["email"] == before
    assert "не совпадает" in record.report


@pytest.mark.django_db
def test_both_passwords_reach_the_store_and_the_card_says_only_present(klass, asem, curator):
    load(klass, asem)
    block = card_block(curator, klass[0])
    assert {row["kind"]: row["present"] for row in block["credentials"]} == {"email": True, "common_app": True}
    assert StudentCredential.objects.filter(student=klass[0]).count() == 2
    assert "Pass-Email-1" not in str(block) and "Pass-CA-2" not in str(block)


@pytest.mark.django_db
def test_common_app_email_and_flag_reach_the_card(klass, asem, curator):
    load(klass, asem)
    assert card_block(curator, klass[0])["common_app_email"] == "serikov.ca@commonapp.org"
    klass[0].admission.refresh_from_db()
    assert klass[0].admission.has_common_app is True


@pytest.mark.django_db
def test_drive_folder_reaches_the_card(klass, asem, curator):
    load(klass, asem)
    assert card_block(curator, klass[0])["drive_folder_url"] == FULL["drive"]


@pytest.mark.django_db
def test_passport_link_and_expiry_reach_the_card(klass, asem, curator):
    load(klass, asem)
    passport = next(d for d in card_block(curator, klass[0])["documents"] if d["code"] == "passport")
    assert passport["is_link"] is True
    assert passport["external_url"] == FULL["passport"]
    assert passport["expires_at"] == "2028-05-01"


@pytest.mark.django_db
def test_gpa_reaches_the_exam_domain_and_the_card(klass, asem, curator):
    load(klass, asem)
    assert card_block(curator, klass[0])["gpa"] == 4.7
    klass[0].exam.refresh_from_db()
    assert klass[0].exam.gpa == Decimal("4.7")


@pytest.mark.django_db
def test_three_ielts_and_three_sat_reach_the_card(klass, asem, curator):
    """IELTS-1..3 и SAT-1..3 — шесть попыток, каждая видна, все «дата уточняется»."""
    load(klass, asem)
    attempts = card_block(curator, klass[0])["imported_attempts"]
    scores = sorted((a["exam"], a["score"]) for a in attempts)
    assert scores == [
        ("IELTS", 6.5),
        ("IELTS", 7.0),
        ("IELTS", 7.5),
        ("SAT", 1310.0),
        ("SAT", 1380.0),
        ("SAT", 1430.0),
    ]
    assert all(a["date_unknown"] for a in attempts)


@pytest.mark.django_db
def test_transcript_and_recommendation_reach_the_card(klass, asem, curator):
    load(klass, asem)
    documents = {d["code"]: d for d in card_block(curator, klass[0])["documents"]}
    assert documents["transcript"]["external_url"] == FULL["transcript"]
    assert documents["recommendation"]["external_url"] == FULL["recommendation"]


# --- Свойства загрузки ---------------------------------------------------------


@pytest.mark.django_db
def test_one_upload_writes_all_domains_in_one_transaction(klass, asem, monkeypatch):
    """Сбой на баллах откатывает и телефон, и пароли: половины таблицы не бывает."""

    def boom(*args, **kwargs):
        raise RuntimeError("сбой на середине")

    monkeypatch.setattr(admission_import, "_apply_scores", boom)
    with pytest.raises(RuntimeError):
        load(klass, asem)

    klass[0].admission.refresh_from_db()
    assert klass[0].admission.student_phone == ""
    assert not StudentCredential.objects.filter(student=klass[0]).exists()
    assert not StudentDocument.objects.filter(student=klass[0]).exists()


@pytest.mark.django_db
def test_rights_do_not_change_after_the_upload(klass, asem, curator, stranger):
    """Куратор чужой группы карточку не видит, ученик видит своё без паролей."""
    load(klass, asem)
    # чужому куратору — 404, как и до загрузки
    assert login(curator).get(f"/api/curator/students/{stranger.pk}/").status_code == 404

    mine = login(klass[0].user).get("/api/students/me/").json()
    assert mine["admission"]["student_phone"] == "+77073896373"
    assert "Pass-Email-1" not in str(mine)
    assert "ciphertext" not in str(mine)


@pytest.mark.django_db
def test_second_upload_updates_and_does_not_duplicate(klass, asem, curator):
    """Та же таблица дважды — те же шесть попыток, три документа и два пароля."""
    load(klass, asem)
    load(klass, asem, ielts2="7.5", gpa="4.8")

    assert ExamAttempt.objects.filter(student=klass[0], source=AttemptSource.ADMISSION_IMPORT).count() == 6
    assert StudentDocument.objects.filter(student=klass[0]).count() == 3
    assert StudentCredential.objects.filter(student=klass[0]).count() == 2
    block = card_block(curator, klass[0])
    assert block["gpa"] == 4.8
    ielts = sorted(a["score"] for a in block["imported_attempts"] if a["exam"] == "IELTS")
    assert ielts == [6.5, 7.5, 7.5]
