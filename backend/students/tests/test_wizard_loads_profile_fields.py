"""Мастер импорта загружает поля профилей всех доменов (D43, второй шаг).

Вкладка «Поля по CSV» с ручным сопоставлением жила рядом с мастером, пока
он знал только колонки таблицы поступления. Здесь — умения, которыми мастер
её заменяет: значения «как в карточке», ключ ученика по почте и логину,
лист без группы, ручное назначение колонки, 8–10 по домену, отмена загрузки.
"""

# ruff: noqa: F811 — фикстуры таблицы поступления приходят импортом и стоят параметрами тестов

from __future__ import annotations

import pytest

from core.models import AuditLog
from students import admission_import
from students.tests.test_admission_import_and_credentials import (  # noqa: F401 — фикстуры той же таблицы
    admin,
    asem,
    book,
    boston,
    chicago,
    klass,
    kymbat,
    login,
    stranger,
)

pytestmark = pytest.mark.django_db


def rows_of(sheets):
    return [row for sheet in sheets for row in sheet.rows]


# --- Значения «как в карточке» -----------------------------------------------------


def test_profile_fields_are_recognised_next_to_the_table_columns(klass, admin):
    """Колонки полей профилей узнаются в том же листе, что ФИО и телефон."""
    header = ["ФИО", "Номер телефона", "Целевая страна", "ielts цель", "Статус по дисциплине", "Что-то своё"]
    uploaded = book({"Chicago": (header, [[klass[0].full_name, "8 707 389 63 73", "Канада", "7.5", "зелёный", "x"]])})
    sheets = admission_import.parse(uploaded, actor=admin)
    assert sheets[0].columns == ["name", "phone", "behavior_status", "target_country", "ielts_target"]
    assert sheets[0].unknown == ["Что-то своё"]
    payload = admission_import.preview_payload(sheets)
    by_key = {column["key"]: column for column in payload["columns"]}
    assert by_key["ielts_target"]["domain"] == "exam" and by_key["behavior_status"]["domain"] == "behavior"
    # порядок доменов — порядок реестра: таблица поступления, затем поля профилей
    assert payload["domains"] == ["admission", "exam", "behavior"]


def test_value_is_checked_like_in_the_card_and_written_with_the_journal(klass, admin):
    """Вариант из списка — подписью, число — в границах; запись идёт в журнал источником «импорт»."""
    student = klass[0]
    header = ["ФИО", "ielts цель", "Уровень обучения", "Кабинет подачи", "Часов в неделю"]
    uploaded = book({"Chicago": (header, [[student.full_name, "7.5", "Бакалавриат", "да", "6"]])})
    record = admission_import.apply(uploaded, actor=admin)
    student.exam.refresh_from_db()
    student.admission.refresh_from_db()
    assert str(student.exam.ielts_target) == "7.5" and student.exam.hours_per_week == 6
    assert student.admission.has_application_account is True and student.admission.target_level == "bachelor"
    assert record.students_updated == 1
    entries = AuditLog.objects.filter(source="import", field_name__in=["ielts_target", "hours_per_week"])
    assert entries.count() == 2 and {entry.actor_id for entry in entries} == {admin.pk}


def test_value_the_card_would_refuse_is_a_row_error_with_a_hint(klass, admin):
    """IELTS 12.5 — ошибка строки с диапазоном; соседняя строка загружается."""
    header = ["ФИО", "ielts"]
    uploaded = book({"Chicago": (header, [[klass[0].full_name, "12.5"], [klass[1].full_name, "6.5"]])})
    sheets = admission_import.parse(uploaded, actor=admin)
    bad, good = rows_of(sheets)
    assert "от 0 до 9" in bad.error and "IELTS" in bad.error
    assert not good.error and good.values == {"ielts_current": "6.5"}


def test_preview_says_what_will_be_overwritten(klass, admin):
    student = klass[0]
    student.exam.ielts_current = "6.0"
    student.exam.save(update_fields=["ielts_current"])
    uploaded = book({"Chicago": (["ФИО", "ielts"], [[student.full_name, "7.0"], [klass[1].full_name, "6.5"]])})
    payload = admission_import.preview_payload(admission_import.parse(uploaded, actor=admin))
    first, second = payload["sheets"][0]["rows"]
    assert [(o["old"], o["new"]) for o in first["overwrites"]] == [("6.0", "7.0")]
    assert second["overwrites"] == [] and payload["counts"]["overwrites"] == 1
    assert first["fields"] == [{"key": "ielts_current", "title": "Текущий балл IELTS", "value": "7.0"}]


