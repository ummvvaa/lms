"""Комментарий к оценке, права журнала по клетке, «Отчёт по ученику», смена вида
черновика, «Обновить данные» и правила текста ИИ (правки после проверки на проде,
30.09.2026)."""

from __future__ import annotations

from unittest import mock

import pytest

from academics import marks as marking
from academics import report_drafts
from academics import reports as reporting
from academics.calendar import scale_of
from academics.models import Course, DraftState, Grade, ParentReport, ReportPeriod, ReportRole, ReportTemplate
from academics.schedule import substitute
from academics.tests.conftest import days, login, school_day
from students.models import GroupLanguage

pytestmark = pytest.mark.django_db


def grade_post(client, lesson, student, value, comment=None):
    body = {"student": student.pk, "value": value}
    if comment is not None:
        body["comment"] = comment
    return client.post(f"/api/acad/lessons/{lesson.pk}/grade/", body, format="json")


# --- Оценка и комментарий ------------------------------------------------------------


def test_grade_and_comment_are_saved_by_one_request_from_the_lesson_screen(lesson, pupils, as_teacher):
    answer = grade_post(as_teacher, lesson, pupils["aliya"], 7, "Эссе без плана, но идеи интересные")
    assert answer.status_code == 200, answer.content
    row = Grade.objects.get(lesson=lesson, student=pupils["aliya"])
    assert (row.value, row.comment) == (7, "Эссе без плана, но идеи интересные")
    roster = {r["id"]: r for r in as_teacher.get(f"/api/acad/lessons/{lesson.pk}/").json()["roster"]}
    assert roster[pupils["aliya"].pk]["grade"] == 7
    assert roster[pupils["aliya"].pk]["comment"] == "Эссе без плана, но идеи интересные", "колонка «Комментарий»"


def test_comment_to_a_standing_grade_and_keyboard_grade_keeps_the_comment(lesson, pupils, as_teacher):
    """Панель ячейки: оценка по нажатию, комментарий — «Сохранить» вместе с оценкой."""
    assert grade_post(as_teacher, lesson, pupils["aliya"], 5).status_code == 200
    assert grade_post(as_teacher, lesson, pupils["aliya"], 5, "Не сдала план").status_code == 200
    assert Grade.objects.get(lesson=lesson, student=pupils["aliya"]).comment == "Не сдала план"
    # цифра с клавиатуры в матрице шлёт оценку без комментария — комментарий остаётся
    assert grade_post(as_teacher, lesson, pupils["aliya"], 6).status_code == 200
    row = Grade.objects.get(lesson=lesson, student=pupils["aliya"])
    assert (row.value, row.comment) == (6, "Не сдала план")
    too_long = grade_post(as_teacher, lesson, pupils["aliya"], 6, "x" * 400)
    assert too_long.status_code == 200 and len(Grade.objects.get(pk=row.pk).comment) == 300


def test_grade_from_the_journal_cell_is_in_the_journal(lesson, pupils, teacher, as_teacher):
    course = lesson.course
    assert grade_post(as_teacher, lesson, pupils["damir"], 9, "Хорошо отвечает у доски").status_code == 200
    journal = as_teacher.get(f"/api/acad/journals/{course.pk}/").json()
    column = next(i for i, c in enumerate(journal["columns"]) if c["lesson"] == lesson.pk)
    assert journal["columns"][column]["may_grade"] is True and journal["columns"][column]["may_mark"] is True
    row = next(r for r in journal["rows"] if r["id"] == pupils["damir"].pk)
    assert row["cells"][column] == {**row["cells"][column], "grade": 9, "comment": "Хорошо отвечает у доски"}


def test_journal_cell_is_closed_where_the_server_refuses(
    year, subjects, teacher, other_teacher, cohorts, calendar, pupils
):
    """Урок журнала на замене: у владельца журнала клетка закрыта и сказано, кто ставит."""
    from academics.schedule import create_once

    future = create_once(
        subject=subjects["alg"], teacher=teacher, cohort=cohorts["boston"], date=days(1), slot=3, room="204"
    )
    substitute(future, teacher=other_teacher, reason="больничный")
    journal = login(teacher).get(f"/api/acad/journals/{future.course_id}/").json()
    column = next(c for c in journal["columns"] if c["lesson"] == future.pk)
    assert journal["may_edit"] is True, "журнал свой"
    assert column["may_grade"] is False and column["may_mark"] is False
    assert column["teacher"] == other_teacher.full_name
    assert column["may_grade"] == (grade_post(login(teacher), future, pupils["aliya"], 5).status_code == 200)


