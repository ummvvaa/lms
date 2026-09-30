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
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.domains import ROLE_TITLES, domain_of_role
from core.i18n import language_of
from core.labels import field_title, value_title
from core.phrasing import days_left, listing, people, tn
from students.models import Student
from suggestions.llm import LLMUnavailable, complete
from suggestions.models import SuggestionSource

RULES = (  # i18n-skip: промпт модели
    """Ты помощник директора частной школы, готовящей учеников к поступлению.

Правила, нарушать нельзя:
- опирайся ТОЛЬКО на переданные факты, ничего не добавляй от себя;
- не называй вузов, программ и требований, которых нет в переданных данных;
- не обещай вероятность поступления: слов «шанс», «прогноз», «вероятность» быть не должно.
  Процент — это соответствие требованиям справочника, и называть его надо так;
- не используй внутренние ярлыки вроде «слабый», «критический», A/B/C;
- пиши по-русски, коротко и по делу, без канцелярита и без общих слов;
- учеников называй по номерам, которые переданы: имена подставит система.
"""
)  # fmt: skip


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
            # без подписи — ответ правил, до модели дело не дошло: спрашивать
            # было не о чем. «Модель не ответила» здесь была бы неправдой
            "detail": self.detail or (str(NOT_ASKED) if self.offline else ""),
        }


#: операция ответила сама, модель не звали: данных для вопроса нет
NOT_ASKED = gettext_lazy("Модель не спрашивали: данных для вопроса нет")


def offline_reason(error: Exception | str | None = None) -> str:
    """Почему ответ собран правилами.

    «Модель не подключена» при живом ключе отправляет администратора
    проверять ключ, с которым всё в порядке, а «не ответила» без причины
    не говорит, что чинить. Поэтому причина — со слов провайдера.
    """
    from suggestions.llm import is_configured

    if not is_configured():
        return _("Собрано правилами: модель не подключена")
    why = str(error or "").strip()
    if not why:
        return _("Собрано правилами: модель не ответила")
    # причина из `llm.empty_reason` уже называет модель — второй раз не повторяем
    if why.startswith(_("модель вернула пустой ответ")) or why == _("модель отказалась отвечать"):
        return _("Собрано правилами: {reason}").format(reason=why)
    return _("Собрано правилами: модель не ответила — {reason}").format(reason=why)


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
        return f"ученик {self.number_of[student.pk]}"  # i18n-skip: номер ученика для промпта модели

    def restore(self, text: str) -> str:
        """Вернуть имена на место: «ученик 3» → «Ахметова Алия».

        Окончание учитываем: модель пишет «ученика 3» и «ученику 3»,
        и без этого половина номеров оставалась номерами.
        """
        import re

        def swap(match: re.Match) -> str:
            student = self.by_number.get(int(match.group(1)))
            return student.full_name if student else match.group(0)

        return re.sub(r"[Уу]ченик[а-яё]{0,3}\s+(\d+)", swap, text)  # i18n-skip: регулярное выражение


# --- Факты для операций ---------------------------------------------------


