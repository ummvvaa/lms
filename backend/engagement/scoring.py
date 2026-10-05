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

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from core import school_rules
from core.phrasing import tn
from engagement.models import StudentGameState, XPEvent, XPKind
from students.models import Student

#: Действие → правило школы «сколько XP за него» (`core.school_rules`, раздел
#: «XP и уровни»). Действия без правила нет: тест сверяет словарь с `XPKind`
AWARD_RULES = {
    XPKind.TASK_DONE: school_rules.XP_TASK_DONE,
    XPKind.EXERCISE_SOLVED: school_rules.XP_EXERCISE_SOLVED,
    XPKind.MOCK_TAKEN: school_rules.XP_MOCK_TAKEN,
    XPKind.PROFILE_SECTION: school_rules.XP_PROFILE_SECTION,
    XPKind.ESSAY_SUBMITTED: school_rules.XP_ESSAY_SUBMITTED,
    XPKind.ONBOARDING_DONE: school_rules.XP_ONBOARDING_DONE,
    XPKind.MATERIAL_APPROVED: school_rules.XP_MATERIAL_APPROVED,
    XPKind.HOMEWORK_ON_TIME: school_rules.XP_HOMEWORK_ON_TIME,
}


def award_size(kind: str, values: dict | None = None) -> int:
    """Сколько XP стоит действие. `values` — правила школы, если вызывающий их уже прочитал."""
    rule = AWARD_RULES.get(kind)
    if rule is None:
        return 0
    return int(values[rule] if values is not None else school_rules.value(rule))


def level_step(values: dict | None = None) -> int:
    """Сколько XP в одном уровне. Уровни отмечают движение, а не выстраивают гонку."""
    code = school_rules.XP_LEVEL_STEP
    return int(values[code] if values is not None else school_rules.value(code))


def level_for(xp: int, step: int | None = None) -> int:
    """Уровень по сумме XP. Первый уровень — сразу, с нуля."""
    return max(1, xp // (step or level_step()) + 1)


def xp_to_next(xp: int, step: int | None = None) -> tuple[int, int]:
    """Сколько набрано внутри текущего уровня и сколько нужно всего."""
    step = step or level_step()
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
        raise ValueError(gettext("XP за «{kind}» не начисляется: это не действие ученика").format(kind=kind))

    # размер начисления и шаг уровня — одним чтением правил школы
    values = school_rules.values()
    size = award_size(kind, values) if amount is None else amount
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
    state.level = level_for(state.xp, level_step(values))
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
        return tn(
            state.streak_days,
            "{n} день подряд — так держать|{n} дня подряд — так держать|{n} дней подряд — так держать",
        )
    if state.streak_days == 1:
        return gettext("Сегодня уже поработали. Завтра — второй день подряд")
    if state.best_streak:
        return tn(
            state.best_streak,
            "Начнём заново. Ваш лучший результат — {n} день подряд|"
            "Начнём заново. Ваш лучший результат — {n} дня подряд|"
            "Начнём заново. Ваш лучший результат — {n} дней подряд",
        )
    return gettext("Сделайте сегодня одно дело — и стрик начнётся")


def summary(student: Student) -> dict:
    """Состояние для дашборда ученика."""
    state = refresh_streak(get_state(student))
    inside, step = xp_to_next(state.xp)
    return {
        "xp": state.xp,
        # уровень — по действующему шагу: сохранённый пересчитывается только при начислении
        # и после смены правила расходился бы с полоской «набрано / нужно»
        "level": level_for(state.xp, step),
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
    values = school_rules.values()
    return [
        {"kind": kind, "title": XPKind(kind).label, "amount": award_size(kind, values)}
        for kind in XPKind.values
        if award_size(kind, values) > 0
    ]