# --- «Отчёт по ученику»: список учеников группы ------------------------------------------


def test_report_by_student_lists_pupils_of_the_picked_group_by_code(pupils, boston, chicago, as_curator, as_kymbat):
    """Окно шлёт код группы: так фильтрует список учеников. Куратор — только свои."""
    mine = as_curator.get(f"/api/students/?group={boston.code}&page_size=200").json()["results"]
    assert {row["id"] for row in mine} == {pupils[k].pk for k in ("aliya", "damir", "nurai")}
    assert as_curator.get(f"/api/students/?group={chicago.code}&page_size=200").json()["results"] == []
    everyone = as_kymbat.get(f"/api/students/?group={chicago.code}&page_size=200").json()["results"]
    assert [row["id"] for row in everyone] == [pupils["stranger"].pk]
    by_id = as_kymbat.get(f"/api/students/?group={boston.pk}&page_size=200").json()["results"]
    assert by_id == [], "по номеру группы список пуст — поэтому окно шлёт код"


def test_reports_screen_gives_group_language(pupils, boston, as_curator):
    boston.language = GroupLanguage.KK
    boston.save(update_fields=["language"])
    groups = as_curator.get("/api/acad/reports/").json()["groups"]
    assert groups == [{"id": boston.pk, "code": boston.code, "language": "kk", "language_title": "Казахский"}]


# --- Смена вида и языка черновика ----------------------------------------------------------


@pytest.fixture
def month_report(lesson, pupils, teacher, calendar, curator):
    marking.set_grade(
        lesson, pupils["aliya"], 8, comment="Старается", actor=teacher, calendar=calendar, scale=scale_of(calendar.year)
    )
    start, end = reporting.month_bounds(lesson.date)
    return reporting.build_report(
        pupils["aliya"],
        kind=ReportPeriod.MONTH,
        start=start,
        end=end,
        calendar=calendar,
        config=reporting.report_settings(calendar),
    )


def test_switching_variant_builds_a_draft_for_the_same_student_and_period(
    month_report, as_curator, django_capture_on_commit_callbacks
):
    with mock.patch("academics.report_drafts.draft") as draft, django_capture_on_commit_callbacks(execute=True):
        answer = as_curator.post(
            f"/api/acad/reports/{month_report.pk}/switch/", {"template": "review", "language": "kk"}, format="json"
        )
    assert answer.status_code == 200, answer.content
    body = answer.json()
    fresh = ParentReport.objects.get(pk=body["report"])
    assert (fresh.template, fresh.language, fresh.student_id) == ("review", "kk", month_report.student_id)
    assert (fresh.period_start, fresh.period_end) == (month_report.period_start, month_report.period_end)
    assert body["language_title"] == "Казахский" and body["template_title"].startswith("Вариант 1")
    assert draft.call_count == 1, "новый вариант — черновик ИИ заказан"
    back = as_curator.post(f"/api/acad/reports/{fresh.pk}/switch/", {"template": "standard"}, format="json").json()
    assert back["report"] == month_report.pk, "месяц «с — по» возвращается к тому же стандартному отчёту"
    ParentReport.objects.get(pk=month_report.pk)  # прежний отчёт остаётся


# --- «Обновить данные» -------------------------------------------------------------------


def test_refresh_takes_fresh_marks_grades_and_comments(
    year, subjects, teacher, cohorts, calendar, pupils, curator, as_curator
):
    """Снимок до урока — «пока не было»; урок отмечен — «Обновить данные» его видит."""
    from academics.schedule import create_once

    day = school_day(-1, calendar)
    lesson = create_once(subject=subjects["alg"], teacher=teacher, cohort=cohorts["boston"], date=day, slot=2, room="1")
    start, end = reporting.month_bounds(day)
    report = reporting.build_report(
        pupils["aliya"],
        kind=ReportPeriod.MONTH,
        start=start,
        end=end,
        calendar=calendar,
        config=reporting.report_settings(calendar),
    )
    assert "пока не было" in {line.value for line in report.lines.all()}
    marking.save_attendance(lesson, [], actor=teacher, calendar=calendar)
    fresh = as_curator.post(f"/api/acad/reports/{report.pk}/refresh/", {}, format="json").json()
    values = str(fresh["sections"])
    assert fresh["changed"] is True and "пока не было" not in values and "100 %" in values
    assert fresh["needs_confirm"] is False and fresh["redrafting"] is False, "у стандартного текстов ИИ нет"


