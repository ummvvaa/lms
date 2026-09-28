"""PDF отчёта родителям: переносы по словам, одна страница, разделы целиком, без повторов.

Вид проверяется по самому PDF: текст страниц — через pypdf, ширины —
тем же шрифтом, которым PDF собран.
"""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from academics import pdf as rendering
from academics import reports as reporting
from academics.models import ReportLine, ReportPeriod, ReportSection
from academics.tests.conftest import days

pytestmark = pytest.mark.django_db


@pytest.fixture
def report(lesson, eng_lesson, pupils, teacher, calendar, admin):
    from academics import marks as marking
    from academics.calendar import scale_of

    marking.set_grade(lesson, pupils["aliya"], 8, actor=teacher, calendar=calendar, scale=scale_of(calendar.year))
    start, end = reporting.month_bounds(days(0))
    rows = reporting.build_for_period(kind=ReportPeriod.MONTH, start=start, end=end, calendar=calendar, actor=admin)
    report = next(row for row in rows if row.student_id == pupils["aliya"].pk)
    report.curator_word = "Алия держит темп по алгебре. Английскому нужно внимание: оценок пока нет."
    report.save()
    return report


def pages_of(report) -> list[str]:
    reader = PdfReader(io.BytesIO(rendering.render(report, curator_name="Асель Куратор")))
    return [page.extract_text() for page in reader.pages]


def replace_lines(report, rows: list[tuple[str, str, str, str]]) -> None:
    ReportLine.objects.filter(report=report).delete()
    ReportLine.objects.bulk_create(
        ReportLine(report=report, section=section, order=i, title=title, value=value, note=note)
        for i, (section, title, value, note) in enumerate(rows)
    )


def test_row_titles_do_not_repeat_the_section_title_and_empty_subject_is_one_phrase(report):
    lines = list(report.lines.all())
    for line in lines:
        assert line.title != rendering.SECTION_TITLES[line.section], f"подпись повторяет раздел: {line.title}"
    empty = [line for line in lines if line.section == ReportSection.GRADES and line.value == reporting.NO_GRADES]
    assert empty, "у английского оценок нет"
    for line in empty:
        assert line.note == "", "одна фраза, без «оценок нет» рядом"


def test_short_report_is_one_page(report):
    assert len(pages_of(report)) == 1


def test_words_wrap_only_whole(report):
    """Каждое слово помещается в свою колонку целиком — середину слова не рвёт."""
    missing = "Аттестат, Транскрипт, Сертификат экзамена, Рекомендательное письмо, Паспорт"
    rows = [
        (ReportSection.ATTENDANCE, reporting.ATTENDANCE_ROW, "96 %", "уроков с отметкой: 76"),
        (ReportSection.GRADES, "Казахский язык и литература", "сейчас выходит 4", "ФО 8.3, СОР 12 из 15, СОЧ 21 из 25"),
        (ReportSection.GRADES, "Химия", reporting.NO_GRADES, ""),
        (ReportSection.DOCUMENTS, "Собрано", "0 из 5", ""),
        (ReportSection.DOCUMENTS, "Не хватает", missing, ""),
    ]
    replace_lines(report, rows)

    pdf = rendering.ReportPdf()
    title_w, value_w, note_w = pdf.layout([(title, value, note) for _s, title, value, note in rows])
    pad = rendering.CELL_PADDING[1] + rendering.CELL_PADDING[3]
    for _section, title, value, note in rows:
        cells = [(title, title_w, "B"), (value, value_w if note else value_w + note_w, ""), (note, note_w, "")]
        for text, width, style in cells:
            pdf.set_font(pdf.family, style=style, size=rendering.ROW_SIZE)
            for word in text.split():
                assert pdf.get_string_width(word) <= width - pad, f"«{word}» не помещается в колонку"

    text = " ".join(pages_of(report))
    assert "Рекомендательное" in text, "слово целиком, без переноса посреди"


def test_old_snapshot_row_named_like_its_section_is_not_repeated(report):
    replace_lines(
        report,
        [
            (ReportSection.ATTENDANCE, "Посещаемость", "уроков с отметкой ещё не было", ""),
            (ReportSection.EXAMS, "Экзамены и вузы", "данных пока нет", ""),
        ],
    )
    text = pages_of(report)[0]
    assert text.count("Посещаемость") == 1 and text.count("Экзамены и вузы") == 1
    assert "Уроков с отметкой ещё не было" in text


def test_long_report_does_not_cut_a_section_between_pages(report):
    subjects = [f"Предмет номер {i}" for i in range(1, 27)]
    rows = [(ReportSection.ATTENDANCE, reporting.ATTENDANCE_ROW, "90 %", "уроков с отметкой: 80")]
    rows += [(ReportSection.GRADES, title, "сейчас выходит 4", "ФО 7, СОР 11 из 15") for title in subjects]
    rows += [(ReportSection.EXAMS, "IELTS", "6.5", "цель 7.5"), (ReportSection.DOCUMENTS, "Собрано", "3 из 5", "")]
    rows += [(ReportSection.DISCIPLINE, "Замечания", "нет", "")]
    replace_lines(report, rows)

    pages = pages_of(report)
    assert len(pages) >= 2, "длинный отчёт не влез бы на одну страницу"
    for section, title in rendering.SECTION_TITLES.items():
        own = [row[1] for row in rows if row[0] == section]
        holder = [i for i, page in enumerate(pages) if title in page]
        assert len(holder) == 1, f"раздел «{title}» на двух страницах или пропал"
        for row_title in own:
            assert row_title in pages[holder[0]], f"строка «{row_title}» ушла от своего раздела"
