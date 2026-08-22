"""ИИ объясняет соответствие.

Опирается только на данные из `AdmissionRequirement`. Если требований
в справочнике нет — так и говорит, а не выдумывает пороги.

Без подключённой модели объяснение всё равно собирается: из тех же
критериев движка соответствия, только формулировки проще.
"""

from __future__ import annotations

from students.models import Student
from suggestions.llm import LLMUnavailable, complete, is_configured
from universities.matching import match
from universities.models import Program

SYSTEM = """Ты помогаешь ученику понять, чего не хватает для поступления.

Правила, нарушать нельзя:
- опирайся ТОЛЬКО на переданные требования и баллы, ничего не добавляй от себя;
- если требований нет, так и скажи, не придумывай пороги;
- не используй ярлыки вроде «слабый», «критический», A/B/C — говори о конкретных баллах;
- пиши по-русски, коротко, дружелюбно и по делу;
- не обещай вероятность поступления: слов «шанс», «прогноз», «вероятность» быть не должно;
- в конце назови ОДНО действие, которое больше всего поднимет соответствие требованиям.
"""


def _offline_explanation(result) -> str:
    """Объяснение без модели: те же факты, формулировки попроще."""
    if not result.has_requirements:
        return (
            f"Требования программы «{result.program_name}» ещё не заведены в справочнике, "
            "поэтому сказать, проходите ли вы, нельзя. Попросите директора по поступлению их добавить."
        )
    if result.is_open:
        return (
            f"По всем заведённым требованиям {result.university_name} — {result.program_name} вы проходите. "
            "Дальше выигрывают эссе и портфолио."
        )

    lines = [f"До {result.university_name} — {result.program_name} осталось немного:"]
    for criterion in result.unmet:
        if criterion.is_unknown:
            lines.append(f"• {criterion.title}: данных нет, нужен результат от {criterion.threshold}")
        else:
            lines.append(
                f"• {criterion.title}: сейчас {criterion.current}, нужно {criterion.threshold} "
                f"— добрать {criterion.gap}"
            )

    biggest = max(result.unmet, key=lambda c: c.gap if not c.is_unknown else c.threshold)
    lines.append(f"Больше всего сейчас даст работа над «{biggest.title}».")
    return "\n".join(lines)


def explain_student_program(*, student_id: int, program_id: int, actor=None) -> dict:
    """Объяснить соответствие ученика программе."""
    student = Student.objects.filter(pk=student_id).select_related("exam").first()
    program = Program.objects.filter(pk=program_id).select_related("university", "requirement").first()
    if student is None or program is None:
        return {"ok": False, "detail": "Ученик или программа не найдены"}

    result = match(student, program)

    if not result.has_requirements:
        # без требований объяснять нечего — модель не зовём вовсе
        return {
            "ok": True,
            "has_requirements": False,
            "text": _offline_explanation(result),
            "offline": True,
        }

    if not is_configured():
        return {"ok": True, "has_requirements": True, "text": _offline_explanation(result), "offline": True}

    # в модель уходят только критерии этой программы, не профиль целиком
    facts = {
        "программа": f"{result.university_name} — {result.program_name}",
        "критерии": [
            {
                "название": c.title,
                "у ученика": c.current,
                "требуется": c.threshold,
                "не хватает": c.gap if not c.is_met else 0,
            }
            for c in result.criteria
        ],
    }

    try:
        response = complete(
            system=SYSTEM,
            user=f"Данные:\n{facts}\n\nОбъясни, чего не хватает и что больше всего поднимет соответствие требованиям.",
            purpose="explain_match",
            actor=actor,
            max_tokens=700,
        )
        text = response.content.strip() or _offline_explanation(result)
        offline = False
    except LLMUnavailable:
        text, offline = _offline_explanation(result), True

    return {
        "ok": True,
        "has_requirements": True,
        "text": text,
        "offline": offline,
        "criteria": [c.as_dict() for c in result.criteria],
    }
