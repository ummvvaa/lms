"""Предпросмотр выгрузки показывает то же, что ляжет в файл.

Ручка выгрузки одна: с `?preview=1` она отвечает таблицей, без него — книгой.
Оба ответа собирает `core/exports.py` из одних колонок и строк; тест держит
их вместе на значениях, которые чаще всего расходятся, — дата, время, «да/нет»,
пустота, число.
"""

from __future__ import annotations

import datetime as dt
import json
from io import BytesIO

from django.test import RequestFactory
from openpyxl import load_workbook
from rest_framework.request import Request

from core import exports
from core.exports import Column, table_payload, workbook_of_sheets, workbook_response

ROWS = [
    {"name": "Сериков Данияр", "day": dt.date(2026, 9, 7), "ok": True, "score": 7.5, "note": None},
    {"name": "Ахметова Айгерим", "day": dt.date(2026, 10, 1), "ok": False, "score": 1480, "note": "пересдача"},
]
COLUMNS = [
    Column("Ученик", lambda row: row["name"]),
    Column("День", lambda row: row["day"]),
    Column("Сдал", lambda row: row["ok"]),
    Column("Балл", lambda row: row["score"]),
    Column("Заметка", lambda row: row["note"]),
]


def ask(path: str) -> Request:
    return Request(RequestFactory().get(path))


def test_preview_and_file_come_from_the_same_request_handler():
    preview = workbook_response(
        filename="проба.xlsx", sheet="Лист", columns=COLUMNS, rows=ROWS, request=ask("/x/?preview=1")
    )
    assert preview["Content-Type"].startswith("application/json")
    payload = json.loads(preview.content)
    assert payload["filename"] == "проба.xlsx"
    sheet = payload["sheets"][0]
    assert sheet["columns"] == ["Ученик", "День", "Сдал", "Балл", "Заметка"]
    assert sheet["rows"][0] == ["Сериков Данияр", "07.09.2026", "да", "7.5", ""]
    assert sheet["rows"][1] == ["Ахметова Айгерим", "01.10.2026", "нет", "1480", "пересдача"]
    assert sheet["total"] == 2

    book = workbook_response(filename="проба.xlsx", sheet="Лист", columns=COLUMNS, rows=ROWS, request=ask("/x/"))
    assert "spreadsheetml" in book["Content-Type"]
    page = load_workbook(BytesIO(book.content))["Лист"]
    in_file = list(page.values)
    assert list(in_file[0]) == sheet["columns"]
    # те же значения: дата в файле — датой, в предпросмотре — так, как её покажет Excel
    assert in_file[1][0] == "Сериков Данияр" and in_file[1][1].date() == dt.date(2026, 9, 7)
    assert [in_file[1][2], in_file[2][2]] == ["да", "нет"]
    assert in_file[1][4] in ("", None)


def test_without_a_request_the_answer_is_always_a_file():
    book = workbook_of_sheets(filename="проба.xlsx", sheets=[("Лист", COLUMNS, ROWS)])
    assert "spreadsheetml" in book["Content-Type"]


def test_every_sheet_of_the_book_is_in_the_preview():
    payload = table_payload(
        filename="книга.xlsx", sheets=[("Chicago", COLUMNS, ROWS[:1]), ("Boston", COLUMNS, ROWS[1:])]
    )
    assert [page["title"] for page in payload["sheets"]] == ["Chicago", "Boston"]
    assert [page["total"] for page in payload["sheets"]] == [1, 1]


def test_a_long_sheet_is_cut_on_the_screen_and_says_so(monkeypatch):
    monkeypatch.setattr(exports, "PREVIEW_ROWS", 3)
    many = [{"name": f"Ученик {n}", "day": None, "ok": True, "score": n, "note": ""} for n in range(10)]
    page = table_payload(filename="много.xlsx", sheets=[("Лист", COLUMNS, many)])["sheets"][0]
    assert len(page["rows"]) == 3 and page["total"] == 10
