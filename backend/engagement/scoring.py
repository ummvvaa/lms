"""Начисление XP, уровни и стрик.

Инвариант №12: XP даётся за действия, а не за результаты. Функция `award`
принимает только виды из `XPKind`, а там нет ни одного пункта про баллы
экзаменов, GPA или статусы — и не должно появиться.

Стрик считается по дням, в которые ученик сделал хотя бы одно действие.
Пропуск обнуляет. Формулировки при этом остаются поддерживающими: ученику
с нулевым стриком система не сообщает, что он всё потерял.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from engagement.models import StudentGameState, XPEvent, XPKind
from students.models import Student

#: Сколько XP стоит каждое действие. Размеры настраиваются.
DEFAULT_AWARDS = {
    XPKind.TASK_DONE: 10,
    XPKind.EXERCISE_SOLVED: 5,
    XPKind.MOCK_TAKEN: 25,
    XPKind.PROFILE_SECTION: 15,
    XPKind.ESSAY_SUBMITTED: 20,
    XPKind.ONBOARDING_DONE: 30,
}

#: Сколько XP нужно на каждый следующий уровень. Растёт, но не круто:
#: цель — отмечать движение, а не выстраивать соревнование.
LEVEL_STEP = 100


def award_size(kind: str) -> int:
    configured = getattr(settings, "XP_AWARDS", {})
    return int(configured.get(kind, DEFAULT_AWARDS.get(kind, 0)))


def level_for(xp: int) -> int:
    """Уровень по сумме XP. Первый уровень — сразу, с нуля."""
    step = int(getattr(settings, "XP_LEVEL_STEP", LEVEL_STEP))
    return max(1, xp // step + 1)


def xp_to_next(xp: int) -> tuple[int, int]:
    """Сколько набрано внутри текущего уровня и сколько нужно всего."""
    step = int(getattr(settings, "XP_LEVEL_STEP", LEVEL_STEP))
    return xp % step, step


def get_state(student: Student) -> StudentGameState:
    state, _ = StudentGameState.objects.get_or_create(student=student)
    return state


@transaction.atomic
def award(
    student: Student,
    *,
    kind: str,
    object_label: str = "",
    object_id: str = "",
    note: str = "",
    amount: int | None = None,
) -> XPEvent | None:
    """Начислить XP за действие.

    Повторное начисление за тот же объект не проходит: пере-открыл задачу
    и закрыл снова — это не второй повод дать XP.
    """
    if kind not in XPKind.values:
        raise ValueError(f"XP за «{kind}» не начисляется: это не действие ученика")

    size = award_size(kind) if amount is None else amount
    if size <= 0:
        return None

    if (
        object_id
        and XPEvent.objects.filter(student=student, kind=kind, object_label=object_label, object_id=object_id).exists()
    ):
        return None

    event = XPEvent.objects.create(
        student=student,
        kind=kind,
        amount=size,
        object_label=object_label,
        object_id=object_id,
        note=note,
    )

    state = get_state(student)
    state.xp += size
    state.level = level_for(state.xp)
    _touch_streak(state)
    state.save(update_fields=["xp", "level", "streak_days", "best_streak", "last_active_on", "updated_at"])
    return event


def _touch_streak(state: StudentGameState) -> None:
    """Отметить сегодняшнюю активность и пересчитать стрик."""
    today = timezone.localdate()
    if state.last_active_on == today:
        return
    if state.last_active_on == today - timedelta(days=1):
        state.streak_days += 1
    else:
        state.streak_days = 1
    state.best_streak = max(state.best_streak, state.streak_days)
    state.last_active_on = today


def refresh_streak(state: StudentGameState) -> StudentGameState:
    """Сбросить стрик, если день пропущен.

    Считается при чтении: без этого стрик «висел» бы бесконечно у того,
    кто ушёл на каникулы и не заходит.
    """
    today = timezone.localdate()
    if state.last_active_on is None:
        return state
    if state.last_active_on < today - timedelta(days=1) and state.streak_days:
        state.streak_days = 0
        state.save(update_fields=["streak_days", "updated_at"])
    return state


def streak_phrase(state: StudentGameState) -> str:
    """Поддерживающая формулировка. Никаких «вы всё потеряли»."""
    if state.streak_days >= 2:
        return f"{state.streak_days} дней подряд — так держать"
    if state.streak_days == 1:
        return "Сегодня уже поработали. Завтра — второй день подряд"
    if state.best_streak:
        return f"Начнём заново. Ваш лучший результат — {state.best_streak} дней подряд"
    return "Сделайте сегодня одно дело — и стрик начнётся"


def summary(student: Student) -> dict:
    """Состояние для дашборда ученика."""
    state = refresh_streak(get_state(student))
    inside, step = xp_to_next(state.xp)
    return {
        "xp": state.xp,
        "level": state.level,
        "level_progress": inside,
        "level_step": step,
        "streak_days": state.streak_days,
        "best_streak": state.best_streak,
        "active_today": state.is_active_today,
        "streak_phrase": streak_phrase(state),
        "recent": [
            {
                "kind": event.kind,
                "kind_title": event.get_kind_display(),
                "amount": event.amount,
                "note": event.note,
                "created_at": event.created_at,
            }
            for event in student.xp_events.all()[:10]
        ],
    }


def awards_table() -> list[dict]:
    """За что и сколько дают — ученику это видно, чтобы не было загадок."""
    return [
        {"kind": kind, "title": XPKind(kind).label, "amount": award_size(kind)}
        for kind in XPKind.values
        if award_size(kind) > 0
    ]
