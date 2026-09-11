"""Разбор таблицы поступления Асем (фаза 65).

Асем ведёт учеников в Excel: по листу на группу, в строке — контакты,
пароли, ссылки на папку, паспорт, табель и рекомендацию, срок паспорта,
GPA и до трёх результатов IELTS и SAT. Данные ей приносят кураторы.
Решение владельца: таблица заливается один раз, дальше всё ведётся
в карточке. Повторный запуск не дублирует, а обновляет.

Что важно в разборе и почему:

* **лист — это группа** по своему имени (`Chicago ` с пробелом → CHICAGO);
  листа без группы мы не трогаем вовсе: угадывать, чей это класс, нельзя;
* **колонки ищутся по заголовкам, не по позиции**: в BOSTON, MIT и HARVARD
  между паролем почты и паролем Common App вставлена почта Common App,
  и в одном из листов её заголовок начинается с полусотни переносов;
* **пустая ячейка ничего не стирает**. Таблица заполнялась годами
  и местами не дозаполнена; пустота в ней значит «не знаю», а не «нет»;
* **из текста попытка не создаётся**. В ячейках баллов встречаются
  «общ баллы или ссылки?» и даже дата — это заметки Асем себе,
  а не результат экзамена;
* **почта из таблицы сверяется с реестром и не переписывает его**:
  почта ученика — его вход в систему, и менять её импортом опасно.

Пароли идут прямо в шифрованное хранилище (`students.credentials`)
и на шаге проверки не показываются — только «есть / нет».
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

#: Колонки таблицы: ключ — как поле зовётся у нас, значения — обрывки
#: заголовка Асем. Ищем по вхождению: заголовки приходят с переносами,
#: хвостами пробелов и разным регистром.
COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "name": ("фио", "ф.и.о", "ученик", "студент"),
    "phone": ("номер телефона", "телефон"),
    "common_app_email": ("электронный адрес common app", "почта common app", "common app email"),
    "email": ("электронный адрес", "почта", "email", "e-mail"),
    "email_password": ("пароль от эл", "пароль от почт", "пароль эл"),
    "common_app_password": ("пароль от common app", "пароль common app"),
    "drive_folder": ("папку студента", "папка студента", "гугл драйв", "drive"),
    "passport_link": ("ссылка на паспорт", "паспорт ссылка"),
    "passport_expiry": ("срок годности паспорта", "срок паспорта", "годност"),
    "gpa": ("средний gpa", "gpa", "средний балл"),
    "ielts_1": ("ielts-1", "ielts 1"),
    "ielts_2": ("ielts-2", "ielts 2"),
    "ielts_3": ("ielts-3", "ielts 3"),
    "sat_1": ("sat-1", "sat 1"),
    "sat_2": ("sat-2", "sat 2"),
    "sat_3": ("sat-3", "sat 3"),
    "transcript_link": ("ссылка на табел", "табел"),
    "recommendation_link": ("рек. письмо", "рекоменд"),
}

#: Порядок важен: «Электронный адрес Common app» должен разбираться
#: раньше «Электронный адрес», иначе почта Common App легла бы в почту
#: ученика. Позиция колонок в листах разная, а этот порядок — общий.
COLUMN_ORDER: tuple[str, ...] = (
    "name",
    "phone",
    "common_app_email",
    "common_app_password",
    "email_password",
    "email",
    "drive_folder",
    "passport_link",
    "passport_expiry",
    "gpa",
    "ielts_1",
    "ielts_2",
    "ielts_3",
    "sat_1",
    "sat_2",
    "sat_3",
    "transcript_link",
    "recommendation_link",
)

#: Колонки баллов: какой экзамен и какой это по счёту результат
SCORE_COLUMNS: tuple[tuple[str, str, int], ...] = (
    ("ielts_1", "IELTS", 1),
    ("ielts_2", "IELTS", 2),
    ("ielts_3", "IELTS", 3),
    ("sat_1", "SAT", 1),
    ("sat_2", "SAT", 2),
    ("sat_3", "SAT", 3),
)

#: Колонки-ссылки и типы документов, которыми они становятся
LINK_DOCUMENTS: tuple[tuple[str, str], ...] = (
    ("passport_link", "passport"),
    ("transcript_link", "transcript"),
    ("recommendation_link", "recommendation"),
)

#: Опечатки в домене почты, которые видно глазом, но не программой:
#: писать на такой адрес бессмысленно, а чинить его импортом мы не вправе.
#: Сверяется домен целиком — «gmail.com» не должен ловиться на «gmail.co»
EMAIL_SUSPECTS: dict[str, str] = {
    "gmail.ru": "домен «gmail.ru» — у Gmail такого нет, вероятно «gmail.com»",
    "gmail.co": "домен «gmail.co» — похоже на обрезанный «gmail.com»",
    "mail.ru.com": "домен «mail.ru.com» — вероятно «mail.ru»",
}


class FileRejected(ValueError):
    """Файл нельзя разбирать вовсе — дело не в отдельной строке."""


def _text(value) -> str:
    """Ячейка строкой: без переносов, без хвостов, без «None»."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _header_key(title: str) -> str:
    return re.sub(r"\s+", " ", str(title or "")).strip().lower()


