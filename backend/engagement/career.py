"""Профтест: анкета плюс разбор моделью (фаза 45).

Владелец продукта согласовал упрощённый вариант: анкета и разбор, без
адаптивного теста. Половина одиннадцатиклассников не знает, куда идти, —
и простой вариант уже помогает.

Два правила, из-за которых файл выглядит именно так:

* **без ключа модели профтест не работает и честно об этом говорит.**
  Разбор анкеты правилами дал бы бессмысленный результат — «любите
  математику, значит, идите в математику», — а притворяться хуже, чем
  сказать «недоступно»;
* **инвариант №10**: специальности и программы берутся только
  из справочника. В модель уходят номера программ, обратно принимаются
  тоже номера — назвать вуз, которого нет в базе, ей физически нечем.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from engagement.models import CareerAnswer, CareerDirection, CareerQuestion, CareerRun, CareerRunStatus
from students.models import Student
from universities.models import Program

#: Сколько программ отдаём модели. Больше — лишний контекст и лишние деньги.
CANDIDATES = 60

#: Сколько направлений принимаем из разбора: больше пяти человек не читает.
MAX_DIRECTIONS = 5

SYSTEM = """Ты помогаешь ученику школы понять, какие направления обучения ему подходят.

Правила, нарушать нельзя:
- предлагай от трёх до пяти направлений, каждое — с объяснением, почему оно подходит
  именно по ответам ученика, а не вообще;
- для каждого направления назови школьные предметы и экзамены, которые под него нужны;
- программы указывай ТОЛЬКО номерами из переданного списка справочника школы;
  программы, которой нет в списке, не существует — не называй её никак;
- если под направление в справочнике программ нет, оставь список программ пустым
  и скажи об этом в объяснении;
