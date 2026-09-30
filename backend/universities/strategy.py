"""Общая стратегия подбора: три карточки текстом (фаза 40).

Факты собирает движок соответствия — названия вузов и числа берутся
только из справочника (инвариант №10). Модель их формулирует; без ключа
те же карточки собирает код, с пометкой об упрощённом режиме.

Ни в одной формулировке нет слова «шанс»: это соответствие требованиям
(инвариант №11) — правило закреплено тестом по текстам.
"""

from __future__ import annotations

from collections import Counter

from django.utils import translation
from django.utils.translation import gettext as _

from core.i18n import language_of
from core.parallels import parallel_of
from students.models import ExamGoal, Student
from universities.matching import MatchResult
from universities.models import MatchRun


def _facts(student: Student, run: MatchRun, final: list[MatchResult]) -> dict:
    """Факты для стратегии: только справочник и разрывы движка."""
    top = [
        {"university": r.university_name, "program": r.program_name, "percent": r.percent, "summary": r.summary()}
        for r in final[:5]
    ]
    gap_counter: Counter[str] = Counter()
    for result in final:
        for criterion in result.unmet:
            gap_counter[criterion.short_gap()] += 1
    goals = [
        (
            _("{exam} → {score} к {date}").format(
                exam=g.exam.name, score=g.target_score, date=f"{g.exam_date:%d.%m.%Y}"
            )
            if g.exam_date
            else f"{g.exam.name} → {g.target_score}"
        )
        for g in ExamGoal.objects.filter(student=student, target_score__isnull=False).select_related("exam")[:5]
    ]
    return {
        "top": top,
        "common_gaps": [gap for gap, _n in gap_counter.most_common(3)],
        "goals": goals,
        "open_count": sum(1 for r in final if r.is_open),
        "final_count": len(final),
        "grade": parallel_of(student),
        "graduation_year": student.graduation_year,
    }


def _rules(facts: dict) -> dict:
    """Запасной путь: три карточки правилами, без модели."""
    top = facts["top"]
    if not top:
        position = _(
            "Разобранных программ пока нет: в справочнике не нашлось программ с требованиями "
            "под выбранную специальность и страны. Попробуйте расширить условия."
        )
    else:
        names = ", ".join(f"{t['university']} ({t['percent']}%)" for t in top[:3])
        position = _(
            "Вы проходите по требованиям в {open} из {total} программ финального "
            "списка. Ближе всего сейчас: {names}. Проценты — соответствие требованиям из справочника."
        ).format(open=facts["open_count"], total=facts["final_count"], names=names)

    if facts["common_gaps"]:
        gaps = ", ".join(facts["common_gaps"])
        improve = _("Чаще всего не хватает: {gaps}. Это и есть то, что даст больше всего программ.").format(gaps=gaps)
        if facts["goals"]:
            improve += " " + _("Ваши цели уже поставлены: {goals}.").format(goals="; ".join(facts["goals"]))
    else:
        improve = _(
            "Явных разрывов по финальному списку нет — усиливайте портфолио и держите текущие баллы: "
            "они уже закрывают требования."
        )

    if facts["goals"]:
        next_step = _(
            "В этом месяце: проверьте регистрацию на ближайший экзамен из ваших целей и закройте "
            "одну задачу плана. Даты целей — в календаре."
        )
    else:
        next_step = _(
            "В этом месяце: поставьте цель по экзамену с датой в портфолио — от неё начнут работать "
            "календарь, напоминания и расчёт «если закрыть разрывы»."
        )

    return {"position": position, "improve": improve, "next_step": next_step, "offline": True}


def build_strategy(student: Student, run: MatchRun, final: list[MatchResult]) -> dict:
    """Три карточки: моделью, если она есть, иначе правилами.

    Считается фоновой задачей и сохраняется в прогоне ученика: текст —
    на его языке, а не на языке того, кто запустил подбор.
    """
    with translation.override(language_of(getattr(student, "user", None))):
        return _build_strategy(student, run, final)


def _build_strategy(student: Student, run: MatchRun, final: list[MatchResult]) -> dict:
    from suggestions import llm

    facts = _facts(student, run, final)
    if not llm.is_available() or not facts["top"]:
        return _rules(facts)

    schema = {
        "type": "object",
        "properties": {
            "position": {"type": "string"},
            "improve": {"type": "string"},
            "next_step": {"type": "string"},
        },
        "required": ["position", "improve", "next_step"],
    }
    system = (  # i18n-skip: промпт модели, язык ответа ИИ настраивается отдельно
        "Ты помогаешь школьнику готовиться к поступлению. Собери три коротких абзаца по-русски: "
        "«текущая позиция», «что важно усилить», «следующий шаг в этом месяце». Пиши только по фактам "
        "из запроса — вузы и числа не выдумывай. Проценты называй «соответствием требованиям», "
        "слова «шанс», «вероятность» и «прогноз» не используй. Тон — поддерживающий и конкретный."
    )
    try:
        answer = llm.complete(
            system=system,
            user=str(facts),
            purpose="selection_strategy",
            actor=student.user,
            role="student",
            schema=schema,
            max_tokens=800,
        )
        data = answer.parsed if isinstance(answer.parsed, dict) else {}
        position = str(data.get("position") or "").strip()
        improve = str(data.get("improve") or "").strip()
        next_step = str(data.get("next_step") or "").strip()
        banned = ("шанс", "вероятност", "прогноз")  # i18n-skip: фильтр запретных слов в ответе модели
        if not (position and improve and next_step):
            return _rules(facts)
        # модель могла нарушить запрет — фильтр в коде, а не в промпте
        if any(word in text.lower() for text in (position, improve, next_step) for word in banned):
            return _rules(facts)
        return {"position": position, "improve": improve, "next_step": next_step, "offline": False}
    except llm.LLMUnavailable:
        return _rules(facts)