def test_current_score_column_does_not_become_an_attempt(klass, admin):
    """«ielts» — текущий балл профиля, «IELTS-1» — попытка: одно в другое не попадает."""
    from students.models import ExamAttempt

    student = klass[0]
    uploaded = book({"Chicago": (["ФИО", "ielts", "IELTS-1"], [[student.full_name, "6.5", "7.0"]])})
    admission_import.apply(uploaded, actor=admin)
    student.exam.refresh_from_db()
    assert str(student.exam.ielts_current) == "6.5"
    assert [str(a.total_score) for a in ExamAttempt.objects.filter(student=student)] == ["7.0"]


def test_header_alike_for_fields_of_two_domains_is_left_to_the_person(klass, admin):
    """«Статус» похож и на дисциплину, и на поступление — мастер не угадывает."""
    uploaded = book({"Chicago": (["ФИО", "Статус"], [[klass[0].full_name, "A"]])})
    sheets = admission_import.parse(uploaded, actor=admin)
    assert sheets[0].columns == ["name"] and sheets[0].unknown == ["Статус"]


# --- Ключ ученика: почта или логин ---------------------------------------------------


def test_sheet_without_names_finds_students_by_email_or_login(klass, stranger, admin):
    """Колонки ФИО нет — ученика находит почта или логин, точным совпадением по всей школе."""
    by_login = klass[1]
    by_login.user.login = "erzhanova.m"
    by_login.user.save(update_fields=["login"])
    header = ["email", "ielts"]
    body = [[klass[0].email, "6.5"], ["ERZHANOVA.M", "7.0"], [stranger.email, "5.5"], ["nobody@example.kz", "6.0"]]
    sheets = admission_import.parse(book({"Chicago": (header, body)}), actor=admin)
    assert sheets[0].by_key and sheets[0].columns == ["student_key", "ielts_current"]
    first, second, other_group, missing = rows_of(sheets)
    assert (first.student, second.student) == (klass[0].pk, by_login.pk) and first.by_key
    # ключ ищет по всей школе: ученик другой группы найден, как и во вкладке «Поля по CSV»
    assert other_group.student == stranger.pk and not other_group.error
    assert missing.student is None and missing.error == "ученик с такой почтой или логином не найден"


def test_email_header_next_to_names_stays_the_personal_email(klass, admin):
    """С колонкой ФИО «почта» — личная почта в карточке, а не ключ (решение владельца)."""
    uploaded = book({"Chicago": (["ФИО", "Почта"], [[klass[0].full_name, "own@mail.kz"]])})
    sheets = admission_import.parse(uploaded, actor=admin)
    assert not sheets[0].by_key and sheets[0].columns == ["name", "email"]
    assert rows_of(sheets)[0].values == {"email": "own@mail.kz"}


def test_list_sheet_reads_table_fields_like_the_card_and_guesses_nothing(klass, admin):
    """В листе-списке телефон и GPA — «как в карточке»; признак Common App сам не ставится."""
    student = klass[0]
    header = ["логин", "Номер телефона", "GPA", "Электронный адрес Common App"]
    uploaded = book({"Chicago": (header, [[student.email, "8 707 000 00 00", "4.5", "ca@example.org"]])})
    admission_import.apply(uploaded, actor=admin)
    student.admission.refresh_from_db()
    student.exam.refresh_from_db()
    assert student.admission.student_phone == "8 707 000 00 00"
    assert student.admission.common_app_email == "ca@example.org" and student.admission.has_common_app is False
    assert str(student.exam.gpa) == "4.50"


def test_sheet_with_neither_names_nor_key_is_skipped_with_words(klass, admin):
    sheets = admission_import.parse(book({"Chicago": (["ielts", "sat"], [["6.5", "1300"]])}), actor=admin)
    assert "нет колонки с почтой или логином" in sheets[0].error and sheets[0].rows == []


# --- Лист без группы -------------------------------------------------------------------


