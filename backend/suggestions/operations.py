"""Операции уровня управления — то, ради чего модель и подключается.

Общее устройство у всех одинаковое:

1. собрать факты из базы — только те, что нужны операции;
2. отдать их модели обезличенно, идентификаторами вместо имён;
3. подставить имена обратно на сервере;
4. если модели нет, лимит выбран или провайдер молчит — собрать тот же
   ответ правилами и честно сказать, что он собран без модели.

Профиль ученика целиком не уходит никогда. Инварианты №10, №11 и №12
действуют: вузов вне справочника не называем, процент — это соответствие
требованиям, а не шанс, XP за баллы не начисляется.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from itertools import pairwise
from typing import Any

from django.db.models import Count
from django.utils import timezone

from core.domains import ROLE_TITLES, domain_of_role
from core.labels import field_title, value_title
from core.phrasing import counted, days_left, listing, people
from students.models import Student
from suggestions.llm import LLMUnavailable, complete

RULES = """Ты помощник директора частной школы, готовящей учеников к поступлению.

Правила, нарушать нельзя:
- опирайся ТОЛЬКО на переданные факты, ничего не добавляй от себя;
- не называй вузов, программ и требований, которых нет в переданных данных;
- не обещай вероятность поступления: слов «шанс», «прогноз», «вероятность» быть не должно.
  Процент — это соответствие требованиям справочника, и называть его надо так;
