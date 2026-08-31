"""Фаза 46, часть 1: квиз без публичных рейтингов.

Главное, что здесь проверяется, — не механика счёта, а обещание школе:
**публичной таблицы отдельных учеников нет ни в каком виде.** В ответе API
для роли ученика не должно быть чужих результатов, кроме командных сумм.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from prep.models import Question, QuestionOption, QuizKind, QuizMatch, QuizPlayer, QuizStatus
from students.models import AdmissionProfile, BehaviorProfile, ExamProfile, SportProfile, Student, TalentProfile


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
def classmate(db, group, make_user):
    """Второй ученик того же класса — соперник по вызову."""
    other = Student.objects.create(
        last_name="Соперник",
        first_name="Второй",
        email="rival.quiz@example.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=other)
    user = make_user("student", other.email)
    other.user = user
    other.save(update_fields=["user"])
    return other


@pytest.fixture
def bank(db):
    """Десять заданий с вариантами — иначе играть не из чего."""
    made = []
    for i in range(10):
        question = Question.objects.create(exam_type="IELTS", section="reading", topic="Skimming", text=f"Вопрос {i}")
        QuestionOption.objects.create(question=question, letter="A", text="верно", is_correct=True)
        QuestionOption.objects.create(question=question, letter="B", text="неверно")
        made.append(question)
    return made


def play(api, user, *, kind: str = "solo", correct: int = 5) -> dict:
    """Сыграть матч: ответить на часть вопросов верно и закончить."""
    api.force_authenticate(user)
    started = api.post("/api/prep/quiz/start/", {"kind": kind, "exam_type": "IELTS"}, format="json")
    assert started.status_code == 201, started.data
    session = started.data["session"]
    state = api.get(f"/api/prep/practice/{session}/").data
    for index, row in enumerate(state["questions"]):
        option = next(o for o in row["options"] if (o["letter"] == "A") == (index < correct))
        api.post(
            f"/api/prep/practice/{session}/answer/",
            {"answer_id": row["answer_id"], "option": option["id"], "seconds": 5},
            format="json",
        )
    finished = api.post(f"/api/prep/quiz/players/{started.data['player']}/finish/", {"seconds": 60}, format="json")
    assert finished.status_code == 200, finished.data
    return {"player": started.data["player"], "match": finished.data, "code": started.data["match"]["code"]}


# --- Банк -------------------------------------------------------------------


@pytest.mark.django_db
def test_empty_bank_explains_itself(api, student_user):
    """Пустой банк объясняется словами, а не пустым экраном."""
    state = api if api.force_authenticate(student_user) is None else api
    data = state.get("/api/prep/quiz/").data
    assert data["bank"]["ready"] is False
    assert "не загружен" in data["bank"]["detail"]
    refused = state.post("/api/prep/quiz/start/", {"kind": "solo", "exam_type": "IELTS"}, format="json")
    assert refused.status_code == 400
    assert "банке нет заданий" in refused.data["detail"]


# --- Соло -------------------------------------------------------------------


@pytest.mark.django_db
def test_solo_score_is_counted_by_the_server(api, student_user, student, bank):
    """Счёт по точности и скорости считает сервер, а не клиент."""
    result = play(api, student_user, correct=7)
    player = QuizPlayer.objects.get(student=student)
    assert player.correct == 7
    assert player.total == 10
    assert player.score > 0
    assert player.best_streak == 7
    mine = next(row for row in result["match"]["players"] if row["is_me"])
    assert mine["score"] == player.score


@pytest.mark.django_db
def test_solo_result_is_personal(api, student_user, classmate, make_user, bank, student):
    """Чужой соло-результат ученику не показывается вовсе."""
    play(api, student_user, correct=6)
    match = QuizMatch.objects.get()

    api.force_authenticate(classmate.user)
    answer = api.get(f"/api/prep/quiz/matches/{match.pk}/")
    assert answer.status_code == 404, "чужой матч ученику не открывается"

    # и в своём состоянии он видит только свои матчи
    state = api.get("/api/prep/quiz/").data
    assert state["matches"] == []


# --- Вызов ------------------------------------------------------------------


@pytest.mark.django_db
def test_duel_is_visible_only_to_its_two_players(api, student_user, classmate, bank, group, make_user):
    """Результат вызова видят только двое участников."""
    api.force_authenticate(student_user)
    started = api.post("/api/prep/quiz/start/", {"kind": "duel", "exam_type": "IELTS"}, format="json")
    code = started.data["match"]["code"]
    assert code, "вызов обязан дать код: списка одноклассников ученику не показываем"

    api.force_authenticate(classmate.user)
    joined = api.post("/api/prep/quiz/join/", {"code": code}, format="json")
    assert joined.status_code == 201, joined.data
    match = QuizMatch.objects.get(kind=QuizKind.DUEL)
    assert match.status == QuizStatus.RUNNING
    assert match.players.count() == 2

    # третий в вызов не попадает
    third = Student.objects.create(
        last_name="Третий",
        first_name="Лишний",
        email="third.quiz@example.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    third_user = make_user("student", third.email)
    third.user = third_user
    third.save(update_fields=["user"])
    api.force_authenticate(third_user)
    refused = api.post("/api/prep/quiz/join/", {"code": code}, format="json")
    assert refused.status_code == 400
    # и чужой матч он не открывает
    assert api.get(f"/api/prep/quiz/matches/{match.pk}/").status_code == 404

    # а участник видит обоих
    api.force_authenticate(student_user)
    seen = api.get(f"/api/prep/quiz/matches/{match.pk}/").data
    assert len(seen["players"]) == 2


@pytest.mark.django_db
def test_wrong_code_says_so(api, student_user, bank):
    api.force_authenticate(student_user)
    answer = api.post("/api/prep/quiz/join/", {"code": "ZZZZZZ"}, format="json")
    assert answer.status_code == 400
    assert "проверьте код" in answer.data["detail"]


# --- Командный зачёт и обещание про рейтинги --------------------------------


@pytest.mark.django_db
def test_team_standings_show_classes_not_students(api, student_user, classmate, bank, student):
    """Публичен результат команды, а не отдельного ученика."""
    play(api, student_user, correct=8)
    play(api, classmate.user, correct=3)

    api.force_authenticate(student_user)
    teams = api.get("/api/prep/quiz/").data["teams"]
    assert teams["teams"], "зачёт классов пуст, хотя матчи сыграны"
    row = teams["teams"][0]
    assert row["team"] == student.group.code
    assert row["score"] > 0
    # ни одного имени и ни одного номера ученика в зачёте
    assert set(row) == {"team", "score", "matches", "accuracy"}


@pytest.mark.django_db
def test_student_answer_carries_no_one_elses_results(api, student_user, classmate, bank, student):
    """Приёмка фазы: в ответе API ученику нет чужих результатов.

    Проверяем по самому ответу, а не по экрану: имя и номер соперника
    не должны встретиться нигде, кроме матча, в котором ученик играл сам.
    """
    play(api, classmate.user, correct=9)
    play(api, student_user, correct=4)

    api.force_authenticate(student_user)
    payload = api.get("/api/prep/quiz/").json()
    text = str(payload)
    assert str(classmate) not in text
    assert f"'student': {classmate.pk}" not in text
    # свой результат при этом на месте
    assert payload["stats"]["matches"] == 1


@pytest.mark.django_db
def test_personal_stats_are_personal(api, student_user, classmate, bank):
    play(api, student_user, correct=5)
    play(api, classmate.user, correct=10)

    api.force_authenticate(student_user)
    stats = api.get("/api/prep/quiz/").data["stats"]
    assert stats["matches"] == 1
    assert stats["accuracy"] == 50
    assert stats["best_streak"] == 5


@pytest.mark.django_db
def test_director_sees_a_match_for_his_students(api, make_user, student_user, bank):
    """Директору личная статистика видна: это его работа, а не рейтинг."""
    play(api, student_user, correct=5)
    match = QuizMatch.objects.get()
    api.force_authenticate(make_user("director_exam"))
    seen = api.get(f"/api/prep/quiz/matches/{match.pk}/")
    assert seen.status_code == 200
    assert seen.data["players"][0]["score"] > 0


@pytest.mark.django_db
def test_quiz_is_a_student_screen(api, make_user):
    api.force_authenticate(make_user("director_exam"))
    assert api.get("/api/prep/quiz/").status_code == 403
    assert api.post("/api/prep/quiz/start/", {"exam_type": "IELTS"}, format="json").status_code == 403


def test_no_public_leaderboard_anywhere_in_the_code():
    """Ни в коде квиза, ни во фронте нет общей таблицы учеников.

    Проверка по исходникам: агрегат по ученикам мимо групп — это и есть
    рейтинг, а он у нас запрещён решением, а не вкусом.
    """
    import re
    from pathlib import Path

    root = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
    quiz = (root / "backend" / "prep" / "quiz.py").read_text(encoding="utf-8")
    # зачёт считается по группам, а не по ученикам
    assert 'values("student__group__code")' in quiz
    assert re.search(r'values\(\s*"student"\s*\)', quiz) is None
    screen = (root / "frontend" / "src" / "screens" / "Quiz.tsx").read_text(encoding="utf-8")
    for word in ("Таблица лидеров", "Рейтинг", "leaderboard"):
        assert word not in screen, f"на экране квиза появилось «{word}»"
