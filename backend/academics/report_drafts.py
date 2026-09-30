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
import re
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

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
from core.i18n import language_of, render, translate
from students.models import GroupLanguage

log = logging.getLogger(__name__)

NAME = "{name}"

#: язык текста в запросе модели — язык отчёта, а не того, кто собирал
LANGUAGE_WORDS = {GroupLanguage.KK: "казахском", GroupLanguage.RU: "русском"}  # i18n-skip: промпт ИИ

# скобки держат пометку стража на первой строке оператора
# fmt: off
SYSTEM = (  # i18n-skip: промпт ИИ, язык ответа задаётся в самом запросе
    """Ты помогаешь куратору школы написать отчёт родителям об ученике.
Пиши так, как написал бы живой учитель или куратор в письме родителям.

Откуда брать:
- главный источник — комментарии учителей к оценкам за период. Перескажи их
  своими словами, близко к смыслу учителя. Ничего не добавляй от себя: ни
  качеств, ни событий, ни планов, которых нет в комментариях и данных;
- дальше — оценки, Mock Test, посещаемость и уровень английского.

Какое поле о чём:
- отзыв учителя по предмету (eep, sat_verbal, sat_math, subjects) — только то,
  что сказал учитель. Совет в отзыве — только если его дал сам учитель; своих
  советов («… көңіл бөлу керек», «стоит поработать над …») сюда не добавляй;
- рекомендации — только в «Итогах и рекомендациях» (summary) и в
  «Характеристике» (character), и только выведенные из данных: слабый раздел
  Mock Test, ошибки, которые назвал учитель, пропуски и опоздания;
- поля не повторяют друг друга: итоги дают общий вывод и что делать дальше,
  не пересказывая отзывы и Mock Test слово в слово.

Объём:
- каждое поле — 3–6 предложений связным текстом, без списков и эмодзи;
- мало комментариев — поле короче, но без воды и общих слов;
- для поля совсем нет данных — верни пустую строку.

Слова:
- пробный экзамен называй как в шаблонах школы: «IELTS Mock Test»,
  «SAT Mock Test» (kk: «IELTS Mock Test нәтижесінде …», ru: «в IELTS Mock
  Test …»).
  Слов «пробник», «пробный», «сынақ» не пиши;
- разделы IELTS в обоих языках — по-английски, как в таблице отчёта:
  Listening, Reading, Writing, Speaking. Не «тыңдалым», «оқылым», «жазылым»,
  «айтылым», не «аудирование», «чтение», «письмо», «говорение»;
- живой язык учителя, без канцелярита и шаблонов. Не пиши: «следует отметить»,
  «стоит отметить», «в целом можно сказать», «демонстрирует стабильную
  динамику», «на протяжении периода», «является», «в рамках»; по-казахски —
  «атап өткен жөн», «жалпы алғанда», «тұрақты динамика көрсетеді», «барысында»;
- без служебных слов и внутренней кухни школы: не называй виды оценивания
  (ФО, СОР, СОЧ, формативное, суммативное; қалыптастырушы, жиынтық бағалау,
  БЖБ, ТЖБ), не пиши «/10», «из 10», «показатель», «көрсеткіші», не объясняй,
  как считали посещаемость (никаких «по минутам», «минутпен», процентов);
- не повторяй цифры, которые уже стоят в таблицах отчёта (оценки по
  предметам, дни, баллы Mock Test): текст объясняет, а не дублирует;
- не называй даты периода — они в шапке отчёта;
- о том, чего нет, не пиши вообще: нет комментариев по предмету — предмет
  не упоминай; нет Mock Test — поле пустое. Никаких «нет данных»,
  «комментарий не предоставлен», «оценок пока нет», «дерек жоқ»,
  «пікір берілмеген», «тіркелмеген»;
- без внутренних ярлыков, без сравнения с одноклассниками и средних по группе;
  балл Mock Test — не шанс поступления и не прогноз.

Время глаголов:
- то, что было за период (пропуски, опоздания, результат Mock Test), —
  прошедшим временем. По-казахски: «сабақ жібермеген», «бір рет кешіккен»,
  «Listening бөлімін жақсы орындаған»; не «кешігу болған», не «кешігеді»;
- по-русски пола ученика ты не знаешь, поэтому прошедшее время — только в
  формах без рода: «пропусков не было», «было одно опоздание», «в IELTS
  Mock Test сильнее всего вышел Listening». Не «опоздал», не «получила», не
  «опаздывает», не «не пропускал занятия и не опаздывал» — а «пропусков и
  опозданий не было»; не «{name} лучше всего справляется с Listening» и не
  «у {name} сильнее всего вышел Listening» — а «в IELTS Mock Test лучше всего
  вышел Listening»;
- разделы Mock Test называй прямо (Listening, Reading, Writing, Speaking), без
  описательных замен вроде «задания на восприятие языка»;
- то, что учитель говорит о работе сейчас, — настоящим: «{name} пока пишет
  эссе без плана».

Имя:
- ученика называй «{name}» — так, как в образцах школы: по имени, один-два
  раза на поле, а не в каждой фразе. Ученик — подлежащее: не «эссе пока
  пишутся без плана», а «{name} пока пишет эссе без плана»; не «Speaking
  стал увереннее», а «{name} увереннее говорит в Speaking»;
- только в именительном падеже, без окончаний и суффиксов после «{name}».
  Если фразе нужен другой падеж («эссе Мираса», «Мирастың эсселері»),
  перестрой её так, чтобы {name} был подлежащим: не «эссе {name} стали
  длиннее», а «{name} пишет эссе длиннее»; не «{name} эсселері ұзарды», а
  «{name} эссені ұзағырақ жазады». В каждом непустом поле назови {name} хотя бы
  раз — лучше подлежащим в первой фразе.

Так НЕ писать (kk):
«01.09.2026–30.09.2026 кезеңінде сабаққа қатысу көрсеткіші 100% болды: бір оқу
күнінде сабақтан қалу да, кешігу де тіркелмеді. Creative Writing пәні бойынша
қалыптастырушы бағалау нәтижесі — 2/10. Тапсырмаларға қатысты мұғалім пікірі
берілмеген.»
Так писать (kk), характеристика, если учитель написал «Эссе без плана,
аргументы слабые, но идеи интересные»:
«{name} сабақ жібермеген, кешікпеген. Creative Writing мұғалімінің айтуынша,
{name} қызықты идеялар ұсынады, бірақ эссені әзірге жоспарсыз жазады, ал
дәлелдері әлсіз. Келесі жұмыстарда эссені қысқа жоспардан бастаған пайдалы.»
Так писать (kk), комментарий к Mock Test:
«IELTS Mock Test нәтижесінде {name} Listening бөлімін ең жақсы орындаған,
Reading те жақсы шыққан. Writing бөлімі әзірге әлсіздеу.»

Так НЕ писать (ru):
«За период с 01.09.2026 по 30.09.2026 показатель посещаемости по минутам
составил 100%. По предмету Creative Writing результат формативного
оценивания — 2/10. Комментарии учителя по заданиям не предоставлены. В целом
можно сказать, что ученик демонстрирует стабильную динамику. На пробнике
лучше всего получилось аудирование.»
Так писать (ru), характеристика, при том же комментарии учителя:
«Пропусков и опозданий за этот период не было. Учитель Creative Writing
отмечает, что {name} предлагает интересные идеи, но пока пишет эссе без плана
и приводит слабые аргументы. В следующих работах полезно начинать эссе
с короткого плана.»
Так писать (ru), отзыв учителя, если учитель написал только «Эссе стали
длиннее, но много ошибок в артиклях»:
«{name} пишет эссе длиннее, чем раньше, но делает много ошибок в артиклях.»
(без «учитель советует» и без советов от себя)
Так писать (ru), комментарий к Mock Test:
«В IELTS Mock Test сильнее всего вышли Listening и Reading. Слабее — Writing,
на него {name} стоит обратить внимание.»

Если комментариев учителей нет совсем, а посещаемость есть — одна фраза
о посещаемости, и всё; предметы не перечисляй."""
)
# fmt: on

