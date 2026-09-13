"""Выгрузка таблиц в XLSX — один код на все экраны (фаза 61).

Куратор выгружает учеников, в фазе 62 тем же кодом уйдут документы,
в 63 — результаты пробников. Второй способ собрать книгу означал бы
две разные шапки и два разных формата даты в одном продукте.

Файл собирается в памяти по запросу и на сервере не хранится — как CV
портфолио: выгрузка ученика не должна лежать в каталоге ещё месяц.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Any

from django.http import HttpResponse
from django.utils import timezone


@dataclass(frozen=True)
class Column:
    """Колонка выгрузки: заголовок по-русски и как достать значение."""

    title: str
    value: Callable[[Any], Any]
    #: ширина в символах — иначе Excel показывает «#####» вместо дат
    width: int = 18


def _cell(value: Any) -> Any:
    """Значение в том виде, в каком его поймёт Excel."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, datetime):
        return timezone.localtime(value).replace(tzinfo=None)
    if isinstance(value, date):
        return value
    return value


def _disposition(filename: str) -> str:
    """Имя файла для заголовка: латиницей в `filename`, точное — в `filename*`.

    Русское имя в обычном `filename` часть браузеров сохраняет кракозябрами,
    поэтому даём оба варианта, как советует RFC 6266.
    """
    from urllib.parse import quote

    ascii_name = filename.encode("ascii", "ignore").decode() or "export.xlsx"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def workbook_response(*, filename: str, sheet: str, columns: Iterable[Column], rows: Iterable[Any]) -> HttpResponse:
    """Собрать книгу из одного листа и отдать её ответом на скачивание."""
    return workbook_of_sheets(filename=filename, sheets=[(sheet, list(columns), list(rows))])


def workbook_of_sheets(*, filename: str, sheets: Iterable[tuple[str, Iterable[Column], Iterable[Any]]]) -> HttpResponse:
    """Книга из нескольких листов: «лист — группа» (фаза 70).

    Лист отдают целиком: куратору — его группу, и ничего чужого в нём
    нет. Пустые листы не создаются — лист без строк человек открывает,
    ищет, чего в нём нет, и не находит.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    book = Workbook()
    book.remove(book.active)

    for title, columns, rows in sheets:
        columns = list(columns)
        page = book.create_sheet(title[:31])
        page.append([column.title for column in columns])
        for index, column in enumerate(columns, start=1):
            letter = page.cell(row=1, column=index).column_letter
            page.column_dimensions[letter].width = column.width
            page.cell(row=1, column=index).font = Font(bold=True)
            page.cell(row=1, column=index).alignment = Alignment(vertical="center")
        # шапка остаётся на месте при прокрутке: без этого таблицу на 250 строк
        # читать нечем — к двадцатой строке уже не помнишь, что в колонке
        page.freeze_panes = "A2"
        for row in rows:
            page.append([_cell(column.value(row)) for column in columns])

    if not book.sheetnames:
        book.create_sheet("Пусто")

    buffer = BytesIO()
    book.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = _disposition(filename)
    response["Cache-Control"] = "private, no-store"
    return response
