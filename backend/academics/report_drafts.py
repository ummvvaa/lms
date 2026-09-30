"""Черновик текстов отчёта родителям по шаблону школы — пишет ИИ, правит куратор.

Модель получает только данные ученика из LMS за период: ФО по предметам,
комментарии учителей к оценкам, пробники, уровень английского, посещаемость.
Имени и фамилии ученика в запросе нет: модель пишет «{name}», имя
подставляется здесь. Пустые данные — модель не вызывается вовсе.
Модель недоступна или бюджет исчерпан — поля остаются пустыми, куратор
пишет сам (решение владельца, 30.09.2026).

Текст отчёта пишется прямо в отчёт, а не предложением (решение владельца,
30.09.2026, исключение из инварианта №3): без проверки куратором отчёт
не скачивается. Модель отвечает только номерами журналов из запроса:
чужой номер отбрасывается, блок «учитель — предмет» строится по данным LMS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from academics.models import (
    Course,
    DraftState,
    Grade,
    ParentReport,
    ReportReview,
    ReportRole,
    ReportSection,
    ReportTemplate,
    ReviewKind,
)
from academics.school_reports import subject_title
from students.models import GroupLanguage

log = logging.getLogger(__name__)

NAME = "{name}"

LANGUAGE_WORDS = {GroupLanguage.KK: "казахском", GroupLanguage.RU: "русском"}

SYSTEM = """Ты помогаешь куратору школы написать отчёт родителям об ученике.

Правила:
- пиши ТОЛЬКО из переданных данных: оценок, комментариев учителей, пробников,
  посещаемости и уровня английского. Ничего не придумывай: ни качеств, ни
  событий, ни планов, которых нет в данных;
- нет данных для поля — верни для него пустую строку;
- ученика называй только «{name}» и только в именительном падеже, без
  окончаний и суффиксов после «{name}»; пола ученика ты не знаешь — избегай
  слов, у которых есть род (в русском — прошедшего времени вроде «получил»);