#: фразы, которых в тексте для родителей быть не должно: служебные слова,
#: объяснение подсчёта и рассказ о пустых данных. Предложение с такой
#: фразой убирается целиком — модель просили так не писать, а родитель не
#: должен прочесть «пікір берілмеген» (30.09.2026)
FORBIDDEN = (  # i18n-skip: регулярные выражения для фильтра текста ИИ
    # рассказ о том, чего нет
    r"\bнет (ни )?(данных|комментари\w*|оценок|пробник\w*|информаци\w*|сведений)",
    r"\bданн\w*(\s+\S+){0,2}\s+нет\b",
    r"(комментари\w*|пробник\w*|оцен\w*)\s+(пока\s+)?нет\b",
    r"(дерек|мәлімет|пікір|сынақ)\w*\s+жоқ",
    r"не предоставлен",
    r"не указан",
    r"не выставлен",
    r"не поступал",
    r"комментари\w* отсутству",
    r"информаци\w* нет",
    r"берілмеген",
    r"көрсетілмеген",
    r"тіркелмеген",
    r"тіркелмеді",
    r"қорытынды жасау\w* дерек",
    # служебные слова и кухня подсчёта
    r"по минутам",
    r"минутпен",
    r"показател",
    r"көрсеткіш",
    r"формативн",
    r"суммативн",
    r"қалыптастырушы",
    r"жиынтық бағалау",
    r"\b(ФО|СОР|СОЧ|БЖБ|ТЖБ)\b",
    # шаблоны
    r"следует отметить",
    r"стоит отметить",
    r"в целом можно сказать",
    r"демонстрирует",
    r"атап өткен жөн",
    r"жалпы алғанда",
)
_FORBIDDEN = re.compile("|".join(FORBIDDEN), re.IGNORECASE)
_SENTENCES = re.compile(r"(?<=[.!?…])\s+")


