"""Фаза 65: данные поступления, пароли учеников и импорт таблицы Асем.

Здесь стерегутся три разные беды.

**Пароль утёк.** Пароль от почты ученика открывает его аккаунт целиком,
поэтому проверка не «работает ли показ», а «нет ли пароля где-то ещё»:
страж обходит ответы API и выгрузки под каждой ролью и ищет и открытый
текст, и шифртекст. Пропустить такую утечку глазами — легко.

**Балл уехал не тому или из ниоткуда.** В таблице Асем в клетках баллов
встречаются заметки себе («общ баллы или ссылки?») и даже даты. Попытка
из текста не создаётся; ученик ищется только внутри своей группы.

**Повторный запуск удвоил всё.** Таблица одноразовая, но её зальют
второй раз — и второй заход обязан обновлять, а не плодить.
"""

from __future__ import annotations

import datetime as dt
import io
import json
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient

from accounts.curators import assign
from accounts.models import User
from core import secrets
from core.models import AuditLog
from students import admission_import, credentials
from students.models import (
    AdmissionProfile,
    AttemptFormat,
    AttemptSource,
    BehaviorProfile,
    CredentialKind,
    DocumentStatus,
    DocumentType,
    ExamAttempt,
    ExamProfile,
    SportProfile,
    Student,
    StudentCredential,
    StudentDocument,
    StudyGroup,
    TalentProfile,
)

TODAY = timezone.localdate()

#: Заголовок обычного листа — восемнадцать колонок, как у Асем
HEADER_18 = [
    "№",
    "ФИО",
    "Номер телефона",
    "Электронный адрес",
    "Пароль от эл. адреса",
    "Пароль от Common app",
    "ссылка на папку студента в гугл драйве",
    "ссылка на паспорт",
    "срок годности паспорта",
    "Средний GPA\n",
    "IELTS-1",
    "IELTS-2",
    "IELTS-3",
    "SAT-1",
    "SAT-2",
    "SAT-3",
    "ссылка на табеля",
    "ссылка рек. письмо ",
]

#: BOSTON, MIT и HARVARD: девятнадцатая колонка — почта Common App между
#: двумя паролями. В настоящем файле её заголовок начинается с полусотни
#: переносов строки, поэтому здесь он такой же
HEADER_19 = HEADER_18[:5] + ["\n" * 50 + "Электронный адрес Common app"] + HEADER_18[5:]


def days(n: int) -> dt.date:
    return TODAY + dt.timedelta(days=n)


@pytest.fixture
def chicago(db) -> StudyGroup:
    return StudyGroup.objects.create(code="CHICAGO", grade=11)


@pytest.fixture
def boston(db) -> StudyGroup:
    return StudyGroup.objects.create(code="BOSTON", grade=11)


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
    return make_user("admin", "admin65@example.kz", full_name="Администратор")


@pytest.fixture
def asem(make_user) -> User:
    return make_user("director_admission", "asem65@example.kz", full_name="Асем")


@pytest.fixture
def kymbat(make_user) -> User:
    return make_user("director_exam", "kymbat65@example.kz", full_name="Кымбат")


@pytest.fixture
def curator(make_user, chicago, admin) -> User:
    user = make_user("curator", "curator65@example.kz", full_name="Асель Ермекова")
    assign(group=chicago, curator=user, since=days(-30), actor=admin)
    return user


@pytest.fixture
def klass(chicago, make_user) -> list[Student]:
    return [
        make_student(chicago, "Сериков", "Данияр", "serikov65@example.kz", make_user),
        make_student(chicago, "Ержанова", "Малика", "erzhanova65@example.kz", make_user),
        make_student(chicago, "Оспанов", "Тимур", "ospanov65@example.kz", make_user),
    ]


