"""Разборы профтеста ученика одним файлом Word — для профориентолога и родителей.

В файл идут все готовые разборы ученика: у каждого набора тестов — последний
готовый (`ready_analyses`). Текст — версия профориентолога, как она сейчас на
экране, с его правками; версия для ученика в Word не идёт. Порядок: шапка
с гербом школы, «Общая картина по всем тестам» (если разборов больше одного),
затем каждый разбор с новой страницы — тест и дата, общий вывод, профиль
интересов таблицей с выделенными сильными шкалами, направления.

Стек — тот же, что у отчётов родителям (`academics.report_files`): python-docx
под docxtpl, шрифт Times New Roman 12, лист A4. Документ собирается кодом, а не
из шаблона: число разборов, шкал и направлений у каждого ученика своё.
Подписи разделов — на языке выгрузки (`translation.override`), тексты разбора —
на языке разбора или в сохранённом переводе (`career.translation`).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from career.analysis import _key, profile
from career.models import AnalysisStatus, CareerAnalysis
from core.parallels import parallel_of

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CREST = Path(__file__).resolve().parent / "assets" / "crest.png"
#: шрифт и размер — как в отчётах родителям по шаблонам школы
FONT = "Times New Roman"
#: заголовки — тёплым тёмным акцентом школы, строки сильных шкал — светлым
ACCENT = "9A3412"
STRONG_FILL = "FCE7DC"
HEAD_FILL = "F3EEE9"
#: символы, на которых Windows не распакует архив или не сохранит файл
UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


@dataclass
class ScaleText:
    test: str
    title: str
    score: int
    top: int
    label: str
    meaning: str
    strong: bool


@dataclass
class DirectionText:
    title: str
    title_abroad: str
    reasoning: str
    professions: str
    exams: str
    subjects: str
    next_steps: str
    #: «Программа — вуз (страна) · уровень»: названия не переводятся
    programs: list[str] = field(default_factory=list)


@dataclass
class AnalysisText:
    """Что идёт в файл из одного разбора — оригинал или перевод, одинаково."""

    pk: int
    #: (название теста, дата прохождения)
    tests: list[tuple[str, str]]
    created: str
    summary: str
    scales: list[ScaleText]
    directions: list[DirectionText]


@dataclass
class OverviewText:
    """«Общая картина по всем тестам» — четыре части."""

    repeats: str
    agreements: str
    differences: str
    confirmed: str


def ready_analyses(student) -> list[CareerAnalysis]:
    """Готовые разборы ученика: по каждому набору тестов — последний, старые первыми.

    Разборы «Идёт», «Не получился» и «Отменён» в файл не идут.
    """
    rows = (
        CareerAnalysis.objects.filter(student=student, status=AnalysisStatus.DONE)
        .prefetch_related("attempts__test", "scales", "directions__programs__university")
        .order_by("-created_at", "-id")
    )
    seen: set[frozenset[int]] = set()
    out: list[CareerAnalysis] = []
    for row in rows:
        tests = frozenset(attempt.test_id for attempt in row.attempts.all())
        if tests in seen:
            continue
        seen.add(tests)
        out.append(row)
    out.sort(key=lambda row: (row.created_at, row.pk))
    return out


def _date(moment) -> str:
    return timezone.localtime(moment).strftime("%d.%m.%Y") if moment else ""


def _program(program) -> str:
    university = program.university
    place = f"{university.name} ({university.country})" if university.country else university.name
    level = program.get_level_display() if program.level else ""
    return f"{program.name} — {place}" + (f" · {level}" if level else "")


def text_of(analysis: CareerAnalysis) -> AnalysisText:
    """Разбор как на экране профориентолога: его текст, его правки.

    Сильная шкала — по диапазонам теста, как в самом разборе (`analysis.profile`).
    У разборов до профиля интересов строк профиля нет — таблица собирается
    из баллов попыток, без объяснений.
    """
    attempts = sorted(analysis.attempts.all(), key=lambda a: (a.finished_at or a.started_at, a.pk))
    strong: set[tuple[str, str]] = set()
    fallback: list[ScaleText] = []
    for attempt in attempts:
        for line in profile(attempt):
            if line.strong:
                strong.add((_key(attempt.test.title), _key(line.title)))
            fallback.append(
                ScaleText(attempt.test.title, line.title, line.score, line.top, line.label, "", line.strong)
            )
    scales = [
        ScaleText(
            row.test_title,
            row.title,
            row.score,
            row.top,
            row.label,
            row.meaning,
            (_key(row.test_title), _key(row.title)) in strong,
        )
        for row in analysis.scales.all()
    ]
    directions = [
        DirectionText(
            title=row.title,
            title_abroad=row.title_abroad,
            reasoning=row.reasoning,
            professions=row.professions,
            exams=row.exams,
            subjects=row.subjects,
            next_steps=row.next_steps,
            programs=[_program(program) for program in row.programs.all()],
        )
        for row in analysis.directions.all()
    ]
    return AnalysisText(
        pk=analysis.pk,
        tests=[(attempt.test.title, _date(attempt.finished_at)) for attempt in attempts],
        created=_date(analysis.finished_at or analysis.created_at),
        summary=analysis.summary,
        scales=scales or fallback,
        directions=directions,
    )


def file_name(student) -> str:  # i18n-skip: имя файла задано школой, одно на все языки
    """«Фамилия_Имя_профтест.docx» без символов, которые ломают архив на Windows."""
    return f"{safe(student.last_name)}_{safe(student.first_name)}_профтест.docx"


def safe(text: str) -> str:
    cleaned = UNSAFE.sub(" ", str(text or ""))
    return "_".join(cleaned.split()).strip("._") or "_"


# --- Документ ----------------------------------------------------------------------------


def _fonts(element, size=None) -> None:
    """Шрифт на все алфавиты: кириллица и казахские буквы — тем же Times New Roman."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    rpr = element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for name in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        fonts.attrib.pop(qn(name), None)
    for name in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(name), FONT)