def read_columns(header: list[str]) -> dict[str, int]:
    """Сопоставить заголовки листа с нашими колонками.

    Один заголовок достаётся одной колонке: иначе «Электронный адрес»
    подошёл бы и почте ученика, и почте Common App.
    """
    taken: set[int] = set()
    found: dict[str, int] = {}
    keys = [_header_key(title) for title in header]
    for name in COLUMN_ORDER:
        hints = COLUMN_HINTS[name]
        for index, key in enumerate(keys):
            if index in taken or not key:
                continue
            if any(hint in key for hint in hints):
                found[name] = index
                taken.add(index)
                break
    return found


# --- Разбор ячеек ---------------------------------------------------------


def parse_phone(raw: str) -> str | None:
    """Телефон к виду `+7XXXXXXXXXX`; не разбирается — `None`.

    В таблице встречается всё: `87753730924.0` (Excel сделал из номера
    число), `=77715019917` (формула, чтобы ноль не съелся), пробелы,
    скобки и дефисы. Формат один, поэтому и правило одно.
    """
    text = _text(raw)
    if not text:
        return None
    text = text.lstrip("=").strip()
    # хвост «.0» от числового формата Excel — не часть номера
    text = re.sub(r"\.0+$", "", text)
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10 and digits[0] == "7":
        return "+7" + digits
    return None


def parse_email(raw: str) -> tuple[str, str]:
    """Почта и предупреждение о ней. Пустое предупреждение — всё чисто."""
    text = _text(raw)
    if not text:
        return "", ""
    if text.startswith("@"):
        return text, "адрес начинается с «@» — перед ним потерялось имя ящика"
    low = text.lower()
    if "@" not in low or "." not in low.split("@")[-1]:
        return text, "не похоже на адрес почты"
    domain = low.rsplit("@", 1)[-1]
    if domain.endswith(".con"):
        return text, "домен оканчивается на «.con» — похоже на опечатку в «.com»"
    warning = EMAIL_SUSPECTS.get(domain, "")
    return text, warning


def parse_expiry(raw) -> tuple[dt.date | None, str]:
    """Срок годности паспорта. Текст вместо даты — предупреждение, поле пустое."""
    if isinstance(raw, dt.datetime):
        return raw.date(), ""
    if isinstance(raw, dt.date):
        return raw, ""
    text = _text(raw)
    if not text:
        return None, ""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(text, pattern).date(), ""
        except ValueError:
            continue
    return None, f"срок паспорта записан словами: «{text[:60]}» — дату впишите руками"