- не обещай поступление и не употребляй слова «шанс», «вероятность», «прогноз»;
- пиши по-русски, коротко и по делу, без общих слов вроде «вы творческая личность».
"""

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "общий вывод в двух-трёх предложениях"},
        "directions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "название направления"},
                    "why": {"type": "string", "description": "почему подходит по ответам"},
                    "subjects": {"type": "string", "description": "школьные предметы под направление"},
                    "exams": {"type": "string", "description": "экзамены под направление"},
                    "programs": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "номера программ из переданного списка",
                    },
                },
                "required": ["title", "why"],
            },
        },
    },
    "required": ["directions"],
}


class CareerUnavailable(RuntimeError):
    """Профтест без модели не работает — и говорит об этом прямо."""


@dataclass(frozen=True)
class Availability:
    """Доступен ли профтест и почему нет."""

    available: bool
    detail: str


def availability() -> Availability:
    """Состояние профтеста для экрана: работает или почему не работает."""
    from suggestions.llm import is_available, is_configured
    from suggestions.llm import status as llm_status

    if is_available():
        return Availability(True, "Профтест доступен")
    detail = llm_status()["detail"]
    if not is_configured():
        return Availability(
            False,
            "Профтест разбирает ответы моделью, а она не подключена. "
            "Разбор правилами дал бы бессмысленный результат, поэтому раздел ждёт ключ. " + detail,
        )
    return Availability(False, detail)


def questions() -> list[CareerQuestion]:
    return list(CareerQuestion.objects.filter(is_active=True))


def _candidates() -> list[Program]:
    """Программы справочника, которые уйдут в модель."""
    return list(
        Program.objects.filter(is_active=True, university__is_active=True)
        .select_related("university")
        .order_by("university__world_rank", "university__name")[:CANDIDATES]
    )


def _prompt(answers: list[tuple[CareerQuestion, str]], programs: list[Program]) -> str:
    lines = ["Ответы ученика:"]
    for question, value in answers:
        lines.append(f"- {question.text}: {value.strip() or 'не ответил'}")
    lines.append("")
    if programs:
        lines.append("Программы справочника школы (только из них можно выбирать):")
        for program in programs:
            level = program.get_level_display()
            lines.append(f"- id={program.pk}: {program.name} · {program.university.name} · {level}")
    else:
        lines.append("Справочник программ школы пуст: списки программ оставь пустыми и скажи об этом.")
    lines.append("")
    lines.append("Назови от трёх до пяти направлений.")
    return "\n".join(lines)


def run_for(student: Student, *, answers: dict[str, str], actor=None, role: str = "") -> CareerRun:
    """Пройти профтест: сохранить ответы, получить разбор, разложить строками.

    Ответы и направления хранятся строками, а не одним текстом (инвариант
    №5 и №6): по ним потом сравнивают проходы между собой.

    Запись прохода и вызов модели намеренно в разных транзакциях: неудачный
    разбор должен остаться в истории с причиной, а не исчезнуть вместе
    с ответами — иначе ученик не поймёт, было его прохождение или нет.
    """
    from suggestions.llm import LLMUnavailable, complete

    state = availability()
    if not state.available:
        raise CareerUnavailable(state.detail)

    asked = questions()
    if not asked:
        raise CareerUnavailable("Анкета пуста: вопросы профтеста заводит директор школы. Пока их нет, разбирать нечего")

    with transaction.atomic():
        run = CareerRun.objects.create(student=student)
        pairs: list[tuple[CareerQuestion, str]] = []
        for question in asked:
            value = (answers.get(question.code) or "").strip()
            CareerAnswer.objects.create(run=run, question=question, value=value)
            pairs.append((question, value))

    programs = _candidates()
    known = {program.pk: program for program in programs}
    try:
        answer = complete(
            system=SYSTEM,
            user=_prompt(pairs, programs),
            purpose="career_test",
            actor=actor,
            role=role,
            schema=RESULT_SCHEMA,
            max_tokens=1800,
        )
    except LLMUnavailable as error:
        run.status = CareerRunStatus.FAILED
        run.error = str(error) or "Модель сейчас недоступна"
        run.save(update_fields=["status", "error"])
        raise CareerUnavailable(run.error) from error

    parsed = answer.parsed if isinstance(answer.parsed, dict) else {}
    run.summary = str(parsed.get("summary") or "")
    rows = parsed.get("directions")
    if not isinstance(rows, list) or not rows:
        run.status = CareerRunStatus.FAILED
        run.error = "Модель вернула пустой разбор — попробуйте пройти анкету ещё раз"
        run.save(update_fields=["summary", "status", "error"])
        raise CareerUnavailable(run.error)

    order = 0
    for item in rows[:MAX_DIRECTIONS]:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            continue
        order += 1
        direction = CareerDirection.objects.create(
            run=run,
            order=order,
            title=str(item["title"]).strip()[:150],
            reasoning=str(item.get("why") or "").strip(),
            subjects=str(item.get("subjects") or "").strip()[:300],
            exams=str(item.get("exams") or "").strip()[:300],
        )
        # принимаем только номера из переданного списка (инвариант №10)
        picked = [known[pid] for pid in (item.get("programs") or []) if isinstance(pid, int) and pid in known]
        if picked:
            direction.programs.set(picked)

    if order == 0:
        run.status = CareerRunStatus.FAILED
        run.error = "Разбор пришёл без направлений — попробуйте ещё раз"
    run.save(update_fields=["summary", "status", "error"])
    return run


def agree(direction: CareerDirection, *, user, student: Student) -> dict:
    """Ученик согласен с направлением — оно уходит предложением директору.

    Пишем не в профиль, а в `Suggestion`: целевую специальность ведёт домен
    «Поступление», и решение принимает его директор (инвариант №1, фаза 37).
    """
    from django.utils import timezone

    from suggestions.engine import create_student_suggestions

    created, rejected = create_student_suggestions(
        author=user,
        student=student,
        rows=[
            {
                "model": "students.AdmissionProfile",
                "field": "target_major",
                "value": direction.title,
                "student": student.pk,
                "reason": "выбрано по разбору профтеста",
            }
        ],
    )
    if not created:
        return {"ok": False, "detail": rejected[0]["reason"] if rejected else "Предложение не создалось"}

    direction.agreed_at = timezone.now()
    direction.suggestion = created[0]
    direction.save(update_fields=["agreed_at", "suggestion"])
    return {
        "ok": True,
        "suggestion": created[0].pk,
        "detail": "Направление ушло директору по поступлению — он подтвердит его в вашем профиле",
    }
