"""Помощник учителя: пять кнопок и свободный вопрос — только чтение и только свои ученики.

Граница — `core.scope`: ученики составов учителя и состав урока на замене
в день урока. Чужого ученика нет ни в одной кнопке и ни в фактах для
модели; писать помощник учителя не может ничего.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from academics.models import Lesson, LessonKind
from academics.schedule import create_once, substitute
from academics.tests.conftest import days, school_day
from suggestions.models import Suggestion

pytestmark = pytest.mark.django_db

CODES = ("lessons_week", "unmarked", "lagging", "no_grades", "assessments")

LIVE_LLM = {
    "PROVIDER": "anthropic",
    "API_KEY": "test-key",
    "BASE_URL": "https://api.example",
    "MODEL": "claude-sonnet-5",
    "TIMEOUT": 5,
    "RETRIES": 0,
    "RETRY_DELAY": 0,
    "NO_RETENTION": True,
    "SEARCH": False,
    "SEARCH_MAX_USES": 0,
}


def ask(client, **body) -> dict:
    response = client.post("/api/assistant/ask/", body, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def said(answer: dict) -> str:
    message = answer["message"]
    return "\n".join([message["text"], *message["lines"]])


@pytest.fixture
def model_box(monkeypatch):
    """Подменить HTTP-слой провайдера и запомнить, что ушло в модель."""
    box: dict = {}

    def install(text: str):
        class Answer:
            status_code = 200

            def json(self):
                return {
                    "id": "msg_1",
                    "model": "claude-sonnet-5",
                    "content": [{"type": "text", "text": text}],
                    "usage": {"input_tokens": 300, "output_tokens": 80},
                }

        def fake_post(url, json=None, headers=None, timeout=None):
            box["json"] = json
            return Answer()

        import requests

        monkeypatch.setattr(requests, "post", fake_post)
        return box

    return install


def test_teacher_gets_five_read_only_buttons(as_teacher):
    body = as_teacher.get("/api/assistant/quick/").json()
    assert [button["code"] for button in body["buttons"]] == list(CODES)
    assert as_teacher.get("/api/assistant/threads/").status_code == 200


def test_lagging_names_own_students_below_the_thresholds(as_teacher, marked_journal, pupils):
    text = said(ask(as_teacher, command="lagging"))
    assert "Ахметова Алия" in text and "выходит 2" in text
    assert "Сериков Дамир" in text and "посещаемость 0 %" in text
    assert "Абдрахман" not in text
    assert "Чужестранцев" not in text


def test_no_grades_takes_only_those_who_were_in_class(as_teacher, marked_journal, pupils):
    text = said(ask(as_teacher, command="no_grades"))
    assert "Абдрахман Нурай" in text
    # у Алии оценки есть, Дамира на уроках не было
    assert "Ахметова" not in text and "Сериков" not in text
    assert "Чужестранцев" not in text


def test_unmarked_and_assessments_are_the_teachers_own(
    as_teacher, teacher, marked_journal, subjects, cohorts, calendar
):
    create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-1, calendar),
        slot=8,
        room="204",
    )
    ahead = create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(3, calendar),
        slot=2,
        room="204",
    )
    Lesson.objects.filter(pk=ahead.pk).update(kind=LessonKind.SOR, number=1, max_score=20)

    unmarked = said(ask(as_teacher, command="unmarked"))
    assert "8 урок" in unmarked and "алгебра BOSTON" in unmarked
    assert "английский" not in unmarked, "чужой урок в неотмеченных"

    works = said(ask(as_teacher, command="assessments"))
    assert "СОР 1" in works and "максимум 20" in works


def test_substitution_shows_the_lesson_but_not_the_roster(
    as_teacher, teacher, other_teacher, marked_journal, subjects, cohorts, calendar
):
    later = create_once(
        subject=subjects["eng"], teacher=other_teacher, cohort=cohorts["chicago"], date=days(0), slot=9, room="305"
    )
    substitute(later, teacher=teacher, reason="болеет")
    for code in CODES:
        text = said(ask(as_teacher, command=code))
        assert "Чужестранцев" not in text, f"чужой ученик в кнопке {code}"
    week = said(ask(as_teacher, command="lessons_week"))
    assert "(замена)" in week and "CHICAGO" in week


def test_teacher_writes_nothing(as_teacher, marked_journal, pupils):
    before = Suggestion.objects.count()
    answer = ask(as_teacher, text="Поставь задачу Серикову: догнать тему", students=[pupils["damir"].pk])
    assert "только читает" in answer["message"]["text"]
    assert answer["message"]["suggestion"] is None
    assert Suggestion.objects.count() == before
    # команды и предложения учителю по-прежнему закрыты
    assert as_teacher.get("/api/suggestions/").status_code == 404
    assert as_teacher.post("/api/commands/run/", {"command": "focus_today"}, format="json").status_code == 404


def test_foreign_button_is_refused_for_the_teacher(as_teacher, marked_journal):
    answer = ask(as_teacher, command="focus_today")
    assert "нет" in answer["message"]["text"].lower()


@override_settings(LLM=LIVE_LLM)
def test_free_question_gets_facts_only_about_own_students(as_teacher, marked_journal, pupils, model_box):
    box = model_box("У ученика 3 ниже всех посещаемость — он не был ни на одном уроке.")
    answer = ask(as_teacher, text="Что с Сериковым, почему он отстаёт?", students=[pupils["stranger"].pk])

    sent = str(box["json"])
    # факты — только о своих: чужой ученик из выбора выпадает
    assert "Чужестранцев" not in sent
    # имена в фактах обезличены, вопрос уходит как написан (решение владельца)
    assert "Ахметова" not in sent and "Абдрахман" not in sent
    assert "Сериковым" in sent
    assert "судя по фамилии: ученик" in sent

    text = answer["message"]["text"]
    assert answer["message"]["offline"] is False
    assert "Сериков Дамир" in text, "номер не превратился обратно в имя"


def test_without_a_model_the_free_question_is_refused_honestly(as_teacher, marked_journal):
    answer = ask(as_teacher, text="Кто у меня отстаёт?")
    assert "не подключена" in answer["message"]["text"]


def test_window_and_thresholds_come_from_school_settings(as_teacher, marked_journal, admin):
    from core import school_rules

    school_rules.set_value(school_rules.QUARTER_GRADE_BELOW, 2, actor=admin)
    school_rules.set_value(school_rules.ATTENDANCE_BELOW, 0, actor=admin)
    text = said(ask(as_teacher, command="lagging"))
    assert "Отстающих нет" in text

    # окно в один день: урок вчера — учебный день назад, в окно попадает только сегодня
    school_rules.set_value(school_rules.NO_GRADES_DAYS, 1, actor=admin)
    text = said(ask(as_teacher, command="no_grades"))
    assert "Абдрахман" not in text