@pytest.fixture
def school_report(month_report):
    return reporting.build_report(
        month_report.student,
        kind=ReportPeriod.CUSTOM,
        start=month_report.period_start,
        end=month_report.period_end,
        calendar=__import__("academics.calendar", fromlist=["load"]).load(),
        config=reporting.report_settings(__import__("academics.calendar", fromlist=["load"]).load()),
        template=ReportTemplate.PROGRESS,
        language="ru",
    )


def test_refresh_redrafts_texts_but_asks_before_overwriting_curator_edits(
    school_report, as_curator, django_capture_on_commit_callbacks
):
    with mock.patch("academics.report_drafts.draft") as draft, django_capture_on_commit_callbacks(execute=True):
        plain = as_curator.post(f"/api/acad/reports/{school_report.pk}/refresh/", {}, format="json").json()
    assert plain["redrafting"] is True and plain["needs_confirm"] is False
    assert draft.call_args.kwargs["overwrite"] is True, "по свежим данным тексты пишутся заново"
    # куратор поправил итоги — без его «да» тексты не трогаются
    as_curator.patch(f"/api/acad/reports/{school_report.pk}/", {"summary": "Итог куратора"}, format="json")
    school_report.refresh_from_db()
    assert school_report.texts_edited_at is not None
    with mock.patch("academics.report_drafts.draft") as draft, django_capture_on_commit_callbacks(execute=True):
        asked = as_curator.post(f"/api/acad/reports/{school_report.pk}/refresh/", {}, format="json").json()
    assert asked["needs_confirm"] is True and asked["redrafting"] is False
    draft.assert_not_called()
    school_report.refresh_from_db()
    assert school_report.summary == "Итог куратора"
    with mock.patch("academics.report_drafts.draft") as draft, django_capture_on_commit_callbacks(execute=True):
        agreed = as_curator.post(
            f"/api/acad/reports/{school_report.pk}/refresh/", {"overwrite": True}, format="json"
        ).json()
    assert agreed["redrafting"] is True
    assert draft.call_count == 1 and draft.call_args.kwargs["overwrite"] is True


def test_bulk_refresh_keeps_edited_texts(school_report, as_curator, django_capture_on_commit_callbacks):
    as_curator.patch(f"/api/acad/reports/{school_report.pk}/", {"summary": "Итог куратора"}, format="json")
    with mock.patch("academics.report_drafts.draft") as draft, django_capture_on_commit_callbacks(execute=True):
        answer = as_curator.post("/api/acad/reports/refresh/", {"ids": [school_report.pk]}, format="json").json()
    assert answer["kept"] == 1
    draft.assert_not_called()


def test_ai_overwrite_clears_the_edit_mark(school_report):
    from suggestions.llm import LLMResponse

    school_report.texts_edited_at = school_report.built_at
    school_report.save(update_fields=["texts_edited_at"])
    answer = LLMResponse(content="", parsed={"summary": "{name} старается.", "subjects": []}, model="test")
    with mock.patch("suggestions.llm.complete", return_value=answer):
        report_drafts.draft(school_report, overwrite=True)
    school_report.refresh_from_db()
    assert school_report.texts_edited_at is None and school_report.summary == "Алия старается."


# --- Тексты ИИ ------------------------------------------------------------------------------


def test_prompt_has_no_name_no_minutes_no_dates_and_comments_first(school_report):
    facts = report_drafts.collect(school_report)
    sent = report_drafts.prompt(school_report, facts)
    assert "Алия" not in sent and "Ахметова" not in sent, "ни имени, ни фамилии"
    assert "минут" not in sent and "%" not in sent, "процент по минутам модель не получает"
    assert f"{school_report.period_start:%d.%m.%Y}" not in sent, "дат периода в запросе нет"
    assert "«Старается»" in sent and sent.index("Комментарии учителей") < sent.index("Что заполнить")