def csv_file(text: str, name: str = "fields.csv"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


def test_list_sheet_needs_no_group(klass, stranger, admin):
    """Лист-список называется как угодно: учеников двух групп находит ключ."""
    uploaded = book({"Лист1": (["email", "ielts"], [[klass[0].email, "6.5"], [stranger.email, "7.0"]])})
    sheets = admission_import.parse(uploaded, actor=admin)
    assert not sheets[0].error and sheets[0].group_id is None
    assert [row.student for row in rows_of(sheets)] == [klass[0].pk, stranger.pk]
    payload = admission_import.preview_payload(sheets)
    assert payload["groups"] == [] and payload["list_rows"] == 2 and payload["counts"]["ready"] == 2


def test_csv_list_loads_without_choosing_a_group(klass, admin):
    """CSV со списком (ключ — почта) грузится без выбора группы, с любым разделителем."""
    record = admission_import.apply(csv_file(f"email;ielts\n{klass[0].email};6.5\n"), actor=admin)
    klass[0].exam.refresh_from_db()
    assert str(klass[0].exam.ielts_current) == "6.5" and record.students_updated == 1


def test_csv_with_names_still_asks_for_the_group(klass, admin):
    with pytest.raises(admission_import.FileRejected, match="укажите группу"):
        admission_import.parse(csv_file(f"ФИО,ielts\n{klass[0].full_name},6.5\n"), actor=admin)
    sheets = admission_import.parse(csv_file(f"ФИО,ielts\n{klass[0].full_name},6.5\n"), group="CHICAGO", actor=admin)
    assert rows_of(sheets)[0].student == klass[0].pk


def test_csv_in_a_wrong_encoding_is_refused_with_words(klass, admin):
    from django.core.files.uploadedfile import SimpleUploadedFile

    broken = SimpleUploadedFile("f.csv", "почта,ielts\nx@y.kz,6\n".encode("cp1251"), content_type="text/csv")
    with pytest.raises(admission_import.FileRejected, match="UTF-8"):
        admission_import.parse(broken, actor=admin)


def test_table_sheet_of_an_unknown_group_is_still_skipped(klass, admin):
    """Таблица с ФИО по-прежнему привязана к группе листа."""
    sheets = admission_import.parse(book({"Лист1": (["ФИО", "ielts"], [[klass[0].full_name, "6.5"]])}), actor=admin)
    assert "нет в системе" in sheets[0].error


# --- Ручное назначение колонки ---------------------------------------------------------


def test_person_assigns_a_column_the_wizard_did_not_recognise(klass, admin):
    """Произвольный заголовок назначается полю руками — слово человека главнее распознавания."""
    student = klass[0]
    header = ["кто", "балл за пробник", "Статус", "мусор"]
    uploaded = book({"Лист1": (header, [[student.email, "6.5", "B", "x"]])})
    assert "нет колонки с почтой" in admission_import.parse(uploaded, actor=admin)[0].error
    assigned = {"кто": "student_key", "балл за пробник": "ielts_current", "Статус": "admission_status", "мусор": ""}
    sheets = admission_import.parse(uploaded, actor=admin, assigned=assigned)
    assert sheets[0].by_key and sheets[0].columns == ["student_key", "admission_status", "ielts_current"]
    assert sheets[0].unknown == ["мусор"]
    admission_import.apply(uploaded, actor=admin, assigned=assigned)
    student.exam.refresh_from_db()
    student.admission.refresh_from_db()
    assert str(student.exam.ielts_current) == "6.5" and student.admission.status == "B"


def test_assignment_overrides_what_the_wizard_recognised(klass, admin):
    """«ielts» мастер кладёт в текущий балл; человек переназначил в цель — в цель и ляжет."""
    student = klass[0]
    uploaded = book({"Лист1": (["email", "ielts"], [[student.email, "7.5"]])})
    admission_import.apply(uploaded, actor=admin, assigned={"ielts": "ielts_target"})
    student.exam.refresh_from_db()
    assert str(student.exam.ielts_target) == "7.5" and student.exam.ielts_current is None


def test_preview_endpoint_takes_assignments_and_offers_the_registry(klass, admin):
    import json

    student = klass[0]
    uploaded = book({"Лист1": (["кто", "балл"], [[student.email, "6.5"]])})
    client = login(admin)
    answer = client.post(
        "/api/admission-imports/preview/",
        {"file": uploaded, "assigned": json.dumps({"кто": "student_key", "балл": "ielts_current", "x": "нет такого"})},
        format="multipart",
    ).json()
    assert [column["key"] for column in answer["columns"]] == ["ielts_current"]
    assert answer["columns"][0]["header"] == "балл" and answer["counts"]["ready"] == 1
    keys = {row["key"] for row in answer["assignable"]}
    assert {"name", "student_key", "phone", "ielts_1", "ielts_current", "sport_rank"} <= keys


# --- 8–10 классы: параллель закрывает домен, а не строку ----------------------------------


@pytest.fixture
def junior(db, make_user):
    from students.models import StudyGroup
    from students.tests.test_admission_import_and_credentials import make_student

    group = StudyGroup.objects.create(code="KIOTO", parallel=9)
    return make_student(group, "Младшев", "Тимур", "junior65@example.kz", make_user)


def test_junior_gets_discipline_and_sport_but_not_exams(junior, admin):
    """Дисциплина и спорт у 8–10 ведутся — загружаются; экзамены — нет, и об этом сказано."""
    header = ["email", "Статус по дисциплине", "Спортивный разряд", "ielts"]
    uploaded = book({"Лист1": (header, [[junior.email, "critical", "КМС", "6.5"]])})
    sheets = admission_import.parse(uploaded, actor=admin)
    row = rows_of(sheets)[0]
    assert not row.error and row.values == {"behavior_status": "critical", "sport_rank": "КМС"}
    assert row.warnings == ["«Экзамены» ведётся только у 11 параллели — значения пропущены"]
    admission_import.apply(uploaded, actor=admin)
    junior.behavior.refresh_from_db()
    junior.sport.refresh_from_db()
    junior.exam.refresh_from_db()
    assert junior.behavior.status == "critical" and junior.sport.rank == "КМС" and junior.exam.ielts_current is None


def test_junior_row_with_only_closed_domains_is_an_error_as_before(junior, admin):
    """Файл одних экзаменов ученику 8–10 не нужен: строка — ошибка, как в таблице поступления."""
    uploaded = book({"Лист1": (["email", "ielts", "Целевая страна"], [[junior.email, "6.5", "Канада"]])})
    row = rows_of(admission_import.parse(uploaded, actor=admin))[0]
    assert row.error == "поступление ведётся только у 11 параллели — строка пропущена"


# --- Отмена загрузки -------------------------------------------------------------------


def test_field_values_are_loaded_as_a_batch_per_domain_and_can_be_reverted(klass, admin):
    """Поля профилей идут пачкой на домен: её отменяют целиком, как загрузку вкладки «Поля по CSV»."""
    from core.imports import revert_batch
    from core.models import ImportBatch

    student = klass[0]
    student.exam.ielts_current = "6.0"
    student.exam.save(update_fields=["ielts_current"])
    uploaded = book({"Лист1": (["email", "ielts", "Целевая страна"], [[student.email, "7.0", "Канада"]])})
    record = admission_import.apply(uploaded, actor=admin)
    batches = {batch.domain_code: batch for batch in ImportBatch.objects.all()}
    assert set(batches) == {"exam", "admission"} and batches["exam"].file_name == record.file_name
    assert batches["exam"].rows_updated == 1 and batches["exam"].audit_entries.count() == 1
    assert "можно отменить целиком" in record.report

    revert_batch(batches["exam"], actor=admin)
    student.exam.refresh_from_db()
    student.admission.refresh_from_db()
    # экзамены вернулись, поступление — отдельная пачка — осталось
    assert str(student.exam.ielts_current) == "6.0" and student.admission.target_country == "Канада"


def test_table_columns_of_the_admission_table_stay_outside_the_batch(klass, asem):
    """Таблица поступления пишет как раньше: пачки и обещания отмены у неё нет."""
    from core.models import ImportBatch

    uploaded = book(
        {"Chicago": (["ФИО", "Номер телефона", "IELTS-1"], [[klass[0].full_name, "8 707 389 63 73", "6.5"]])}
    )
    record = admission_import.apply(uploaded, actor=asem)
    assert ImportBatch.objects.count() == 0 and "можно отменить" not in record.report
