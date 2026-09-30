"""Выгрузка таблиц в XLSX — один код на все экраны (фаза 61).

Куратор выгружает учеников, в фазе 62 тем же кодом уйдут документы,
в 63 — результаты пробников. Второй способ собрать книгу означал бы
две разные шапки и два разных формата даты в одном продукте.

Файл собирается в памяти по запросу и на сервере не хранится — как CV
портфолио: выгрузка ученика не должна лежать в каталоге ещё месяц.

Предпросмотр. Файл не скачивается сразу: сначала человек видит на экране ту
же таблицу и жмёт «Скачать xlsx». Данные предпросмотра собирает этот же код
из тех же колонок и строк (`table_payload`) — второй сборки, которая однажды
разошлась бы с файлом, нет. Ручка выгрузки одна: с `?preview=1` она отвечает
таблицей, без него — книгой.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Any

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.functional import Promise
from django.utils.translation import gettext as _

#: сколько строк листа уходит в предпросмотр. Файл отдаётся целиком; экрану
#: тысяча строк ни к чему — их число предпросмотр называет словами
PREVIEW_ROWS = 500


@dataclass(frozen=True)
class Column:
    """Колонка выгрузки: заголовок и как достать значение.

    Заголовок — на языке того, кто выгружает: `_()` или ленивая строка,
    в книгу он попадает строкой (`str`) в момент сборки.
    """

    title: str
    value: Callable[[Any], Any]
    #: ширина в символах — иначе Excel показывает «#####» вместо дат
    width: int = 18


def _cell(value: Any) -> Any:
    """Значение в том виде, в каком его поймёт Excel."""
    if value is None:
        return ""
    if isinstance(value, Promise):
        # ленивая подпись (слово-отметка, вариант выбора) — строкой на языке выгрузки
        return str(value)
    if isinstance(value, bool):
        return _("да") if value else _("нет")
    if isinstance(value, datetime):
        return timezone.localtime(value).replace(tzinfo=None)
    if isinstance(value, date):
        return value
    return value


def _shown(value: Any) -> str:
    """То же значение, каким человек увидит его в Excel: для экрана предпросмотра."""
    value = _cell(value)
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return "" if value is None else str(value)


def wants_preview(request) -> bool:
    """Просят таблицу на экран, а не файл: `?preview=1` или `preview` в теле."""
    if request is None:
        return False
    asked = request.query_params.get("preview") if hasattr(request, "query_params") else None
    if asked is None and isinstance(getattr(request, "data", None), dict):
        asked = request.data.get("preview")
    return str(asked or "").lower() in ("1", "true", "yes")


def table_payload(*, filename: str, sheets: Iterable[tuple[str, Iterable[Column], Iterable[Any]]]) -> dict:
    """Листы книги данными: те же колонки и те же строки, что уйдут в файл."""
    pages = []
    for title, columns, rows in sheets:
        columns, rows = list(columns), list(rows)
        pages.append(
            {
                "title": sheet_title(title),
                "columns": [str(column.title) for column in columns],
                "rows": [[_shown(column.value(row)) for column in columns] for row in rows[:PREVIEW_ROWS]],
                "total": len(rows),
            }
        )
    return {"filename": filename, "sheets": pages, "preview_rows": PREVIEW_ROWS}


#: Транслит для запасного имени файла: браузер без `filename*` сохранит
#: «Ahmetova Aliya — otchet za sentyabr 2026.pdf», а не «  2026.pdf»
TRANSLIT = str.maketrans(  # i18n-skip: таблица транслита, не текст
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
        "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya", "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u", "ү": "u",
        "һ": "h", "і": "i", "—": "-", "–": "-", "«": "", "»": "", "\u00a0": " ",
    }
)  # fmt: skip

#: Расширение по типу содержимого — запасное имя не должно потерять «.pdf»
EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/csv": ".csv",
}

#: Символы, которые Excel не пускает в имя листа
SHEET_FORBIDDEN = str.maketrans({c: " " for c in "\\/:*?[]"})


def ascii_filename(filename: str, content_type: str = "") -> str:
    """Запасное имя латиницей: транслит, остальное вычищается, расширение по типу."""
    import re

    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem, ext = filename, ""
    wanted = EXTENSIONS.get(content_type, f".{ext}" if ext else "")
    text = stem.lower().translate(TRANSLIT)
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9._ -]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .-")
    return (text or "export") + (wanted or "")


def _disposition(filename: str, content_type: str = "") -> str:
    """Имя файла для заголовка: латиницей в `filename`, точное — в `filename*`.

    Русское имя в обычном `filename` часть браузеров сохраняет кракозябрами,
    поэтому даём оба варианта, как советует RFC 6266. Запасное — транслитом,
    с расширением по типу файла (D61).
    """
    from urllib.parse import quote

    return f"attachment; filename=\"{ascii_filename(filename, content_type)}\"; filename*=UTF-8''{quote(filename)}"


def sheet_title(title: str) -> str:
    """Имя листа Excel: без `\\ / : * ? [ ]` и не длиннее 31 (D61)."""
    cleaned = " ".join(str(title).translate(SHEET_FORBIDDEN).split()).strip()
    return (cleaned or _("Лист"))[:31]


def file_response(*, content: bytes, filename: str, content_type: str) -> HttpResponse:
    """Собранный в памяти файл ответом на скачивание — с тем же заголовком, что у книг."""
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = _disposition(filename, content_type)
    response["Cache-Control"] = "private, no-store"
    return response


def workbook_response(
    *, filename: str, sheet: str, columns: Iterable[Column], rows: Iterable[Any], request=None
) -> HttpResponse:
    """Собрать книгу из одного листа и отдать её ответом на скачивание."""
    return workbook_of_sheets(filename=filename, sheets=[(sheet, list(columns), list(rows))], request=request)


def workbook_of_sheets(
    *, filename: str, sheets: Iterable[tuple[str, Iterable[Column], Iterable[Any]]], request=None
) -> HttpResponse:
    """Книга из нескольких листов: «лист — группа» (фаза 70).

    Лист отдают целиком: куратору — его группу, и ничего чужого в нём
    нет. Пустые листы не создаются — лист без строк человек открывает,
    ищет, чего в нём нет, и не находит.

    С `request`, который просит предпросмотр, отвечает таблицей для экрана.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    sheets = [(title, list(columns), list(rows)) for title, columns, rows in sheets]
    if wants_preview(request):
        response = JsonResponse(
            table_payload(filename=filename, sheets=sheets), json_dumps_params={"ensure_ascii": False}
        )
        response["Cache-Control"] = "private, no-store"
        return response

    book = Workbook()
    book.remove(book.active)

    for title, columns, rows in sheets:
        columns = list(columns)
        page = book.create_sheet(sheet_title(title))
        page.append([str(column.title) for column in columns])
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
        book.create_sheet(sheet_title(_("Пусто")))

    buffer = BytesIO()
    book.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = _disposition(
        filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Cache-Control"] = "private, no-store"
    return response
