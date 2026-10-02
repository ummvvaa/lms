"""Состав подгрупп английского файлом школы: проверка, запись, повтор.

Ученики вымышленные. Поток BOSTON + CHICAGO: две подгруппы EEP и одна GE
(у ученика одна из них). Файл — «Подгруппа | ФИО | Группа».
"""

from __future__ import annotations

import datetime as dt
import io

import pytest
from openpyxl import Workbook

from academics.cohorts import make_stream, member_ids
from academics.models import Cohort, CohortKind, CohortMembership, Subject
from academics.subgroup_members import plan, subgroup_key
from academics.tests.conftest import login, make_student
from core.models import AuditLog

pytestmark = pytest.mark.django_db

URL = "/api/acad/cohorts/members/"


@pytest.fixture
def english(subjects, cohorts, pupils):
    # как в школе: EEP и GE — разные потоки и предметы, но из одних групп
    parts = [cohorts["boston"], cohorts["chicago"]]
    eep, ge = make_stream(name="EEP", parts=parts), make_stream(name="GE", parts=parts)
    general = Subject.objects.create(code="ge", title="Английский язык (GE)", short_title="Англ. GE", order=4)
    made = {}
    for name, stream, subject in (
        ("EEP-1", eep, subjects["eng"]),
        ("EEP-2", eep, subjects["eng"]),
        ("GE-1", ge, general),
    ):
        made[name] = Cohort.objects.create(kind=CohortKind.SUBGROUP, stream=stream, subject=subject, name=name)
    return made


def book(*rows, header=("Подгруппа", "ФИО", "Группа"), title="Лист1") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    sheet.append(["Состав подгрупп английского"])  # заголовок над таблицей не мешает
    sheet.append(list(header))
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def upload(client, content: bytes, **extra):
    file = io.BytesIO(content)
    file.name = "состав.xlsx"
    return client.post(URL, {"file": file, **extra}, format="multipart")


FULL = (
    ("EEP-1", "Ахметова Алия", "BOSTON"),
    ("ЕЕР-1", "Сериков Дамир", "BOSTON"),  # кириллица в названии подгруппы
    ("GE-1", "Абдрахман Нурай", "BOSTON"),
    ("EEP-2", "Чужестранцев Ерлан", "CHICAGO"),
)


def test_subgroup_names_match_whatever_the_alphabet():
    assert subgroup_key("ЕЕР 8 – 1") == subgroup_key("EEP8-1") == "EEP8-1"
    assert subgroup_key("ГЕ-10.1-2") == "GE-10.1-2"


def test_preview_writes_nothing_and_apply_sets_members_from_the_year_start(english, pupils, kymbat, year):
    client = login(kymbat)
    preview = upload(client, book(*FULL))
    assert preview.status_code == 200, preview.content
    data = preview.json()
    assert data["ok"] is True and data["errors"] == []
    assert {row["name"]: row["students"] for row in data["subgroups"]} == {"EEP-1": 2, "EEP-2": 1, "GE-1": 1}
    assert not CohortMembership.objects.filter(cohort__in=english.values()).exists(), "проверка ничего не пишет"

    applied = upload(client, book(*FULL), apply="true")
    assert applied.status_code == 200, applied.content
    assert applied.json()["applied"] is True
    assert set(member_ids(english["EEP-1"])) == {pupils["aliya"].pk, pupils["damir"].pk}
    assert member_ids(english["GE-1"]) == [pupils["nurai"].pk]
    assert {row.since for row in CohortMembership.objects.filter(cohort__in=english.values())} == {year.starts}
    assert AuditLog.objects.filter(new_value__startswith="Изменён состав EEP-1", source="import").exists()

    # повтор того же файла ничего не удваивает
    upload(client, book(*FULL), apply="true")
    assert CohortMembership.objects.filter(cohort__in=english.values(), until__isnull=True).count() == 4


