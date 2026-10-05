"""Чтение загруженной таблицы: заголовок и строки первого листа.

Общее чтение CSV и XLSX для импортов со своим разбором — справочник вузов,
стипендии, пробники, список учеников. Поля профилей учеников загружает
мастер импорта по реестру соответствий (`students.admission_import`,
`students.import_registry`): прежний импорт с ручным сопоставлением
колонок, который жил в этом модуле, убран 05.10.2026.
"""

from __future__ import annotations


def read_table(uploaded) -> tuple[list[str], list[list[str]]]:
    """Прочитать загруженный CSV/XLSX в заголовок и строки."""
    name = (uploaded.name or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        wb = load_workbook(uploaded, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header = [str(c).strip() if c is not None else "" for c in next(rows, [])]
        body = [["" if v is None else str(v).strip() for v in row] for row in rows]
        wb.close()
        return header, body

    import csv
    import io

    text = uploaded.read()
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], []
    return [c.strip() for c in rows[0]], [[c.strip() for c in r] for r in rows[1:]]
