"""ИИ и эссе.

Единственное разрешённое действие — задавать ученику вопросы, помогающие
раскрыть историю. Писать и переписывать текст эссе нельзя: ни целиком,
ни абзацами, ни «отредактируй мне вот это».

Вся активность ученика с ИИ по эссе видна куратору: каждый обмен
складывается в `EssayAssistLog`.
"""

from __future__ import annotations

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.i18n import active_language
from suggestions.llm import LLMUnavailable, complete, is_available
from suggestions.models import EssayAssistLog

SYSTEM = (  # i18n-skip: промпт модели
    """Ты помогаешь школьнику раскрыть собственную историю для эссе.

Категорически запрещено:
- писать текст эссе или его фрагменты;
- переписывать, редактировать или улучшать присланный текст;
- предлагать готовые формулировки, которые можно вставить в эссе.

Разрешено только одно: задавать вопросы, которые помогут ученику вспомнить
детали, мотивы и последствия его собственного опыта.

Ответ — 3–5 вопросов списком. Ничего кроме вопросов.
"""
)  # fmt: skip

#: Ответ, когда модель недоступна: вопросы общие, но по делу.
FALLBACK_QUESTIONS = [
    gettext_lazy("Что конкретно вы сделали в этой истории — какими были ваши действия, а не действия команды?"),
    gettext_lazy("Что было самым трудным моментом и как вы через него прошли?"),
    gettext_lazy("Что вы поняли о себе после этого, чего не понимали раньше?"),
    gettext_lazy("Как этот опыт связан с тем, чему вы хотите учиться дальше?"),
    gettext_lazy("Какая деталь этой истории запомнилась вам сильнее всего и почему?"),
]


def ask_questions(*, essay_id: int, prompt: str, actor=None) -> dict:
    """Задать ученику вопросы по его истории. Текст эссе не создаётся."""
    from roadmap.models import Essay

    essay = Essay.objects.filter(pk=essay_id).select_related("student").first()
    if essay is None:
        return {"ok": False, "detail": _("Эссе не найдено")}

    if is_available():
        try:
            response = complete(  # i18n-skip: промпт модели
                language=active_language(),
                system=SYSTEM,
                user=f"Ученик рассказывает: {prompt}\n\nЗадай вопросы, которые помогут раскрыть эту историю.",
                purpose="essay_questions",
                actor=actor,
                max_tokens=600,
            )
            questions = response.content.strip() or "\n".join(f"• {q}" for q in FALLBACK_QUESTIONS)
            offline = False
        except LLMUnavailable:
            questions, offline = "\n".join(f"• {q}" for q in FALLBACK_QUESTIONS), True
    else:
        questions, offline = "\n".join(f"• {q}" for q in FALLBACK_QUESTIONS), True

    # куратор видит всё: и что спросил ученик, и что ответил ИИ
    EssayAssistLog.objects.create(essay=essay, student=essay.student, prompt=prompt, questions=questions)

    return {"ok": True, "questions": questions, "offline": offline}