def clean(text: str) -> str:
    """Текст для родителей без служебных фраз: «2/10» → «2», запретное предложение — прочь.

    «у {name}», «для {name}» — косвенный падеж, а имя подставляется
    в именительном: «у Мирас». Предлог уходит вместе с именем — «В IELTS
    Mock Test сильнее всего вышел Listening» остаётся грамотным.
    """
    text = re.sub(r"\s(?:у|для|к|от)\s\{name\}", "", text or "", flags=re.IGNORECASE)  # i18n-skip: регулярное выражение
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*/\s*10\b", r"\1", text)
    text = re.sub(r"\s+из\s+10\b", "", text)  # i18n-skip: регулярное выражение
    kept = [part for part in _SENTENCES.split(text.strip()) if part and not _FORBIDDEN.search(part)]
    return " ".join(kept).strip()


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

    def said(self, role: str) -> list[CourseFacts]:
        """Журналы раздела, где учителя написали комментарии."""
        return [row for row in self.courses if row.role == role and row.comments]

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


def prompt(report: ParentReport, facts: Facts) -> str:  # i18n-skip: промпт ИИ, язык ответа задаётся в самом запросе
    """Запрос модели: данные без имени, фамилии, группы и дат периода.

    Посещаемость — днями, без процента «по минутам»: процент тянул модель
    объяснять подсчёт родителям. Комментарии учителей — первым списком:
    это главный источник текста (30.09.2026).
    """
    language = LANGUAGE_WORDS.get(report.language, "русском")
    out = [f"Напиши тексты отчёта на {language} языке.", ""]
    days_total = int(facts.attendance.get("days_total") or 0)
    if days_total:
        out.append(
            "Посещаемость (для одной живой фразы, числа в текст не переносить): "
            f"учебных дней {days_total}, пропущено дней {facts.attendance.get('days_missed') or 0}, "
            f"опозданий {facts.attendance.get('late') or 0}."
        )
    if facts.level:
        out.append(f"Уровень английского: {facts.level}.")
    for exam, scores in (("IELTS", facts.ielts), ("SAT", facts.sat)):
        if scores:
            parts = ", ".join(f"{k.capitalize()} {v}" for k, v in scores.items() if v)
            out.append(f"Последний {exam} Mock Test (баллы в таблице отчёта): {parts}.")
    commented = [row for row in facts.courses if row.comments]
    out.append("")
    if commented:
        out.append("Комментарии учителей к оценкам (главный источник; номер журнала, предмет, раздел отчёта):")
        for row in commented:
            role = dict(ReportRole.choices).get(row.role, "") if row.role else "обычный предмет"
            said = " | ".join(f"«{text}»" for text in row.comments)
            grades = ", ".join(str(v) for v in row.grades)
            tail = f"; оценки из 10 (в текст не переносить): {grades}" if grades else ""
            out.append(f"- №{row.course.pk}: {row.title}; раздел: {role}; комментарии: {said}{tail}")
    else:
        out.append("Комментариев учителей за период нет — предметы в тексте не называй.")
    quiet = [row for row in facts.courses if row.grades and not row.comments]
    if quiet:
        out.append(
            "Оценки без комментариев (только для общего впечатления — эти предметы не называй, числа не переноси): "
            + "; ".join(f"{row.title}: {', '.join(str(v) for v in row.grades)}" for row in quiet)
            + "."
        )
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
            f"- subjects: по отзыву для журналов {numbers} — пересказ комментариев учителя этого журнала "
            "без своих советов, 3–6 предложений, если комментариев хватает; журнал без комментариев не включай"
        )
    else:
        out.append("- subjects: пустой список")
    return "\n".join(out)


