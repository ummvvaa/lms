"""Выгрузки учебной части в Excel — через общий `core.exports`.

Журнал: лист «Посещаемость» и лист «Оценки» одного журнала за период.
Посещаемость группы по урокам за день или месяц, успеваемость группы —
теми же колонками, что на экране. Импорта нет: оценки и расписание
вводятся в интерфейсе.
"""

from __future__ import annotations

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from academics.calendar import WEEKDAYS_SHORT
from academics.marks import MARK_SHORT, MARK_WORDS, kind_label
from academics.results import CourseContext
from core.exports import Column, workbook_of_sheets
from students.models import Student

#: клетка «ДЗ» словами: проверено без оценки — «✓», ждёт проверки — «сдано»
HOMEWORK_WORDS = {"checked": "✓", "submitted": gettext_lazy("сдано"), "missed": "—", "pending": ""}


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
            if lesson.kind == "fo":
                return grade.value
            return _("{got} из {maximum}").format(got=grade.value, maximum=lesson.max_score or "").strip()

        return Column(title, value, 12)

    from homework import services as homework

    assignments = homework.assignments_map([lesson.pk for lesson in lessons])
    submissions = homework.submissions_map(list(assignments), [s.pk for s in students]) if assignments else {}

    def homework_column(lesson):
        """«ДЗ» рядом с уроком — так же, как в журнале на экране."""
        title = _("{date} ДЗ").format(date=f"{lesson.date:%d.%m}")

        def value(student):
            state = homework.journal_state(submissions.get((lesson.pk, student.pk)), assignments[lesson.pk])
            return HOMEWORK_WORDS[state["state"]] if state["grade"] is None else state["grade"]

        return Column(title, value, 10)

    def grades_with_homework():
        for lesson in lessons:
            yield grade_column(lesson)
            if lesson.pk in assignments:
                yield homework_column(lesson)

    attendance_columns = [Column(_("Ученик"), lambda s: s.full_name, 30), *[mark_column(lesson) for lesson in lessons]]
    attendance_columns.append(
        Column(_("Пропуски"), lambda s: context.stats(s.pk).absent + context.stats(s.pk).excused, 12)
    )
    grade_columns = [Column(_("Ученик"), lambda s: s.full_name, 30), *grades_with_homework()]
    grade_columns += [
        Column(_("Средний ФО"), lambda s: context.stats(s.pk).fo_avg, 12),
        Column(_("СОР"), lambda s: _fraction(context.stats(s.pk).sor_got, context.stats(s.pk).sor_max), 12),
        Column(_("СОЧ"), lambda s: _fraction(context.stats(s.pk).soch_got, context.stats(s.pk).soch_max), 12),
        Column(_("Сейчас выходит"), lambda s: context.stats(s.pk).quarter_grade, 14),
        Column(_("Итог"), lambda s: context.stats(s.pk).final, 10),
    ]
    topic_columns = [
        Column(_("Дата"), lambda lesson: lesson.date, 12),
        Column(_("Урок"), lambda lesson: lesson.slot, 8),
        Column(_("Вид"), kind_label, 10),
        Column(_("Тема"), lambda lesson: lesson.topic, 40),
        Column(_("Домашнее задание"), lambda lesson: lesson.homework, 40),
    ]
    return workbook_of_sheets(
        filename=filename,
        sheets=[
            (_("Посещаемость"), attendance_columns, students),
            (_("Оценки"), grade_columns, students),
            (_("Темы"), topic_columns, lessons),
        ],
        request=request,
    )


def _fraction(got: int, maximum: int) -> str:
    return _("{got} из {maximum}").format(got=got, maximum=maximum) if maximum else ""


def day_attendance_workbook(*, filename: str, slots: list[int], rows: list[dict], group_code: str, request=None):
    """Посещаемость группы за день: строки — ученики, столбцы — уроки дня."""
    columns = [Column(_("Ученик"), lambda row: row["full_name"], 30)]
    for index, slot in enumerate(slots):
        title = _("{slot} урок").format(slot=slot)
        columns.append(Column(title, (lambda i: lambda row: _cell_words(row["cells"][i]))(index), 14))
    columns.append(Column(_("Пропусков"), lambda row: row["absent"] + row["excused"], 12))
    columns.append(Column(_("Уроков с отметкой"), lambda row: row["marked"], 16))
    return workbook_of_sheets(filename=filename, sheets=[(group_code, columns, rows)], request=request)


def _cell_words(cell: dict) -> str:
    if not cell.get("has_lesson"):
        return _("нет урока")
    mark = cell.get("mark")
    if mark is None:
        return _("не отмечен") if cell.get("started") else ""
    # опоздание с известным временем прихода — с минутами, как в клетке экрана
    if mark == "late" and cell.get("late_by") is not None:
        return _("{late} на {minutes} мин").format(late=MARK_WORDS["late"], minutes=cell["late_by"])
    return str(MARK_WORDS.get(mark, ""))


def month_attendance_workbook(*, filename: str, days: list, rows: list[dict], group_code: str, request=None):
    """Посещаемость группы за месяц: в ячейке короткая отметка, справа процент."""
    columns = [Column(_("Ученик"), lambda row: row["full_name"], 30)]
    for index, day in enumerate(days):
        columns.append(Column(f"{day:%d.%m}", (lambda i: lambda row: _month_cell(row["cells"][i]))(index), 8))
    columns.append(Column(_("Посещаемость, %"), lambda row: row["pct"], 14))
    columns.append(Column(_("Без причины"), lambda row: row["absent"], 12))
    columns.append(Column(_("По уважительной"), lambda row: row["excused"], 14))
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
    columns = [Column(_("Ученик"), lambda row: row["full_name"], 30)]
    for index, subject in enumerate(subjects):
        columns.append(Column(subject["short_title"], (lambda i: lambda row: row["cells"][i]["text"])(index), 12))
    columns.append(Column(_("Посещаемость, %"), lambda row: row["attendance_pct"], 14))
    return workbook_of_sheets(filename=filename, sheets=[(group_code, columns, rows)], request=request)