def parse_score(raw, exam: str) -> tuple[Decimal | None, str]:
    """Балл экзамена по шкале из реестра. Текст — пропуск ячейки с предупреждением."""
    from core.domains import scale_of

    text = _text(raw)
    if not text:
        return None, ""
    try:
        value = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None, f"в ячейке {exam} не балл, а текст: «{text[:60]}»"
    scale = scale_of(exam)
    if scale is None:
        return None, f"шкала {exam} неизвестна"
    if not scale.holds(value):
        return None, f"{exam} {value} не по шкале: от {scale.minimum} до {scale.maximum} шагом {scale.step}"
    return value, ""


def parse_gpa(raw) -> tuple[Decimal | None, str]:
    """Средний балл аттестата: 0–5, как в реестре у поля GPA."""
    text = _text(raw)
    if not text:
        return None, ""
    try:
        value = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None, f"в ячейке GPA не число, а текст: «{text[:60]}»"
    if not (Decimal("0") <= value <= Decimal("5")):
        return None, f"GPA {value} вне шкалы 0–5"
    return value, ""


def parse_link(raw) -> tuple[str, str]:
    """Ссылка на документ вне системы."""
    text = _text(raw)
    if not text:
        return "", ""
    if not text.lower().startswith(("http://", "https://")):
        return "", f"ссылка не похожа на адрес: «{text[:60]}»"
    return text, ""


# --- Строки и листы -------------------------------------------------------


@dataclass
class Row:
    """Одна строка листа после разбора: что нашли и что не сошлось."""

    index: int
    raw_name: str
    student: int | None = None
    student_name: str = ""
    candidates: list[dict] = field(default_factory=list)
    values: dict = field(default_factory=dict)
    scores: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    #: пароли — только «есть / нет»: на шаге проверки их не показывают
    passwords: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    skip: bool = False

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "raw_name": self.raw_name,
            "student": self.student,
            "student_name": self.student_name,
            "candidates": self.candidates,
            "phone": self.values.get("student_phone", ""),
            "email": self.values.get("email", ""),
            "common_app_email": self.values.get("common_app_email", ""),
            "drive_folder_url": self.values.get("drive_folder_url", ""),
            "gpa": float(self.values["gpa"]) if self.values.get("gpa") is not None else None,
            "passport_expires": self.values.get("passport_expires"),
            "scores": [{**s, "value": float(s["value"])} for s in self.scores],
            "links": [{"doc_type": link["doc_type"], "url": link["url"]} for link in self.links],
            "has_email_password": self.passwords.get("email", False),
            "has_common_app_password": self.passwords.get("common_app", False),
            "warnings": self.warnings,
            "error": self.error,
            "skip": self.skip,
        }


@dataclass
class Sheet:
    """Один лист файла: чья это группа и что в строках."""

    name: str
    group_code: str = ""
    group_id: int | None = None
    error: str = ""
    rows: list[Row] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "group_code": self.group_code,
            "group": self.group_id,
            "error": self.error,
            "rows": [row.as_dict() for row in self.rows],
            "ready": sum(1 for row in self.rows if not row.error and not row.skip),
            "skipped": sum(1 for row in self.rows if row.error or row.skip),
        }


@dataclass
class Fix:
    """Правка человека по строке: кому отнести или пропустить."""

    student: int | None = None
    skip: bool = False


