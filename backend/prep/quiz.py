"""Квиз в нашем виде: соло, вызов по коду, командный зачёт по классам.

У образца здесь рейтинговые матчи, MMR, лиги и публичная таблица лидеров.
**Мы так не делаем, и это решение принято.** У нас 250 подростков
в состоянии поступления, публичное сравнение бьёт по тем, кому и так
тяжело, а «топ-50 по XP» на экране — ежедневное напоминание остальным
двумстам, что они не в нём.

Что осталось от соревнования: личный результат на время, вызов один
на один (видят только двое) и командный зачёт по классам, где публична
сумма класса, а не строка ученика.

Вызов передаётся кодом, а не выбором из списка одноклассников: список
учеников ученику не показывается нигде, включая сырой ответ API
(инвариант №7, решение фазы 26 про поиск).
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from prep.models import (
    PracticeAnswer,
    PracticeSession,
    QuizKind,
    QuizMatch,
    QuizPlayer,
    QuizQuestion,
    QuizStatus,
    SessionStatus,
)
from prep.services import PrepError, available_questions
from students.models import Student

#: Сколько заданий в матче по умолчанию — пять минут игры, не урок.
DEFAULT_SIZE = 10

#: Норма времени на задание: быстрее — прибавка к счёту, медленнее — нет.
SECONDS_PER_QUESTION = 45

#: Сколько стоит верный ответ. Точность важнее скорости, поэтому база
#: крупная, а прибавка за скорость мелкая: выигрывает тот, кто решил больше.
POINTS_PER_CORRECT = 100
POINTS_PER_SAVED_SECOND = 2

#: Сколько дней входит в командный зачёт: сезон, а не «за всё время».
TEAM_DAYS = 30

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _code() -> str:
    """Код вызова: алфавит без похожих знаков — его диктуют голосом."""
    return "".join(random.choice(CODE_ALPHABET) for _ in range(6))


@dataclass(frozen=True)
class Scored:
    score: int
    correct: int
    total: int
    seconds: int
    best_streak: int


def score_of(session: PracticeSession) -> Scored:
    """Счёт по точности и скорости. Считает сервер, а не клиент."""
    rows = list(session.answers.all())
    score = 0
    correct = 0
    seconds = 0
    streak = best = 0
    for row in rows:
        seconds += row.seconds
        if row.is_correct:
            correct += 1
            streak += 1
            best = max(best, streak)
            saved = max(0, SECONDS_PER_QUESTION - row.seconds)
            score += POINTS_PER_CORRECT + saved * POINTS_PER_SAVED_SECOND
        else:
            streak = 0
    return Scored(score=score, correct=correct, total=len(rows), seconds=seconds, best_streak=best)


def _make_session(student: Student, match: QuizMatch) -> PracticeSession:
    """Своя сессия каждому участнику, но набор заданий один и тот же."""
    session = PracticeSession.objects.create(student=student, exam_type=match.exam_type, section=match.section)
    for row in match.questions.select_related("question").all():
        PracticeAnswer.objects.create(session=session, question=row.question)
    return session


@transaction.atomic
def start_solo(student: Student, *, exam_type: str, section: str = "", size: int = DEFAULT_SIZE) -> QuizPlayer:
    """Соло на время. Результат личный: он не попадает ни в какой общий список."""
    pool = list(available_questions(exam_type=exam_type, section=section))
    if not pool:
        raise PrepError("В банке нет заданий по этому экзамену — загрузите банк или попросите академического директора")
    match = QuizMatch.objects.create(kind=QuizKind.SOLO, exam_type=exam_type, section=section)
    for order, question in enumerate(random.sample(pool, min(size, len(pool))), start=1):
        QuizQuestion.objects.create(match=match, question=question, order=order)
    return QuizPlayer.objects.create(match=match, student=student, session=_make_session(student, match))


@transaction.atomic
def start_duel(student: Student, *, exam_type: str, section: str = "", size: int = DEFAULT_SIZE) -> QuizPlayer:
    """Вызов: тот же набор заданий и код, который ученик передаёт сам."""
    pool = list(available_questions(exam_type=exam_type, section=section))
    if not pool:
        raise PrepError("В банке нет заданий по этому экзамену — вызывать не с чем")
    match = QuizMatch.objects.create(
        kind=QuizKind.DUEL, exam_type=exam_type, section=section, status=QuizStatus.WAITING, code=_code()
    )
    for order, question in enumerate(random.sample(pool, min(size, len(pool))), start=1):
        QuizQuestion.objects.create(match=match, question=question, order=order)
    return QuizPlayer.objects.create(match=match, student=student, session=_make_session(student, match))


@transaction.atomic
def join_by_code(student: Student, *, code: str) -> QuizPlayer:
    """Принять вызов по коду. Больше двух участников в матче не бывает."""
    match = QuizMatch.objects.filter(code=code.strip().upper(), kind=QuizKind.DUEL).first()
    if match is None:
        raise PrepError("Такого вызова нет — проверьте код")
    mine = match.players.filter(student=student).first()
    if mine is not None:
        return mine
    if match.players.count() >= 2:
        raise PrepError("В этом вызове уже двое — попросите завести новый")
    match.status = QuizStatus.RUNNING
    match.save(update_fields=["status"])
    return QuizPlayer.objects.create(match=match, student=student, session=_make_session(student, match))


@transaction.atomic
def finish(player: QuizPlayer, *, seconds: int = 0) -> QuizPlayer:
    """Закончить свою половину матча и посчитать счёт."""
    session = player.session
    if session.status == SessionStatus.RUNNING:
        session.status = SessionStatus.FINISHED
        session.finished_at = timezone.now()
        session.seconds_spent = max(0, seconds)
        session.save(update_fields=["status", "finished_at", "seconds_spent"])

    scored = score_of(session)
    player.score = scored.score
    player.correct = scored.correct
    player.total = scored.total
    player.seconds = scored.seconds or session.seconds_spent
    player.best_streak = scored.best_streak
    player.finished_at = timezone.now()
    player.save(update_fields=["score", "correct", "total", "seconds", "best_streak", "finished_at"])

    match = player.match
    everyone_done = not match.players.filter(finished_at__isnull=True).exists()
    if everyone_done and (match.kind == QuizKind.SOLO or match.players.count() >= 2):
        match.status = QuizStatus.DONE
        match.finished_at = timezone.now()
        match.save(update_fields=["status", "finished_at"])
    return player


def match_payload(match: QuizMatch, *, viewer: Student | None, staff: bool = False) -> dict:
    """Матч глазами смотрящего.

    Чужой результат виден только участнику этого же матча и сотруднику.
    Ученику, который в матче не играл, чужих чисел не отдаётся вовсе —
    это и есть «публичной таблицы нет ни в каком виде».
    """
    players = list(match.players.select_related("student").all())
    inside = staff or (viewer is not None and any(player.student_id == viewer.pk for player in players))
    rows = []
    for player in players:
        if not inside and (viewer is None or player.student_id != viewer.pk):
            continue
        rows.append(
            {
                "id": player.pk,
                "student": player.student_id,
                "name": str(player.student),
                "is_me": viewer is not None and player.student_id == viewer.pk,
                "score": player.score,
                "correct": player.correct,
                "total": player.total,
                "percent": player.percent,
                "seconds": player.seconds,
                "best_streak": player.best_streak,
                "finished": player.finished_at is not None,
            }
        )
    return {
        "id": match.pk,
        "kind": match.kind,
        "kind_title": match.get_kind_display(),
        "exam_type": match.exam_type,
        "section": match.section,
        "status": match.status,
        "code": match.code if match.status == QuizStatus.WAITING else "",
        "created_at": match.created_at,
        "players": rows,
    }


def my_matches(student: Student, *, limit: int = 20) -> list[dict]:
    """Матчи ученика: свои и те, где он участник вызова."""
    matches = (
        QuizMatch.objects.filter(players__student=student)
        .distinct()
        .prefetch_related("players__student")
        .order_by("-created_at")[:limit]
    )
    return [match_payload(match, viewer=student) for match in matches]


def personal_stats(student: Student) -> dict:
    """Личная статистика. Видит её сам ученик и директора — больше никто."""
    players = list(QuizPlayer.objects.filter(student=student, finished_at__isnull=False))
    matches = len(players)
    correct = sum(player.correct for player in players)
    total = sum(player.total for player in players)
    seconds = sum(player.seconds for player in players)
    return {
        "matches": matches,
        "accuracy": round(correct / total * 100) if total else 0,
        "average_seconds": round(seconds / total) if total else 0,
        "best_streak": max((player.best_streak for player in players), default=0),
        "best_score": max((player.score for player in players), default=0),
    }


def team_standings(*, days: int = TEAM_DAYS) -> dict:
    """Командный зачёт по классам: публична сумма класса, а не строка ученика.

    Здесь намеренно нет ни одного имени: агрегат считается запросом
    по группам, и строк отдельных учеников в ответе не появляется.
    """
    since = timezone.now() - dt.timedelta(days=days)
    rows = (
        QuizPlayer.objects.filter(finished_at__gte=since, student__group__isnull=False)
        .values("student__group__code")
        .annotate(score=Sum("score"), matches=Count("id"), correct=Sum("correct"), answered=Sum("total"))
        .order_by("-score")
    )
    return {
        "days": days,
        "teams": [
            {
                "team": row["student__group__code"],
                "score": int(row["score"] or 0),
                "matches": row["matches"],
                "accuracy": round((row["correct"] or 0) / row["answered"] * 100) if row["answered"] else 0,
            }
            for row in rows
        ],
    }


def bank_state(exam_type: str = "") -> dict:
    """Есть ли из чего играть. Пустой банк объясняется словами, а не пустотой."""
    pool = available_questions(exam_type=exam_type)
    total = pool.count()
    return {
        "questions": total,
        "ready": total > 0,
        "detail": (
            "Банк заданий пока не загружен: играть не из чего. Загружает его администратор, "
            "ведёт академический директор"
            if total == 0
            else ""
        ),
    }
