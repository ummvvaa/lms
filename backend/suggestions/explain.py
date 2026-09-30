"""ИИ объясняет соответствие.

Опирается только на данные из `AdmissionRequirement`. Если требований
в справочнике нет — так и говорит, а не выдумывает пороги.

Без подключённой модели объяснение всё равно собирается: из тех же
критериев движка соответствия, только формулировки проще.
"""

from __future__ import annotations

from django.utils.translation import gettext as _

from core.i18n import active_language
from students.models import Student
from suggestions.llm import LLMUnavailable, complete, is_available
from universities.matching import match
from universities.models import Program

SYSTEM = (  # i18n-skip: промпт модели
    """Ты помогаешь ученику понять, чего не хватает для поступления.

Правила, нарушать нельзя:
- опирайся ТОЛЬКО на переданные требования и баллы, ничего не добавляй от себя;
- если требований нет, так и скажи, не придумывай пороги;
- не используй ярлыки вроде «слабый», «критический», A/B/C — говори о конкретных баллах;
- пиши коротко, дружелюбно и по делу;
- не обещай вероятность поступления: слов «шанс», «прогноз», «вероятность» быть не должно;
- в конце назови ОДНО действие, которое больше всего поднимет соответствие требованиям.
"""
)  # fmt: skip


def _offline_explanation(result) -> str:
    """Объяснение без модели: те же факты, формулировки попроще."""
    if not result.has_requirements:
        return _(
            "Требования программы «{program}» ещё не заведены в справочнике, "
            "поэтому сказать, проходите ли вы, нельзя. Попросите директора по поступлению их добавить."
        ).format(program=result.program_name)
    if result.is_open:
        return _(
            "По всем заведённым требованиям {university} — {program} вы проходите. "
            "Дальше выигрывают эссе и портфолио."
        ).format(university=result.university_name, program=result.program_name)

    lines = [
        _("До {university} — {program} осталось немного:").format(
            university=result.university_name, program=result.program_name
        )
    ]
    for criterion in result.unmet:
        if criterion.is_unknown:
            lines.append(
                _("• {criterion}: данных нет, нужен результат от {threshold}").format(
                    criterion=criterion.title, threshold=criterion.threshold
                )
            )
        else:
            lines.append(
                _("• {criterion}: сейчас {current}, нужно {threshold} — добрать {gap}").format(
                    criterion=criterion.title,
                    current=criterion.current,
                    threshold=criterion.threshold,
                    gap=criterion.gap,
                )
            )

    biggest = max(result.unmet, key=lambda c: c.gap if not c.is_unknown else c.threshold)
    lines.append(_("Больше всего сейчас даст работа над «{criterion}».").format(criterion=biggest.title))
    return "\n".join(lines)


def explain_student_program(*, student_id: int, program_id: int, actor=None) -> dict:
    """Объяснить соответствие ученика программе."""
    student = Student.objects.filter(pk=student_id).select_related("exam").first()
    program = Program.objects.filter(pk=program_id).select_related("university", "requirement").first()
    if student is None or program is None:
        return {"ok": False, "detail": _("Ученик или программа не найдены")}

    result = match(student, program)

    if not result.has_requirements:
        # без требований объяснять нечего — модель не зовём вовсе
        return {
            "ok": True,
            "has_requirements": False,
            "text": _offline_explanation(result),
            "offline": True,
        }

    if not is_available():
        return {"ok": True, "has_requirements": True, "text": _offline_explanation(result), "offline": True}

    # в модель уходят только критерии этой программы, не профиль целиком
    facts = {  # i18n-skip: данные для промпта модели
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
        response = complete(  # i18n-skip: промпт модели
            language=active_language(),
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
