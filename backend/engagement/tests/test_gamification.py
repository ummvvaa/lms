"""Фаза 11: XP, уровни и стрик.

Инвариант №12 проверяется буквально: за баллы экзаменов, GPA и статусы
начислений нет и быть не может.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from engagement import scoring
from engagement.models import StudentGameState, XPEvent, XPKind
from roadmap.models import Task, TaskStatus
from roadmap.services import complete
from students.models import ExamProfile, Student


@pytest.fixture
def student(db):
    person = Student.objects.create(last_name="Ким", first_name="Дана", email="xp@school.kz", graduation_year=2027)
    ExamProfile.objects.create(student=person)
    return person


# --- инвариант №12 -------------------------------------------------------


@pytest.mark.django_db
def test_xp_is_given_for_actions_only():
    """В перечне начислений нет ни одного пункта про результат."""
    forbidden = ("ielts", "sat", "gpa", "score", "балл", "status", "статус", "toefl", "act")

    for kind in XPKind.values:
        low = f"{kind} {XPKind(kind).label}".lower()
        for word in forbidden:
            assert word not in low, f"«{kind}» похоже на начисление за результат"


@pytest.mark.django_db
def test_award_refuses_an_unknown_kind(student):
    with pytest.raises(ValueError, match="не начисляется"):
        scoring.award(student, kind="ielts_improved")


@pytest.mark.django_db
def test_raising_a_score_gives_no_xp(student):
    """Балл вырос — XP не начислился. Иначе система поощряет приписки."""
    student.exam.ielts_current = Decimal("7.5")
    student.exam.save()

    assert XPEvent.objects.filter(student=student).count() == 0


# --- начисление ----------------------------------------------------------


@pytest.mark.django_db
def test_completing_a_task_awards_xp(student):
    task = Task.objects.create(student=student, title="Сдать IELTS", category="test")

    complete(task, status=TaskStatus.DONE)

    state = scoring.get_state(student)
    assert state.xp == scoring.award_size(XPKind.TASK_DONE)
    assert XPEvent.objects.get(student=student).object_id == str(task.pk)


@pytest.mark.django_db
def test_reopening_and_closing_again_does_not_double_the_award(student):
    task = Task.objects.create(student=student, title="Собрать документы", category="documents")

    complete(task, status=TaskStatus.DONE)
    complete(task, status=TaskStatus.TODO)
    complete(task, status=TaskStatus.DONE)

    assert XPEvent.objects.filter(student=student).count() == 1


@pytest.mark.django_db
def test_level_grows_with_xp(student, set_rules):
    set_rules(xp_task_done=40)
    for i in range(3):
        complete(Task.objects.create(student=student, title=f"Задача {i}", category="test"), status=TaskStatus.DONE)

    state = scoring.get_state(student)
    assert state.xp == 120
    assert state.level == 2


@pytest.mark.django_db
def test_award_sizes_and_level_step_are_school_rules(student, set_rules):
    """У каждого действия — своё правило с прежним числом; шаг уровня действует сразу, XP не меняются."""
    from core import school_rules

    assert set(scoring.AWARD_RULES) == set(XPKind.values)
    former = {
        "task_done": 10,
        "exercise_solved": 5,
        "mock_taken": 25,
        "profile_section": 15,
        "essay_submitted": 20,
        "onboarding_done": 30,
        "material_approved": 25,
        "homework_on_time": 5,
    }
    assert {kind: scoring.award_size(kind) for kind in XPKind.values} == former
    assert school_rules.BY_CODE[school_rules.XP_TASK_DONE].section == school_rules.XP

    set_rules(xp_task_done=40)
    for i in range(3):
        complete(Task.objects.create(student=student, title=f"Шаг {i}", category="test"), status=TaskStatus.DONE)
    summary = scoring.summary(student)
    assert (summary["xp"], summary["level"], summary["level_progress"], summary["level_step"]) == (120, 2, 20, 100)

    set_rules(xp_level_step=50)
    summary = scoring.summary(student)
    assert (summary["xp"], summary["level"], summary["level_progress"], summary["level_step"]) == (120, 3, 20, 50)


@pytest.mark.django_db
def test_zero_award_gives_no_xp_and_leaves_the_table(student, set_rules):
    """Ноль в правиле — действие XP не даёт и из таблицы «за что дают» уходит."""
    set_rules(xp_task_done=0)
    complete(Task.objects.create(student=student, title="Без XP", category="test"), status=TaskStatus.DONE)
    assert not XPEvent.objects.filter(student=student).exists()
    assert "task_done" not in {row["kind"] for row in scoring.awards_table()}


# --- стрик ---------------------------------------------------------------


@pytest.mark.django_db
def test_streak_starts_at_one_on_the_first_action(student):
    complete(Task.objects.create(student=student, title="Первая", category="test"), status=TaskStatus.DONE)

    assert scoring.get_state(student).streak_days == 1


@pytest.mark.django_db
def test_streak_grows_on_a_second_day(student):
    state = StudentGameState.objects.create(
        student=student, xp=10, streak_days=1, last_active_on=timezone.localdate() - timedelta(days=1)
    )

    complete(Task.objects.create(student=student, title="Вторая", category="test"), status=TaskStatus.DONE)

    state.refresh_from_db()
    assert state.streak_days == 2
    assert state.best_streak == 2


@pytest.mark.django_db
def test_a_missed_day_resets_the_streak(student):
    StudentGameState.objects.create(
        student=student, xp=50, streak_days=5, best_streak=5, last_active_on=timezone.localdate() - timedelta(days=3)
    )

    complete(Task.objects.create(student=student, title="После перерыва", category="test"), status=TaskStatus.DONE)

    state = scoring.get_state(student)
    assert state.streak_days == 1
    # лучший результат помним: он нужен для поддерживающей формулировки
    assert state.best_streak == 5


@pytest.mark.django_db
def test_streak_resets_on_reading_too(student):
    """Ушёл на каникулы — стрик не должен висеть вечно."""
    StudentGameState.objects.create(
        student=student, xp=50, streak_days=7, last_active_on=timezone.localdate() - timedelta(days=5)
    )

    assert scoring.summary(student)["streak_days"] == 0


@pytest.mark.django_db
def test_wording_stays_supportive_at_zero(student):
    StudentGameState.objects.create(student=student, xp=0, streak_days=0)

    phrase = scoring.summary(student)["streak_phrase"]

    assert "потер" not in phrase.lower()
    assert "начн" in phrase.lower()


@pytest.mark.django_db
def test_summary_has_no_comparison_with_others(student):
    """Рейтингов и таблиц лидеров быть не должно — это вредно."""
    payload = scoring.summary(student)

    forbidden = ("rank", "place", "leader", "top", "место", "рейтинг", "лучше_чем")
    keys = " ".join(payload.keys()).lower()
    for word in forbidden:
        assert word not in keys