- без внутренних ярлыков, без сравнения с одноклассниками и средних по группе;
- балл пробника — не шанс поступления и не прогноз;
- тон тёплый и уважительный, как у учителя в письме родителям;
- каждое поле — два-четыре предложения, без списков и эмодзи."""

#: поля ответа модели и когда их вообще можно заполнять
FIELDS = ("eep", "sat_verbal", "sat_math", "mock_comment", "character", "summary")


def schema_for(template: str) -> dict:
    props = {name: {"type": "string"} for name in FIELDS}
    props["subjects"] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"course": {"type": "integer"}, "text": {"type": "string"}},
            "required": ["course", "text"],
            "additionalProperties": False,
        },
    }
    return {
        "type": "object",
        "properties": props,
        "required": [*FIELDS, "subjects"],
        "additionalProperties": False,
    }


@dataclass
class CourseFacts:
    course: Course
    title: str
    teacher: str
    role: str
    grades: list[int] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.grades and not self.comments


@dataclass
class Facts:
    """Всё, что модели можно знать об ученике за период."""

    courses: list[CourseFacts]
    attendance: dict
    ielts: dict
    sat: dict
    level: str

    def role(self, role: str) -> list[CourseFacts]:
        return [row for row in self.courses if row.role == role and not row.empty]

    @property
    def commented(self) -> list[CourseFacts]:
        """Журналы без раздела отчёта, где учителя что-то написали."""
        return [row for row in self.courses if row.role == ReportRole.NONE and row.comments]

    @property
    def empty(self) -> bool:
        has_courses = any(not row.empty for row in self.courses)
        days = int(self.attendance.get("days_total") or 0)
        return not has_courses and not days and not self.ielts and not self.sat and not self.level


def collect(report: ParentReport) -> Facts:
    """Данные ученика за период отчёта — из снимка и журналов."""
    from academics.payloads import user_name
    from academics.results import student_courses
    from academics.school_reports import DAYS_MISSED, DAYS_TOTAL, ENGLISH_LEVEL, LATE, PCT

    student = report.student
    start, end = report.period_start, report.period_end
    courses = student_courses(student.pk, min(end, timezone.localdate()))
    facts = {
        course.pk: CourseFacts(
            course=course,
            title=subject_title(course.subject, report.language),
            teacher=user_name(course.teacher) if course.teacher_id else "",
            role=course.report_role,
        )
        for course in courses
    }
    rows = (
        Grade.objects.filter(
            student=student, lesson__course_id__in=list(facts), lesson__date__gte=start, lesson__date__lte=end
        )
        .exclude(lesson__status="cancelled")
        .select_related("lesson")
        .order_by("lesson__date", "lesson__slot")
    )
    for grade in rows:
        item = facts[grade.lesson.course_id]
        if grade.lesson.kind == "fo":
            item.grades.append(grade.value)
        if grade.comment.strip():
            item.comments.append(grade.comment.strip())
    lines = {line.code: line for line in report.lines.all()}
    attendance = {
        "days_total": lines[DAYS_TOTAL].value if DAYS_TOTAL in lines else "0",
        "days_missed": lines[DAYS_MISSED].value if DAYS_MISSED in lines else "0",
        "late": lines[LATE].value if LATE in lines else "0",
        "pct": lines[PCT].value if PCT in lines else "",
    }
    ielts = {line.code: line.value for line in report.lines.all() if line.section == ReportSection.IELTS}
    sat = {line.code: line.value for line in report.lines.all() if line.section == ReportSection.SAT}
    level = lines[ENGLISH_LEVEL].value if ENGLISH_LEVEL in lines else ""
    if not level:
        from academics.school_reports import english_level_on

        level = english_level_on(student.pk, end)
    return Facts(courses=list(facts.values()), attendance=attendance, ielts=ielts, sat=sat, level=level)


def prompt(report: ParentReport, facts: Facts) -> str:
    """Запрос модели: данные без имени, фамилии и группы."""
    language = LANGUAGE_WORDS.get(report.language, "русском")
    out = [
        f"Напиши тексты отчёта на {language} языке. "
        f"Период: {report.period_start:%d.%m.%Y}–{report.period_end:%d.%m.%Y}.",
        "",
        "Посещаемость: учебных дней {days_total}, пропущено дней {days_missed}, опозданий {late}, "
        "посещаемость по минутам {pct}.".format(**{k: v or "нет" for k, v in facts.attendance.items()}),
    ]
    if facts.level:
        out.append(f"Уровень английского: {facts.level}.")
    if facts.ielts:
        out.append("Пробник IELTS: " + ", ".join(f"{k} {v}" for k, v in facts.ielts.items() if v) + ".")
    if facts.sat:
        out.append("Пробник SAT: " + ", ".join(f"{k} {v}" for k, v in facts.sat.items() if v) + ".")
    out.append("")
    out.append("Журналы (номер, предмет, раздел отчёта, оценки ФО по 10-балльной шкале, комментарии учителя):")
    for row in facts.courses:
        if row.empty:
            continue
        role = dict(ReportRole.choices).get(row.role, "") if row.role else "обычный предмет"
        grades = ", ".join(str(v) for v in row.grades) or "нет"
        comments = " | ".join(row.comments) or "нет"
        out.append(f"- №{row.course.pk}: {row.title}; раздел: {role}; оценки: {grades}; комментарии: {comments}")
    out.append("")
    out.append("Что заполнить:")
    wants = wanted(report, facts)
    for name, words in FIELD_WORDS.items():
        if name in wants:
            out.append(f"- {name}: {words}")
        else:
            out.append(f"- {name}: оставь пустой строкой")
    if report.template == ReportTemplate.PROGRESS and facts.commented:
        numbers = ", ".join(f"№{row.course.pk}" for row in facts.commented)
        out.append(
            f"- subjects: по отзыву для журналов {numbers} — только из комментариев учителя этого журнала; "
            "журнал без комментариев не включай"
        )
    else:
        out.append("- subjects: пустой список")
    return "\n".join(out)


FIELD_WORDS = {
    "eep": "отзыв по английскому (GE/EEP) — из журналов раздела «GE / EEP» и уровня английского",
    "sat_verbal": "отзыв по SAT Verbal — из журналов раздела «SAT Verbal»",
    "sat_math": "отзыв по SAT Math — из журналов раздела «SAT Math»",
    "mock_comment": "комментарий по результатам пробника: сильные секции и что подтянуть, только по баллам",
    "character": "общий отзыв об учёбе: посещаемость, оценки, отношение к заданиям по комментариям учителей",
    "summary": "итоги и рекомендации: что получается и над чем работать — по всем данным",
}


def wanted(report: ParentReport, facts: Facts) -> set[str]:
    """Какие поля можно заполнять: у каждого поля должны быть свои данные."""
    out = set()
    if facts.role(ReportRole.EEP) or (facts.level and any(r.role == ReportRole.EEP for r in facts.courses)):
        out.add("eep")
    if facts.role(ReportRole.SAT_VERBAL):
        out.add("sat_verbal")
    if facts.role(ReportRole.SAT_MATH):
        out.add("sat_math")
    if report.template == ReportTemplate.REVIEW:
        out.add("character")
    else:
        if facts.ielts or facts.sat:
            out.add("mock_comment")
        out.add("summary")
    return out


class DraftRefused(ValueError):
    """Черновик сейчас не пишется — текст объясняет почему."""


def draft(report: ParentReport, *, actor=None, overwrite: bool = False) -> ParentReport:
    """Написать черновик текстов. Возвращает отчёт с новым состоянием черновика.

    `overwrite` — «Написать заново»: тексты заменяются целиком. Иначе
    заполняются только пустые поля: правку куратора ИИ не трогает.
    """
    from suggestions.llm import LLMUnavailable, complete

    if report.template == ReportTemplate.STANDARD:
        raise DraftRefused("У стандартного отчёта черновика нет")
    facts = collect(report)
    if facts.empty:
        _state(report, DraftState.SKIPPED, "За период нет ни оценок, ни отметок, ни пробников — писать не из чего")
        return report
    wants = wanted(report, facts)
    try:
        answer = complete(
            system=SYSTEM,
            user=prompt(report, facts),
            purpose="parent_report",
            actor=actor,
            role=getattr(actor, "role", "") or "",
            schema=schema_for(report.template),
            max_tokens=2500,
        )
    except LLMUnavailable as error:
        _state(report, DraftState.FAILED, (str(error) or "ИИ недоступен")[:200] + " — тексты пишет куратор")
        return report
    parsed = answer.parsed if isinstance(answer.parsed, dict) else {}
    first = report.student.first_name.strip()

    def text(name: str) -> str:
        if name not in wants:
            return ""
        return str(parsed.get(name) or "").replace(NAME, first).strip()

    with transaction.atomic():
        report.refresh_from_db()
        for name in ("mock_comment", "character", "summary"):
            value = text(name)
            if overwrite or not getattr(report, name).strip():
                setattr(report, name, value)
        by_kind = {row.kind: row for row in report.reviews.all()}
        for name, kind in (
            ("eep", ReviewKind.EEP),
            ("sat_verbal", ReviewKind.SAT_VERBAL),
            ("sat_math", ReviewKind.SAT_MATH),
        ):
            row = by_kind.get(kind)
            if row is None:
                continue
            value = text(name)
            if overwrite or not row.text.strip():
                courses = facts.role(kind)
                row.text = value
                row.by_ai = bool(value)
                if courses:
                    row.course = courses[0].course
                    row.teacher_name = courses[0].teacher
                    row.subject_title = courses[0].title
                row.save()
        if report.template == ReportTemplate.PROGRESS:
            _subject_reviews(report, parsed, facts, overwrite=overwrite)
        report.draft_state = DraftState.DONE
        report.draft_note = ""
        report.drafted_at = timezone.now()
        report.save(update_fields=["mock_comment", "character", "summary", "draft_state", "draft_note", "drafted_at"])
    from core.audit import record_event

    record_event(student=report.student, code="report_drafted", text=f"за {report.title}", actor=actor, source="ai")
    return report


def _subject_reviews(report: ParentReport, parsed: dict, facts: Facts, *, overwrite: bool) -> None:
    """Блоки «учитель — предмет»: только журналы из запроса и только с комментариями."""
    known = {row.course.pk: row for row in facts.commented}
    have = {row.course_id: row for row in report.reviews.filter(kind=ReviewKind.SUBJECT)}
    order = 10 + len(have)
    first = report.student.first_name.strip()
    for item in parsed.get("subjects") or []:
        if not isinstance(item, dict):
            continue
        course_id = item.get("course")
        text = str(item.get("text") or "").replace(NAME, first).strip()
        if not isinstance(course_id, int) or course_id not in known or not text:
            continue
        row = have.get(course_id)
        facts_row = known[course_id]
        if row is None:
            order += 1
            ReportReview.objects.create(
                report=report,
                kind=ReviewKind.SUBJECT,
                order=order,
                course=facts_row.course,
                teacher_name=facts_row.teacher,
                subject_title=facts_row.title,
                text=text,
                by_ai=True,
            )
        elif overwrite or not row.text.strip():
            row.text = text
            row.by_ai = True
            row.save(update_fields=["text", "by_ai"])


def _state(report: ParentReport, state: str, note: str) -> None:
    report.draft_state = state
    report.draft_note = note[:250]
    report.save(update_fields=["draft_state", "draft_note"])


def request_draft(report: ParentReport, *, actor=None, overwrite: bool = False) -> None:
    """Поставить черновик в очередь: модель отвечает долго, сборка ждать не должна."""
    from academics.tasks import draft_report

    report.draft_state = DraftState.PENDING
    report.draft_note = ""
    report.save(update_fields=["draft_state", "draft_note"])
    actor_id = getattr(actor, "pk", None)
    transaction.on_commit(lambda: draft_report.delay(report.pk, actor_id, overwrite))
