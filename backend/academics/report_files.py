"""Файлы отчётов по шаблонам школы: Word из шаблона, PDF из того же Word.

Шаблоны — docx школы с подстановками `docxtpl` в `academics/report_templates`:
`review_kk.docx`, `review_ru.docx` (вариант 1), `progress_kk.docx`,
`progress_ru.docx` (вариант 2). Внешний вид — ровно файлы школы: шрифты,
размеры, таблицы, цвета, логотип, эмодзи; лист A4. Шаблоны можно открыть
в Word и поправить вид, не трогая теги `{{ … }}` и `{% … %}`.

PDF получается из того же docx через LibreOffice без графики (`soffice
--headless --convert-to pdf`): источник один, поэтому Word и PDF совпадают.
Каждый запуск — со своим профилем LibreOffice во временной папке: два
одновременных запуска с общим профилем мешают друг другу.

Архив по группе собирается в очереди (`academics.tasks.export_reports`):
состояние и готовый файл лежат в общем кэше час, забрать их может только
тот, кто заказал.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

from django.core.cache import cache
from django.utils import translation
from django.utils.translation import gettext

from academics.models import ParentReport, ReportSection, ReportTemplate, ReviewKind
from academics.school_reports import (
    DAYS_MISSED,
    DAYS_PRESENT,
    DAYS_TOTAL,
    ENGLISH_LEVEL,
    LATE,
    PCT,
    SPORT,
    address_name,
)
from core.i18n import language_of
from students.models import GroupLanguage

TEMPLATES = Path(__file__).resolve().parent / "report_templates"

#: сколько ждать LibreOffice на один вызов: первый запуск — секунды, группа — десятки
CONVERT_TIMEOUT = 300
#: сколько хранится готовый архив и его состояние
EXPORT_TTL = 60 * 60

WORD = "docx"
PDF = "pdf"
FORMATS = (PDF, WORD)
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class FileRefused(ValueError):
    """Файл сейчас не собрать — текст объясняет почему."""


def template_path(report: ParentReport) -> Path:
    base = "review" if report.template == ReportTemplate.REVIEW else "progress"
    language = report.language if report.language in GroupLanguage.values else GroupLanguage.RU
    return TEMPLATES / f"{base}_{language}.docx"


# --- Подстановки ---------------------------------------------------------------

#: заголовки блоков отзывов; постоянные — как в шаблоне школы. Эмодзи
#: перед заголовком ставит сам шаблон по виду блока (`block.kind`)
REVIEW_TITLES = {  # i18n-skip: язык отчёта выбирается при сборке
    GroupLanguage.RU: {
        ReviewKind.SAT_VERBAL: "SAT Verbal Trainer",
        ReviewKind.SAT_MATH: "SAT Math Trainer",
        ReviewKind.EEP: "GE / EEP",
    },
    GroupLanguage.KK: {
        ReviewKind.SAT_VERBAL: "SAT Verbal тренері",
        ReviewKind.SAT_MATH: "SAT Math тренері",
        ReviewKind.EEP: "GE және EEP",
    },
}


def curator_name(report: ParentReport) -> str:
    """Как подписывается куратор группы: «Имя Отчество»."""
    from academics.payloads import user_name
    from accounts.curators import curator_of

    student = report.student
    assignment = curator_of(student.group) if student.group_id else None
    return address_name(user_name(assignment.curator)) if assignment else ""


def paragraphs(text: str) -> list[str]:
    """Текст куратора по абзацам: пустые строки — граница абзаца."""
    return [part.strip() for part in text.replace("\r", "").split("\n") if part.strip()]


def context_of(report: ParentReport) -> dict:
    """Всё, что подставляется в шаблон: только снимок и тексты отчёта."""
    lines = list(report.lines.all())
    facts = (ReportSection.ATTENDANCE, ReportSection.PROFILE)
    by_code = {line.code: line.value for line in lines if line.section in facts}
    grades = [{"subject": line.title, "value": line.value} for line in lines if line.section == ReportSection.GRADES]
    ielts = {line.code: line.value for line in lines if line.section == ReportSection.IELTS}
    sat = {line.code: line.value for line in lines if line.section == ReportSection.SAT}
    reviews = {row.kind: row for row in report.reviews.all()}
    language = report.language if report.language in GroupLanguage.values else GroupLanguage.RU
    blocks = []
    for kind in (ReviewKind.SAT_VERBAL, ReviewKind.SAT_MATH, ReviewKind.EEP):
        row = reviews.get(kind)
        if row is not None and row.text.strip():
            blocks.append({"kind": kind, "title": REVIEW_TITLES[language][kind], "paragraphs": paragraphs(row.text)})
    for row in report.reviews.filter(kind=ReviewKind.SUBJECT).order_by("order", "id"):
        if row.text.strip():
            head = " — ".join(part for part in (row.teacher_name, row.subject_title) if part)
            blocks.append({"kind": ReviewKind.SUBJECT, "title": head, "paragraphs": paragraphs(row.text)})
    student = report.student
    # вариант 1: пункты раздела 2 — только с текстом или уровнем; номера разделов — подряд
    eep = reviews.get(ReviewKind.EEP)
    verbal = reviews.get(ReviewKind.SAT_VERBAL)
    math = reviews.get(ReviewKind.SAT_MATH)
    exam_items = {
        "eep_level": by_code.get(ENGLISH_LEVEL, ""),
        "eep": eep.text.strip() if eep else "",
        "sat_verbal": verbal.text.strip() if verbal else "",
        "sat_math": math.text.strip() if math else "",
    }
    has_exams = any(exam_items.values())
    sport = by_code.get(SPORT, "")
    numbers = {}
    counter = 0
    for name, present in (
        ("attendance", True),
        ("exams", has_exams),
        ("grades", True),
        ("sport", bool(sport)),
        ("character", bool(report.character.strip())),
    ):
        if present:
            counter += 1
            numbers[name] = counter
    period_mark = "ж" if language == GroupLanguage.KK else " г."  # i18n-skip: язык отчёта выбирается при сборке
    return {
        "student": f"{student.last_name} {student.first_name}".strip(),
        "group": student.group.code if student.group_id else "",
        "period": f"{report.period_start:%d.%m}-{report.period_end:%d.%m.%Y}{period_mark}",
        "period_span": f"{report.period_start:%d.%m.%Y} — {report.period_end:%d.%m.%Y}",
        "days_total": by_code.get(DAYS_TOTAL, ""),
        "days_present": by_code.get(DAYS_PRESENT, ""),
        "days_missed": by_code.get(DAYS_MISSED, ""),
        "late": by_code.get(LATE, ""),
        "pct": by_code.get(PCT, ""),
        "grades": grades,
        "ielts": ielts,
        "sat": sat,
        "has_mock": bool(ielts or sat),
        "mock_comment": paragraphs(report.mock_comment),
        "reviews": blocks,
        "summary": paragraphs(report.summary),
        "character": paragraphs(report.character),
        "sport": sport,
        "has_exams": has_exams,
        **exam_items,
        "n": numbers,
        "curator": curator_name(report),
    }


def render_docx(report: ParentReport) -> bytes:
    """Word по шаблону школы."""
    from docxtpl import DocxTemplate

    path = template_path(report)
    if not path.is_file():
        raise FileRefused(gettext("Шаблона {name} нет на сервере").format(name=path.name))
    document = DocxTemplate(str(path))
    document.render(context_of(report), autoescape=True)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


# --- PDF через LibreOffice -----------------------------------------------------------


def soffice() -> str:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if not found:
        raise FileRefused(gettext("PDF сейчас не собрать: на сервере нет LibreOffice. Скачайте Word"))
    return found


def to_pdf(documents: list[bytes]) -> list[bytes]:
    """Docx → PDF одним запуском LibreOffice на все файлы: запуск — самое долгое."""
    if not documents:
        return []
    binary = soffice()
    with tempfile.TemporaryDirectory(prefix="lms-report-") as work:
        root = Path(work)
        names = []
        for index, payload in enumerate(documents):
            name = root / f"r{index:04d}.docx"
            name.write_bytes(payload)
            names.append(name)
        command = [
            binary,
            f"-env:UserInstallation=file://{root / 'profile'}",
            "--headless",
            "--norestore",
            "--nolockcheck",
            "--convert-to",
            "pdf",
            "--outdir",
            str(root / "out"),
            *[str(name) for name in names],
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=CONVERT_TIMEOUT)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise FileRefused(gettext("PDF не собрался — попробуйте ещё раз или скачайте Word")) from error
        out = []
        for name in names:
            pdf = root / "out" / f"{name.stem}.pdf"
            if not pdf.is_file():
                raise FileRefused(gettext("PDF не собрался — попробуйте ещё раз или скачайте Word"))
            out.append(pdf.read_bytes())
    return out


def render(report: ParentReport, file_format: str) -> tuple[bytes, str, str]:
    """Один отчёт: содержимое, имя файла и тип."""
    from academics.pdf import render as render_standard
    from academics.reports import file_stem

    stem = file_stem(report)
    if report.template == ReportTemplate.STANDARD:
        if file_format == WORD:
            raise FileRefused(gettext("Стандартный отчёт скачивается только в PDF"))
        return render_standard(report, curator_name=_standard_curator(report)), f"{stem}.pdf", "application/pdf"
    document = render_docx(report)
    if file_format == WORD:
        return document, f"{stem}.docx", DOCX_TYPE
    return to_pdf([document])[0], f"{stem}.pdf", "application/pdf"


def _standard_curator(report: ParentReport) -> str:
    from academics.payloads import user_name
    from accounts.curators import curator_of

    student = report.student
    assignment = curator_of(student.group) if student.group_id else None
    return user_name(assignment.curator) if assignment else ""


def render_zip(reports: list[ParentReport], file_format: str, progress=None) -> bytes:
    """Архив отчётов: шаблоны школы одним запуском LibreOffice, стандартные — как раньше."""
    from academics.pdf import render as render_standard
    from academics.reports import file_stem

    files: list[tuple[str, bytes]] = []
    pending: list[tuple[str, bytes]] = []
    for index, report in enumerate(reports, start=1):
        stem = file_stem(report)
        if report.template == ReportTemplate.STANDARD:
            files.append((f"{stem}.pdf", render_standard(report, curator_name=_standard_curator(report))))
        elif file_format == WORD:
            files.append((f"{stem}.docx", render_docx(report)))
        else:
            pending.append((f"{stem}.pdf", render_docx(report)))
        if progress is not None:
            progress(index)
    if pending:
        for (name, _), pdf in zip(pending, to_pdf([payload for _, payload in pending]), strict=True):
            files.append((name, pdf))
    buffer = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(files):
            unique = name
            counter = 2
            while unique in used:
                unique = name.replace(".", f" ({counter}).", 1)
                counter += 1
            used.add(unique)
            archive.writestr(unique, payload)
    return buffer.getvalue()


# --- Архив в очереди ------------------------------------------------------------------


def _state_key(job: str) -> str:
    return f"report-export:{job}"


def _file_key(job: str) -> str:
    return f"report-export-file:{job}"


def start_export(*, user, ids: list[int], file_format: str, zip_name: str) -> str:
    """Заказать архив: номер задания; сам архив собирает очередь."""
    from academics.tasks import export_reports

    job = uuid.uuid4().hex
    cache.set(
        _state_key(job),
        {"state": "pending", "done": 0, "total": len(ids), "user": user.pk, "name": zip_name, "error": ""},
        EXPORT_TTL,
    )
    export_reports.delay(job, user.pk, ids, file_format, zip_name)
    return job


def export_state(job: str, user) -> dict | None:
    """Состояние задания — только тому, кто заказал."""
    state = cache.get(_state_key(job))
    if not state or state.get("user") != user.pk:
        return None
    return state


def export_file(job: str, user) -> tuple[bytes, str] | None:
    state = export_state(job, user)
    if state is None or state.get("state") != "done":
        return None
    payload = cache.get(_file_key(job))
    if payload is None:
        return None
    return payload, state["name"]


def run_export(job: str, *, user_id: int, ids: list[int], file_format: str, zip_name: str) -> str:
    """Собрать архив и положить в кэш. Отчёты помечаются «выгружен»."""
    from academics.reports import ReportRefused, mark_exported
    from accounts.models import User

    state = cache.get(_state_key(job)) or {"user": user_id, "name": zip_name, "total": len(ids)}

    def save(**changes) -> None:
        state.update(changes)
        cache.set(_state_key(job), state, EXPORT_TTL)

    user = User.objects.filter(pk=user_id).first()
    rows = list(
        ParentReport.objects.filter(pk__in=ids)
        .select_related("student", "student__group", "student__sport", "student__sport__sport_type")
        .prefetch_related("lines", "reviews")
        .order_by("student__group__code", "student__last_name", "student__first_name")
    )
    save(state="running", done=0, total=len(rows))
    try:
        # очередь без языка запроса: причина отказа — на языке того, кто заказал;
        # текст отчётов от этого не зависит — его язык выбран при сборке
        with translation.override(language_of(user)):
            payload = render_zip(rows, file_format, progress=lambda done: save(done=done))
    except FileRefused as error:
        save(state="failed", error=str(error))
        return "failed"
    for row in rows:
        try:
            mark_exported(row, actor=user)
        except ReportRefused:
            continue
    cache.set(_file_key(job), payload, EXPORT_TTL)
    save(state="done", done=len(rows))
    return "done"
