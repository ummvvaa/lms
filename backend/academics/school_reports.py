"""Отчёты родителям по шаблонам школы: снимок данных, тексты, сообщение родителям.

Два шаблона школы (решение владельца, 30.09.2026):

- вариант 1 — «Отзыв об успеваемости» (`ReportTemplate.REVIEW`): посещаемость
  днями, отзывы GE/EEP (с уровнем английского), SAT Verbal и SAT Math,
  средняя ФО по предметам табеля, спортивное направление, общий отзыв;
- вариант 2 — «Отчёт о прогрессе» (`ReportTemplate.PROGRESS`): посещаемость,
  список ФО по предметам табеля, последний пробник IELTS и/или SAT за период
  с комментарием, отзывы учителей, итоги и рекомендации.

Данные — только из LMS: нет данных — строки нет, а куратор видит пометку.
Снимок хранится строками `ReportLine` с кодом строки, как у стандартного
отчёта: родитель получает ровно то, что проверил куратор. Тексты пишет
ИИ черновиком (`academics.report_drafts`), правит куратор.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from academics.calendar import today
from academics.models import (
    Course,
    EnglishLevel,
    Grade,
    LessonKind,
    ParentReport,
    ReportLine,
    ReportRole,
    ReportSection,
    ReportTemplate,
    Scheme,
)
from students.models import GroupLanguage, Student

#: коды строк снимка
DAYS_TOTAL = "days_total"
DAYS_PRESENT = "days_present"
DAYS_MISSED = "days_missed"
LATE = "late"
PCT = "pct"
GRADE = "grade"
ENGLISH_LEVEL = "english_level"
SPORT = "sport"
IELTS_PARTS = ("listening", "reading", "writing", "speaking", "overall")
SAT_PARTS = ("verbal", "math", "overall")

#: пропущенный день — день, где на всех отмеченных уроках «не был»;
#: уважительная тоже «не был», она лишь не снижает процент по правилу школы
MISSED_MARKS = frozenset({"absent", "excused"})


def is_school_template(template: str) -> bool:
    return template in (ReportTemplate.REVIEW, ReportTemplate.PROGRESS)


def default_language(student: Student) -> str:
    """Язык отчёта по умолчанию — язык группы ученика."""
    if student.group_id and student.group.language in GroupLanguage.values:
        return student.group.language
    return GroupLanguage.RU


def subject_title(subject, language: str) -> str:
    """Название предмета на языке отчёта; казахского нет — русское."""
    if language == GroupLanguage.KK and subject.title_kk.strip():
        return subject.title_kk.strip()
    return subject.title


def number(value: float) -> str:
    """8 → «8», 8.25 → «8,3»: как в отчётах школы, без лишних нулей."""
    text = f"{round(value, 1):.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _score(value) -> str:
    if value is None:
        return ""
    text = f"{float(value):.1f}".rstrip("0").rstrip(".")
    return text


# --- Данные ------------------------------------------------------------------


@dataclass(frozen=True)
class Days:
    """Посещаемость днями для шаблонов школы."""

    total: int
    present: int
    missed: int
    late: int
    pct: int | None


def attendance_days(student_id: int, start: dt.date, end: dt.date) -> Days:
    """Учебные дни, посещённые, пропущенные, опоздания и процент по минутам.

    Учебный день — день, где у ученика отмечен хотя бы один урок. Пропущен —
    если на всех отмеченных уроках дня он «не был». Опоздания — штуками.
    Процент — по минутам урока, та же `Presence`, что везде.
    """
    from academics.results import student_attendance

    totals = student_attendance(student_id, start, min(end, today()))
    missed = sum(1 for marks in totals.marked.values() if marks and all(mark in MISSED_MARKS for mark in marks))
    days = len(totals.marked)
    return Days(total=days, present=days - missed, missed=missed, late=totals.late, pct=totals.pct)


@dataclass
class SubjectGrades:
    """ФО по предмету табеля за период — у одного предмета бывает два журнала."""

    subject: object
    values: list[int]

    @property
    def average(self) -> float | None:
        return sum(self.values) / len(self.values) if self.values else None


def fo_grades(student_id: int, start: dt.date, end: dt.date) -> list[SubjectGrades]:
    """ФО за период по предметам табеля («ФО, СОР, СОЧ») в порядке предметов.

    Предметы «Только ФО» (SAT, классный час, профориентация) не идут, СОР
    и СОЧ — тоже: они в баллах из максимума. Предмет без оценок остаётся
    строкой с пустой клеткой.
    """
    from academics.results import student_courses

    courses = [c for c in student_courses(student_id, min(end, today())) if c.subject.scheme == Scheme.KZ]
    by_subject: dict[int, SubjectGrades] = {}
    for course in courses:
        by_subject.setdefault(course.subject_id, SubjectGrades(subject=course.subject, values=[]))
    rows = (
        Grade.objects.filter(
            student_id=student_id,
            lesson__course__in=courses,
            lesson__date__gte=start,
            lesson__date__lte=end,
            lesson__kind=LessonKind.FO,
        )
        .exclude(lesson__status="cancelled")
        .select_related("lesson", "lesson__course")
        .order_by("lesson__date", "lesson__slot", "id")
    )
    for grade in rows:
        by_subject[grade.lesson.course.subject_id].values.append(grade.value)
    return list(by_subject.values())


def latest_mock(student_id: int, exam_type: str, start: dt.date, end: dt.date):
    """Последний пробник экзамена за период или None."""
    from students.models import AttemptFormat, ExamAttempt

    return (
        ExamAttempt.objects.filter(
            student_id=student_id,
            exam_type=exam_type,
            attempt_format=AttemptFormat.MOCK,
            date__gte=start,
            date__lte=end,
        )
        .order_by("-date", "-id")
        .first()
    )


def english_level_on(student_id: int, day: dt.date) -> str:
    """Уровень английского на дату; не внесён — пусто."""
    row = EnglishLevel.objects.filter(student_id=student_id, since__lte=day).order_by("-since", "-id").first()
    return row.level if row else ""


def sport_of(student: Student) -> str:
    """Вид спорта из спортивного раздела (домен Нурлыбека); не внесён — пусто."""
    from students.models import SportProfile

    profile = SportProfile.objects.filter(student=student).select_related("sport_type").first()
    if profile is None or profile.sport_type_id is None:
        return ""
    return profile.sport_type.name


def build_lines(student: Student, *, template: str, language: str, start: dt.date, end: dt.date) -> list[dict]:
    """Строки снимка отчёта по шаблону школы."""
    lines: list[dict] = []

    def add(section: str, code: str, title: str, value: str, note: str = "") -> None:
        lines.append(
            {
                "section": section,
                "code": code,
                "order": len(lines) + 1,
                "title": title[:120],
                "value": value[:120],
                "note": note[:300],
            }
        )

    days = attendance_days(student.pk, start, end)
    add(ReportSection.ATTENDANCE, DAYS_TOTAL, "Учебных дней", str(days.total))
    add(ReportSection.ATTENDANCE, DAYS_PRESENT, "Посещено дней", str(days.present))
    add(ReportSection.ATTENDANCE, DAYS_MISSED, "Пропущено дней", str(days.missed))
    add(ReportSection.ATTENDANCE, LATE, "Опозданий", str(days.late))
    add(ReportSection.ATTENDANCE, PCT, "Общая посещаемость", f"{days.pct}%" if days.pct is not None else "")

    for row in fo_grades(student.pk, start, end):
        if template == ReportTemplate.REVIEW:
            value = number(row.average) if row.average is not None else ""
        else:
            value = ", ".join(str(v) for v in row.values)
        add(ReportSection.GRADES, GRADE, subject_title(row.subject, language), value)

    if template == ReportTemplate.REVIEW:
        add(ReportSection.PROFILE, ENGLISH_LEVEL, "Уровень английского", english_level_on(student.pk, end))
        add(ReportSection.PROFILE, SPORT, "Спортивное направление", sport_of(student))
    else:
        ielts = latest_mock(student.pk, "IELTS", start, end)
        if ielts is not None:
            scores = [ielts.listening, ielts.reading, ielts.writing, ielts.speaking, ielts.total_score]
            for part, value in zip(IELTS_PARTS, scores, strict=True):
                add(ReportSection.IELTS, part, part.capitalize(), _score(value), f"{ielts.date:%d.%m.%Y}")
        sat = latest_mock(student.pk, "SAT", start, end)
        if sat is not None:
            scores = [sat.verbal, sat.math, sat.total_score]
            for part, value in zip(SAT_PARTS, scores, strict=True):
                add(ReportSection.SAT, part, part.capitalize(), _score(value), f"{sat.date:%d.%m.%Y}")
    return lines


def gaps(report: ParentReport) -> list[str]:
    """Чего нет в данных — пометки куратору на экране отчёта, не в файле."""
    out = []
    lines = list(report.lines.all())
    by_code = {line.code: line for line in lines}
    if not by_code.get(DAYS_TOTAL) or by_code[DAYS_TOTAL].value == "0":
        out.append("За период нет ни одного отмеченного урока — посещаемость по нулям")
    empty = [line.title for line in lines if line.code == GRADE and not line.value]
    if empty:
        out.append("Нет оценок ФО за период: " + ", ".join(empty))
    if report.template == ReportTemplate.REVIEW:
        if not by_code.get(ENGLISH_LEVEL) or not by_code[ENGLISH_LEVEL].value:
            out.append("Уровень английского не внесён — его вносят учитель GE/EEP, Кымбат или куратор")
        if not by_code.get(SPORT) or not by_code[SPORT].value:
            out.append("Спортивное направление не внесено — раздел «Спорт» в карточке ученика")
    elif not any(line.section in (ReportSection.IELTS, ReportSection.SAT) for line in lines):
        out.append("Пробников IELTS и SAT за период нет — блок пробника в отчёт не попадёт")
    return out


# --- Отзывы учителей -----------------------------------------------------------

#: три постоянных блока отзывов — по порядку шаблона школы
FIXED_REVIEWS = (ReportRole.SAT_VERBAL, ReportRole.SAT_MATH, ReportRole.EEP)


def teachers_of(student: Student, role: str, on: dt.date) -> list[Course]:
    """Журналы ученика с этим разделом отчёта."""
    from academics.results import student_courses

    return [course for course in student_courses(student.pk, on) if course.report_role == role]


def ensure_reviews(report: ParentReport) -> None:
    """Три постоянных блока отзывов у отчёта есть всегда (пустые — не печатаются)."""
    from academics.models import ReportReview

    have = set(report.reviews.values_list("kind", flat=True))
    for order, role in enumerate(FIXED_REVIEWS, start=1):
        if role not in have:
            ReportReview.objects.create(report=report, kind=role, order=order)


def address_name(full_name: str) -> str:
    """«Алтынбекова Айгерім Алтынбековна» → «Айгерім Алтынбековна»: как подписывается куратор."""
    words = full_name.split()
    if len(words) >= 3:
        return " ".join(words[1:3])
    return full_name.strip()


# --- Сообщение родителям ----------------------------------------------------------

#: текст сообщения родителям — слова владельца (30.09.2026), русский — перевод.
#: Лежит файлами рядом с шаблонами: в нём эмодзи школы, а в исходниках
#: сервера эмодзи нет (страж `test_no_emoji_in_backend_sources`)
MESSAGES = Path(__file__).resolve().parent / "report_templates"


def message_text(report: ParentReport) -> str:
    language = report.language if report.language in GroupLanguage.values else GroupLanguage.RU
    return (MESSAGES / f"message_{language}.txt").read_text(encoding="utf-8").strip()


def lines_of(report: ParentReport, section: str) -> list[ReportLine]:
    return [line for line in report.lines.all() if line.section == section]