def read_sheets(uploaded) -> list[tuple[str, list[str], list[list]]]:
    """Прочитать книгу целиком: имя листа, заголовок и строки.

    Читаем сами, а не общим `read_table`: тому нужен один лист, а здесь
    лист — это группа, и все они нужны разом.
    """
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    name = (getattr(uploaded, "name", "") or "").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise FileRejected("Таблица поступления читается из книги Excel (.xlsx): лист — это группа")
    uploaded.seek(0)
    try:
        book = load_workbook(uploaded, read_only=True, data_only=True)
    except (InvalidFileException, KeyError, ValueError) as error:
        raise FileRejected(f"Файл не открылся как книга Excel: {error}") from error

    out = []
    for sheet_name in book.sheetnames:
        rows = [list(row) for row in book[sheet_name].iter_rows(values_only=True)]
        if not rows:
            out.append((sheet_name, [], []))
            continue
        header = [_text(cell) for cell in rows[0]]
        # пустые строки — хвост таблицы и разделитель под заголовком:
        # в одних листах он есть, в других данные идут сразу
        body = [row for row in rows[1:] if any(_text(cell) for cell in row)]
        out.append((sheet_name, header, body))
    book.close()
    return out


def _group_of(sheet_name: str):
    """Группа по имени листа: `Chicago ` → CHICAGO."""
    from students.models import StudyGroup

    code = _text(sheet_name).upper()
    return StudyGroup.objects.filter(code__iexact=code).first()


def parse(uploaded, *, fixes: dict[str, Fix] | None = None) -> list[Sheet]:
    """Разобрать книгу целиком, ничего не записывая."""
    from students.models import Student
    from suggestions.name_matching import find

    fixes = fixes or {}
    sheets_raw = read_sheets(uploaded)
    if not sheets_raw:
        raise FileRejected("В книге нет ни одного листа")

    out: list[Sheet] = []
    for sheet_name, header, body in sheets_raw:
        sheet = Sheet(name=sheet_name, group_code=_text(sheet_name).upper())
        group = _group_of(sheet_name)
        if group is None:
            sheet.error = f"Группы «{sheet.group_code}» нет в системе — лист пропущен целиком"
            out.append(sheet)
            continue
        sheet.group_id = group.pk
        columns = read_columns(header)
        if "name" not in columns:
            sheet.error = "На листе не нашлась колонка «ФИО» — лист пропущен целиком"
            out.append(sheet)
            continue

        students = list(Student.objects.filter(group=group, is_active=True).select_related("group"))
        seen: dict[int, int] = {}
        for number, raw in enumerate(body, start=1):

            def cell(name: str, line: list = raw, columns: dict = columns):
                index = columns.get(name, -1)
                return line[index] if 0 <= index < len(line) else None

            raw_name = _text(cell("name"))
            # строка без ФИО — не ошибка: это хвост листа или его разметка
            if not raw_name:
                continue
            row = Row(index=number, raw_name=raw_name)
            fix = fixes.get(f"{sheet_name}:{number}")
            if fix and fix.skip:
                row.skip = True
            _resolve_student(row, students=students, fix=fix, finder=find)
            _resolve_values(row, cell=cell)
            if row.student is not None:
                if row.student in seen:
                    row.error = f"этот ученик уже был в строке №{seen[row.student]}"
                else:
                    seen[row.student] = number
            sheet.rows.append(row)
        out.append(sheet)
    return out


def _resolve_student(row: Row, *, students: list, fix: Fix | None, finder) -> None:
    """Найти ученика строки: правкой человека или нечётким сравнением ФИО."""
    if fix and fix.student:
        chosen = next((s for s in students if s.pk == fix.student), None)
        if chosen is not None:
            row.student, row.student_name = chosen.pk, chosen.full_name
            return
    outcome = finder(row.raw_name, students=students)
    row.candidates = [c.as_dict() for c in outcome.candidates]
    if outcome.is_confident and outcome.best:
        row.student, row.student_name = outcome.best.student_id, outcome.best.full_name
        return
    row.error = "похожих учеников несколько — выберите" if outcome.is_ambiguous else "ученик не найден в этой группе"


