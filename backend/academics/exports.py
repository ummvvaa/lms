"""Выгрузки учебной части в Excel — через общий `core.exports`.

Журнал: лист «Посещаемость» и лист «Оценки» одного журнала за период.
Посещаемость группы по урокам за день или месяц, успеваемость группы —
теми же колонками, что на экране. Импорта нет: оценки и расписание
вводятся в интерфейсе.
"""

from __future__ import annotations

from academics.calendar import WEEKDAYS_SHORT
from academics.marks import MARK_SHORT, MARK_WORDS, kind_label
from academics.results import CourseContext
from core.exports import Column, workbook_of_sheets
from students.models import Student


def journal_workbook(context: CourseContext, *, filename: str, request=None):
    """Два листа: посещаемость и оценки, строки — ученики, столбцы — уроки."""
    students = list(Student.objects.filter(pk__in=context.student_ids).order_by("last_name", "first_name", "id"))
    lessons = context.lessons

    def mark_column(lesson):
        title = f"{lesson.date:%d.%m} {WEEKDAYS_SHORT[lesson.date.weekday()]}"

        def value(student):
            mark = context.marks.get((lesson.pk, student.pk))
            if mark is None:
                return MARK_WORDS["unmarked"] if not lesson.is_marked else ""
            return MARK_WORDS[mark]

        return Column(title, value, 12)

    def grade_column(lesson):
        title = f"{lesson.date:%d.%m} {kind_label(lesson)}"

        def value(student):
            grade = context.grades.get((lesson.pk, student.pk))
            if grade is None:
                return ""
            return grade.value if lesson.kind == "fo" else f"{grade.value} из {lesson.max_score or ''}".strip()

        return Column(title, value, 12)

    attendance_columns = [Column("Ученик", lambda s: s.full_name, 30), *[mark_column(lesson) for lesson in lessons]]
    attendance_columns.append(
        Column("Пропуски", lambda s: context.stats(s.pk).absent + context.stats(s.pk).excused, 12)
    )
    grade_columns = [Column("Ученик", lambda s: s.full_name, 30), *[grade_column(lesson) for lesson in lessons]]
    grade_columns += [
        Column("Средний ФО", lambda s: context.stats(s.pk).fo_avg, 12),
        Column("СОР", lambda s: _fraction(context.stats(s.pk).sor_got, context.stats(s.pk).sor_max), 12),
        Column("СОЧ", lambda s: _fraction(context.stats(s.pk).soch_got, context.stats(s.pk).soch_max), 12),
        Column("Сейчас выходит", lambda s: context.stats(s.pk).quarter_grade, 14),
        Column("Итог", lambda s: context.stats(s.pk).final, 10),
    ]
    topic_columns = [
        Column("Дата", lambda lesson: lesson.date, 12),
        Column("Урок", lambda lesson: lesson.slot, 8),
        Column("Вид", kind_label, 10),
        Column("Тема", lambda lesson: lesson.topic, 40),
        Column("Домашнее задание", lambda lesson: lesson.homework, 40),
    ]
    return workbook_of_sheets(
        filename=filename,
        sheets=[
            ("Посещаемость", attendance_columns, students),
            ("Оценки", grade_columns, students),
            ("Темы", topic_columns, lessons),
        ],
        request=request,
    )


def _fraction(got: int, maximum: int) -> str:
    return f"{got} из {maximum}" if maximum else ""


def day_attendance_workbook(*, filename: str, slots: list[int], rows: list[dict], group_code: str, request=None):
    """Посещаемость группы за день: строки — ученики, столбцы — уроки дня."""
    columns = [Column("Ученик", lambda row: row["full_name"], 30)]
    for index, slot in enumerate(slots):
        columns.append(Column(f"{slot} урок", (lambda i: lambda row: _cell_words(row["cells"][i]))(index), 14))
    columns.append(Column("Пропусков", lambda row: row["absent"] + row["excused"], 12))
    columns.append(Column("Уроков с отметкой", lambda row: row["marked"], 16))
    return workbook_of_sheets(filename=filename, sheets=[(group_code, columns, rows)], request=request)


def _cell_words(cell: dict) -> str:
    if not cell.get("has_lesson"):
        return "нет урока"
    mark = cell.get("mark")
    if mark is None:
        return "не отмечен" if cell.get("started") else ""
    # опоздание с известным временем прихода — с минутами, как в клетке экрана
    if mark == "late" and cell.get("late_by") is not None:
        return f"{MARK_WORDS['late']} на {cell['late_by']} мин"
    return MARK_WORDS.get(mark, "")


def month_attendance_workbook(*, filename: str, days: list, rows: list[dict], group_code: str, request=None):
    """Посещаемость группы за месяц: в ячейке короткая отметка, справа процент."""
    columns = [Column("Ученик", lambda row: row["full_name"], 30)]
    for index, day in enumerate(days):
        columns.append(Column(f"{day:%d.%m}", (lambda i: lambda row: _month_cell(row["cells"][i]))(index), 8))
    columns.append(Column("Посещаемость, %", lambda row: row["pct"], 14))
    columns.append(Column("Без причины", lambda row: row["absent"], 12))
    columns.append(Column("По уважительной", lambda row: row["excused"], 14))
    return workbook_of_sheets(filename=filename, sheets=[(group_code, columns, rows)], request=request)


def _month_cell(cell: dict) -> str:
    parts = []
    for key in ("absent", "excused", "late"):
        if cell.get(key):
            parts.append(f"{cell[key]}{MARK_SHORT[key]}")
    # минуты опозданий дня, как в клетке экрана: «1оп 10»
    if cell.get("late") and cell.get("late_minutes"):
        parts[-1] = f"{parts[-1]} {cell['late_minutes']}"
    return " ".join(parts)


def group_grades_workbook(*, filename: str, subjects: list, rows: list[dict], group_code: str, request=None):
    """Успеваемость группы: строки — ученики, столбцы — предметы, справа посещаемость."""
    columns = [Column("Ученик", lambda row: row["full_name"], 30)]
    for index, subject in enumerate(subjects):
        columns.append(Column(subject["short_title"], (lambda i: lambda row: row["cells"][i]["text"])(index), 12))
    columns.append(Column("Посещаемость, %", lambda row: row["attendance_pct"], 14))
    return workbook_of_sheets(filename=filename, sheets=[(group_code, columns, rows)], request=request)
