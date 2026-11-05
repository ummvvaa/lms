"""Лист A4 с печатным QR секции: герб, название, адрес, дни и часы, код, три шага.

Собирается fpdf2 тем же шрифтом, что отчёт родителям (`academics/fonts`,
Golos Text — в нём есть казахские буквы). Код рисуется прямоугольниками
по матрице пакета `qrcode`: вектор печатается чётко в любом размере,
картинок и внешних сервисов нет — ссылка никуда, кроме LMS, не уходит.

Инструкция — сразу на трёх языках школы: лист висит на площадке один на
всех, язык интерфейса читающего ему неизвестен. Название, адрес и расписание —
как заведены в секции.
"""

# i18n-skip-file: лист печатается сразу на трёх языках — тексты шагов заданы здесь на ru, kk и en

from __future__ import annotations

import logging

import qrcode
from django.utils import translation
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from academics.pdf import ACCENT, FONT_FILES, FONTS, INK, INK_2, INK_3, LINE
from sport import printed
from sport.models import Section

logging.getLogger("fontTools").setLevel(logging.WARNING)

#: сторона кода на листе, мм: крупно, чтобы камера брала с двух шагов; меньше нижней границы не сжимается
QR_SIDE = 120
QR_MIN = 70
#: высота блока шагов на трёх языках, мм — место под него остаётся внизу листа
STEPS_HEIGHT = 50
#: поле листа, мм
MARGIN = 16
#: шаги на трёх языках: заголовок, три шага, условие
STEPS = (
    (
        "Отметься на занятии",
        ("Наведи камеру телефона на код", "Войди в LMS", "Разреши доступ к геолокации"),
        "Отметка засчитывается только во время занятия и рядом с площадкой.",
    ),
    (
        "Сабаққа белгілен",
        ("Телефон камерасын кодқа бағытта", "LMS-ке кір", "Геолокацияға рұқсат бер"),
        "Белгі тек сабақ кезінде және алаңның жанында есептеледі.",
    ),
    (
        "Check in to the session",
        ("Point your phone camera at the code", "Sign in to LMS", "Allow access to your location"),
        "Check-in counts only during the session and near the venue.",
    ),
)


def _crest():
    """Герб школы — тот же файл, что в шапке разборов профтеста."""
    from career.word import CREST

    return CREST if CREST.is_file() else None


def schedule_lines(section: Section) -> list[str]:
    """Дни и часы занятий секции: «Суббота · 12:00–13:00 · параллели 10–11», час — строкой."""
    with translation.override("ru"):
        return [
            " · ".join(
                part
                for part in (
                    str(slot.get_weekday_display()),
                    f"{slot.starts:%H:%M}–{slot.ends:%H:%M}",
                    f"параллели {slot.parallel_from}–{slot.parallel_to}",
                    slot.room,
                )
                if part
            )
            for slot in section.slots.filter(archived_at__isnull=True).order_by("weekday", "starts", "parallel_from")
        ]


def _matrix(url: str) -> list[list[bool]]:
    """Матрица кода без полей: уровень M — запас на потёртый лист при коротком коде."""
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
    code.add_data(url)
    code.make(fit=True)
    return code.get_matrix()


def _draw_code(pdf: FPDF, url: str, x: float, y: float, side: float) -> None:
    """Код прямоугольниками: тёмные клетки подряд — одной полосой, по строкам и по столбцам.

    Полосы двух направлений перекрывают каждый стык соседних тёмных клеток:
    при печати и на экране между ними не остаётся волосяных щелей.
    """
    matrix = _matrix(url)
    size = len(matrix)
    cell = side / size
    pdf.set_fill_color(0, 0, 0)

    def runs(line: list[bool]):
        start = None
        for index, dark in enumerate([*line, False]):
            if dark and start is None:
                start = index
            elif not dark and start is not None:
                yield start, index - start
                start = None

    for row in range(size):
        for start, length in runs(matrix[row]):
            pdf.rect(x + start * cell, y + row * cell, length * cell, cell, style="F")
    for column in range(size):
        for start, length in runs([matrix[row][column] for row in range(size)]):
            if length > 1:
                pdf.rect(x + column * cell, y + start * cell, cell, length * cell, style="F")


def render(section: Section) -> bytes:
    """PDF листа для печати. Без места секции кода нет — решает вызывающий."""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(MARGIN, MARGIN, MARGIN)
    pdf.set_auto_page_break(auto=False)
    for style, name in FONT_FILES.items():
        pdf.add_font("Golos", style=style, fname=str(FONTS / name))
    pdf.set_title(f"QR — {section.title}")
    pdf.add_page()
    width = pdf.w - 2 * MARGIN

    def line(text: str, *, size: float, style: str = "", color=INK, height: float | None = None, align="C") -> None:
        pdf.set_font("Golos", style=style, size=size)
        pdf.set_text_color(*color)
        pdf.multi_cell(width, height or size * 0.5, text, align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    crest = _crest()
    if crest is not None:
        pdf.image(str(crest), x=(pdf.w - 24) / 2, y=MARGIN, h=24, w=24, keep_aspect_ratio=True)
        pdf.set_y(MARGIN + 28)
    line(section.title, size=30, style="B", height=13)
    pdf.ln(1)
    line(section.address, size=13, color=INK_2, height=6.5)
    pdf.ln(2)
    for text in schedule_lines(section):
        line(text, size=12, color=INK_2, height=6)

    # код — по центру листа, в тонкой рамке с полем: камере нужна светлая кромка вокруг.
    # Сторона — сколько осталось места над шагами: у секции с длинным расписанием код меньше
    pad = 6
    top = pdf.get_y() + 8 + pad
    side = max(QR_MIN, min(QR_SIDE, pdf.h - MARGIN - STEPS_HEIGHT - top - pad - 8))
    left = (pdf.w - side) / 2
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.4)
    pdf.rect(left - pad, top - pad, side + 2 * pad, side + 2 * pad, style="D", round_corners=True, corner_radius=4)
    _draw_code(pdf, printed.print_url(section), left, top, side)
    pdf.set_y(top + side + pad + 8)

    # три языка — тремя колонками одной высоты
    gap = 5
    column = (width - 2 * gap) / 3
    base = pdf.get_y()
    for index, (title, steps, condition) in enumerate(STEPS):
        x = MARGIN + index * (column + gap)
        pdf.set_xy(x, base)
        pdf.set_font("Golos", style="B", size=12.5)
        pdf.set_text_color(*ACCENT)
        pdf.multi_cell(column, 6, title, align="L", new_x=XPos.LEFT, new_y=YPos.NEXT)
        pdf.ln(1.5)
        for number, step in enumerate(steps, start=1):
            pdf.set_x(x)
            pdf.set_font("Golos", style="B", size=11)
            pdf.set_text_color(*INK)
            pdf.cell(6, 5.4, f"{number}.", new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.set_font("Golos", size=11)
            pdf.multi_cell(column - 6, 5.4, step, align="L", new_x=XPos.LEFT, new_y=YPos.NEXT)
            pdf.ln(1)
        pdf.set_x(x)
        pdf.ln(1)
        pdf.set_x(x)
        pdf.set_font("Golos", size=9)
        pdf.set_text_color(*INK_3)
        pdf.multi_cell(column, 4.4, condition, align="L", new_x=XPos.LEFT, new_y=YPos.NEXT)
    return bytes(pdf.output())


def filename(section: Section) -> str:
    return f"QR {section.title}.pdf"
