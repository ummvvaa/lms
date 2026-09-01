"""Фаза 42: формат банка, прогресс по темам, статистика, теория.

Банк пуст по решению владельца — механика проверяется на загруженных
тестовых данных, а на пустом банке экраны честно показывают ноль.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rest_framework.test import APIClient

from prep.imports import import_questions
from prep.models import Question, QuestionPassage, TheoryLesson

_ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
DOC = _ROOT / "docs" / "QUESTION_BANK.md"


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.fixture
def kymbat(make_user):
    return make_user("director_exam", "kymbat42@school.kz", full_name="Кымбат")


# --- Формат загрузки -------------------------------------------------------


_HEADER = ",".join(
    [
        "exam_type",
        "section",
        "topic",
        "question_type",
        "text",
        "A",
        "B",
        "C",
        "D",
        "correct",
        "passage_key",
        "passage_kind",
        "passage_title",
        "passage_text",
    ]
)
READING_CSV = (
    _HEADER
    + "\n"
    + "IELTS,reading,Main idea,single,Q1,a,b,c,d,A,P1,reading,City growth,Over the last decade cities grew.\n"
    + "IELTS,reading,Detail,single,Q2,a,b,c,d,B,P1,reading,,\n"
    + "IELTS,reading,Detail,single,Q3,a,b,c,d,C,P1,reading,,\n"
    + "IELTS,reading,Detail,single,Q4,a,b,c,d,D,P1,reading,,\n"
    + "IELTS,reading,Detail,single,Q5,a,b,c,d,A,P1,reading,,\n"
)


@pytest.mark.django_db
def test_reading_passage_links_group_of_questions():
    result = import_questions(READING_CSV)
    assert result.created == 5
    assert result.passages == 1

    passage = QuestionPassage.objects.get()
    assert passage.kind == "reading"
    assert "cities grew" in passage.body
    # один текст — пять вопросов, все ссылаются на него
    assert passage.questions.count() == 5


WRITING_CSV = """exam_type,section,topic,question_type,text,criteria,sample_answer,correct
IELTS,writing,Task 2,writing,Discuss both views.,Coherence and grammar,A model answer,
"""


@pytest.mark.django_db
def test_writing_question_needs_no_options():
    result = import_questions(WRITING_CSV)
    assert result.created == 1
    question = Question.objects.get()
    assert question.question_type == "writing"
    assert question.criteria and question.sample_answer
    assert question.options.count() == 0


@pytest.mark.django_db
def test_audio_file_attached_by_name():
    csv = """exam_type,section,topic,question_type,text,A,B,correct,passage_key,passage_kind,audio_file
IELTS,listening,Numbers,single,How much?,10,12,B,L1,listening,clip.mp3
"""
    media = {"clip.mp3": (b"ID3fakeaudio", "audio/mpeg")}
    result = import_questions(csv, media=media)
    assert result.created == 1
    passage = QuestionPassage.objects.get()
    assert passage.kind == "listening"
    assert passage.audio  # файл сохранён
    assert passage.audio_content_type == "audio/mpeg"


@pytest.mark.django_db
def test_multiple_correct_and_extra_fields():
    csv = """exam_type,section,topic,subtopic,difficulty,question_type,text,A,B,C,D,correct,expected_seconds,source_year
SAT,math,Algebra,Linear,hard,multiple,Pick two,a,b,c,d,"A,C",90,2023
"""
    result = import_questions(csv)
    assert result.created == 1
    question = Question.objects.get()
    assert question.subtopic == "Linear"
    assert question.expected_seconds == 90
    assert question.source_year == 2023
    correct = set(question.options.filter(is_correct=True).values_list("letter", flat=True))
    assert correct == {"A", "C"}


@pytest.mark.django_db
def test_bad_rows_are_skipped_with_reasons():
    csv = """exam_type,section,topic,question_type,text,A,B,correct
