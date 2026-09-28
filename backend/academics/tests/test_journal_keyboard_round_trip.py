"""Журнал с клавиатуры — на уровне API: то, на что опирается сетка учителя.

Клавиша в сетке — это ровно два запроса: цифра → `lessons/<id>/grade/`,
буква «н» → `lessons/<id>/attendance/`, Backspace → снять оценку, второй
Backspace → вернуть «был». Сетка показывает то, что отдаёт журнал, поэтому
проверяем круг целиком: запрос → журнал за месяц урока → в клетке то же.
"""

from __future__ import annotations


def journal_cell(client, lesson, student) -> tuple[dict, dict]:
    """Колонка урока и клетка ученика в журнале за месяц урока — как их видит сетка."""
    journal = client.get(f"/api/acad/journals/{lesson.course.pk}/?period={lesson.date:%Y-%m}").json()
    col = next(i for i, column in enumerate(journal["columns"]) if column["lesson"] == lesson.pk)
    row = next(r for r in journal["rows"] if r["id"] == student.pk)
    return journal["columns"][col], row["cells"][col]


def test_keyboard_grade_and_mark_are_saved_and_come_back_in_the_journal(lesson, pupils, as_teacher):
    """Цифра, «н» и Backspace по правилам журнала (`docs/academics.md`, «Оценки», п. 2):
    оценка ставится только присутствующему, отметка «н» оценку снимает,
    оценка отсутствующему делает его присутствующим."""
    aliya = pupils["aliya"]
    grade_url = f"/api/acad/lessons/{lesson.pk}/grade/"
    mark_url = f"/api/acad/lessons/{lesson.pk}/attendance/"
    column, cell = journal_cell(as_teacher, lesson, aliya)
    # клетка годится для цифры: урок ФО, прошёл, окно правки открыто
    assert column["kind"] == "fo" and not column["future"] and not column["locked"]
    assert cell["grade"] is None

    # «8» — оценка сохранена и видна в журнале
    graded = as_teacher.post(grade_url, {"student": aliya.pk, "value": 8}, format="json")
    assert graded.status_code == 200 and graded.json()["grade"] == 8
    assert journal_cell(as_teacher, lesson, aliya)[1]["grade"] == 8

    # Backspace при оценке — снимает оценку
    cleared = as_teacher.post(grade_url, {"student": aliya.pk, "value": None}, format="json")
    assert cleared.status_code == 200 and cleared.json()["grade"] is None
    assert journal_cell(as_teacher, lesson, aliya)[1]["grade"] is None

    # «н» — отметка сохранена
    assert (
        as_teacher.post(mark_url, {"rows": [{"student": aliya.pk, "mark": "absent"}]}, format="json").status_code == 200
    )
    assert journal_cell(as_teacher, lesson, aliya)[1]["mark"] == "absent"

    # «8» отсутствующему — оценка встала, ученик стал присутствующим
    assert as_teacher.post(grade_url, {"student": aliya.pk, "value": 8}, format="json").status_code == 200
    _column, cell = journal_cell(as_teacher, lesson, aliya)
    assert cell["grade"] == 8 and cell["mark"] != "absent"

    # «н» поверх оценки — оценка снята: отсутствующему её не ставят
    as_teacher.post(mark_url, {"rows": [{"student": aliya.pk, "mark": "absent"}]}, format="json")
    _column, cell = journal_cell(as_teacher, lesson, aliya)
    assert (cell["grade"], cell["mark"]) == (None, "absent")

    # Backspace без оценки — возвращает «был»
    assert (
        as_teacher.post(mark_url, {"rows": [{"student": aliya.pk, "mark": "present"}]}, format="json").status_code
        == 200
    )
    _column, cell = journal_cell(as_teacher, lesson, aliya)
    assert cell["grade"] is None and cell["mark"] == "present"


def test_zero_key_means_the_top_of_the_fo_scale(lesson, pupils, as_teacher):
    """«0» в сетке — десятка: сетка шлёт `fo_max` шкалы, сервер его принимает."""
    journal = as_teacher.get(f"/api/acad/journals/{lesson.course.pk}/?period={lesson.date:%Y-%m}").json()
    top = journal["scale"]["fo_max"]
    saved = as_teacher.post(
        f"/api/acad/lessons/{lesson.pk}/grade/", {"student": pupils["aliya"].pk, "value": top}, format="json"
    )
    assert saved.status_code == 200 and saved.json()["grade"] == top
