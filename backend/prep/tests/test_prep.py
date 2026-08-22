"""Фаза 12: банк заданий, тренировки и пробные экзамены.

Ключевое: платформенный мок создаёт `ExamAttempt` с источником `platform`
и НЕ меняет текущий балл в профиле. Решение принимает директор экзаменов.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.passwords import set_password
from engagement.models import XPEvent, XPKind
from prep import services
from prep.models import Difficulty, MockExam, MockSection, Question, QuestionOption, Section
from students.models import AttemptFormat, AttemptSource, ExamAttempt, ExamProfile, Student

PASSWORD = "Подготовка!Проверка26"


def make_question(topic="Reading basics", *, section=Section.READING, exam="IELTS", correct="B") -> Question:
    question = Question.objects.create(
        exam_type=exam,
        section=section,
        topic=topic,
        difficulty=Difficulty.MEDIUM,
        text=f"Вопрос по теме {topic}",
        explanation="Потому что так написано в тексте.",
        source="Демобанк",
    )
    for letter in ("A", "B", "C"):
        QuestionOption.objects.create(
            question=question, letter=letter, text=f"Вариант {letter}", is_correct=letter == correct
        )
    return question


@pytest.fixture
def student(db):
    user = User.objects.create_user(email="prep.student@school.kz", password=None, role=Role.STUDENT)
    set_password(user, PASSWORD)
    person = Student.objects.create(
        last_name="Ким",
        first_name="Дана",
        email="prep.student@school.kz",
        grade=11,
        graduation_year=2027,
        user=user,
    )
    ExamProfile.objects.create(student=person, ielts_current=Decimal("6.5"))
    return person


@pytest.fixture
def bank(db):
    return [make_question(f"Тема {i}") for i in range(6)]


@pytest.fixture
def api(student):
    client = APIClient()
    client.post("/api/auth/login/", {"email": student.email, "password": PASSWORD}, format="json")
    return client


def answer_all(session, *, correctly: bool):
    for row in session.answers.select_related("question"):
        options = list(row.question.options.all())
        pick = next(o for o in options if o.is_correct == correctly) if not correctly else row.question.correct_option
        services.answer_question(session, answer_id=row.pk, option_id=pick.pk, seconds=5)


# --- банк -----------------------------------------------------------------


@pytest.mark.django_db
def test_practice_needs_questions_in_the_bank(student):
    with pytest.raises(services.PrepError, match="нет заданий"):
        services.start_practice(student, exam_type="IELTS")


@pytest.mark.django_db
def test_practice_takes_questions_from_the_bank(student, bank):
    session = services.start_practice(student, exam_type="IELTS", size=4)

    assert session.total == 4
    assert set(session.answers.values_list("question_id", flat=True)) <= {q.pk for q in bank}


@pytest.mark.django_db
def test_correct_answer_is_decided_by_the_server(student, bank):
    session = services.start_practice(student, exam_type="IELTS", size=1)
    row = session.answers.first()
    wrong = row.question.options.filter(is_correct=False).first()

    services.answer_question(session, answer_id=row.pk, option_id=wrong.pk)

    row.refresh_from_db()
    assert row.is_correct is False


@pytest.mark.django_db
def test_option_from_another_question_is_refused(student, bank):
    session = services.start_practice(student, exam_type="IELTS", size=1)
    row = session.answers.first()
    other = QuestionOption.objects.exclude(question=row.question).first()

    with pytest.raises(services.PrepError, match="не относится"):
        services.answer_question(session, answer_id=row.pk, option_id=other.pk)


# --- разбор ---------------------------------------------------------------


@pytest.mark.django_db
def test_review_shows_explanations_and_weak_topics(student, bank):
    session = services.start_practice(student, exam_type="IELTS", size=3)
    answer_all(session, correctly=False)

    review = services.finish_practice(session)

    assert review["correct"] == 0
    assert all(q["explanation"] for q in review["questions"])
    assert len(review["weak_topics"]) == 3
    assert "начните" in review["recommendation"]


@pytest.mark.django_db
def test_correct_answers_leave_no_weak_topics(student, bank):
    session = services.start_practice(student, exam_type="IELTS", size=3)
    answer_all(session, correctly=True)

    review = services.finish_practice(session)

    assert review["weak_topics"] == []
    assert "сложность выше" in review["recommendation"]


@pytest.mark.django_db
def test_correct_answers_are_hidden_until_the_end(student, bank):
    session = services.start_practice(student, exam_type="IELTS", size=2)

    payload = services.session_payload(session)

    assert all("correct_option" not in q for q in payload["questions"])


# --- пробный экзамен ------------------------------------------------------


@pytest.fixture
def mock(db, bank):
    exam = MockExam.objects.create(title="Пробный IELTS", exam_type="IELTS", time_limit_minutes=30)
    MockSection.objects.create(mock=exam, section=Section.READING, question_count=4, order=1)
    return exam


@pytest.mark.django_db
def test_mock_creates_a_platform_attempt(student, mock):
    run, _ = services.start_mock(student, mock)
    answer_all(run.session, correctly=True)

    result = services.finish_mock(run)

    attempt = ExamAttempt.objects.get(student=student)
    assert attempt.attempt_format == AttemptFormat.MOCK
    assert attempt.source == AttemptSource.PLATFORM
    assert result["score"] == float(attempt.total_score)


@pytest.mark.django_db
def test_mock_does_not_touch_the_current_score(student, mock):
    before = student.exam.ielts_current

    run, _ = services.start_mock(student, mock)
    answer_all(run.session, correctly=False)
    services.finish_mock(run)

    student.exam.refresh_from_db()
    assert student.exam.ielts_current == before


@pytest.mark.django_db
def test_director_decides_whether_it_counts(student, mock, db):
    director = User.objects.create_user(email="kymbat@school.kz", password=None, role=Role.DIRECTOR_EXAM)
    run, _ = services.start_mock(student, mock)
    answer_all(run.session, correctly=True)
    services.finish_mock(run)

    services.review_mock(run, count_it=True, actor=director)

    student.exam.refresh_from_db()
    run.refresh_from_db()
    assert run.counted_in_profile is True
    assert student.exam.ielts_current == run.exam_attempt.total_score


@pytest.mark.django_db
def test_declining_leaves_the_score_alone(student, mock, db):
    director = User.objects.create_user(email="k2@school.kz", password=None, role=Role.DIRECTOR_EXAM)
    before = student.exam.ielts_current
    run, _ = services.start_mock(student, mock)
    answer_all(run.session, correctly=True)
    services.finish_mock(run)

    services.review_mock(run, count_it=False, actor=director)

    student.exam.refresh_from_db()
    assert student.exam.ielts_current == before


@pytest.mark.django_db
def test_weak_topics_become_roadmap_tasks(student, mock):
    from roadmap.models import Task

    run, _ = services.start_mock(student, mock)
    answer_all(run.session, correctly=False)
    services.finish_mock(run)

    titles = list(Task.objects.filter(student=student).values_list("title", flat=True))
    assert any("Подтянуть тему" in title for title in titles)


@pytest.mark.django_db
def test_xp_is_for_taking_the_mock_not_for_the_score(student, mock, db):
    """Инвариант №12: два ученика с разным результатом получают одинаково."""
    weaker = Student.objects.create(
        last_name="Второй", first_name="Ученик", email="second@school.kz", grade=11, graduation_year=2027
    )
    ExamProfile.objects.create(student=weaker)

    good, _ = services.start_mock(student, mock)
    answer_all(good.session, correctly=True)
    services.finish_mock(good)

    bad, _ = services.start_mock(weaker, mock)
    answer_all(bad.session, correctly=False)
    services.finish_mock(bad)

    first = XPEvent.objects.get(student=student, kind=XPKind.MOCK_TAKEN)
    second = XPEvent.objects.get(student=weaker, kind=XPKind.MOCK_TAKEN)

    assert first.amount == second.amount
    # и балл при этом разный — значит начисление действительно не про результат
    assert good.exam_attempt.total_score != bad.exam_attempt.total_score


@pytest.mark.django_db
def test_finishing_twice_does_not_duplicate_the_attempt(student, mock):
    run, _ = services.start_mock(student, mock)
    answer_all(run.session, correctly=True)

    services.finish_mock(run)
    services.finish_mock(run)

    assert ExamAttempt.objects.filter(student=student).count() == 1
    assert XPEvent.objects.filter(student=student, kind=XPKind.MOCK_TAKEN).count() == 1


@pytest.mark.django_db
def test_mock_reports_missing_questions_honestly(student, bank):
    exam = MockExam.objects.create(title="Слишком большой", exam_type="IELTS")
    MockSection.objects.create(mock=exam, section=Section.READING, question_count=50, order=1)

    run, shortages = services.start_mock(student, exam)

    assert shortages
    assert shortages[0].asked == 50
    assert shortages[0].available == len(bank)
    assert run.session.total == len(bank)


# --- доступ ---------------------------------------------------------------


@pytest.mark.django_db
def test_student_cannot_see_other_students_session(api, student, bank, db):
    other = Student.objects.create(
        last_name="Чужой", first_name="Ученик", email="other@school.kz", grade=11, graduation_year=2027
    )
    session = services.start_practice(other, exam_type="IELTS", size=1)

    assert api.get(f"/api/prep/practice/{session.pk}/").status_code == 404


@pytest.mark.django_db
def test_student_does_not_get_the_answer_key(api, bank):
    """Список банка ученику не отдаётся вовсе — иначе тренировка бессмысленна."""
    payload = api.get("/api/prep/questions/").data

    assert payload["count"] == 0


@pytest.mark.django_db
def test_only_exam_director_keeps_the_bank(db):
    sport = User.objects.create_user(email="sport@school.kz", password=None, role=Role.DIRECTOR_SPORT)
    set_password(sport, PASSWORD)
    client = APIClient()
    client.post("/api/auth/login/", {"email": sport.email, "password": PASSWORD}, format="json")

    response = client.post(
        "/api/prep/questions/",
        {"exam_type": "IELTS", "section": "reading", "topic": "Тема", "text": "Вопрос"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_student_cannot_see_the_platform_mock_list(api):
    assert api.get("/api/prep/runs/platform/").status_code == 403
