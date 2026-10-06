"""D75 (06.10.2026): оценка из панели ячейки журнала видна сразу.

На проде семь нажатий за семь секунд ушли 200-ми, а клетка стояла пустой:
журнал ждал полного перезапроса, каждое следующее нажатие его отменяло.
Теперь фронт берёт клетку из ответа на запись — здесь сторожится, что ответ
несёт всё, что клетке нужно, и что журнал с ним согласен; и что ответы API
не кэшируются браузером.
"""

from __future__ import annotations

import pytest

from academics.tests.conftest import login

pytestmark = pytest.mark.django_db


def test_grade_answer_carries_the_lesson_roster_and_the_journal_agrees(lesson, pupils, teacher, as_teacher):
    aliya = pupils["aliya"]
    answer = as_teacher.post(
        f"/api/acad/lessons/{lesson.pk}/grade/", {"student": aliya.pk, "value": 8, "comment": "Teest"}, format="json"
    )
    assert answer.status_code == 200, answer.json()
    body = answer.json()
    assert body["grade"] == 8 and body["comment"] == "Teest"
    assert body["lesson"]["id"] == lesson.pk and body["lesson"]["course"] == lesson.course_id
    assert body["lesson"]["marked"] is True
    row = next(r for r in body["roster"] if r["id"] == aliya.pk)
    # оценка ставится присутствующему: отметка «был» приходит явно
    assert (row["mark"], row["grade"], row["comment"]) == ("present", 8, "Teest")
    # журнал отдаёт ту же клетку — патч из ответа и перезапрос не расходятся
    journal = as_teacher.get(f"/api/acad/journals/{lesson.course_id}/").json()
    column = next(i for i, c in enumerate(journal["columns"]) if c["lesson"] == lesson.pk)
    line = next(r for r in journal["rows"] if r["id"] == aliya.pk)
    assert line["cells"][column] == {
        "mark": "present",
        "grade": 8,
        "comment": "Teest",
        "arrived": None,
        "late_by": None,
        "late_as_absent": False,
    }
    assert journal["columns"][column]["unmarked"] is False


def test_attendance_answer_carries_the_roster_too(lesson, pupils, as_teacher):
    damir = pupils["damir"]
    answer = as_teacher.post(
        f"/api/acad/lessons/{lesson.pk}/attendance/", {"rows": [{"student": damir.pk, "mark": "absent"}]}, format="json"
    )
    assert answer.status_code == 200, answer.json()
    body = answer.json()
    assert body["lesson"]["id"] == lesson.pk
    assert next(r for r in body["roster"] if r["id"] == damir.pk)["mark"] == "absent"


def test_api_answers_are_not_stored_by_the_browser(lesson, teacher, kymbat):
    api = login(teacher)
    for path in (f"/api/acad/journals/{lesson.course_id}/", "/api/acad/meta/", "/api/notifications/"):
        answer = api.get(path)
        assert answer.status_code == 200, path
        assert answer["Cache-Control"] == "private, no-store", path
    # выгрузка ставит свой заголовок — он не затирается
    export = login(kymbat).get(f"/api/acad/journals/{lesson.course_id}/export/")
    assert export.status_code == 200
    assert "no-store" in export["Cache-Control"]