def _styles(document) -> None:
    from docx.enum.section import WD_ORIENT
    from docx.shared import Cm, Pt, RGBColor

    section = document.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2)
    section.top_margin, section.bottom_margin = Cm(1.6), Cm(1.6)
    normal = document.styles["Normal"]
    normal.font.name, normal.font.size = FONT, Pt(12)
    _fonts(normal.element)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.15
    for name, size, before in (("Heading 1", 16, 0), ("Heading 2", 13, 12), ("Heading 3", 12, 10)):
        style = document.styles[name]
        style.font.name, style.font.size, style.font.bold = FONT, Pt(size), True
        style.font.italic = False
        style.font.color.rgb = RGBColor.from_string(ACCENT if name != "Heading 3" else "191A15")
        _fonts(style.element)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.keep_with_next = True
    for name in ("List Bullet", "Table Grid"):
        _fonts(document.styles[name].element)


def _shade(cell, fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shading)


def _widths(table, widths) -> None:
    """Ширины столбцов сеткой таблицы: LibreOffice ширину ячеек без сетки не читает."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    table.autofit = False
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    table._tbl.tblPr.append(layout)
    for column, width in zip(table.columns, widths, strict=True):
        column.width = width
    for row in table.rows:
        for cell, width in zip(row.cells, widths, strict=True):
            cell.width = width


def _keep_row(row) -> None:
    """Строка таблицы не рвётся между страницами."""
    from docx.oxml import OxmlElement

    row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def _repeat_header(row) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    mark = OxmlElement("w:tblHeader")
    mark.set(qn("w:val"), "true")
    row._tr.get_or_add_trPr().append(mark)


def _page_number(section) -> None:
    """Внизу страницы: имя ученика и номер страницы."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    number = OxmlElement("w:fldSimple")
    number.set(qn("w:instr"), "PAGE")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "1"
    run.append(text)
    number.append(run)
    paragraph._p.append(number)
    for item in paragraph.runs:
        item.font.size = Pt(9)


