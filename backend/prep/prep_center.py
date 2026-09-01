"""Центр подготовки: прогресс по темам и статистика ученика (фаза 42).

Прогресс считается по банку и ответам: «решено N из M» — сколько разных
заданий ученик уже прошёл из того, что есть. Пока банк пуст, всё честно
показывает ноль и объясняет, что заданий нет, — не выдумывает вопросы.

Прогноз — это прогноз балла за тренировки, а не предсказание результата
экзамена: считается по доле верных, честно об этом говорит.
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Count, Q

from prep.models import PracticeAnswer, Question, Section
from students.models import ExamType, Student

#: Порядок экзаменов на плитках, когда справочник ничего не подсказал.
CENTER_EXAMS = ("SAT", "IELTS", "TOEFL", "ENT", "ACT", "HSK", "Duolingo")

EXAM_TITLES = {code: dict(ExamType.choices).get(code, code) for code in CENTER_EXAMS}


def visible_exams() -> tuple[str, ...]:
    """Экзамены, которые школа сейчас показывает ученику.

    Признак показа живёт у записи справочника (`ExamKind.is_active`),
    а не в коде: школа ведёт два экзамена, но данные по остальным целы,
    и понадобится ЕНТ — включается галочкой, без выката (фаза 48).

    Справочник ведёт названия («ЕНТ»), а банк и попытки — коды («ENT»),
    поэтому имя приводится к коду по подписям `ExamType`.
    """
    from directories.models import ExamKind

    code_by_title = {title: code for code, title in ExamType.choices}
    known = set(dict(ExamType.choices))
    names = ExamKind.objects.filter(is_active=True).order_by("sort_order", "name").values_list("name", flat=True)
    codes = [code_by_title.get(name, name) for name in names]
    visible = tuple(code for code in codes if code in known)
    # пустой справочник не должен оставлять раздел вовсе без экзаменов
    return visible or CENTER_EXAMS


def _solved_question_ids(student: Student, *, exam: str = "", section: str = "") -> set[int]:
    """Разные задания, на которые ученик уже ответил (не пустым выбором)."""
    rows = PracticeAnswer.objects.filter(session__student=student).exclude(chosen__isnull=True)
    if exam:
        rows = rows.filter(question__exam_type=exam)
    if section:
        rows = rows.filter(question__section=section)
    return set(rows.values_list("question_id", flat=True))


def exams(student: Student) -> list[dict]:
    """Плитки видимых экзаменов: банк по каждому и прогресс ученика."""
    bank = dict(Question.objects.filter(is_active=True).values_list("exam_type").annotate(n=Count("id")).order_by())
    solved = dict(
        PracticeAnswer.objects.filter(session__student=student)
        .exclude(chosen__isnull=True)
        .values_list("question__exam_type")
        .annotate(n=Count("question_id", distinct=True))
        .order_by()
    )
    return [
        {
            "exam_type": code,
            "title": EXAM_TITLES.get(code, code),
            "bank_total": bank.get(code, 0),
            "solved": solved.get(code, 0),
        }
        for code in visible_exams()
    ]


def sections(student: Student, exam: str) -> list[dict]:
    """Секции экзамена с числом заданий и прогрессом."""
    rows = (
        Question.objects.filter(is_active=True, exam_type=exam)
        .values("section")
        .annotate(total=Count("id"))
        .order_by("section")
    )
    solved = _solved_question_ids(student, exam=exam)
    section_titles = dict(Section.choices)
    solved_by_section = Question.objects.filter(pk__in=solved).values("section").annotate(n=Count("id")).order_by()
    solved_map = {row["section"]: row["n"] for row in solved_by_section}
    return [
        {
            "section": row["section"],
            "title": section_titles.get(row["section"], row["section"]),
            "total": row["total"],
            "solved": solved_map.get(row["section"], 0),
        }
        for row in rows
    ]


def topics(student: Student, exam: str, section: str) -> list[dict]:
    """Темы секции с прогрессом «решено N из M» по каждой отдельно."""
    rows = (
        Question.objects.filter(is_active=True, exam_type=exam, section=section)
        .values("topic")
        .annotate(total=Count("id"))
        .order_by("topic")
    )
    solved = _solved_question_ids(student, exam=exam, section=section)
    solved_by_topic = (
        Question.objects.filter(pk__in=solved, section=section).values("topic").annotate(n=Count("id")).order_by()
    )
    solved_map = {row["topic"]: row["n"] for row in solved_by_topic}
    return [
        {
            "topic": row["topic"],
            "total": row["total"],
            "solved": solved_map.get(row["topic"], 0),
            "percent": round(solved_map.get(row["topic"], 0) / row["total"] * 100) if row["total"] else 0,
        }
        for row in rows
    ]


def _forecast(student: Student, exam: str) -> dict:
    """Прогноз балла за тренировки по доле верных, с оговоркой о нехватке.

    Пока ответов мало, прямо говорится: «нужно N ответов». Это прогноз
    за тренировки, а не предсказание результата экзамена (инвариант №11 —
    родственный: не обещаем результат).
    """
    from prep.services import _score_for_share

    answers = PracticeAnswer.objects.filter(session__student=student, question__exam_type=exam).exclude(
        chosen__isnull=True
    )
    total = answers.count()
    need = max(0, 20 - total)
    correct = answers.filter(is_correct=True).count()
    share = correct / total if total else 0.0
    return {
        "enough": need == 0,
        "need_more": need,
        "answered": total,
        "share_percent": round(share * 100),
        "score": _score_for_share(exam, share) if need == 0 else None,
    }


def statistics(student: Student, exam: str) -> dict:
    """Статистика по экзамену: прогноз, до цели, рост, серия, календарь, слабые."""
    from engagement.scoring import summary as game_summary
    from students.models import ExamGoal

    forecast = _forecast(student, exam)

    goal = (
        ExamGoal.objects.filter(student=student, exam__name__iexact=exam, target_score__isnull=False)
        .order_by("exam_date")
        .first()
    )
    to_goal = None
    if goal is not None and forecast["score"] is not None:
        to_goal = round(float(goal.target_score) - forecast["score"], 1)

    # рост: доля верных в последних 20 ответах против предыдущих 20
    recent = list(
        PracticeAnswer.objects.filter(session__student=student, question__exam_type=exam)
        .exclude(chosen__isnull=True)
        .order_by("-answered_at")
        .values_list("is_correct", flat=True)[:40]
    )
    growth = None
    if len(recent) >= 20:
        newer = recent[:20]
        older = recent[20:40]
        if older:
            growth = round((sum(newer) / len(newer) - sum(older) / len(older)) * 100)

    # календарь активности: ответов по дням за 90 дней
    since = dt.date.today() - dt.timedelta(days=90)
    by_day = (
        PracticeAnswer.objects.filter(session__student=student, question__exam_type=exam, answered_at__date__gte=since)
        .values("answered_at__date")
        .annotate(n=Count("id"))
        .order_by("answered_at__date")
    )
    calendar = {str(row["answered_at__date"]): row["n"] for row in by_day}

    # слабые темы по всем ответам экзамена
    weak_rows = (
        PracticeAnswer.objects.filter(session__student=student, question__exam_type=exam)
        .exclude(chosen__isnull=True)
        .values("question__topic")
        .annotate(total=Count("id"), correct=Count("id", filter=Q(is_correct=True)))
        .order_by()
    )
    weak = sorted(
        (
            {
                "topic": row["question__topic"],
                "total": row["total"],
                "correct": row["correct"],
                "percent": round(row["correct"] / row["total"] * 100),
            }
            for row in weak_rows
            if row["total"] >= 3 and row["correct"] / row["total"] < 0.7
        ),
        key=lambda r: r["percent"],
    )[:10]

    game = game_summary(student)
    return {
        "forecast": forecast,
        "to_goal": to_goal,
        "growth": growth,
        "streak": game.get("streak_days", 0),
        "best_streak": game.get("best_streak", 0),
        "calendar": calendar,
        "weak_topics": weak,
        "achievements": _achievements(student),
    }


def _achievements(student: Student) -> list[dict]:
    """Бейджи с прогрессом: закрытые показаны замком (фаза 42).

    Закрытый = ученик ещё не получал XP этого вида. Прогресс — сколько
    таких начислений уже было.
    """
    from engagement.scoring import awards_table

    earned = dict(student.xp_events.values_list("kind").annotate(n=Count("id")).order_by())
    return [
        {
            "kind": row["kind"],
            "title": row["title"],
            "amount": row["amount"],
            "earned": row["kind"] in earned,
            "count": earned.get(row["kind"], 0),
        }
        for row in awards_table()
    ]