def _resolve_values(row: Row, *, cell) -> None:
    """Разобрать ячейки строки: контакты, ссылки, GPA, баллы, пароли."""
    raw_phone = _text(cell("phone"))
    if raw_phone:
        phone = parse_phone(raw_phone)
        if phone is None:
            row.error = f"телефон «{raw_phone[:40]}» не разбирается"
        else:
            row.values["student_phone"] = phone

    email, warning = parse_email(cell("email"))
    if email:
        row.values["email"] = email
    if warning:
        row.warnings.append(f"почта: {warning}")

    common_email, warning = parse_email(cell("common_app_email"))
    if common_email:
        row.values["common_app_email"] = common_email
    if warning:
        row.warnings.append(f"почта Common App: {warning}")

    folder, warning = parse_link(cell("drive_folder"))
    if folder:
        row.values["drive_folder_url"] = folder
    if warning:
        row.warnings.append(f"папка на Диске: {warning}")

    gpa, warning = parse_gpa(cell("gpa"))
    if gpa is not None:
        row.values["gpa"] = gpa
    if warning:
        row.warnings.append(warning)

    expires, warning = parse_expiry(cell("passport_expiry"))
    if expires is not None:
        row.values["passport_expires"] = expires
    if warning:
        row.warnings.append(warning)

    for column, doc_type in LINK_DOCUMENTS:
        url, warning = parse_link(cell(column))
        if url:
            row.links.append({"doc_type": doc_type, "url": url})
        if warning:
            row.warnings.append(f"{doc_type}: {warning}")

    for column, exam, slot in SCORE_COLUMNS:
        value, warning = parse_score(cell(column), exam)
        if value is not None:
            row.scores.append({"exam": exam, "slot": slot, "value": value})
        if warning:
            row.warnings.append(warning)

    row.passwords = {
        "email": bool(_text(cell("email_password"))),
        "common_app": bool(_text(cell("common_app_password"))),
    }
    row.values["_password_email"] = _text(cell("email_password"))
    row.values["_password_common_app"] = _text(cell("common_app_password"))


def preview_payload(sheets: list[Sheet]) -> dict:
    """Шаг «Проверка»: листы со строками и общие числа. Паролей здесь нет."""
    rows = [row for sheet in sheets for row in sheet.rows]
    return {
        "sheets": [sheet.as_dict() for sheet in sheets],
        "counts": {
            "sheets": len(sheets),
            "sheets_skipped": sum(1 for sheet in sheets if sheet.error),
            "rows": len(rows),
            "ready": sum(1 for row in rows if not row.error and not row.skip),
            "errors": sum(1 for row in rows if row.error and not row.skip),
            "warnings": sum(1 for row in rows if row.warnings),
            "skipped": sum(1 for row in rows if row.skip),
            "attempts": sum(len(row.scores) for row in rows if not row.error and not row.skip),
            "links": sum(len(row.links) for row in rows if not row.error and not row.skip),
            "passwords": sum(
                sum(1 for has in row.passwords.values() if has) for row in rows if not row.error and not row.skip
            ),
        },
    }


# --- Применение -----------------------------------------------------------


@transaction.atomic
def apply(uploaded, *, actor, fixes: dict[str, Fix] | None = None):
    """Записать разобранное одной транзакцией и вернуть отчёт-запись.

    Половина таблицы записанной хуже, чем отказ: строки с ошибками
    здесь уже исправлены или пропущены человеком, а сбой на середине
    откатывает всё.
    """
    from students.models import AdmissionImport

    sheets = parse(uploaded, fixes=fixes)
    today = timezone.localdate()
    report: list[str] = []
    students_updated = 0
    attempts = links = passwords = skipped = 0

    for sheet in sheets:
        if sheet.error:
            report.append(f"{sheet.name}\t—\t—\tлист\t{sheet.error}")
            continue
        for row in sheet.rows:
            if row.skip or row.error:
                skipped += 1
                reason = "пропущена человеком" if row.skip else row.error
                report.append(f"{sheet.name}\t{row.index}\t{row.raw_name}\tпропуск\t{reason}")
                continue
            outcome = _apply_row(row, actor=actor, today=today)
            students_updated += 1 if outcome["changed"] else 0
            attempts += outcome["attempts"]
            links += outcome["links"]
            passwords += outcome["passwords"]
            for warning in row.warnings:
                report.append(f"{sheet.name}\t{row.index}\t{row.student_name}\tвнимание\t{warning}")
            for note in outcome["notes"]:
                report.append(f"{sheet.name}\t{row.index}\t{row.student_name}\tвнимание\t{note}")

    record = AdmissionImport.objects.create(
        uploaded_by=actor if getattr(actor, "pk", None) else None,
        file_name=getattr(uploaded, "name", "") or "",
        sheets=len(sheets),
        students_updated=students_updated,
        attempts_created=attempts,
        documents_created=links,
        credentials_saved=passwords,
        rows_skipped=skipped,
        report="\n".join(report),
    )
    return record