def test_rules_have_examples_in_both_languages():
    for words in ("Так НЕ писать (kk)", "Так писать (kk)", "Так НЕ писать (ru)", "Так писать (ru)"):
        assert words in report_drafts.SYSTEM
    for banned in ("следует отметить", "атап өткен жөн", "по минутам", "пікір берілмеген", "/10"):
        assert banned in report_drafts.SYSTEM
    for rule in ("IELTS Mock Test", "SAT Mock Test", "Listening, Reading, Writing, Speaking", "бір рет кешіккен"):
        assert rule in report_drafts.SYSTEM, "названия как в шаблонах школы, прошедшее время фактов"


@pytest.mark.parametrize(
    "raw, kept, dropped",
    [
        (
            "{name} сабаққа тұрақты қатысады. Сабаққа қатысу көрсеткіші 100% болды. "
            "Тапсырмаларға қатысты мұғалім пікірі берілмеген. Қорытынды жасауға дерек жоқ.",
            "{name} сабаққа тұрақты қатысады.",
            ("көрсеткіші", "берілмеген", "дерек жоқ"),
        ),
        (
            "{name} ходит на уроки без пропусков. Посещаемость по минутам — 100%. "
            "Комментарии учителя не предоставлены. Оценка по Creative Writing — 2/10. "
            "В целом можно сказать, что ученик демонстрирует стабильную динамику.",
            "{name} ходит на уроки без пропусков. Оценка по Creative Writing — 2.",
            ("по минутам", "не предоставлены", "/10", "демонстрирует"),
        ),
        (
            "Результат формативного оценивания по ФО — 7 из 10. {name} старается.",
            "{name} старается.",
            ("формативн", "ФО"),
        ),
    ],
)
def test_forbidden_phrases_never_reach_the_parent(raw, kept, dropped):
    text = report_drafts.clean(raw)
    assert text == kept
    for words in dropped:
        assert words not in text


def test_name_after_a_preposition_is_dropped_with_it():
    """Имя подставляется в именительном: «у Мирас» не пишется — предлог уходит вместе с именем."""
    text = report_drafts.clean("В IELTS Mock Test у {name} сильнее всего вышел Listening.")
    assert text == "В IELTS Mock Test сильнее всего вышел Listening."
    assert report_drafts.clean("{name} пишет эссе длиннее.") == "{name} пишет эссе длиннее."


def test_draft_drops_forbidden_sentences_from_the_model(school_report):
    from suggestions.llm import LLMResponse

    answer = LLMResponse(
        content="",
        parsed={
            "summary": "{name} старается на уроках. Данных по пробникам нет. Комментарии учителя не предоставлены.",
            "mock_comment": "Пробника нет — нет данных.",
            "subjects": [],
        },
        model="test",
    )
    with mock.patch("suggestions.llm.complete", return_value=answer):
        report_drafts.draft(school_report, overwrite=True)
    school_report.refresh_from_db()
    assert school_report.summary == "Алия старается на уроках."
    assert school_report.mock_comment == ""


def test_review_block_is_written_only_from_teacher_comments(year, subjects, cohorts, make_user, calendar, pupils):
    """Одни оценки в журнале раздела — не отзыв: блок GE/EEP остаётся пустым."""
    from academics.schedule import create_once

    trainer = make_user("teacher", "eep@example.kz", full_name="Англичанова Айгуль")
    day = school_day(-3, calendar)
    lesson = create_once(subject=subjects["eng"], teacher=trainer, cohort=cohorts["boston"], date=day, slot=6, room="1")
    Course.objects.filter(pk=lesson.course_id).update(report_role=ReportRole.EEP)
    scale = scale_of(calendar.year)
    marking.set_grade(lesson, pupils["aliya"], 9, actor=trainer, calendar=calendar, scale=scale)
    start, end = reporting.month_bounds(lesson.date)
    report = reporting.build_report(
        pupils["aliya"],
        kind=ReportPeriod.CUSTOM,
        start=start,
        end=end,
        calendar=calendar,
        config=reporting.report_settings(calendar),
        template=ReportTemplate.REVIEW,
        language="kk",
    )
    facts = report_drafts.collect(report)
    assert "eep" not in report_drafts.wanted(report, facts)
    marking.set_grade(
        lesson, pupils["aliya"], 9, comment="Сөйлеуі жақсарды", actor=trainer, calendar=calendar, scale=scale
    )
    assert "eep" in report_drafts.wanted(report, report_drafts.collect(report))
    assert report.draft_state == DraftState.NONE