def _exam_facts(student: Student) -> dict:
    profile = getattr(student, "exam", None)
    if profile is None:
        return {}
    return {  # i18n-skip: факты для промпта модели
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


def pool_of(actor, role: str, ids=None) -> list[int]:
    """Ученики, о которых операция вправе говорить.

    Граница одна с экранами — `core.scope.visible_ids`: руководитель видит
    всю школу, куратор свои группы, учитель свои составы. Сверху — домен
    роли: у Асем и экзаменов Кымбат только 11, как в таблице домена
    (`core.parallels.students_of_domain`). Выбор с экрана сужает, но
    за границу не выводит.
    """
    from core.parallels import students_of_domain
    from core.scope import visible_ids

    pool = visible_ids(actor, ids)
    domain = domain_of_role(role)
    if domain is not None and pool:
        keep = set(students_of_domain(Student.objects.filter(pk__in=pool), domain.code).values_list("id", flat=True))
        pool = [pk for pk in pool if pk in keep]
    return pool


def _students_of(ids: list[int] | None, *, actor, role: str):
    rows = Student.objects.filter(pk__in=pool_of(actor, role, ids)).select_related(
        "group", "behavior", "admission", "exam", "talent", "sport"
    )
    return list(rows.order_by("last_name", "first_name", "id")[:60])


def _one_of(student_id, *, actor, role: str, related: tuple[str, ...] = ()) -> Student | None:
    """Один ученик — только если он в границе человека; иначе «не найден»."""
    if not pool_of(actor, role, [student_id]):
        return None
    return Student.objects.filter(pk=student_id).select_related(*related).first()


# --- «Объясни этот список» ------------------------------------------------


def explain_list(*, student_ids: list[int], actor, role: str) -> Outcome:
    """Что общего у этих учеников, с чего начать, кто в приоритете."""
    students = _students_of(student_ids, actor=actor, role=role)
    if not students:
        return Outcome(text=_("В списке никого нет — снимите фильтры или отметьте учеников"), offline=True)

    domain = domain_of_role(role)
    code = domain.code if domain else "exam"
    roster = Roster(students)

    facts = []
    for student in students:
        pairs = _domain_facts(student, code)
        readiness = _readiness_of(student)
        facts.append(  # i18n-skip: факты для промпта модели
            f"{roster.label(student)}: {', '.join(f'{k} — {v}' for k, v in pairs.items()) or 'данных нет'}"
            f"; готовность {readiness}%"
        )

    offline = _offline_list_summary(students, code, roster)
    text = _ask(  # i18n-skip: промпт модели
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
    return Outcome(text=roster.restore(text.text), offline=text.offline, detail=text.detail)


def _readiness_of(student: Student) -> int:
    from core.readiness import compute

    return int(compute(student).score)


def _offline_list_summary(students, code: str, roster: Roster) -> str:
    """Тот же ответ правилами: числа и имена, без литературы."""
    scored = sorted(students, key=lambda s: _readiness_of(s))
    lowest = scored[:3]
    average = round(sum(_readiness_of(s) for s in students) / len(students))
    lines = [
        _("В списке {people}, средняя готовность — {average}%.").format(people=people(len(students)), average=average),
        _("Ниже всех: {students}.").format(students=listing([f"{s.full_name} ({_readiness_of(s)}%)" for s in lowest])),
        _("С них и стоит начать: у остальных запас больше."),
    ]
    return " ".join(lines)


# --- «Что изменилось за неделю» -------------------------------------------


def week_changes(*, actor, role: str, days: int = 7, student_ids: list[int] | None = None) -> Outcome:
    """Сводка по домену с выводами, а не перечислением правок.

    `student_ids` сужает сводку до этих учеников — так её зовёт проверка
    модели на вымышленном ученике, не трогая журнал живых.
    """
    from core.models import AuditLog

    domain = domain_of_role(role)
    if domain is None:
        return Outcome(text=_("У вашей роли нет своего домена — сводку собирать не из чего"), offline=True)

    since = timezone.now() - timedelta(days=days)
    entries = AuditLog.objects.filter(domain_code=domain.code, created_at__gte=since)
    if student_ids is not None:
        entries = entries.filter(student_id__in=student_ids)
    grouped = (
        entries.values("model_label", "field_name")
        .annotate(n=Count("id"), people=Count("student_id", distinct=True))
        .order_by("-n")[:10]
    )
    facts = [
        tn(
            row["people"],
            "{field}: правок {count} у {n} ученика|{field}: правок {count} у {n} учеников|"
            "{field}: правок {count} у {n} учеников",
            field=field_title(row["model_label"], row["field_name"]),
            count=row["n"],
        )
        for row in grouped
    ]

    if not facts:
        return Outcome(
            text=tn(
                days,
                "За {n} день в домене «{domain}» ничего не менялось|"
                "За {n} дня в домене «{domain}» ничего не менялось|"
                "За {n} дней в домене «{domain}» ничего не менялось",
                domain=domain.title,
            ),
            offline=True,
        )

    offline = tn(
        days,
        "За {n} день в домене «{domain}» правок: {count}. {changes}.|"
        "За {n} дня в домене «{domain}» правок: {count}. {changes}.|"
        "За {n} дней в домене «{domain}» правок: {count}. {changes}.",
        domain=domain.title,
        count=entries.count(),
        changes=listing(facts),
    )
    answer = _ask(  # i18n-skip: промпт модели
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
    return Outcome(text=answer.text, offline=answer.offline, detail=answer.detail)


# --- «На кого смотреть сегодня» -------------------------------------------


def focus_today(*, actor, role: str, limit: int = 5, student_ids: list[int] | None = None) -> Outcome:
    """Короткий список с обоснованием по каждому. `student_ids` — у куратора его группы."""
    domain = domain_of_role(role)
    students = _students_of(student_ids, actor=actor, role=role)
    if not students:
        return Outcome(text=_("Учеников в базе нет — заводит их администратор"), offline=True)

    ranked = sorted(students, key=_readiness_of)[:limit]
    roster = Roster(ranked)

    reasons = [_focus_reason(student) for student in ranked]
    offline_lines = [f"{student.full_name} — {reason}" for student, reason in zip(ranked, reasons, strict=True)]

    answer = _ask(  # i18n-skip: промпт модели
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
        detail=answer.detail,
    )


def _focus_reason(student: Student) -> str:
    """Почему на него смотреть — по настоящим данным, без ярлыков."""
    from core.readiness import compute

    result = compute(student)
    weakest = str(result.weakest.title) if result.weakest else _("готовность")
    overdue = student.tasks.filter(status__in=("todo", "in_progress"), due_date__lt=timezone.localdate()).count()
    parts = [_("слабее всего — {part}").format(part=weakest.lower())]
    if overdue:
        parts.append(_("просрочено задач: {count}").format(count=overdue))
    return ", ".join(parts)


# --- Массовая постановка задач --------------------------------------------


def bulk_tasks(*, student_ids: list[int], wish: str, actor, role: str) -> Outcome:
    """Одна задача, сформулированная моделью, — всем выделенным ученикам.

    Пишется не в базу, а в предложение: применяет человек (инвариант №3).
    """
    from suggestions.engine import create_suggestion

    students = _students_of(student_ids, actor=actor, role=role)
    if not students:
        return Outcome(text=_("Никто не выделен — отметьте учеников в таблице"), offline=True)
    if not wish.strip():
        return Outcome(text=_("Опишите словами, что нужно сделать"), offline=True)

    default_title = wish.strip()[:200]
    answer = _ask(  # i18n-skip: промпт и схема ответа модели
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
        source_type=SuggestionSource.ASSISTANT,
        command="bulk_action",
        rows=rows,
        source_ref=wish.strip()[:250],
    )
    return Outcome(
        text=_("Задача «{title}» со сроком {date} предложена для {people}").format(
            title=title, date=due.strftime("%d.%m.%Y"), people=people(len(students))
        ),
        offline=answer.offline,
        suggestion=suggestion.pk,
        rows=len(rows) - len(rejected),
        detail=". ".join(
            part
            for part in (answer.detail, _("Предложение готово — откройте предпросмотр и примените то, с чем согласны"))
            if part
        ),
    )


# --- План подготовки к экзамену -------------------------------------------


def prep_plan(*, student_id: int, actor, role: str) -> Outcome:
    """От текущего балла к целевому: часы, темы по секциям, дата мока."""
    student = _one_of(student_id, actor=actor, role=role, related=("exam",))
    if student is None:
        return Outcome(text=_("Ученик не найден"), offline=True)

    facts = _exam_facts(student)
    weak = _weak_topics(student)
    offline = _offline_prep_plan(student, facts, weak)

    answer = _ask(  # i18n-skip: промпт модели
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
    return Outcome(text=answer.text, offline=answer.offline, detail=answer.detail)


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
    lines = [_("План собран правилами: модель не подключена.")]
    if profile and profile.ielts_current and profile.ielts_target:
        gap = float(profile.ielts_target) - float(profile.ielts_current)
        weeks = max(4, int(gap / 0.5) * 6)
        lines.append(
            tn(
                weeks,
                "До цели по IELTS осталось {gap} балла. При {hours} часах в неделю на это уходит около {n} недели.|"
                "До цели по IELTS осталось {gap} балла. При {hours} часах в неделю на это уходит около {n} недель.|"
                "До цели по IELTS осталось {gap} балла. При {hours} часах в неделю на это уходит около {n} недель.",
                gap=f"{gap:.1f}",
                hours=profile.hours_per_week or 6,
            )
        )
    if weak:
        lines.append(_("Слабые темы по последним разборам: {topics}.").format(topics=listing(weak)))
    else:
        lines.append(_("Разборов онлайн Mock Test ещё не было — начните с него: он покажет слабые темы."))
    if profile and profile.next_mock_date:
        lines.append(
            _("Следующий Mock Test назначен на {date}.").format(date=profile.next_mock_date.strftime("%d.%m.%Y"))
        )
    else:
        suggested = timezone.localdate() + timedelta(days=21)
        lines.append(
            _("Следующий Mock Test стоит назначить примерно на {date}.").format(date=suggested.strftime("%d.%m.%Y"))
        )
    return " ".join(lines)


# --- Пробелы портфолио в задачи -------------------------------------------


def gap_to_tasks(*, student_id: int, actor, role: str) -> Outcome:
    """Пробелы портфолио превращаются в задачи роадмапа со сроками."""
    from suggestions.engine import create_suggestion

    student = _one_of(student_id, actor=actor, role=role, related=("talent",))
    if student is None:
        return Outcome(text=_("Ученик не найден"), offline=True)

    gaps = _portfolio_gaps(student)
    if not gaps:
        return Outcome(
            text=_("У {student} портфолио закрывает все направления — новых задач не нужно").format(
                student=student.full_name
            ),
            offline=True,
        )
    # задачи читает ученик — названия на его языке, а ответ директору — на языке директора
    with translation.override(language_of(getattr(student, "user", None))):
        task_titles = _portfolio_gaps(student)

    key = uuid.uuid4().hex[:16]
    rows = []
    for i, gap in enumerate(task_titles, start=1):
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
        source_type=SuggestionSource.ASSISTANT,
        command="gap_to_tasks",
        rows=rows,
        source_ref=f"пробелы портфолио: {student.full_name}",  # i18n-skip: источник сохраняется в базе
    )
    return Outcome(
        text=_("Пробелов найдено: {count}. {gaps}").format(count=len(gaps), gaps=listing(gaps)),
        lines=gaps,
        offline=True,
        suggestion=suggestion.pk,
        rows=len(rows),
        detail=_("Задачи предложены — примените те, что считаете нужными"),
    )


#: Что считаем направлением портфолио. Категории те же, что у активностей.
PORTFOLIO_TRACKS = {
    "olympiad": gettext_lazy("Выступить на олимпиаде"),
    "research": gettext_lazy("Сделать исследовательскую работу"),
    "leadership": gettext_lazy("Взять лидерскую роль в проекте"),
    "volunteering": gettext_lazy("Набрать часы волонтёрства"),
}


def _portfolio_gaps(student: Student) -> list[str]:
    have = set(student.activities.values_list("category", flat=True))
    return [str(title) for code, title in PORTFOLIO_TRACKS.items() if code not in have]


# --- Проверка баланса списка вузов ----------------------------------------


def check_balance(*, student_id: int, actor, role: str) -> Outcome:
    """Перекос в reach, отсутствие safety, конфликтующие дедлайны."""
    from universities.models import StudentUniversity

    student = _one_of(student_id, actor=actor, role=role)
    if student is None:
        return Outcome(text=_("Ученик не найден"), offline=True)

    rows = list(
        StudentUniversity.objects.filter(student=student).select_related(
            "program", "program__university", "admission_round"
        )
    )
    if not rows:
        return Outcome(
            text=_("У {student} в списке пока нет ни одной программы").format(student=student.full_name), offline=True
        )

    counts = {"reach": 0, "target": 0, "safety": 0}
    for row in rows:
        counts[row.tier] = counts.get(row.tier, 0) + 1

    problems = _balance_problems(counts, rows)
    facts = (  # i18n-skip: факты для промпта модели
        f"Программ в списке: {len(rows)} (reach {counts['reach']}, target {counts['target']}, "
        f"safety {counts['safety']}).\n"
        + "\n".join(
            f"- {row.program.university.name} — {row.program.name}, категория {row.tier}, "
            f"дедлайн {row.deadline or 'не заведён'}"
            for row in rows[:30]
        )
    )
    offline = (
        listing(problems) + "."
        if problems
        else _("Список сбалансирован: есть и запасные варианты, и дедлайны разведены.")
    )

    answer = _ask(  # i18n-skip: промпт модели
        purpose="check_balance",
        actor=actor,
        role=role,
        system=RULES + "\nПроверь баланс списка вузов: перекос, нехватка запасных вариантов, близкие дедлайны.",
        user=facts + "\n\nСкажи в трёх фразах, что поправить.",
        fallback=offline,
    )
    return Outcome(text=answer.text, lines=problems, offline=answer.offline, detail=answer.detail)


def _balance_problems(counts: dict, rows: list) -> list[str]:
    """Перекос считаем правилами: числа не зависят от красноречия."""
    problems: list[str] = []
    total = sum(counts.values())
    if counts.get("safety", 0) == 0:
        problems.append(_("в списке нет ни одного запасного варианта (safety)"))
    if total and counts.get("reach", 0) / total > 0.6:
        problems.append(_("перекос в сторону reach: {count} из {total}").format(count=counts["reach"], total=total))
    if counts.get("target", 0) == 0:
        problems.append(_("нет программ категории target — списку не на что опереться"))

    dated = [row for row in rows if row.deadline]
    dated.sort(key=lambda r: r.deadline)
    for first, second in pairwise(dated):
        if (second.deadline - first.deadline).days <= 3:
            problems.append(
                _("дедлайны {first} и {second} стоят вплотную ({first_date} и {second_date})").format(
                    first=first.program.university.name,
                    second=second.program.university.name,
                    first_date=first.deadline.strftime("%d.%m"),
                    second_date=second.deadline.strftime("%d.%m"),
                )
            )
            break
    soon = [row for row in dated if 0 <= (row.deadline - timezone.localdate()).days <= 14]
    if soon:
        nearest = soon[0]
        problems.append(
            _("ближайший дедлайн — {university}, {when}").format(
                university=nearest.program.university.name,
                when=days_left((nearest.deadline - timezone.localdate()).days),
            )
        )
    return problems


# --- Общая обвязка --------------------------------------------------------


@dataclass
class Answer:
    text: str
    parsed: Any = None
    offline: bool = True
    #: почему ответ собран правилами — для подписи под ответом
    detail: str = ""


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
    except LLMUnavailable as error:
        return Answer(text=fallback, offline=True, detail=offline_reason(error))

    text = (response.content or "").strip()
    if not text and not response.parsed:
        return Answer(text=fallback, offline=True, detail=offline_reason(_("модель вернула пустой ответ")))
    return Answer(text=text or fallback, parsed=response.parsed, offline=False)


#: Что умеет каждая операция — для реестра команд и экрана помощника.
OPERATIONS = {
    "explain_list": explain_list,
    "week_changes": week_changes,
    "focus_today": focus_today,
    "bulk_tasks": bulk_tasks,
    "prep_plan": prep_plan,
    "gap_to_tasks": gap_to_tasks,
    "check_balance": check_balance,
}


def role_title(role: str) -> str:
    return ROLE_TITLES.get(role, role)