def test_student_in_two_subgroups_is_an_error_and_nothing_is_written(english, kymbat):
    client = login(kymbat)
    rows = (*FULL, ("GE-1", "Ахметова Алия", "BOSTON"))
    response = upload(client, book(*rows), apply="true")
    assert response.status_code == 400
    assert any("у ученика одна подгруппа" in text for text in response.json()["errors"])
    assert not CohortMembership.objects.filter(cohort__in=english.values()).exists()


def test_unknown_subgroup_student_or_group_is_named(english, kymbat):
    data = upload(
        login(kymbat),
        book(
            ("EEP-9", "Ахметова Алия", "BOSTON"),
            ("EEP-1", "Несуществующий Ученик", "BOSTON"),
            ("EEP-1", "Сериков Дамир", "LONDON"),
        ),
    ).json()
    texts = " ".join(data["errors"])
    assert "подгруппы «EEP-9» нет" in texts
    assert "ученика «Несуществующий Ученик» нет" in texts
    assert "группы «LONDON» нет" in texts
    assert data["ok"] is False


def test_moving_to_another_english_closes_the_old_subgroup(english, pupils, kymbat):
    client = login(kymbat)
    upload(client, book(*FULL), apply="true", since="2026-09-01")
    # Алия перешла из EEP в GE; EEP-1 в новом файле нет вовсе
    moved = (("GE-1", "Ахметова Алия", "BOSTON"), ("GE-1", "Абдрахман Нурай", "BOSTON"))
    response = upload(client, book(*moved), apply="true", since="2026-10-05")
    assert response.status_code == 200, response.content
    assert pupils["aliya"].pk not in member_ids(english["EEP-1"], dt.date(2026, 10, 6))
    assert pupils["aliya"].pk in member_ids(english["EEP-1"], dt.date(2026, 9, 20)), "прошлое не переписывается"
    assert set(member_ids(english["GE-1"], dt.date(2026, 10, 6))) == {pupils["aliya"].pk, pupils["nurai"].pk}
    # Дамира в новом файле нет — его состав не тронут
    assert pupils["damir"].pk in member_ids(english["EEP-1"], dt.date(2026, 10, 6))


def test_students_left_out_and_subgroups_left_out_are_warned(english, kymbat):
    data = upload(login(kymbat), book(("EEP-1", "Ахметова Алия", "BOSTON"))).json()
    texts = " ".join(data["warnings"])
    assert "EEP-2" in texts and "состав не меняется" in texts
    assert "Сериков Дамир" in texts and "английского в расписании у них не будет" in texts


def test_sheet_named_as_a_subgroup_and_split_name_columns(english, pupils):
    content = book(("Ахметова", "Алия"), ("Сериков", "Дамир"), header=("Фамилия", "Имя"), title="EEP-1")
    found = plan(content)
    assert found.errors == []
    assert found.wanted == {english["EEP-1"].pk: [pupils["aliya"].pk, pupils["damir"].pk]}
    other = plan(book(("Ахметова", "Алия"), header=("Фамилия", "Имя"), title="Лист1"))
    assert any("нет колонки «Подгруппа»" in text for text in other.errors)


def test_without_group_column_the_student_is_found_in_the_stream_groups(english, pupils):
    found = plan(book(("EEP-2", "Чужестранцев Ерлан"), header=("Подгруппа", "Ученик")))
    assert found.errors == []
    assert found.wanted == {english["EEP-2"].pk: [pupils["stranger"].pk]}


def test_namesakes_are_not_guessed(english, boston, kymbat):
    make_student(boston, "Ахметова", "Алия", "aliya2@example.kz")
    data = upload(login(kymbat), book(("EEP-1", "Ахметова Алия", "BOSTON"))).json()
    assert any("похожих учеников несколько" in text for text in data["errors"])


def test_only_schedule_editors_load_members(english, curator, teacher, admin):
    content = book(*FULL)
    assert upload(login(curator), content).status_code == 403
    assert upload(login(teacher), content).status_code in (403, 404)
    assert upload(login(admin), content).status_code == 200