@pytest.fixture
def stranger(boston, make_user) -> Student:
    return make_student(boston, "Чужаков", "Арман", "stranger65@example.kz", make_user)


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def book(sheets: dict[str, tuple[list, list[list]]], name: str = "postuplenie.xlsx") -> SimpleUploadedFile:
    """Книга Асем: по листу на группу, первая строка — заголовок."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, (header, rows) in sheets.items():
        page = workbook.create_sheet(title=sheet_name)
        page.append(header)
        for row in rows:
            page.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def row18(name: str, **cells) -> list:
    """Строка обычного листа: пустая ячейка значит «не знаю»."""
    order = [
        "phone",
        "email",
        "email_password",
        "common_app_password",
        "drive",
        "passport",
        "expiry",
        "gpa",
        "ielts1",
        "ielts2",
        "ielts3",
        "sat1",
        "sat2",
        "sat3",
        "transcript",
        "recommendation",
    ]
    return ["1.0", name] + [cells.get(key, "") for key in order]


# --- Шифрование и ключ -------------------------------------------------------


def test_password_lives_in_base_only_as_ciphertext(db, klass, asem):
    """В колонке — шифртекст; открытый текст восстанавливается только ключом."""
    student = klass[0]
    credentials.set_credential(student, CredentialKind.EMAIL, "Almaty2010!", actor=asem)

    row = StudentCredential.objects.get(student=student, kind=CredentialKind.EMAIL)
    assert "Almaty2010!" not in row.ciphertext
    assert secrets.decrypt(row.ciphertext) == "Almaty2010!"


def test_wrong_key_does_not_open_passwords(db, klass, asem, settings):
    """Чужой ключ — не «пусто», а честный отказ: так видно подмену ключа."""
    from cryptography.fernet import Fernet

    student = klass[0]
    credentials.set_credential(student, CredentialKind.EMAIL, "Almaty2010!", actor=asem)

    settings.CREDENTIALS_KEY = Fernet.generate_key().decode()
    with pytest.raises(secrets.KeyMismatch):
        credentials.reveal(student, CredentialKind.EMAIL, actor=asem)


def test_production_refuses_to_start_without_key(monkeypatch):
    """Без ключа боевой контур не поднимается: пароли иначе не прочесть."""
    import importlib

    from django.core.exceptions import ImproperlyConfigured

    for name, value in {
        "DJANGO_SECRET_KEY": "x" * 60,
        "DJANGO_ALLOWED_HOSTS": "lms.bhs.kz",
        "DJANGO_ADMIN_PATH": "secret-door/",
        "CREDENTIALS_KEY": "",
    }.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ImproperlyConfigured, match="CREDENTIALS_KEY"):
        importlib.reload(importlib.import_module("config.settings.prod"))


def test_preflight_checks_that_the_key_decrypts_a_control_record(db, settings):
    """`preflight` проверяет не наличие переменной, а что ключ — тот самый."""
    from cryptography.fernet import Fernet

    from core.secrets import ensure_key_check, verify_key

    ensure_key_check()
    ok, detail = verify_key()
    assert ok, detail

    settings.CREDENTIALS_KEY = Fernet.generate_key().decode()
    ok, detail = verify_key()
    assert not ok
    assert "другой ключ" in detail


def test_reveal_writes_a_journal_line(db, klass, asem):
    """Каждый показ — событие: кто, чей, когда."""
    student = klass[0]
    credentials.set_credential(student, CredentialKind.EMAIL, "Almaty2010!", actor=asem)
    before = AuditLog.objects.filter(field_name="credential_reveal").count()

    assert credentials.reveal(student, CredentialKind.EMAIL, actor=asem) == "Almaty2010!"

    entry = AuditLog.objects.filter(field_name="credential_reveal").latest("id")
    assert AuditLog.objects.filter(field_name="credential_reveal").count() == before + 1
    assert entry.actor_id == asem.pk
    assert entry.object_id == str(student.pk)


def test_reveal_endpoint_is_the_only_place_the_password_appears(db, klass, asem, curator, kymbat, admin):
    """Страж: ни открытый пароль, ни шифртекст не встречаются нигде, кроме показа.

    Обходятся ответы карточки, списков, поиска, журнала, очереди и выгрузок
    под каждой ролью, которой ученик виден. Дыра здесь стоит дороже всех
    остальных: это доступ к чужой почте.
    """
    student = klass[0]
    secret_word = "Qw3rty-Almaty-2010"
    credentials.set_credential(student, CredentialKind.EMAIL, secret_word, actor=asem)
    ciphertext = StudentCredential.objects.get(student=student, kind=CredentialKind.EMAIL).ciphertext

    routes = [
        f"/api/students/{student.pk}/",
        "/api/students/",
        f"/api/students/{student.pk}/history/",
        f"/api/profiles/admission/{student.pk}/",
        f"/api/students/{student.pk}/credentials/",
        f"/api/curator/students/{student.pk}/",
        "/api/curator/students/",
        "/api/curator/students/export/",
        "/api/suggestions/",
        f"/api/documents/?student={student.pk}",
        "/api/search/?q=" + student.last_name,
    ]
    for user in (asem, curator, kymbat, admin):
        client = login(user)
        for route in routes:
            response = client.get(route)
            if response.status_code >= 400:
                continue
            body = response.content.decode("utf-8", errors="replace")
            assert secret_word not in body, f"пароль открытым текстом в {route} у {user.role}"
            assert ciphertext not in body, f"шифртекст пароля в {route} у {user.role}"

    revealed = login(asem).post(
        f"/api/students/{student.pk}/credentials/reveal/", {"kind": CredentialKind.EMAIL}, format="json"
    )
    assert revealed.status_code == 200
    assert revealed.data["password"] == secret_word


def test_card_shows_only_whether_the_password_exists(db, klass, asem, curator):
    """В карточке — «есть / нет» и маска; самого пароля в ответе нет."""
    student = klass[0]
    credentials.set_credential(student, CredentialKind.EMAIL, "Almaty2010!", actor=asem)

    payload = login(curator).get(f"/api/curator/students/{student.pk}/").data["admission"]
    kinds = {row["kind"]: row["present"] for row in payload["credentials"]}
    assert kinds == {CredentialKind.EMAIL: True, CredentialKind.COMMON_APP: False}
    assert payload["may_reveal"] is True


def test_stranger_curator_sees_no_password_of_another_group(db, stranger, curator, asem):
    """Куратор чужой группы не видит и не показывает: ученик для него — 404."""
    credentials.set_credential(stranger, CredentialKind.EMAIL, "Almaty2010!", actor=asem)
    client = login(curator)
    assert client.get(f"/api/students/{stranger.pk}/credentials/").status_code == 404
    assert (
        client.post(
            f"/api/students/{stranger.pk}/credentials/reveal/", {"kind": CredentialKind.EMAIL}, format="json"
        ).status_code
        == 404
    )


def test_student_sees_and_changes_only_own_password(db, klass, asem):
    """Ученик — хозяин своих паролей и никаких чужих."""
    mine, other = klass[0], klass[1]
    credentials.set_credential(mine, CredentialKind.EMAIL, "Almaty2010!", actor=asem)
    credentials.set_credential(other, CredentialKind.EMAIL, "Astana2011!", actor=asem)

    client = login(mine.user)
    assert client.get(f"/api/students/{mine.pk}/credentials/").status_code == 200
    assert client.get(f"/api/students/{other.pk}/credentials/").status_code == 404

    changed = client.post(
        f"/api/students/{mine.pk}/credentials/set/",
        {"kind": CredentialKind.EMAIL, "password": "Novyi-Parol-9"},
        format="json",
    )
    assert changed.status_code == 200
    assert credentials.reveal(mine, CredentialKind.EMAIL, actor=asem) == "Novyi-Parol-9"


# --- Разбор таблицы ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("87753730924.0", "+77753730924"),
        ("=77715019917", "+77715019917"),
        ("8 707 389 63 73", "+77073896373"),
        ("8 (702) 814-69-99", "+77028146999"),
        ("7 707 506 8140", "+77075068140"),
        ("8700 207 1315", "+77002071315"),
        ("8(702)6879537", "+77026879537"),
        ("7475582017.0", "+77475582017"),
    ],
)
def test_every_phone_format_from_the_table(raw, expected):
    """Все формы номера из настоящей таблицы приходят к одному виду."""
    assert admission_import.parse_phone(raw) == expected


def test_unparseable_phone_is_a_row_error(db, chicago, klass, asem):
    """Номер, который не разбирается, — ошибка строки, а не тихая пустота."""
    upload = book({"CHICAGO": (HEADER_18, [row18("Сериков Данияр", phone="нет телефона")])})
    sheets = admission_import.parse(upload)
    assert sheets[0].rows[0].error.startswith("телефон")


@pytest.mark.parametrize(
    ("cells", "part"),
    [
        ({"email": "@gmail.com"}, "начинается с «@»"),
        ({"email": "danijar@mail.con"}, "«.con»"),
        ({"email": "danijar@gmail.ru"}, "«gmail.ru»"),
        ({"expiry": "если 2027 сентябрьге дейын просрочен"}, "записано словами"),
        ({"ielts1": "общ баллы или ссылки?"}, "не балл, а текст"),
        ({"ielts1": "9.7"}, "не по шкале"),
        ({"gpa": "отлично"}, "GPA не число"),
        ({"drive": "папка у Асем"}, "не похожа на адрес"),
    ],
)
def test_each_warning_of_the_parser(db, chicago, klass, cells, part):
    """Каждое предупреждение звучит словами и не роняет строку."""
    upload = book({"CHICAGO": (HEADER_18, [row18("Сериков Данияр", **cells)])})
    row = admission_import.parse(upload)[0].rows[0]
    assert not row.error
    assert any(part in warning for warning in row.warnings), row.warnings


def test_nineteen_column_sheet_reads_common_app_email(db, boston, stranger):
    """Лист с девятнадцатой колонкой: почта Common App не попадает в почту ученика."""
    row = ["1.0", "Чужаков Арман", "87001234567", "arman@gmail.com", "parol-pochty"]
    row += ["arman.commonapp@gmail.com", "parol-common-app"] + [""] * 12
    sheets = admission_import.parse(book({"BOSTON": (HEADER_19, [row])}))

    parsed = sheets[0].rows[0]
    assert parsed.values["email"] == "arman@gmail.com"
    assert parsed.values["common_app_email"] == "arman.commonapp@gmail.com"
    assert parsed.passwords == {"email": True, "common_app": True}


def test_sheet_without_a_group_is_skipped_whole(db, chicago, klass):
    """Лист, для которого нет группы, не разбирается: угадывать класс нельзя."""
    sheets = admission_import.parse(book({"Zurich": (HEADER_18, [row18("Кто-то Неизвестный")])}))
    assert sheets[0].error.startswith("Группы «ZURICH» нет")
    assert sheets[0].rows == []


def test_sheet_name_with_a_space_finds_its_group(db, chicago, klass):
    """`Chicago ` с хвостовым пробелом — это группа CHICAGO."""
    sheets = admission_import.parse(book({"Chicago ": (HEADER_18, [row18("Сериков Данияр")])}))
    assert sheets[0].group_id == chicago.pk
    assert sheets[0].rows[0].student is not None


def test_row_without_a_name_is_skipped_silently(db, chicago, klass):
    """Хвост листа без ФИО — не ошибка и не строка отчёта."""
    sheets = admission_import.parse(book({"CHICAGO": (HEADER_18, [row18(""), row18("Сериков Данияр")])}))
    assert len(sheets[0].rows) == 1


def test_unknown_surname_is_a_row_error_with_candidates(db, chicago, klass):
    """Ненайденная фамилия — ошибка строки: человек сопоставит или пропустит."""
    sheets = admission_import.parse(book({"CHICAGO": (HEADER_18, [row18("Неизвестнов Ерлан")])}))
    assert sheets[0].rows[0].error == "ученик не найден в этой группе"
    assert sheets[0].rows[0].student is None


def test_student_is_matched_only_inside_the_sheet_group(db, chicago, boston, klass, stranger):
    """Однофамилец из соседнего класса чужой строки не получает."""
    sheets = admission_import.parse(book({"CHICAGO": (HEADER_18, [row18("Чужаков Арман")])}))
    assert sheets[0].rows[0].student is None


# --- Применение --------------------------------------------------------------


def full_row(name: str) -> list:
    return row18(
        name,
        phone="8 (702) 814-69-99",
        email="serikov65@example.kz",
        email_password="Pochta-2010",
        common_app_password="CommonApp-2010",
        drive="https://drive.google.com/folder/serikov",
        passport="https://drive.google.com/passport/serikov",
        expiry=dt.datetime(2030, 5, 17),
        gpa="4.6",
        ielts1="6.5",
        sat1="1430.0",
        transcript="https://drive.google.com/transcript/serikov",
        recommendation="https://drive.google.com/rec/serikov",
    )


def test_apply_fills_the_admission_block(db, chicago, klass, asem):
    """Одна строка — телефон, папка, GPA, пароли, документы и попытки."""
    student = klass[0]
    record = admission_import.apply(book({"CHICAGO": (HEADER_18, [full_row("Сериков Данияр")])}), actor=asem)

    student.refresh_from_db()
    assert student.admission.student_phone == "+77028146999"
    assert student.admission.drive_folder_url.endswith("/folder/serikov")
    assert student.exam.gpa == Decimal("4.6")
    assert record.students_updated == 1
    assert record.credentials_saved == 2
    assert record.documents_created == 3
    assert record.attempts_created == 2


def test_imported_attempts_are_official_with_an_unknown_date(db, chicago, klass, asem):
    """Баллы — официальные попытки «импорт Асем» с флагом «дата не указана»."""
    student = klass[0]
    admission_import.apply(book({"CHICAGO": (HEADER_18, [full_row("Сериков Данияр")])}), actor=asem)

    attempts = {row.exam_type: row for row in ExamAttempt.objects.filter(student=student)}
    assert set(attempts) == {"IELTS", "SAT"}
    for row in attempts.values():
        assert row.attempt_format == AttemptFormat.OFFICIAL
        assert row.source == AttemptSource.ADMISSION_IMPORT
        assert row.date == TODAY
        assert row.date_unknown is True
    assert attempts["IELTS"].total_score == Decimal("6.5")
    assert attempts["SAT"].total_score == Decimal("1430")


def test_import_does_not_touch_the_current_score(db, chicago, klass, asem):
    """Текущий балл ведёт Кымбат: импорт кладёт попытки и не трогает профиль."""
    student = klass[0]
    student.exam.ielts_current = Decimal("7.0")
    student.exam.save(update_fields=["ielts_current"])

    admission_import.apply(book({"CHICAGO": (HEADER_18, [full_row("Сериков Данияр")])}), actor=asem)

    student.exam.refresh_from_db()
    assert student.exam.ielts_current == Decimal("7.0")


def test_text_in_a_score_cell_creates_no_attempt(db, chicago, klass, asem):
    """«общ баллы или ссылки?» — заметка Асем себе, а не результат экзамена."""
    student = klass[0]
    upload = book({"CHICAGO": (HEADER_18, [row18("Сериков Данияр", ielts1="общ баллы или ссылки?")])})
    record = admission_import.apply(upload, actor=asem)

    assert not ExamAttempt.objects.filter(student=student).exists()
    assert record.attempts_created == 0
    assert any("не балл, а текст" in row["text"] for row in admission_import.report_rows(record))


def test_second_run_updates_and_does_not_duplicate(db, chicago, klass, asem):
    """Повторный запуск таблицы: те же попытки, документы и пароли — обновляются."""
    student = klass[0]
    admission_import.apply(book({"CHICAGO": (HEADER_18, [full_row("Сериков Данияр")])}), actor=asem)

    changed = full_row("Сериков Данияр")
    changed[HEADER_18.index("IELTS-1")] = "7.0"
    second = admission_import.apply(book({"CHICAGO": (HEADER_18, [changed])}), actor=asem)

    assert ExamAttempt.objects.filter(student=student).count() == 2
    assert StudentDocument.objects.filter(student=student).count() == 3
    assert StudentCredential.objects.filter(student=student).count() == 2
    assert second.attempts_created == 0
    assert ExamAttempt.objects.get(student=student, exam_type="IELTS").total_score == Decimal("7.0")


def test_empty_cell_does_not_erase_what_is_already_there(db, chicago, klass, asem):
    """Пустота в таблице значит «не знаю», а не «сотрите то, что есть»."""
    student = klass[0]
    admission_import.apply(book({"CHICAGO": (HEADER_18, [full_row("Сериков Данияр")])}), actor=asem)

    admission_import.apply(book({"CHICAGO": (HEADER_18, [row18("Сериков Данияр")])}), actor=asem)

    student.refresh_from_db()
    assert student.admission.student_phone == "+77028146999"
    assert student.exam.gpa == Decimal("4.6")


def test_email_from_the_table_never_overwrites_the_registry(db, chicago, klass, asem):
    """Почта из таблицы — личная, текст в карточке (фаза 71): логин не трогает,
    с ним не сверяется и предупреждений о несовпадении не даёт."""
    student = klass[0]
    row = row18("Сериков Данияр", email="drugoy-adres@gmail.com")
    record = admission_import.apply(book({"CHICAGO": (HEADER_18, [row])}), actor=asem)

    student.refresh_from_db()
    assert student.email == "serikov65@example.kz"
    assert student.admission.personal_email == "drugoy-adres@gmail.com"
    assert not any("не совпадает" in line["text"] for line in admission_import.report_rows(record))


# --- Документы-ссылки --------------------------------------------------------


def test_links_become_documents_in_the_review_queue(db, chicago, klass, asem):
    """Ссылка — документ без файла, и проверку он проходит ту же, что файл."""
    from suggestions.models import Suggestion, SuggestionSource, SuggestionStatus

    student = klass[0]
    admission_import.apply(book({"CHICAGO": (HEADER_18, [full_row("Сериков Данияр")])}), actor=asem)

    passport = StudentDocument.objects.get(student=student, doc_type=DocumentType.PASSPORT)
    assert passport.is_link is True
    assert not passport.file
    assert passport.status == DocumentStatus.PENDING
    assert passport.expires_at == dt.date(2030, 5, 17)
    assert Suggestion.objects.filter(
        source_type=SuggestionSource.DOCUMENT,
        status=SuggestionStatus.PENDING,
        changes__object_id=str(passport.pk),
    ).exists()


def test_link_document_shows_its_own_mark_in_the_matrix(db, chicago, klass, asem, curator):
    """В матрице и чек-листе документ-ссылка отличим от файла."""
    from students import documents as documents_service
    from students.portfolio import documents_checklist

    student = klass[0]
    admission_import.apply(book({"CHICAGO": (HEADER_18, [full_row("Сериков Данияр")])}), actor=asem)

    cell = documents_service.state_of(Student.objects.filter(pk=student.pk))[student.pk]["cells"]
    assert cell[DocumentType.PASSPORT]["is_link"] is True
    assert cell[DocumentType.PASSPORT]["external_url"].endswith("/passport/serikov")

    line = next(row for row in documents_checklist(student) if row["code"] == DocumentType.PASSPORT)
    assert line["is_link"] is True


def test_link_document_opens_by_redirect_after_the_rights_check(db, chicago, klass, asem, curator, stranger):
    """Адрес открывается тем же маршрутом, что файл, и только своим."""
    student = klass[0]
    admission_import.apply(book({"CHICAGO": (HEADER_18, [full_row("Сериков Данияр")])}), actor=asem)
    passport = StudentDocument.objects.get(student=student, doc_type=DocumentType.PASSPORT)

    response = login(curator).get(f"/api/documents/{passport.pk}/file/")
    assert response.status_code == 302
    assert response["Location"].endswith("/passport/serikov")

    other_curator = login(stranger.user)
    assert other_curator.get(f"/api/documents/{passport.pk}/file/").status_code == 404


def test_passport_expiry_makes_the_document_expiring(db, chicago, klass, asem):
    """Срок паспорта из таблицы — это срок документа, и «истекает» считается по нему."""
    from django.conf import settings as conf

    student = klass[0]
    soon = TODAY + dt.timedelta(days=conf.CURATOR_RULES["DOCUMENT_EXPIRING_DAYS"] - 1)
    row = row18("Сериков Данияр", passport="https://drive.google.com/passport/serikov", expiry=soon)
    admission_import.apply(book({"CHICAGO": (HEADER_18, [row])}), actor=asem)

    passport = StudentDocument.objects.get(student=student, doc_type=DocumentType.PASSPORT)
    passport.status = DocumentStatus.CONFIRMED
    passport.save(update_fields=["status"])
    assert passport.is_expiring is True
    assert passport.state == "expiring"


# --- Права на мастер ---------------------------------------------------------


def test_wizard_is_open_to_admin_and_domain_owners(db, chicago, klass, asem, admin, curator, kymbat):
    """Мастер открыт администратору и владельцам доменов (фаза 72, право
    выровнено в 77-й: до того Кымбат получала 403 на экране, который ей
    показывали); куратор и ученик получают отказ словами."""
    upload = book({"CHICAGO": (HEADER_18, [full_row("Сериков Данияр")])})
    for user, expected in ((asem, 200), (admin, 200), (kymbat, 200), (curator, 403), (klass[0].user, 403)):
        upload.seek(0)
        response = login(user).post("/api/admission-imports/preview/", {"file": upload}, format="multipart")
        assert response.status_code == expected, user.role


def test_preview_writes_nothing_and_hides_passwords(db, chicago, klass, asem):
    """Шаг «Проверка» ничего не пишет, а пароли показывает только как «есть»."""
    upload = book({"CHICAGO": (HEADER_18, [full_row("Сериков Данияр")])})
    payload = login(asem).post("/api/admission-imports/preview/", {"file": upload}, format="multipart").data

    assert StudentCredential.objects.count() == 0
    assert ExamAttempt.objects.count() == 0
    row = payload["sheets"][0]["rows"][0]
    assert row["has_email_password"] is True
    body = json.dumps(payload, ensure_ascii=False, default=str)
    assert "Pochta-2010" not in body
    assert "CommonApp-2010" not in body


def test_apply_reports_everything_that_was_skipped(db, chicago, klass, asem):
    """Отчёт называет причину по каждой пропущенной строке и каждому листу."""
    sheets = {
        "CHICAGO": (HEADER_18, [full_row("Сериков Данияр"), row18("Неизвестнов Ерлан")]),
        "Zurich": (HEADER_18, [row18("Кто-то Неизвестный")]),
    }
    response = login(asem).post("/api/admission-imports/apply/", {"file": book(sheets)}, format="multipart")

    assert response.status_code == 201
    lines = response.data["rows"]
    assert any(line["kind"] == "лист" and "ZURICH" in line["text"] for line in lines)
    assert any(line["kind"] == "пропуск" and "не найден" in line["text"] for line in lines)
    assert response.data["students_updated"] == 1
    assert response.data["rows_skipped"] == 1