def _apply_row(row: Row, *, actor, today: dt.date) -> dict:
    """Записать одну строку: профиль, GPA, пароли, документы-ссылки, попытки."""
    from core.audit import apply_changes
    from core.domains import Source
    from students.models import AdmissionProfile, ExamProfile, Student

    student = Student.objects.get(pk=row.student)
    notes: list[str] = []
    changed = False

    # почта из таблицы сверяется с реестром и не переписывает его: почта —
    # это вход ученика в систему, менять её импортом мы не станем
    table_email = row.values.get("email", "")
    if table_email and student.email and table_email.lower() != student.email.lower():
        notes.append(
            f"почта в таблице «{table_email}» не совпадает с почтой в системе «{student.email}» — "
            "оставлена системная"
        )
    elif table_email and not student.email:
        notes.append(f"в системе у ученика нет почты, в таблице «{table_email}» — заведите вход отдельно")

    profile, _ = AdmissionProfile.objects.get_or_create(student=student)
    admission_changes = {
        name: value
        for name, value in (
            ("student_phone", row.values.get("student_phone", "")),
            ("common_app_email", row.values.get("common_app_email", "")),
            ("drive_folder_url", row.values.get("drive_folder_url", "")),
        )
        # пустая ячейка ничего не стирает: в таблице пустота значит «не знаю»
        if value
    }
    # пароль или почта Common App в таблице значат, что аккаунт заведён:
    # признак читают готовность и дашборд Асем, руками его никто не ставит
    if (row.values.get("common_app_email") or row.passwords.get("common_app")) and not profile.has_common_app:
        admission_changes["has_common_app"] = True
    if admission_changes:
        changed |= bool(apply_changes(profile, admission_changes, actor=actor, source=Source.IMPORT))

    if row.values.get("gpa") is not None:
        exam_profile, _ = ExamProfile.objects.get_or_create(student=student)
        changed |= bool(apply_changes(exam_profile, {"gpa": row.values["gpa"]}, actor=actor, source=Source.IMPORT))

    passwords = _apply_passwords(row, student=student, actor=actor)
    links = _apply_links(row, student=student, actor=actor)
    attempts = _apply_scores(row, student=student, actor=actor, today=today)
    changed = changed or bool(passwords or links or attempts)
    return {"changed": changed, "attempts": attempts, "links": links, "passwords": passwords, "notes": notes}


def _apply_passwords(row: Row, *, student, actor) -> int:
    """Пароли — сразу в шифрованное хранилище, мимо любых ответов API."""
    from students import credentials

    saved = 0
    for kind, key in (("email", "_password_email"), ("common_app", "_password_common_app")):
        plaintext = row.values.get(key, "")
        if plaintext and credentials.set_credential(student, kind, plaintext, actor=actor):
            saved += 1
    return saved


