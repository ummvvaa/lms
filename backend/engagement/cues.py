"""Сюжеты карусели на главной ученика (фаза 49).

Карусель — список незакрытых мест, а не украшение. Правила лежат
справочником (`HomeCue`): условие, заголовок, описание, кнопка, цвет.
Здесь — только то, что справочнику взять неоткуда: проверка условия
по состоянию базы и живое число в надписи над заголовком.

Незакрытых мест нет — список пуст, и карусель на главной не рисуется
вовсе: календарь занимает её место (решение владельца).
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from engagement.models import CueCondition, HomeCue
from students.models import Student

#: сколько дней тишины считаем «план не открывали»
PLAN_IDLE_DAYS = 7
#: горизонт, на котором дедлайн стипендии уже горит
SCHOLARSHIP_HORIZON_DAYS = 30


def _portfolio_gap(student: Student) -> str | None:
    """Портфолио заполнено не до конца: в надписи — сам процент."""
    from students.portfolio import state

    percent = state(student)["percent"]
    if percent >= 100:
        return None
    return f"Портфолио заполнено на {percent}%"


def _exam_goal_gap(student: Student) -> str | None:
    """Есть цель по экзамену, до которой не хватает текущего балла."""
    from students.models import ExamGoal

    exam = getattr(student, "exam", None)
    current = {
        "IELTS": getattr(exam, "ielts_current", None),
        "SAT": getattr(exam, "sat_current", None),
    }
    today = timezone.localdate()
    for goal in ExamGoal.objects.filter(student=student).select_related("exam").order_by("exam_date"):
        kind = goal.exam.name if goal.exam_id else ""
        have = current.get(kind.upper())
        if goal.target_score is None:
            continue
        if have is not None and float(have) >= float(goal.target_score):
            continue
        if goal.exam_date and goal.exam_date >= today:
            return f"До экзамена {(goal.exam_date - today).days} дн."
        if have is None:
            return f"Цель по {kind}: {goal.target_score}"
        return f"{kind} {have} — цель {goal.target_score}"
    return None


def _scholarship_deadline(student: Student) -> str | None:
    """Стипендии с ближайшим дедлайном, которых ученик ещё не сохранял."""
    from universities.models import SavedScholarship, Scholarship

    today = timezone.localdate()
    horizon = today + timedelta(days=SCHOLARSHIP_HORIZON_DAYS)
    saved = set(SavedScholarship.objects.filter(student=student).values_list("scholarship_id", flat=True))
    rows = Scholarship.objects.filter(deadline__gte=today, deadline__lte=horizon).exclude(pk__in=saved)
    count = rows.count()
    if count == 0:
        return None
    return f"Стипендий с ближайшим дедлайном: {count}"


def _plan_idle(student: Student) -> str | None:
    """План есть, но за неделю в нём ничего не двигалось."""
    from roadmap.models import ApplicationPlan, Task

    if not ApplicationPlan.objects.filter(student=student).exists():
        return None
    edge = timezone.now() - timedelta(days=PLAN_IDLE_DAYS)
    moved = Task.objects.filter(student=student, updated_at__gte=edge).exists()
    if moved:
        return None
    return f"Плана не касались {PLAN_IDLE_DAYS} дн."


def _no_universities(student: Student) -> str | None:
    """Список вузов пуст — без него не собрать ни плана, ни сроков."""
    from universities.models import StudentUniversity

    if StudentUniversity.objects.filter(student=student).exists():
        return None
    return "Список вузов пуст"


def _documents_missing(student: Student) -> str | None:
    """В чек-листе документов чего-то не хватает."""
    from students.portfolio import documents_checklist

    rows = documents_checklist(student)
    left = [row for row in rows if not row["done"]]
    if not left:
        return None
    return f"Не загружено документов: {len(left)} из {len(rows)}"


#: Проверка условия. Возвращает надпись над заголовком или None,
#: если место закрыто и сюжету на главной делать нечего.
CHECKS = {
    CueCondition.PORTFOLIO_GAP: _portfolio_gap,
    CueCondition.EXAM_GOAL_GAP: _exam_goal_gap,
    CueCondition.SCHOLARSHIP_DEADLINE: _scholarship_deadline,
    CueCondition.PLAN_IDLE: _plan_idle,
    CueCondition.NO_UNIVERSITIES: _no_universities,
    CueCondition.DOCUMENTS_MISSING: _documents_missing,
}


def build(student: Student) -> list[dict]:
    """Сюжеты для главной: по одному на каждое незакрытое место."""
    cues: list[dict] = []
    for rule in HomeCue.objects.filter(is_active=True):
        check = CHECKS.get(rule.condition)
        if check is None:
            continue
        eyebrow = check(student)
        if eyebrow is None:
            continue
        cues.append(
            {
                "code": rule.code,
                "condition": rule.condition,
                "eyebrow": eyebrow,
                "title": rule.title,
                "note": rule.description,
                "action": rule.action_label,
                "path": rule.action_path,
                "tone": rule.tone,
            }
        )
    return cues
