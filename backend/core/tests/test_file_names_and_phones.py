"""D61: запасное имя файла транслитом с верным расширением, имя листа без запрещённых знаков.

И телефоны родителей: казахстанские номера приводятся к `+7XXXXXXXXXX`.
"""

from __future__ import annotations

import pytest

from core.exports import ascii_filename, sheet_title, workbook_of_sheets
from students.phones import normalize_kz


def test_fallback_name_is_transliterated_and_keeps_the_extension():
    assert (
        ascii_filename("Ахметова Алия — отчёт за сентябрь 2026.pdf", "application/pdf")
        == "ahmetova aliya - otchet za sentyabr 2026.pdf"
    )
    assert (
        ascii_filename("BOSTON — отчёты за сентябрь 2026.zip", "application/zip")
        == "boston - otchety za sentyabr 2026.zip"
    )
    assert ascii_filename("посещаемость-BOSTON-2026-09.xlsx") == "poseshchaemost-boston-2026-09.xlsx"
    assert ascii_filename("Ёжик.pdf", "application/pdf") == "ezhik.pdf"


def test_fallback_name_never_degenerates_to_an_empty_stem():
    assert ascii_filename("—.pdf", "application/pdf") == "export.pdf"
    assert ascii_filename("", "application/zip") == "export.zip"


def test_sheet_title_drops_forbidden_characters_and_fits_excel():
    assert sheet_title("BOSTON 1/2") == "BOSTON 1 2"
    assert sheet_title("a:b*c?d[e]f\\g") == "a b c d e f g"
    assert len(sheet_title("Очень длинное название листа, которое не влезает в Excel")) == 31
    assert sheet_title("") == "Лист"


def test_workbook_with_a_slash_in_the_sheet_name_is_built():
    from core.exports import Column

    response = workbook_of_sheets(filename="тест.xlsx", sheets=[("BOSTON 1/2", [Column("A", lambda r: r)], ["x"])])
    assert response.status_code == 200
    assert 'filename="test.xlsx"' in response["Content-Disposition"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8 707 123 45 67", "+77071234567"),
        ("+7 (707) 123-45-67", "+77071234567"),
        ("77071234567", "+77071234567"),
        ("7071234567", "+77071234567"),
        ("+1 650 555 0101", "+1 650 555 0101"),
        ("+998 90 123 45 67", "+998 90 123 45 67"),
        ("123", "123"),
        ("", ""),
    ],
)
def test_kazakh_phones_are_normalized_and_others_left_alone(raw, expected):
    assert normalize_kz(raw) == expected


@pytest.mark.django_db
def test_parent_contact_saves_a_normalized_phone(student):
    from students.models import ContactRelation, ParentContact

    row = ParentContact.objects.create(
        student=student, full_name="Мама", relation=ContactRelation.MOTHER, phone="8 (707) 123 45 67"
    )
    assert row.phone == "+77071234567"