def _apply_links(row: Row, *, student, actor) -> int:
    """Ссылки на паспорт, табель и рекомендацию — документами-ссылками.

    Тот же документ той же ссылкой второй раз не заводится: повторный
    запуск таблицы обновляет срок, а не плодит строки в чек-листе.
    """
    from core.audit import apply_changes
    from core.domains import Source
    from students import documents as documents_service
    from students.models import DocumentStatus, DocumentType, StudentDocument

    made = 0
    expires = row.values.get("passport_expires")
    for link in row.links:
        doc_type = link["doc_type"]
        existing = (
            StudentDocument.objects.filter(student=student, doc_type=doc_type)
            .exclude(external_url="")
            .order_by("created_at", "id")
            .last()
        )
        wanted = {"external_url": link["url"]}
        if doc_type == DocumentType.PASSPORT and expires is not None:
            wanted["expires_at"] = expires
        if existing is not None:
            apply_changes(existing, wanted, actor=actor, source=Source.IMPORT)
            continue
        document = StudentDocument.objects.create(
            student=student,
            doc_type=doc_type,
            title=f"{DocumentType(doc_type).label}: ссылка из таблицы поступления",
            external_url=link["url"],
            expires_at=wanted.get("expires_at"),
            uploaded_by=actor if getattr(actor, "pk", None) else None,
            status=DocumentStatus.PENDING,
        )
        # проверку документ-ссылка проходит ту же, что и файл (фаза 62)
        documents_service.submit(document, author=actor)
        made += 1
    return made


def _apply_scores(row: Row, *, student, actor, today: dt.date) -> int:
    """Баллы — официальными попытками с источником «импорт Асем».

    Даты в таблице нет: попытка получает дату загрузки и флаг «дата
    не указана», а карточка пишет «дата уточняется». Настоящую дату
    вносит ученик предложением — она флаг и снимет.

    Повторная загрузка не плодит попытки: место результата в таблице
    (IELTS-1, IELTS-2, …) — это и есть его номер, и та же клетка правит
    ту же попытку.
    """
    from core.audit import apply_changes
    from core.domains import Source
    from students.models import AttemptFormat, AttemptSource, ExamAttempt

    made = 0
    by_exam: dict[str, list] = {}
    for exam in ("IELTS", "SAT"):
        by_exam[exam] = list(
            ExamAttempt.objects.filter(student=student, exam_type=exam, source=AttemptSource.ADMISSION_IMPORT).order_by(
                "created_at", "id"
            )
        )
    for score in sorted(row.scores, key=lambda s: (s["exam"], s["slot"])):
        exam, slot, value = score["exam"], score["slot"], score["value"]
        existing = by_exam[exam]
        if slot <= len(existing):
            apply_changes(existing[slot - 1], {"total_score": value}, actor=actor, source=Source.IMPORT)
            continue
        attempt = ExamAttempt.objects.create(
            student=student,
            exam_type=exam,
            attempt_format=AttemptFormat.OFFICIAL,
            source=AttemptSource.ADMISSION_IMPORT,
            date=today,
            date_unknown=True,
            total_score=value,
        )
        existing.append(attempt)
        made += 1
    return made


def report_rows(record) -> list[dict]:
    """Отчёт строками для экрана и выгрузки."""
    out = []
    for line in (record.report or "").splitlines():
        parts = line.split("\t")
        while len(parts) < 5:
            parts.append("")
        out.append({"sheet": parts[0], "row": parts[1], "student": parts[2], "kind": parts[3], "text": parts[4]})
    return out


def record_payload(record) -> dict:
    """Отчёт о загрузке — то, что показывает последний шаг мастера."""
    return {
        "id": record.pk,
        "created_at": record.created_at,
        "file_name": record.file_name,
        "uploaded_by": ((record.uploaded_by.full_name or record.uploaded_by.email) if record.uploaded_by_id else ""),
        "sheets": record.sheets,
        "students_updated": record.students_updated,
        "attempts_created": record.attempts_created,
        "documents_created": record.documents_created,
        "credentials_saved": record.credentials_saved,
        "rows_skipped": record.rows_skipped,
        "rows": report_rows(record),
    }
