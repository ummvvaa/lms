"""PDF отчёта родителям на fpdf2: одна-две страницы A4, крупный шрифт, таблицы.

Шрифт — Golos Text той же версии, что во фронте (`frontend/public/fonts`),
лежит рядом в `academics/fonts` как TTF: fpdf2 2.8 не принимает woff2,
а бэкенд в контейнере фронта не видит. TTF получен из того же woff2
распаковкой fontTools, из сети ничего не тянулось. Лицензия OFL рядом.
Внутренних ярлыков в отчёте нет — правило то же, что для ученика:
снимок собирает `academics.reports`, здесь только вид. PDF строится
по запросу и не хранится.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from django.conf import settings
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from academics.models import ParentReport, ReportSection
from academics.reports import file_stem

FONTS = Path(__file__).resolve().parent / "fonts"

#: fontTools рассказывает о каждом глифе подмножества на уровне INFO —
#: в журнале сервера это сотни строк на один PDF
logging.getLogger("fontTools").setLevel(logging.WARNING)
FONT_FILES = {"": "GolosText-Regular.ttf", "B": "GolosText-Bold.ttf"}

#: Цвета языка интерфейса — те же токены, что на экране
INK = (0x14, 0x13, 0x0F)
INK_2 = (0x55, 0x50, 0x4A)
INK_3 = (0x8A, 0x83, 0x79)
LINE = (0xE6, 0xE0, 0xD6)
SURFACE_2 = (0xFA, 0xF8, 0xF4)
ACCENT = (0xE2, 0x62, 0x2F)

SECTION_TITLES = {
    ReportSection.ATTENDANCE: "Посещаемость",
    ReportSection.GRADES: "Оценки по предметам",
    ReportSection.EXAMS: "Экзамены и вузы",
    ReportSection.DOCUMENTS: "Документы для поступления",
    ReportSection.DISCIPLINE: "Дисциплина",
}


def _fonts_present() -> bool:
    return all((FONTS / name).is_file() for name in FONT_FILES.values())


class ReportPdf(FPDF):
    """Лист A4 с полями 16 мм и Golos Text."""

    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(auto=True, margin=16)
        if _fonts_present():
            for style, name in FONT_FILES.items():
                self.add_font("Golos", style=style, fname=str(FONTS / name))
            self.family = "Golos"
        else:
            # без шрифта в дереве кириллицу не собрать: падать с понятной причиной
            raise RuntimeError("Шрифт Golos Text не найден в academics/fonts")

    def text_line(
        self, text: str, *, size: float = 12, style: str = "", color=INK, height: float | None = None
    ) -> None:
        self.set_font(self.family, style=style, size=size)
        self.set_text_color(*color)
        self.multi_cell(0, height or size * 0.55, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def section(self, title: str) -> None:
        self.ln(3)
        self.set_font(self.family, style="B", size=13)
        self.set_text_color(*INK)
        self.cell(0, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LINE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def rows(self, rows: list[tuple[str, str, str]]) -> None:
        """Таблица «подпись · значение · примечание» с чередованием подложки."""
        self.set_font(self.family, size=11.5)
        self.set_text_color(*INK)
        self.set_draw_color(*LINE)
        self.set_fill_color(*SURFACE_2)
        with self.table(
            col_widths=(58, 38, 82),
            text_align=("LEFT", "LEFT", "LEFT"),
            borders_layout="HORIZONTAL_LINES",
            line_height=7.2,
            padding=(1.6, 2, 1.6, 2),
            first_row_as_headings=False,
            cell_fill_color=SURFACE_2,
            cell_fill_mode="EVEN_ROWS",
        ) as table:
            for title, value, note in rows:
                row = table.row()
                row.cell(title, style=FontFace(emphasis="BOLD", size_pt=11.5))
                row.cell(value)
                row.cell(note, style=FontFace(color=INK_2, size_pt=10.5))


def render(report: ParentReport, *, curator_name: str = "") -> bytes:
    """Собрать PDF одного отчёта."""
    school = getattr(settings, "SCHOOL_NAME", "")
    student = report.student
    pdf = ReportPdf()
    pdf.add_page()
    pdf.set_font(pdf.family, size=10)
    pdf.set_text_color(*INK_3)
    pdf.cell(0, 6, school, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(pdf.family, style="B", size=20)
    pdf.set_text_color(*INK)
    pdf.cell(0, 11, f"{student.last_name} {student.first_name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(pdf.family, size=12)
    pdf.set_text_color(*INK_2)
    group = student.group.code if student.group_id else ""
    pdf.cell(0, 7, f"Отчёт за {report.title} · группа {group}".strip(" ·"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, pdf.get_y() + 2, pdf.l_margin + 30, pdf.get_y() + 2)
    pdf.set_line_width(0.2)
    pdf.ln(5)

    lines = list(report.lines.all())
    for code, title in SECTION_TITLES.items():
        rows = [(line.title, line.value, line.note) for line in lines if line.section == code]
        if not rows:
            continue
        pdf.section(title)
        pdf.rows(rows)

    if report.curator_word.strip():
        pdf.section("Слово куратора")
        pdf.text_line(report.curator_word.strip(), size=12, color=INK, height=6.6)
        if curator_name:
            pdf.ln(1)
            pdf.text_line(curator_name, size=10.5, color=INK_3)

    pdf.ln(6)
    pdf.text_line(
        f"Собрано {report.built_at.astimezone().strftime('%d.%m.%Y')}. Оценки и пропуски — из журналов учителей.",
        size=9.5,
        color=INK_3,
    )
    return bytes(pdf.output())


def render_zip(reports: list[ParentReport], *, curators: dict[int, str] | None = None) -> bytes:
    """Архив: по PDF на ученика. Имена файлов — как у одиночного скачивания."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        used: set[str] = set()
        for report in reports:
            name = file_stem(report)
            stem = name
            counter = 2
            while stem in used:
                stem = f"{name} ({counter})"
                counter += 1
            used.add(stem)
            group_id = report.student.group_id
            curator = (curators or {}).get(group_id, "") if group_id else ""
            archive.writestr(f"{stem}.pdf", render(report, curator_name=curator))
    return buffer.getvalue()