def _lines(text: str) -> list[str]:
    return [line.strip(" \t-•–") for line in str(text or "").replace("\r", "").split("\n") if line.strip(" \t-•–")]


def _paragraphs(document, text: str) -> None:
    for line in _lines(text):
        document.add_paragraph(line)


def _fact(document, label: str, text: str, *, bullets: bool = False) -> None:
    """Подпись жирным и текст под ней; списком — когда строк несколько."""
    lines = _lines(text)
    if not lines:
        return
    head = document.add_paragraph()
    head.paragraph_format.space_before = document.styles["Normal"].paragraph_format.space_after
    head.paragraph_format.space_after = 0
    head.paragraph_format.keep_with_next = True
    head.add_run(label).bold = True
    for line in lines:
        document.add_paragraph(line, style="List Bullet" if bullets and len(lines) > 1 else None)


def _head(document, student, *, actor, moment) -> None:
    from docx.shared import Cm, Pt, RGBColor

    from academics.payloads import user_name

    table = document.add_table(rows=1, cols=2)
    _widths(table, [Cm(3.6), Cm(13.4)])
    left, right = table.rows[0].cells
    if CREST.is_file():
        left.paragraphs[0].add_run().add_picture(str(CREST), width=Cm(3))
    school = right.paragraphs[0]
    run = school.add_run(settings.SCHOOL_NAME)
    run.font.size, run.font.color.rgb = Pt(11), RGBColor.from_string("6B6458")
    title = right.add_paragraph()
    run = title.add_run(_("Разбор результатов профтеста"))
    run.bold, run.font.size, run.font.color.rgb = True, Pt(18), RGBColor.from_string(ACCENT)
    name = right.add_paragraph()
    run = name.add_run(student.full_name)
    run.bold, run.font.size = True, Pt(14)
    group = student.group.code if student.group_id else ""
    rows = [
        [
            _("Группа: {group}").format(group=group) if group else "",
            _("Параллель: {n} класс").format(n=parallel_of(student)),
        ],
        [
            _("Дата выгрузки: {date}").format(date=_date(moment)),
            _("Выгрузил: {name}").format(name=user_name(actor)) if actor else "",
        ],
    ]
    for parts in rows:
        line = right.add_paragraph(" · ".join(part for part in parts if part))
        line.paragraph_format.space_after = 0
        for item in line.runs:
            item.font.size = Pt(11)
    document.add_paragraph()


def _overview(document, overview: OverviewText) -> None:
    document.add_heading(_("Общая картина по всем тестам"), level=1)
    for label, text in (
        (_("Что повторяется в разных тестах"), overview.repeats),
        (_("Где тесты согласуются"), overview.agreements),
        (_("Где тесты расходятся"), overview.differences),
        (_("Какие направления подтверждаются несколькими тестами"), overview.confirmed),
    ):
        if _lines(text):
            document.add_heading(label, level=2)
            _paragraphs(document, text)


def _score(scale: ScaleText) -> str:
    return _("{score} из {top}").format(score=scale.score, top=scale.top) if scale.top else str(scale.score)


