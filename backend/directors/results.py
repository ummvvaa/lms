"""Результаты экзаменов 11 класса у академического директора — на чтение (24.10.2026).

Одна таблица по ученикам: последний Mock Test, лучший официальный балл,
цель и сколько до неё. Новых записей нет — это чтение `ExamAttempt`
и `ExamGoal`. Пробники файлом грузит администратор, Кымбат их читает.
"""

from __future__ import annotations

from decimal import Decimal

from core.parallels import admission_students
from students.models import AttemptFormat, ExamAttempt, ExamGoal, Student

EXAMS = ("IELTS", "SAT")


def goals_map(student_ids) -> dict[tuple[int, str], Decimal]:
    """`(ученик, экзамен)` → цель; экзамен цели — запись справочника с именем IELTS или SAT."""
    out: dict[tuple[int, str], Decimal] = {}
    rows = ExamGoal.objects.filter(student__in=list(student_ids), target_score__isnull=False).values_list(
        "student_id", "exam__name", "target_score"
    )
    for sid, name, target in rows:
        key = (sid, str(name).split()[0].upper())
        if key not in out or target > out[key]:
            out[key] = target
    return out


def goal_of(goals: dict[tuple[int, str], Decimal], student_id: int, exam: str) -> Decimal | None:
    return goals.get((student_id, exam.upper()))


def _sections(attempt: ExamAttempt) -> str:
    """Секции через «/»; секций нет вовсе — пусто: «– / – / – / –» ничего не говорит."""
    if attempt.exam_type == "IELTS":
        parts = (attempt.listening, attempt.reading, attempt.writing, attempt.speaking)
        if all(p is None for p in parts):
            return ""
        return " / ".join(f"{p:.1f}" if p is not None else "–" for p in parts)
    parts = (attempt.math, attempt.verbal)
    if all(p is None for p in parts):
        return ""
    return " / ".join(str(p) if p is not None else "–" for p in parts)


def _score(value) -> str:
    if value is None:
        return ""
    return f"{float(value):.1f}" if float(value) % 1 else str(int(value))


def rows(exam: str, *, group: str = "") -> dict:
    """Строки таблицы по экзамену: ученик, группа, последний мок с секциями, официальный, цель, разница."""
    exam = exam if exam in EXAMS else EXAMS[0]
    students = admission_students(Student.objects.filter(is_active=True)).select_related("group")
    if group:
        students = students.filter(group__code__iexact=group)
    students = list(students.order_by("group__code", "last_name", "first_name"))
    ids = [s.pk for s in students]
    attempts = ExamAttempt.objects.filter(student__in=ids, exam_type=exam, total_score__isnull=False).order_by(
        "student_id", "-date", "-id"
    )
    mock: dict[int, ExamAttempt] = {}
    official: dict[int, ExamAttempt] = {}
    counts: dict[int, int] = {}
    for attempt in attempts:
        counts[attempt.student_id] = counts.get(attempt.student_id, 0) + 1
        if attempt.attempt_format == AttemptFormat.MOCK:
            mock.setdefault(attempt.student_id, attempt)
        else:
            best = official.get(attempt.student_id)
            if best is None or attempt.total_score > best.total_score:
                official[attempt.student_id] = attempt
    goals = goals_map(ids)
    out = []
    for student in students:
        last = mock.get(student.pk)
        best = official.get(student.pk)
        goal = goal_of(goals, student.pk, exam)
        current = best.total_score if best is not None else (last.total_score if last is not None else None)
        gap = float(goal) - float(current) if goal is not None and current is not None else None
        out.append(
            {
                "id": student.pk,
                "full_name": student.full_name,
                "group": student.group.code if student.group_id else "",
                "mock": _score(last.total_score) if last else "",
                "mock_date": last.date if last else None,
                "sections": _sections(last) if last else "",
                "official": _score(best.total_score) if best else "",
                "official_date": best.date if best else None,
                "goal": _score(goal),
                "gap": round(gap, 1) if gap is not None and gap > 0 else 0 if gap is not None else None,
                "attempts": counts.get(student.pk, 0),
            }
        )
    with_mock = [r for r in out if r["mock"]]
    reached = sum(1 for r in out if r["gap"] == 0)
    far = 1.0 if exam == "IELTS" else 100
    summary = {
        "took": len(with_mock),
        "average": (
            _score(round(sum(float(r["mock"]) for r in with_mock) / len(with_mock), 1 if exam == "IELTS" else 0))
            if with_mock
            else ""
        ),
        "reached": reached,
        "with_goal": sum(1 for r in out if r["gap"] is not None),
        "far": sum(1 for r in out if r["gap"] is not None and r["gap"] >= far),
        "official": sum(1 for r in out if r["official"]),
        "students": len(out),
    }
    return {"exam": exam, "rows": out, "summary": summary, "groups": sorted({r["group"] for r in out if r["group"]})}


def history(student: Student) -> list[dict]:
    """Все попытки ученика по IELTS и SAT — окно «История попыток»."""
    attempts = ExamAttempt.objects.filter(student=student, exam_type__in=EXAMS).order_by("-date", "-id")
    return [
        {
            "id": a.pk,
            "exam": a.exam_type,
            "format": a.attempt_format,
            "format_title": a.get_attempt_format_display(),
            "date": None if a.date_unknown else a.date,
            "total": _score(a.total_score),
            "sections": _sections(a),
        }
        for a in attempts
    ]