- не используй внутренние ярлыки вроде «слабый», «критический», A/B/C;
- пиши по-русски, коротко и по делу, без канцелярита и без общих слов;
- учеников называй по номерам, которые переданы: имена подставит система.
"""


@dataclass
class Outcome:
    """Ответ операции: готовый текст плюс отметка, собран ли он моделью."""

    text: str = ""
    lines: list[str] = field(default_factory=list)
    offline: bool = True
    suggestion: int | None = None
    rows: int = 0
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": True,
            "text": self.text,
            "lines": self.lines,
            "offline": self.offline,
            "suggestion": self.suggestion,
            "rows": self.rows,
            "detail": self.detail or (offline_reason() if self.offline else ""),
        }


def offline_reason() -> str:
    """Почему ответ собран правилами.

    «Модель не подключена» при живом ключе отправляет администратора
    проверять ключ, с которым всё в порядке. Причины две, и они разные.
    """
    from suggestions.llm import is_configured

    if not is_configured():
        return "Собрано правилами: модель не подключена"
    return "Собрано правилами: модель не ответила"


# --- Обезличивание --------------------------------------------------------


class Roster:
    """Номера вместо имён: в модель уходит «ученик 3», а не «Ахметова Алия».

    Обратная подстановка делается здесь же, на сервере. Профиль целиком
    не отправляется никогда — только те поля, что нужны операции.
    """

    def __init__(self, students) -> None:
        self.by_number: dict[int, Student] = {i + 1: s for i, s in enumerate(students)}
        self.number_of: dict[int, int] = {s.pk: i + 1 for i, s in enumerate(students)}

    def label(self, student: Student) -> str:
        return f"ученик {self.number_of[student.pk]}"

    def restore(self, text: str) -> str:
        """Вернуть имена на место: «ученик 3» → «Ахметова Алия»."""
        import re

        def swap(match: re.Match) -> str:
            student = self.by_number.get(int(match.group(1)))
            return student.full_name if student else match.group(0)

        return re.sub(r"[Уу]ченик\s+(\d+)", swap, text)


# --- Факты для операций ---------------------------------------------------


def _exam_facts(student: Student) -> dict:
    profile = getattr(student, "exam", None)
    if profile is None:
        return {}
    return {
        "IELTS сейчас": str(profile.ielts_current or "нет данных"),
        "IELTS цель": str(profile.ielts_target or "не задана"),
        "SAT сейчас": str(profile.sat_current or "нет данных"),
        "SAT цель": str(profile.sat_target or "не задан"),
        "часов в неделю": str(profile.hours_per_week or 0),
    }


def _domain_facts(student: Student, domain_code: str) -> dict:
    """Только поля своего домена: чужие директору тут не нужны."""
    from core.domains import DOMAINS

    domain = DOMAINS.get(domain_code)
    if domain is None:
        return {}
    out: dict[str, str] = {}
    for model in domain.models:
        if not model.student_path:
            continue
        profile = getattr(student, model.label.split(".")[-1].replace("Profile", "").lower(), None)
        if profile is None:
            continue
        for spec in model.fields:
            if spec.internal_label:
                continue
            raw = getattr(profile, spec.name, None)
            if raw not in (None, "", 0):
                out[spec.title] = value_title(model.label, spec.name, raw)
    return out


def _students_of(domain_code: str, ids: list[int] | None = None):
    rows = Student.objects.filter(is_active=True).select_related(
        "group", "behavior", "admission", "exam", "talent", "sport"
    )
    if ids:
        rows = rows.filter(pk__in=ids)
    return list(rows[:60])


# --- «Объясни этот список» ------------------------------------------------


def explain_list(*, student_ids: list[int], actor, role: str) -> Outcome:
    """Что общего у этих учеников, с чего начать, кто в приоритете."""
    students = _students_of("", student_ids)
    if not students:
        return Outcome(text="В списке никого нет — снимите фильтры или отметьте учеников", offline=True)

    domain = domain_of_role(role)
    code = domain.code if domain else "exam"
    roster = Roster(students)

    facts = []
    for student in students:
        pairs = _domain_facts(student, code)
        readiness = _readiness_of(student)
        facts.append(
            f"{roster.label(student)}: {', '.join(f'{k} — {v}' for k, v in pairs.items()) or 'данных нет'}"
            f"; готовность {readiness}%"
        )

    offline = _offline_list_summary(students, code, roster)
    text = _ask(
        purpose="explain_list",
        actor=actor,
        role=role,
        system=RULES,
        user=(
            f"Домен: {domain.title if domain else 'общий'}. Учеников: {len(students)}.\n"
            + "\n".join(facts)
            + "\n\nСкажи в трёх-четырёх фразах: что у них общего, с чего начать и кто в приоритете."
        ),
        fallback=offline,
    )
    return Outcome(text=roster.restore(text.text), offline=text.offline)


def _readiness_of(student: Student) -> int:
    from core.readiness import compute

    return int(compute(student).score)


def _offline_list_summary(students, code: str, roster: Roster) -> str:
    """Тот же ответ правилами: числа и имена, без литературы."""
    scored = sorted(students, key=lambda s: _readiness_of(s))
    lowest = scored[:3]
    average = round(sum(_readiness_of(s) for s in students) / len(students))
    lines = [
        f"В списке {people(len(students))}, средняя готовность — {average}%.",
        "Ниже всех: " + listing([f"{s.full_name} ({_readiness_of(s)}%)" for s in lowest]) + ".",
        "С них и стоит начать: у остальных запас больше.",
    ]
    return " ".join(lines)


# --- «Что изменилось за неделю» -------------------------------------------


def week_changes(*, actor, role: str, days: int = 7) -> Outcome:
    """Сводка по домену с выводами, а не перечислением правок."""
    from core.models import AuditLog

    domain = domain_of_role(role)
    if domain is None:
        return Outcome(text="У вашей роли нет своего домена — сводку собирать не из чего", offline=True)

    since = timezone.now() - timedelta(days=days)
    entries = AuditLog.objects.filter(domain_code=domain.code, created_at__gte=since)
    grouped = (
        entries.values("model_label", "field_name")
        .annotate(n=Count("id"), people=Count("student_id", distinct=True))
        .order_by("-n")[:10]
    )
    facts = [
        f"{field_title(row['model_label'], row['field_name'])}: правок {row['n']} у {row['people']} учеников"
        for row in grouped
    ]

    if not facts:
        return Outcome(
            text=f"За {counted(days, ('день', 'дня', 'дней'))} в домене «{domain.title}» ничего не менялось",
            offline=True,
        )

    offline = (
        f"За {counted(days, ('день', 'дня', 'дней'))} в домене «{domain.title}» правок: {entries.count()}. "
        + listing(facts)
        + "."
    )
    answer = _ask(
        purpose="week_changes",
        actor=actor,
        role=role,
        system=RULES,
        user=(
            f"Домен: {domain.title}. Период: {days} дней.\n" + "\n".join(facts) + "\n\n"
            "Скажи в трёх фразах, что из этого важно и на что обратить внимание. Без перечисления цифр подряд."
        ),
        fallback=offline,
    )
    return Outcome(text=answer.text, offline=answer.offline)


# --- «На кого смотреть сегодня» -------------------------------------------


def focus_today(*, actor, role: str, limit: int = 5) -> Outcome:
    """Короткий список с обоснованием по каждому."""
    domain = domain_of_role(role)
    code = domain.code if domain else "exam"
    students = _students_of(code)
    if not students:
        return Outcome(text="Учеников в базе нет — заводит их администратор", offline=True)

    ranked = sorted(students, key=_readiness_of)[:limit]
    roster = Roster(ranked)

    reasons = [_focus_reason(student) for student in ranked]
    offline_lines = [f"{student.full_name} — {reason}" for student, reason in zip(ranked, reasons, strict=True)]

    answer = _ask(
        purpose="focus_today",
        actor=actor,
        role=role,
        system=RULES,
        user=(
            f"Домен: {domain.title if domain else 'общий'}.\n"
            + "\n".join(
                f"{roster.label(student)}: готовность {_readiness_of(student)}%, {reason}"
                for student, reason in zip(ranked, reasons, strict=True)
            )
            + "\n\nПо каждому дай одну фразу: почему смотреть на него сегодня. Формат: «ученик N — причина»."
        ),
        fallback="\n".join(offline_lines),
    )
    lines = [roster.restore(line).strip() for line in answer.text.splitlines() if line.strip()]
    return Outcome(
        text=roster.restore(answer.text) if answer.text else "",
        lines=lines or offline_lines,
        offline=answer.offline,
    )


def _focus_reason(student: Student) -> str:
    """Почему на него смотреть — по настоящим данным, без ярлыков."""
    from core.readiness import compute

    result = compute(student)
    weakest = result.weakest.title if result.weakest else "готовность"
    overdue = student.tasks.filter(status__in=("todo", "in_progress"), due_date__lt=timezone.localdate()).count()
    parts = [f"слабее всего — {weakest.lower()}"]
    if overdue:
        parts.append(f"просрочено задач: {overdue}")
    return ", ".join(parts)


# --- Массовая постановка задач --------------------------------------------


def bulk_tasks(*, student_ids: list[int], wish: str, actor, role: str) -> Outcome:
    """Одна задача, сформулированная моделью, — всем выделенным ученикам.

    Пишется не в базу, а в предложение: применяет человек (инвариант №3).
    """
    from suggestions.engine import create_suggestion

    students = _students_of("", student_ids)
    if not students:
        return Outcome(text="Никто не выделен — отметьте учеников в таблице", offline=True)
    if not wish.strip():
        return Outcome(text="Опишите словами, что нужно сделать", offline=True)

    default_title = wish.strip()[:200]
    answer = _ask(
        purpose="bulk_tasks",
        actor=actor,
        role=role,
        system=RULES + "\nСформулируй одну задачу: короткое название и срок в днях.",
        user=f"Директор просит: {wish.strip()}\nУчеников: {len(students)}",
        fallback=default_title,
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Название задачи, до 120 символов"},
                "days": {"type": "integer", "description": "Через сколько дней срок"},
            },
            "required": ["title"],
        },
    )
    payload = answer.parsed or {}
    title = str(payload.get("title") or default_title)[:200]
    due = timezone.localdate() + timedelta(days=int(payload.get("days") or 14))

    key = uuid.uuid4().hex[:16]
    rows = []
    for student in students:
        row_key = f"{key}-{student.pk}"
        rows.append(
            {
                "student": student.pk,
                "model": "roadmap.Task",
                "field": "title",
                "value": title,
                "new_object_key": row_key,
                "confidence": 0.9,
                "source_quote": wish.strip()[:250],
            }
        )
        rows.append(
            {
                "student": student.pk,
                "model": "roadmap.Task",
                "field": "due_date",
                "value": due.isoformat(),
                "new_object_key": row_key,
                "confidence": 0.9,
            }
        )

    suggestion, rejected = create_suggestion(
        author=actor,
        role=role,
        domain_code=(domain_of_role(role).code if domain_of_role(role) else ""),
        source_type="manual",
        command="bulk_action",
        rows=rows,
        source_ref=wish.strip()[:250],
    )
    return Outcome(
        text=f"Задача «{title}» со сроком {due.strftime('%d.%m.%Y')} предложена для {people(len(students))}",
        offline=answer.offline,
        suggestion=suggestion.pk,
        rows=len(rows) - len(rejected),
        detail="Предложение готово — откройте предпросмотр и примените то, с чем согласны",
    )


# --- План подготовки к экзамену -------------------------------------------


def prep_plan(*, student_id: int, actor, role: str) -> Outcome:
    """От текущего балла к целевому: часы, темы по секциям, дата мока."""
    student = Student.objects.filter(pk=student_id).select_related("exam").first()
    if student is None:
        return Outcome(text="Ученик не найден", offline=True)

    facts = _exam_facts(student)
    weak = _weak_topics(student)
    offline = _offline_prep_plan(student, facts, weak)

    answer = _ask(
        purpose="prep_plan",
        actor=actor,
        role=role,
        system=RULES + "\nСоставь план подготовки: сколько часов в неделю, какие темы, когда следующий пробный.",
        user=(
            "Данные ученика (имя не передано намеренно):\n"
            + "\n".join(f"{k}: {v}" for k, v in facts.items())
            + ("\nСлабые темы по разборам моков: " + ", ".join(weak) if weak else "\nРазборов моков ещё не было")
        ),
        fallback=offline,
    )
    return Outcome(text=answer.text, offline=answer.offline)


def _weak_topics(student: Student) -> list[str]:
    """Слабые темы по последним прохождениям моков — считает движок подготовки."""
    from prep.models import MockRun
    from prep.services import weak_topics as weak_of

    topics: list[str] = []
    for run in MockRun.objects.filter(student=student).select_related("session").order_by("-id")[:3]:
        for row in weak_of(run.session):
            if row["topic"] not in topics:
                topics.append(row["topic"])
    return topics[:8]


def _offline_prep_plan(student: Student, facts: dict, weak: list[str]) -> str:
    profile = getattr(student, "exam", None)
    lines = ["План собран правилами: модель не подключена."]
    if profile and profile.ielts_current and profile.ielts_target:
        gap = float(profile.ielts_target) - float(profile.ielts_current)
        weeks = max(4, int(gap / 0.5) * 6)
        lines.append(
            f"До цели по IELTS осталось {gap:.1f} балла. При {profile.hours_per_week or 6} часах в неделю "
            f"на это уходит около {counted(weeks, ('недели', 'недель', 'недель'))}."
        )
    if weak:
        lines.append("Слабые темы по последним разборам: " + listing(weak) + ".")
    else:
        lines.append("Разборов моков ещё не было — начните с пробного экзамена, он покажет слабые темы.")
    if profile and profile.next_mock_date:
        lines.append(f"Следующий пробный назначен на {profile.next_mock_date.strftime('%d.%m.%Y')}.")
    else:
        suggested = timezone.localdate() + timedelta(days=21)
        lines.append(f"Следующий пробный стоит назначить примерно на {suggested.strftime('%d.%m.%Y')}.")
    return " ".join(lines)


# --- Пробелы портфолио в задачи -------------------------------------------


def gap_to_tasks(*, student_id: int, actor, role: str) -> Outcome:
    """Пробелы портфолио превращаются в задачи роадмапа со сроками."""
    from suggestions.engine import create_suggestion

    student = Student.objects.filter(pk=student_id).select_related("talent").first()
    if student is None:
        return Outcome(text="Ученик не найден", offline=True)

    gaps = _portfolio_gaps(student)
    if not gaps:
        return Outcome(
            text=f"У {student.full_name} портфолио закрывает все направления — новых задач не нужно", offline=True
        )

    key = uuid.uuid4().hex[:16]
    rows = []
    for i, gap in enumerate(gaps, start=1):
        row_key = f"{key}-{i}"
        due = timezone.localdate() + timedelta(days=30 * i)
        rows.append(
            {
                "student": student.pk,
                "model": "roadmap.Task",
                "field": "title",
                "value": gap,
                "new_object_key": row_key,
                "confidence": 0.85,
            }
        )
        rows.append(
            {
                "student": student.pk,
                "model": "roadmap.Task",
                "field": "due_date",
                "value": due.isoformat(),
                "new_object_key": row_key,
                "confidence": 0.85,
            }
        )

    suggestion, _rejected = create_suggestion(
        author=actor,
        role=role,
        domain_code=(domain_of_role(role).code if domain_of_role(role) else ""),
        source_type="manual",
        command="gap_to_tasks",
        rows=rows,
        source_ref=f"пробелы портфолио: {student.full_name}",
    )
    return Outcome(
        text=f"Пробелов найдено: {len(gaps)}. " + listing(gaps),
        lines=gaps,
        offline=True,
        suggestion=suggestion.pk,
        rows=len(rows),
        detail="Задачи предложены — примените те, что считаете нужными",
    )


#: Что считаем направлением портфолио. Категории те же, что у активностей.
PORTFOLIO_TRACKS = {
    "olympiad": "Выступить на олимпиаде",
    "research": "Сделать исследовательскую работу",
    "leadership": "Взять лидерскую роль в проекте",
    "volunteering": "Набрать часы волонтёрства",
}


def _portfolio_gaps(student: Student) -> list[str]:
    have = set(student.activities.values_list("category", flat=True))
    return [title for code, title in PORTFOLIO_TRACKS.items() if code not in have]


# --- Черновик письма родителю ---------------------------------------------


def parent_letter(*, student_id: int, actor, role: str) -> Outcome:
    """Письмо с фактами из системы, без оценочных суждений."""
    student = Student.objects.filter(pk=student_id).select_related("exam", "behavior", "admission").first()
    if student is None:
        return Outcome(text="Ученик не найден", offline=True)

    domain = domain_of_role(role)
    facts = _domain_facts(student, domain.code if domain else "exam")
    readiness = _readiness_of(student)
    offline = _offline_letter(student, facts, readiness)

    answer = _ask(
        purpose="parent_letter",
        actor=actor,
        role=role,
        system=(
            RULES + "\nНапиши черновик письма родителю. Только факты из переданных данных. "
            "Без оценок ребёнка как человека, без слов «ленивый», «способный», «слабый». "
            "Имя ученика не подставляй — его подставит система, пиши «ученик 1»."
        ),
        user=(
            "Факты:\n"
            + "\n".join(f"{k}: {v}" for k, v in facts.items())
            + f"\nготовность: {readiness}%\n\nНапиши письмо на 5–7 строк."
        ),
        fallback=offline,
    )
    text = answer.text.replace("ученик 1", student.full_name).replace("Ученик 1", student.full_name)
    return Outcome(text=text, offline=answer.offline)


def _offline_letter(student: Student, facts: dict, readiness: int) -> str:
    rows = "\n".join(f"— {k}: {v}" for k, v in facts.items()) or "— данных пока немного"
    return (
        f"Здравствуйте!\n\n"
        f"Коротко о том, как идут дела у {student.full_name}.\n{rows}\n"
        f"Общая готовность к поступлению — {readiness}%. "
        f"Это доля выполненного по нашим критериям, а не вероятность поступления.\n\n"
        f"Если удобно, давайте созвонимся и обсудим следующие шаги.\n"
    )


# --- Проверка баланса списка вузов ----------------------------------------


def check_balance(*, student_id: int, actor, role: str) -> Outcome:
    """Перекос в reach, отсутствие safety, конфликтующие дедлайны."""
    from universities.models import StudentUniversity

    student = Student.objects.filter(pk=student_id).first()
    if student is None:
        return Outcome(text="Ученик не найден", offline=True)

    rows = list(
        StudentUniversity.objects.filter(student=student).select_related(
            "program", "program__university", "admission_round"
        )
    )
    if not rows:
        return Outcome(text=f"У {student.full_name} в списке пока нет ни одной программы", offline=True)

    counts = {"reach": 0, "target": 0, "safety": 0}
    for row in rows:
        counts[row.tier] = counts.get(row.tier, 0) + 1

    problems = _balance_problems(counts, rows)
    facts = (
        f"Программ в списке: {len(rows)} (reach {counts['reach']}, target {counts['target']}, "
        f"safety {counts['safety']}).\n"
        + "\n".join(
            f"- {row.program.university.name} — {row.program.name}, категория {row.tier}, "
            f"дедлайн {row.deadline or 'не заведён'}"
            for row in rows[:30]
        )
    )
    offline = (
        listing(problems) + "." if problems else "Список сбалансирован: есть и запасные варианты, и дедлайны разведены."
    )

    answer = _ask(
        purpose="check_balance",
        actor=actor,
        role=role,
        system=RULES + "\nПроверь баланс списка вузов: перекос, нехватка запасных вариантов, близкие дедлайны.",
        user=facts + "\n\nСкажи в трёх фразах, что поправить.",
        fallback=offline,
    )
    return Outcome(text=answer.text, lines=problems, offline=answer.offline)


def _balance_problems(counts: dict, rows: list) -> list[str]:
    """Перекос считаем правилами: числа не зависят от красноречия."""
    problems: list[str] = []
    total = sum(counts.values())
    if counts.get("safety", 0) == 0:
        problems.append("в списке нет ни одного запасного варианта (safety)")
    if total and counts.get("reach", 0) / total > 0.6:
        problems.append(f"перекос в сторону reach: {counts['reach']} из {total}")
    if counts.get("target", 0) == 0:
        problems.append("нет программ категории target — списку не на что опереться")

    dated = [row for row in rows if row.deadline]
    dated.sort(key=lambda r: r.deadline)
    for first, second in pairwise(dated):
        if (second.deadline - first.deadline).days <= 3:
            problems.append(
                f"дедлайны {first.program.university.name} и {second.program.university.name} "
                f"стоят вплотную ({first.deadline.strftime('%d.%m')} и {second.deadline.strftime('%d.%m')})"
            )
            break
    soon = [row for row in dated if 0 <= (row.deadline - timezone.localdate()).days <= 14]
    if soon:
        nearest = soon[0]
        problems.append(
            f"ближайший дедлайн — {nearest.program.university.name}, "
            f"{days_left((nearest.deadline - timezone.localdate()).days)}"
        )
    return problems


# --- Общая обвязка --------------------------------------------------------


@dataclass
class Answer:
    text: str
    parsed: Any = None
    offline: bool = True


def _ask(
    *,
    purpose: str,
    actor,
    role: str,
    system: str,
    user: str,
    fallback: str,
    schema: dict | None = None,
    max_tokens: int = 900,
) -> Answer:
    """Спросить модель, а если её нет — вернуть ответ, собранный правилами."""
    try:
        response = complete(
            system=system,
            user=user,
            purpose=purpose,
            actor=actor,
            role=role,
            schema=schema,
            max_tokens=max_tokens,
        )
    except LLMUnavailable:
        return Answer(text=fallback, offline=True)

    text = (response.content or "").strip()
    if not text and not response.parsed:
        return Answer(text=fallback, offline=True)
    return Answer(text=text or fallback, parsed=response.parsed, offline=False)


#: Что умеет каждая операция — для реестра команд и экрана помощника.
OPERATIONS = {
    "explain_list": explain_list,
    "week_changes": week_changes,
    "focus_today": focus_today,
    "bulk_tasks": bulk_tasks,
    "prep_plan": prep_plan,
    "gap_to_tasks": gap_to_tasks,
    "parent_letter": parent_letter,
    "check_balance": check_balance,
}


def role_title(role: str) -> str:
    return ROLE_TITLES.get(role, role)
