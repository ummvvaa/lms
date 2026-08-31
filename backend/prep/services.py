"""Тренировки и пробные экзамены: сборка, ответы, разбор.

Результат мока не трогает текущий балл ученика: он создаёт `ExamAttempt`
с форматом `mock` и источником `platform`, а решение «учитывать ли»
принимает директор экзаменов. Автоматически платформенный мок ничего
в `ExamProfile` не меняет.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from prep.models import (
    MockExam,
    MockRun,
    PracticeAnswer,
    PracticeSession,
    Question,
    QuestionOption,
    SessionStatus,
)
from students.models import AttemptFormat, AttemptSource, ExamAttempt, Student

#: Сколько заданий в тренировке по умолчанию.
DEFAULT_PRACTICE_SIZE = 10

#: Тема считается слабой, если верных ответов меньше этой доли.
WEAK_THRESHOLD = 0.6


class PrepError(ValueError):
    """Понятная человеку причина отказа."""


def available_questions(*, exam_type: str = "", section: str = "", difficulty: str = "", topic: str = ""):
    queryset = Question.objects.filter(is_active=True)
    if exam_type:
        queryset = queryset.filter(exam_type=exam_type)
    if section:
        queryset = queryset.filter(section=section)
    if difficulty:
        queryset = queryset.filter(difficulty=difficulty)
    if topic:
        queryset = queryset.filter(topic__iexact=topic)
    # без вариантов ответа задание непроходимо
    return queryset.filter(options__isnull=False).distinct()


@transaction.atomic
def start_practice(
    student: Student,
    *,
    exam_type: str,
    section: str = "",
    difficulty: str = "",
    topic: str = "",
    size: int = DEFAULT_PRACTICE_SIZE,
) -> PracticeSession:
    """Собрать тренировку. Вопросы берутся из банка, а не выдумываются."""
    pool = list(available_questions(exam_type=exam_type, section=section, difficulty=difficulty, topic=topic))
    if not pool:
        raise PrepError("В банке нет заданий по этим параметрам — попросите академического директора их добавить")

    session = PracticeSession.objects.create(
        student=student, exam_type=exam_type, section=section, difficulty=difficulty
    )
    chosen = random.sample(pool, min(size, len(pool)))
    for question in chosen:
        PracticeAnswer.objects.create(session=session, question=question)
    return session


def session_payload(session: PracticeSession, *, with_answers: bool = False) -> dict:
    """Что показать ученику. До завершения верные ответы не отдаются."""
    rows = session.answers.select_related("question", "chosen").prefetch_related("question__options")
    questions = []
    for row in rows:
        question = row.question
        item = {
            "answer_id": row.pk,
            "question": question.pk,
            "text": question.text,
            "section": question.section,
            "topic": question.topic,
            "difficulty": question.difficulty,
            "options": [
                {"id": option.pk, "letter": option.letter, "text": option.text} for option in question.options.all()
            ],
            "chosen": row.chosen_id,
            "answered": row.chosen_id is not None,
        }
        if with_answers:
            correct = question.correct_option
            item.update(
                {
                    "is_correct": row.is_correct,
                    "correct_option": correct.pk if correct else None,
                    "correct_letter": correct.letter if correct else "",
                    "explanation": question.explanation,
                    "source": question.source,
                }
            )
        questions.append(item)

    return {
        "id": session.pk,
        "exam_type": session.exam_type,
        "section": session.section,
        "difficulty": session.difficulty,
        "status": session.status,
        "total": session.total,
        "answered": session.answers.exclude(chosen__isnull=True).count(),
        "correct": session.correct if with_answers else None,
        "percent": session.percent if with_answers else None,
        "questions": questions,
    }


@transaction.atomic
def answer_question(session: PracticeSession, *, answer_id: int, option_id: int | None, seconds: int = 0) -> dict:
    """Записать ответ. Верность считает сервер, а не клиент."""
    if session.status != SessionStatus.RUNNING:
        raise PrepError("Эта сессия уже завершена")

    row = session.answers.filter(pk=answer_id).select_related("question").first()
    if row is None:
        raise PrepError("Такого вопроса в сессии нет")

    option = None
    if option_id is not None:
        option = QuestionOption.objects.filter(pk=option_id, question=row.question).first()
        if option is None:
            raise PrepError("Этот вариант не относится к заданию")

    row.chosen = option
    row.is_correct = bool(option and option.is_correct)
    row.seconds = max(0, seconds)
    row.save(update_fields=["chosen", "is_correct", "seconds"])
    return {"answer_id": row.pk, "answered": True}


def weak_topics(session: PracticeSession) -> list[dict]:
    """Темы, где ошибок больше, чем попаданий."""
    stats: dict[str, dict[str, int]] = {}
    for row in session.answers.select_related("question"):
        topic = row.question.topic or row.question.get_section_display()
        bucket = stats.setdefault(topic, {"total": 0, "correct": 0})
        bucket["total"] += 1
        bucket["correct"] += 1 if row.is_correct else 0

    weak = [
        {
            "topic": topic,
            "total": bucket["total"],
            "correct": bucket["correct"],
            "percent": round(bucket["correct"] / bucket["total"] * 100),
        }
        for topic, bucket in stats.items()
        if bucket["total"] and bucket["correct"] / bucket["total"] < WEAK_THRESHOLD
    ]
    return sorted(weak, key=lambda row: row["percent"])


def recommendation(session: PracticeSession, weak: list[dict]) -> str:
    """Что подтянуть. Одно действие, а не список из десяти пунктов."""
    if session.total == 0:
        return "Сессия пустая — заданий не было."
    if not weak:
        return f"Ошибок почти нет: {session.correct} из {session.total}. Можно брать сложность выше."
    first = weak[0]
    return (
        f"Слабее всего идёт тема «{first['topic']}»: {first['correct']} из {first['total']}. "
        "С неё и начните следующую тренировку."
    )


@transaction.atomic
def finish_practice(session: PracticeSession, *, seconds: int = 0) -> dict:
    """Завершить тренировку и собрать разбор."""
    if session.status == SessionStatus.RUNNING:
        session.status = SessionStatus.FINISHED
        session.finished_at = timezone.now()
        session.seconds_spent = max(session.seconds_spent, seconds)
        session.save(update_fields=["status", "finished_at", "seconds_spent"])

        _award_for_practice(session)

    weak = weak_topics(session)
    payload = session_payload(session, with_answers=True)
    payload.update(
        {
            "weak_topics": weak,
            "recommendation": recommendation(session, weak),
            "seconds_spent": session.seconds_spent,
        }
    )
    return payload


def _award_for_practice(session: PracticeSession) -> None:
    """XP за прохождение, а не за результат (инвариант №12)."""
    from engagement.models import XPKind
    from engagement.scoring import award

    answered = session.answers.exclude(chosen__isnull=True).count()
    if answered == 0:
        return
    award(
        session.student,
        kind=XPKind.EXERCISE_SOLVED,
        object_label="prep.PracticeSession",
        object_id=str(session.pk),
        note=f"Тренировка: {answered} заданий",
    )


# --- пробные экзамены -----------------------------------------------------


@dataclass(frozen=True)
class MockShortage:
    """Каких заданий не хватило, чтобы собрать мок."""

    section: str
    asked: int
    available: int


@transaction.atomic
def start_mock(student: Student, mock: MockExam) -> tuple[MockRun, list[MockShortage]]:
    """Собрать мок из банка по описанию секций."""
    if not mock.is_active:
        raise PrepError("Этот пробный экзамен сейчас недоступен")

    session = PracticeSession.objects.create(student=student, exam_type=mock.exam_type)
    shortages: list[MockShortage] = []
    picked = 0

    for part in mock.sections.all():
        pool = list(available_questions(exam_type=mock.exam_type, section=part.section))
        take = min(part.question_count, len(pool))
        if take < part.question_count:
            shortages.append(MockShortage(part.section, part.question_count, len(pool)))
        for question in random.sample(pool, take):
            PracticeAnswer.objects.create(session=session, question=question)
            picked += 1

    if picked == 0:
        session.delete()
        raise PrepError("В банке нет заданий для этого мока — попросите академического директора их добавить")

    run = MockRun.objects.create(student=student, mock=mock, session=session)
    return run, shortages


def _score_for_share(exam_type: str, share: float) -> float:
    """Доля верных → балл в шкале экзамена. Грубо и честно (см. `_score_for`)."""
    if exam_type in ("IELTS", "TOEFL"):
        # IELTS: 0..9 с шагом 0.5
        return round(share * 9 * 2) / 2
    if exam_type == "SAT":
        return float(round((400 + share * 1200) / 10) * 10)
    if exam_type == "ACT":
        return float(round(share * 36))
    if exam_type == "ENT":
        return float(round(share * 140))
    return round(share * 100, 1)


def _score_for(run: MockRun) -> float:
    """Балл мока в шкале экзамена.

    Пересчёт грубый и честно об этом говорит: точную шкалу знает только
    экзаменатор, а нам нужна сопоставимая динамика.
    """
    session = run.session
    if session.total == 0:
        return 0.0
    return _score_for_share(run.mock.exam_type, session.correct / session.total)


@transaction.atomic
def finish_mock(run: MockRun, *, seconds: int = 0) -> dict:
    """Завершить мок: создать попытку экзамена и собрать разбор.

    Текущий балл в `ExamProfile` при этом не меняется — решение
    принимает директор экзаменов.
    """
    payload = finish_practice(run.session, seconds=seconds)

    if run.exam_attempt is None:
        score = _score_for(run)
        attempt = ExamAttempt.objects.create(
            student=run.student,
            exam_type=run.mock.exam_type,
            attempt_format=AttemptFormat.MOCK,
            source=AttemptSource.PLATFORM,
            date=timezone.localdate(),
            total_score=score,
        )
        run.exam_attempt = attempt
        run.save(update_fields=["exam_attempt"])

        from engagement.models import XPKind
        from engagement.scoring import award

        award(
            run.student,
            kind=XPKind.MOCK_TAKEN,
            object_label="prep.MockRun",
            object_id=str(run.pk),
            note=run.mock.title[:250],
        )
        _tasks_from_weak_topics(run, payload["weak_topics"])

    payload.update(
        {
            "run": run.pk,
            "mock": run.mock.title,
            "exam_type": run.mock.exam_type,
            "score": float(run.exam_attempt.total_score) if run.exam_attempt else None,
            "attempt": run.exam_attempt_id,
            "counted_in_profile": run.counted_in_profile,
            "note": "Балл платформенного мока не меняет текущий балл в профиле — его сверит академический директор.",
        }
    )
    return payload


def _tasks_from_weak_topics(run: MockRun, weak: list[dict]) -> None:
    """Слабые темы превращаются в задачи роадмапа.

    Без этого разбор остаётся текстом, который никто не открывает второй раз.
    """
    from roadmap.models import Task, TaskCategory, TaskPriority

    for row in weak[:3]:
        title = f"Подтянуть тему «{row['topic']}» ({run.mock.exam_type})"
        if Task.objects.filter(student=run.student, title=title).exists():
            continue
        Task.objects.create(
            student=run.student,
            title=title,
            category=TaskCategory.TEST,
            priority=TaskPriority.HIGH if row["percent"] < 40 else TaskPriority.MEDIUM,
            description=(f"На пробном «{run.mock.title}» по этой теме верно {row['correct']} из {row['total']}."),
        )


@transaction.atomic
def review_mock(run: MockRun, *, count_it: bool, actor) -> dict:
    """Директор решает, учитывать ли платформенный мок в текущем балле."""
    run.counted_in_profile = count_it
    run.reviewed_by = actor
    run.reviewed_at = timezone.now()
    run.save(update_fields=["counted_in_profile", "reviewed_by", "reviewed_at"])

    if count_it and run.exam_attempt and run.exam_attempt.total_score is not None:
        from core.audit import apply_changes
        from core.domains import Source

        profile = getattr(run.student, "exam", None)
        field = {"IELTS": "ielts_current", "SAT": "sat_current"}.get(run.mock.exam_type)
        if profile is not None and field:
            apply_changes(profile, {field: run.exam_attempt.total_score}, actor=actor, source=Source.MANUAL)

    return {"run": run.pk, "counted_in_profile": run.counted_in_profile}