FIELD_WORDS = {  # i18n-skip: промпт ИИ, язык ответа задаётся в самом запросе
    "eep": "отзыв по английскому (GE/EEP) — пересказ комментариев учителя журналов раздела «GE / EEP»; "
    "уровень английского можно назвать словами; без своих советов",
    "sat_verbal": "отзыв по SAT Verbal — пересказ комментариев учителя журналов раздела «SAT Verbal», "
    "без своих советов",
    "sat_math": "отзыв по SAT Math — пересказ комментариев учителя журналов раздела «SAT Math», без своих советов",
    "mock_comment": "комментарий к последнему Mock Test: какие разделы сильнее, какие подтянуть — словами, без баллов",
    "character": "характеристика: посещаемость одной фразой, затем что говорят учителя об учёбе "
    "и отношении к заданиям — близко к их словам",
    "summary": "итоги и рекомендации: что получается и над чем работать — по комментариям учителей "
    "и Mock Test; советы — только выведенные из данных",
}


def wanted(report: ParentReport, facts: Facts) -> set[str]:
    """Какие поля можно заполнять: у каждого поля должны быть свои данные.

    Отзыв по разделу (GE/EEP, SAT) пишется только из комментариев учителя:
    одни оценки — не отзыв, а цифры из таблицы (30.09.2026).
    """
    out = set()
    if facts.said(ReportRole.EEP):
        out.add("eep")
    if facts.said(ReportRole.SAT_VERBAL):
        out.add("sat_verbal")
    if facts.said(ReportRole.SAT_MATH):
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
        raise DraftRefused(_("У стандартного отчёта черновика нет"))
    # пометка черновика пишется в очереди, где языка запроса нет: на языке того,
    # кто попросил черновик; сборка по расписанию — на русском
    language = language_of(actor)
    facts = collect(report)
    if facts.empty:
        note = translate(language, "За период нет ни оценок, ни отметок, ни Mock Test — писать не из чего")
        _state(report, DraftState.SKIPPED, note)
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
        reason = (str(error) or translate(language, "ИИ недоступен"))[:200]
        _state(report, DraftState.FAILED, render(language, "{reason} — тексты пишет куратор", reason=reason))
        return report
    parsed = answer.parsed if isinstance(answer.parsed, dict) else {}
    first = report.student.first_name.strip()

    def text(name: str) -> str:
        if name not in wants:
            return ""
        return clean(str(parsed.get(name) or "")).replace(NAME, first).strip()

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
                courses = facts.said(kind)
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
        if overwrite:
            # ИИ переписал всё — правок человека в текстах больше нет
            report.texts_edited_at = None
        report.save(
            update_fields=[
                "mock_comment",
                "character",
                "summary",
                "draft_state",
                "draft_note",
                "drafted_at",
                "texts_edited_at",
            ]
        )
    from academics.reports import event_text
    from core.audit import record_event

    record_event(student=report.student, code="report_drafted", text=event_text(report), actor=actor, source="ai")
    return report


def _subject_reviews(report: ParentReport, parsed: dict, facts: Facts, *, overwrite: bool) -> None:
    """Блоки «учитель — предмет»: только журналы из запроса и только с комментариями."""
    known = {row.course.pk: row for row in facts.commented}
    have = {row.course_id: row for row in report.reviews.filter(kind=ReviewKind.SUBJECT)}
    order = 10 + len(have)
    first = report.student.first_name.strip()
    written: set[int] = set()
    for item in parsed.get("subjects") or []:
        if not isinstance(item, dict):
            continue
        course_id = item.get("course")
        text = clean(str(item.get("text") or "")).replace(NAME, first).strip()
        if not isinstance(course_id, int) or course_id not in known or not text:
            continue
        written.add(course_id)
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
    if overwrite:
        # «переписать»: отзыв ИИ по журналу, где комментариев больше нет, уходит
        for course_id, row in have.items():
            if course_id not in written and row.by_ai:
                row.delete()


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