def _profile(document, scales: list[ScaleText]) -> None:
    from docx.shared import Cm, Pt

    document.add_heading(_("Профиль интересов"), level=2)
    tests = list(dict.fromkeys(scale.test for scale in scales))
    explained = any(scale.meaning for scale in scales)
    widths = [Cm(4.2), Cm(1.9), Cm(3.4), Cm(7.5)] if explained else [Cm(7), Cm(3), Cm(7)]
    heads = [_("Шкала"), _("Балл"), _("Диапазон"), _("Что значит")][: len(widths)]
    for test in tests:
        if len(tests) > 1:
            caption = document.add_paragraph()
            caption.paragraph_format.keep_with_next = True
            caption.add_run(test).italic = True
        table = document.add_table(rows=1, cols=len(widths))
        table.style = document.styles["Table Grid"]
        _repeat_header(table.rows[0])
        for cell, text in zip(table.rows[0].cells, heads, strict=True):
            _shade(cell, HEAD_FILL)
            run = cell.paragraphs[0].add_run(text)
            run.bold, run.font.size = True, Pt(10.5)
        for scale in (row for row in scales if row.test == test):
            row = table.add_row()
            _keep_row(row)
            values = [scale.title, _score(scale), scale.label, scale.meaning][: len(widths)]
            for index, (cell, text) in enumerate(zip(row.cells, values, strict=True)):
                run = cell.paragraphs[0].add_run(text)
                run.font.size = Pt(10.5)
                if scale.strong:
                    _shade(cell, STRONG_FILL)
                    run.bold = index < 2
        _widths(table, widths)
    note = document.add_paragraph()
    note.paragraph_format.space_before = Pt(4)
    run = note.add_run(_("Цветом выделены сильные шкалы — верхний диапазон теста: на них строятся направления."))
    run.italic, run.font.size = True, Pt(10)


def _direction(document, number: int, direction: DirectionText) -> None:
    from docx.shared import Pt, RGBColor

    document.add_heading(f"{number}. {direction.title}", level=3)
    if direction.title_abroad:
        line = document.add_paragraph()
        run = line.add_run(_("Как называется за рубежом: {title}").format(title=direction.title_abroad))
        run.italic, run.font.color.rgb = True, RGBColor.from_string("6B6458")
    _fact(document, _("Почему подходит"), direction.reasoning)
    _fact(document, _("Профессии"), direction.professions)
    _fact(document, _("Что сдавать для поступления"), direction.exams, bullets=True)
    _fact(document, _("Что подтянуть в школе"), direction.subjects, bullets=True)
    _fact(document, _("Что сделать уже сейчас"), direction.next_steps, bullets=True)
    if direction.programs:
        _fact(document, _("Программы каталога"), "\n".join(direction.programs), bullets=True)
    tail = document.paragraphs[-1]
    tail.paragraph_format.space_after = Pt(8)


def _analysis(document, text: AnalysisText, *, new_page: bool) -> None:
    from docx.shared import Pt, RGBColor

    head = document.add_heading(" · ".join(title for title, _when in text.tests), level=1)
    head.paragraph_format.page_break_before = new_page
    if len(text.tests) == 1:
        dates = [_("Тест пройден {date}").format(date=when) for _title, when in text.tests if when]
    else:
        dates = [_("«{test}» пройден {date}").format(test=title, date=when) for title, when in text.tests if when]
    dates.append(_("разбор от {date}").format(date=text.created))
    meta = document.add_paragraph()
    run = meta.add_run("; ".join(dates))
    run.font.size, run.font.color.rgb = Pt(10.5), RGBColor.from_string("6B6458")
    if _lines(text.summary):
        document.add_heading(_("Общий вывод"), level=2)
        _paragraphs(document, text.summary)
    if text.scales:
        _profile(document, text.scales)
    document.add_heading(_("Направления"), level=2)
    if not text.directions:
        document.add_paragraph(_("Направлений нет: сильных шкал в тестах нет, к чему присмотреться — в общем выводе."))
    for number, direction in enumerate(text.directions, start=1):
        _direction(document, number, direction)


def render(
    student,
    texts: list[AnalysisText],
    *,
    language: str,
    actor,
    overview: OverviewText | None = None,
    moment=None,
) -> bytes:
    """Файл ученика: шапка, общая картина, разборы — каждый с новой страницы.

    Первый разбор без общей картины идёт сразу под шапкой: шапка — четверть
    страницы, и лист с одной шапкой был бы пустым.
    """
    from docx import Document

    with translation.override(language):
        document = Document()
        _styles(document)
        _page_number(document.sections[0])
        _head(document, student, actor=actor, moment=moment or timezone.now())
        if overview is not None:
            _overview(document, overview)
        for index, text in enumerate(texts):
            _analysis(document, text, new_page=bool(index) or overview is not None)
        out = io.BytesIO()
        document.save(out)
    return out.getvalue()
