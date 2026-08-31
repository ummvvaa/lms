"""Лестница шагов ученика (фаза 37).

Пока путь не пройден, лестница — главный экран кабинета: пять шагов
с прогрессом, а не дашборд с карточками. Состояния считаются по базе,
как и «Начало работы»: панель не должна врать после очистки данных.

Внесённое учеником, но ещё не подтверждённое директором тоже считается:
шаг «внести баллы» выполнен, когда ученик свою часть сделал — решение
директора не должно держать его на месте.
"""

from __future__ import annotations

from core.domains import ROLE_STUDENT
from students.models import Student


def _pending_fields(student: Student, model_label: str) -> set[str]:
    """Поля модели, по которым у ученика висит нерешённое предложение."""
    from suggestions.models import SuggestionChange, SuggestionStatus

    return set(
        SuggestionChange.objects.filter(
            suggestion__role=ROLE_STUDENT,
            suggestion__status=SuggestionStatus.PENDING,
            student=student,
            model_label=model_label,
        ).values_list("field_name", flat=True)
    )


def build(student: Student) -> dict:
    """Пять шагов пути: что пройдено, что текущее, что ещё заперто."""
    from engagement.onboarding import QUESTIONS
    from universities.models import StudentUniversity

    session = getattr(student, "onboarding", None)
    answered = session.answers.count() if session is not None else 0
    profile_done = answered >= len(QUESTIONS)

    exam = getattr(student, "exam", None)
    exam_pending = _pending_fields(student, "students.ExamProfile")
    score_fields = ("ielts_current", "sat_current", "gpa", "ielts_target", "sat_target")
    scores_done = any(getattr(exam, f, None) is not None for f in score_fields) or bool(
        exam_pending & set(score_fields)
    )

    admission = getattr(student, "admission", None)
    admission_pending = _pending_fields(student, "students.AdmissionProfile")
    direction_done = bool(getattr(admission, "target_major", "")) or "target_major" in admission_pending

    universities = StudentUniversity.objects.filter(student=student).count()
    tasks = student.tasks.count()

    plan_locked = not (direction_done and universities > 0)

    steps = [
        {
            "code": "profile",
            "title": "Заполнить профиль",
            "hint": "Кто вы, куда хотите и какое направление вам ближе",
            "path": "/onboarding",
            "action": "Заполнить",
            "done": profile_done,
            "locked": False,
            "lock_reason": "",
            "count": answered,
            "total": len(QUESTIONS),
        },
        {
            "code": "scores",
            "title": "Внести баллы и цели по экзаменам",
            "hint": "Текущие баллы и то, к чему готовитесь. Директор подтвердит",
            "path": "/my-data",
            "action": "Внести баллы",
            "done": scores_done,
            "locked": False,
            "lock_reason": "",
        },
        {
            "code": "direction",
            "title": "Выбрать направление и запустить подбор",
            "hint": "По направлению и баллам каталог покажет, куда вы проходите",
            "path": "/catalog",
            "action": "Открыть подбор",
            "done": direction_done,
            "locked": False,
            "lock_reason": "",
        },
        {
            "code": "universities",
            "title": "Собрать список вузов",
            "hint": "Отберите программы из каталога в свой список",
            "path": "/catalog",
            "action": "Выбрать вузы",
            "done": universities > 0,
            "locked": False,
            "lock_reason": "",
            "count": universities,
        },
        {
            "code": "plan",
            "title": "Получить план",
            "hint": "Задачи собираются из ваших вузов и их дедлайнов",
            "path": "/roadmap",
            "action": "Открыть план",
            "done": tasks > 0,
            "locked": plan_locked,
            "lock_reason": "Откроется после направления и списка вузов: плана не бывает без вузов",
            "count": tasks,
        },
    ]
    done = sum(1 for s in steps if s["done"])
    return {
        "done": done,
        "total": len(steps),
        "complete": done == len(steps),
        "steps": steps,
    }