NOPE,reading,T,single,Q,a,b,A
IELTS,badsection,T,single,Q,a,b,A
IELTS,reading,T,single,Q,a,b,Z
"""
    result = import_questions(csv)
    assert result.created == 0
    assert len(result.skipped) == 3
    reasons = " ".join(r["reason"] for r in result.skipped)
    assert "экзамен" in reasons and "секция" in reasons


def test_question_bank_doc_describes_format():
    text = DOC.read_text(encoding="utf-8")
    for column in ("exam_type", "section", "topic", "correct", "passage_key", "audio_file", "question_type"):
        assert column in text, f"колонка {column} не описана в QUESTION_BANK.md"
    assert "listening" in text and "writing" in text


# --- Прогресс по темам -----------------------------------------------------


@pytest.mark.django_db
def test_center_exams_shows_only_visible_ones(api, student_user):
    """Плитки показывают экзамены, отмеченные в справочнике (фаза 48).

    Школа ведёт два — SAT и IELTS; остальные пять скрыты признаком показа,
    а не удалены, и включаются галочкой без выката.
    """
    from directories.models import ExamKind

    api.force_authenticate(student_user)
    payload = api.get("/api/prep/center/exams/").data
    codes = {e["exam_type"] for e in payload["exams"]}
    assert codes == {"SAT", "IELTS"}
    # пустой банк — прогресс ноль, экран это переживает
    assert all(e["solved"] == 0 for e in payload["exams"])

    # включили ЕНТ галочкой — он появился, кода в приложении не меняли
    ExamKind.objects.filter(name="ЕНТ").update(is_active=True)
    codes = {e["exam_type"] for e in api.get("/api/prep/center/exams/").data["exams"]}
    assert "ENT" in codes


@pytest.mark.django_db
def test_topic_progress_grows_after_solving(api, student_user, student):
    import_questions(READING_CSV)
    api.force_authenticate(student_user)

    before = api.get("/api/prep/center/IELTS/reading/topics/").data["topics"]
    assert any(t["topic"] == "Detail" and t["total"] == 4 and t["solved"] == 0 for t in before)

    # решаем один вопрос темы Detail через тренировку
    from prep.models import PracticeSession
    from prep.services import answer_question

    question = Question.objects.filter(topic="Detail").first()
    session = PracticeSession.objects.create(student=student, exam_type="IELTS", section="reading")
    from prep.models import PracticeAnswer

    PracticeAnswer.objects.create(session=session, question=question)
    answer_question(
        session,
        answer_id=session.answers.get().pk,
        option_id=question.options.filter(is_correct=True).first().pk,
    )

    after = api.get("/api/prep/center/IELTS/reading/topics/").data["topics"]
    detail = next(t for t in after if t["topic"] == "Detail")
    assert detail["solved"] == 1
    assert detail["percent"] == 25


@pytest.mark.django_db
def test_statistics_forecast_needs_answers(api, student_user, student):
    import_questions(READING_CSV)
    api.force_authenticate(student_user)
    stats = api.get("/api/prep/center/IELTS/statistics/").data
    assert stats["forecast"]["enough"] is False
    assert stats["forecast"]["need_more"] > 0
    assert stats["forecast"]["score"] is None


@pytest.mark.django_db
def test_statistics_and_center_are_for_students(api, kymbat):
    api.force_authenticate(kymbat)
    assert api.get("/api/prep/center/exams/").status_code == 403
    assert api.get("/api/prep/center/IELTS/statistics/").status_code == 403


# --- Теория ----------------------------------------------------------------


@pytest.mark.django_db
def test_theory_led_by_academic_director(api, kymbat, make_user, student_user):
    api.force_authenticate(kymbat)
    made = api.post(
        "/api/prep/theory/",
        {
            "exam_type": "IELTS",
            "section": "reading",
            "title": "Skimming basics",
            "level": "basic",
            "reading_minutes": 4,
        },
        format="json",
    )
    assert made.status_code == 201
    lesson_id = made.data["id"]

    # чужой директор не ведёт теорию
    api.force_authenticate(make_user("director_sport", "n42@school.kz"))
    assert api.post("/api/prep/theory/", {"exam_type": "IELTS", "title": "X"}, format="json").status_code == 403

    # ученик читает
    api.force_authenticate(student_user)
    listing = api.get("/api/prep/theory/?exam_type=IELTS").data
    rows = listing["results"] if isinstance(listing, dict) else listing
    assert any(r["id"] == lesson_id for r in rows)


@pytest.mark.django_db
def test_student_sees_only_active_theory(api, kymbat, student_user):
    TheoryLesson.objects.create(exam_type="IELTS", title="Hidden", is_active=False)
    visible = TheoryLesson.objects.create(exam_type="IELTS", title="Shown", is_active=True)

    api.force_authenticate(student_user)
    listing = api.get("/api/prep/theory/").data
    rows = listing["results"] if isinstance(listing, dict) else listing
    ids = {r["id"] for r in rows}
    assert visible.pk in ids
    assert all(r["id"] != TheoryLesson.objects.get(title="Hidden").pk for r in rows)
