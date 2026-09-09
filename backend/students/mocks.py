"""Пробники файлом: разбор таблицы учителя, проверка строк, применение.

Пробник проводит учитель. Учётной записи у него нет и не будет — он
присылает таблицу, а куратор группы или академический директор загружает
её сюда. Результаты ложатся сразу подтверждёнными: подтверждать нечего,
проверял их учитель, а не ученик о себе рассказал.

Разбор и применение — на сервере, и это два разных запроса одного и того
же файла. Шаг «Проверка» ничего не пишет в базу: он только читает файл
и называет каждую кривую строку по номеру. Шаг «Применить» читает файл
заново и накладывает поверх разбора правки человека — какому ученику
отнести строку, какой балл поставить вместо кривого, какую строку
пропустить. Так между шагами нечему разъехаться: применяется тот же
файл, а не то, что прислал браузер.

Ошибки строк называются по-русски и всегда с подсказкой, что делать:
строка с ошибкой не отменяет файл, но и не применяется молча — человек
либо исправляет её, либо пропускает, и пропуск попадает в отчёт загрузки.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from core.domains import scale_of
from students.models import (
    IELTS_SECTIONS,
    AttemptFormat,
    AttemptSource,
    ExamAttempt,
    ExamType,
    MockImport,
    Student,
)

#: Экзамены, которые школа проводит пробниками. Скрытые (TOEFL, ACT,
#: Duolingo, HSK) сюда не попадают: мастер предлагает только эти два.
MOCK_EXAMS: tuple[str, ...] = (ExamType.IELTS, ExamType.SAT)

#: Как учитель называет колонку с учеником.
NAME_HINTS = ("фио", "ученик", "имя", "фамилия", "student", "name")

#: Как называют колонку с общим баллом.
SCORE_HINTS = ("балл", "итог", "общий", "overall", "total", "score", "band")

#: Названия секций: по-русски и по-английски, как в бланке.
SECTION_HINTS: dict[str, tuple[str, ...]] = {
    "listening": ("listening", "аудирование", "listen"),
    "reading": ("reading", "чтение", "read"),
    "writing": ("writing", "письмо", "write"),
    "speaking": ("speaking", "говорение", "speak"),
}

NOTE_HINTS = ("примечание", "коммент", "note", "comment")

#: Ошибки строки. Ключ уходит на фронт, подпись — человеку.
ERROR_TITLES: dict[str, str] = {
    "no_name": "В строке нет ФИО",
    "not_found": "Ученик не найден в этой группе",
    "ambiguous": "Похожих учеников несколько",
    "no_score": "Нет общего балла",
    "score_range": "Балл вне шкалы",
    "sections_missing": "Заполнены не все секции",
    "sections_range": "Секция вне шкалы",
    "sections_mismatch": "Секции не сходятся с общим баллом",
    "duplicate": "Ученик встречается в файле дважды",
    "already": "У ученика уже есть пробник на эту дату",
}

#: Что человеку делать с этой ошибкой: выбрать ученика или ввести балл.
FIX_KIND: dict[str, str] = {
    "no_name": "student",
    "not_found": "student",
    "ambiguous": "student",
    "no_score": "score",
    "score_range": "score",
    "sections_missing": "skip",
    "sections_range": "score",
    "sections_mismatch": "score",
    "duplicate": "skip",
    "already": "skip",
}


def scale_hint(exam_type: str) -> str:
    """Шкала словами — её показывают там, где балл не подошёл."""
    scale = scale_of(exam_type)
    return f"{exam_type}: {scale.hint}" if scale else exam_type


def in_scale(value: Decimal, exam_type: str) -> bool:
    """Общий балл по шкале экзамена из реестра (D4)."""
    scale = scale_of(exam_type)
    return scale.holds(value) if scale else True


def section_ok(value: Decimal, exam_type: str = ExamType.IELTS) -> bool:
    """Секция по шкале экзамена из реестра: у IELTS 0–9 с шагом 0.5."""
    scale = scale_of(exam_type, section=True)
    return scale.holds(value) if scale else True


def band_of(sections: dict[str, Decimal]) -> Decimal:
    """Общий балл IELTS — среднее четырёх секций, округлённое до 0.5.

    Округление банковское наполовину вверх, как в бланке: 6.25 → 6.5,
    6.125 → 6.0. Питоновский `round` половину округляет к чётному
    и здесь соврал бы на каждом четвёртом ученике.
    """
    total = sum(sections[name] for name in IELTS_SECTIONS)
    doubled = (total / Decimal(4)) * 2
    floor = int(doubled)
    rest = doubled - floor
    if rest >= Decimal("0.5"):
        floor += 1
    return Decimal(floor) / 2


def _clean(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _number(raw: str) -> Decimal | None:
    """Число из ячейки. Запятая как разделитель — обычное дело в таблицах."""
    text = _clean(raw).replace(",", ".").replace(" ", "").replace(" ", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _match_column(title: str, hints: tuple[str, ...]) -> bool:
    low = _clean(title).lower()
    return any(hint in low for hint in hints)


@dataclass
class Columns:
    """Какие колонки нашлись в файле учителя."""

    name: int = -1
    score: int = -1
    note: int = -1
    sections: dict[str, int] = field(default_factory=dict)

    @property
    def found_sections(self) -> bool:
        return all(name in self.sections for name in IELTS_SECTIONS)


def read_columns(header: list[str]) -> Columns:
    """Сопоставить заголовки файла с колонками, которые нам нужны.

    Порядок колонок учителю не задаём: таблицы приходят разные, и требовать
    от него точного порядка — верный способ получить файл не в том порядке.
    """
    columns = Columns()
    for index, title in enumerate(header):
        if columns.name < 0 and _match_column(title, NAME_HINTS):
            columns.name = index
            continue
        matched_section = next(
            (name for name, hints in SECTION_HINTS.items() if _match_column(title, hints)),
            None,
        )
        if matched_section and matched_section not in columns.sections:
            columns.sections[matched_section] = index
            continue
        if columns.score < 0 and _match_column(title, SCORE_HINTS):
            columns.score = index
            continue
        if columns.note < 0 and _match_column(title, NOTE_HINTS):
            columns.note = index
    return columns


class FileRejected(ValueError):
    """Файл нельзя разбирать вовсе — дело не в отдельной строке."""


@dataclass
class Row:
    """Одна строка файла после разбора."""

    index: int
    raw_name: str
    student: int | None = None
    student_name: str = ""
    candidates: list[dict] = field(default_factory=list)
    total: Decimal | None = None
    sections: dict[str, Decimal] = field(default_factory=dict)
    note: str = ""
    error: str = ""
    skip: bool = False

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "raw_name": self.raw_name,
            "student": self.student,
            "student_name": self.student_name,
            "candidates": self.candidates,
            "total": float(self.total) if self.total is not None else None,
            "sections": {name: float(value) for name, value in self.sections.items()},
            "note": self.note,
            "error": self.error,
            "error_title": ERROR_TITLES.get(self.error, ""),
            "fix": FIX_KIND.get(self.error, ""),
            "skip": self.skip,
        }


@dataclass
class Fix:
    """Правка человека по строке: кому отнести, какой балл, пропустить ли."""

    index: int
    student: int | None = None
    total: Decimal | None = None
    sections: dict[str, Decimal] = field(default_factory=dict)
    skip: bool = False


def parse(
    uploaded,
    *,
    exam_type: str,
    group,
    date: dt.date,
    fixes: dict[int, Fix] | None = None,
) -> list[Row]:
    """Прочитать файл и разобрать строки под выбранный экзамен и группу.

    Ученик ищется только среди своей группы: однофамилец из соседнего
    класса не должен получить чужой балл, даже если похож больше.
    """
    from students.import_service import read_table
    from suggestions.name_matching import find

    fixes = fixes or {}
    header, body = read_table(uploaded)
    if not header:
        raise FileRejected("Файл пустой — в нём нет ни заголовка, ни строк")

    columns = read_columns(header)
    if columns.name < 0:
        raise FileRejected("Не нашлась колонка с ФИО — назовите её «ФИО» или «Ученик»")
    if columns.score < 0 and not (exam_type == ExamType.IELTS and columns.found_sections):
        raise FileRejected("Не нашлась колонка с баллом — назовите её «Балл»")
    if exam_type == ExamType.IELTS and not columns.found_sections:
        missing = [name for name in IELTS_SECTIONS if name not in columns.sections]
        raise FileRejected("Для IELTS нужны все четыре секции, а в файле нет: " + ", ".join(missing).title())

    students = list(Student.objects.filter(group=group, is_active=True).select_related("group"))
    taken = set(
        ExamAttempt.objects.filter(
            student__in=students,
            exam_type=exam_type,
            attempt_format=AttemptFormat.MOCK,
            date=date,
        ).values_list("student_id", flat=True)
    )

    rows: list[Row] = []
    seen: dict[int, int] = {}
    for number, raw in enumerate(body, start=1):

        def cell(i: int, line: list = raw) -> str:
            """Ячейка строки по номеру колонки; за краем — пусто."""
            return _clean(line[i]) if 0 <= i < len(line) else ""

        row = Row(index=number, raw_name=cell(columns.name), note=cell(columns.note))
        fix = fixes.get(number)
        if fix and fix.skip:
            row.skip = True

        _resolve_student(row, students=students, fix=fix, finder=find)
        _resolve_scores(row, exam_type=exam_type, columns=columns, cell=cell, fix=fix)

        # дубль и уже загруженный пробник — свойства строки, а не её баллов:
        # проверяем их даже там, где балл не сошёлся, иначе вторая строка
        # того же ученика проскочит как чистая
        if row.student is not None:
            if row.student in seen:
                row.error = "duplicate"
            else:
                seen[row.student] = number
                if row.student in taken and not row.error:
                    row.error = "already"
        rows.append(row)

    # строка целиком пустая — не ошибка, а хвост таблицы: его учитель
    # не заполнял, и ругаться на него незачем
    return [row for row in rows if row.raw_name or row.total is not None or row.sections]


def _resolve_student(row: Row, *, students: list, fix: Fix | None, finder) -> None:
    """Найти ученика строки: правкой человека или нечётким сравнением ФИО."""
    if fix and fix.student:
        chosen = next((s for s in students if s.pk == fix.student), None)
        if chosen is not None:
            row.student, row.student_name = chosen.pk, chosen.full_name
            return
    if not row.raw_name:
        row.error = "no_name"
        return
    outcome = finder(row.raw_name, students=students)
    row.candidates = [c.as_dict() for c in outcome.candidates]
    if outcome.is_confident and outcome.best:
        row.student, row.student_name = outcome.best.student_id, outcome.best.full_name
        return
    row.error = "ambiguous" if outcome.is_ambiguous else "not_found"


def _resolve_scores(row: Row, *, exam_type: str, columns: Columns, cell, fix: Fix | None) -> None:
    """Разобрать секции и общий балл, наложив правку человека."""
    if exam_type == ExamType.IELTS:
        for name in IELTS_SECTIONS:
            # ноль — законный балл, поэтому проверяем на None, а не на «пусто»:
            # с `or` исправленный нулём балл молча вернулся бы к файлу
            fixed = fix.sections.get(name) if fix else None
            value = fixed if fixed is not None else _number(cell(columns.sections[name]))
            if value is not None:
                row.sections[name] = value

    row.total = fix.total if fix and fix.total is not None else _number(cell(columns.score))

    if row.error:
        return
    if exam_type == ExamType.IELTS:
        if len(row.sections) < len(IELTS_SECTIONS):
            row.error = "sections_missing"
            return
        if any(not section_ok(value) for value in row.sections.values()):
            row.error = "sections_range"
            return
        expected = band_of(row.sections)
        if row.total is None:
            # балла в файле нет, а секции есть — считаем сами, это не ошибка
            row.total = expected
        elif row.total != expected:
            row.error = "sections_mismatch"
            return
    if row.total is None:
        row.error = "no_score"
        return
    if not in_scale(row.total, exam_type):
        row.error = "score_range"


def counts(rows: list[Row]) -> dict[str, int]:
    """Сводка разбора: сколько готово, сколько с ошибкой, сколько пропущено."""
    ready = [r for r in rows if not r.error and not r.skip]
    broken = [r for r in rows if r.error and not r.skip]
    return {
        "total": len(rows),
        "ready": len(ready),
        "broken": len(broken),
        "skipped": len([r for r in rows if r.skip]),
    }


def preview_payload(rows: list[Row], *, exam_type: str, group) -> dict:
    """Что показывает шаг «Проверка»."""
    numbers = counts(rows)
    return {
        "exam_type": exam_type,
        "group": group.code,
        "scale": scale_hint(exam_type),
        "sections": list(IELTS_SECTIONS) if exam_type == ExamType.IELTS else [],
        "rows": [row.as_dict() for row in rows],
        "counts": numbers,
        # применять нечего, если каждая строка либо пропущена, либо кривая
        "can_apply": numbers["broken"] == 0 and numbers["ready"] > 0,
        "students": [
            {"id": s.pk, "full_name": s.full_name}
            for s in Student.objects.filter(group=group, is_active=True).order_by("last_name", "first_name")
        ],
    }


def duplicate_of(*, exam_type: str, group, date: dt.date) -> MockImport | None:
    """Уже загруженный пробник того же экзамена в ту же группу на ту же дату."""
    return MockImport.objects.filter(exam_type=exam_type, group=group, date=date).first()


@transaction.atomic
def apply(
    uploaded,
    *,
    exam_type: str,
    group,
    date: dt.date,
    teacher: str,
    actor,
    fixes: dict[int, Fix] | None = None,
) -> MockImport:
    """Записать разобранные строки одной транзакцией.

    Кривая строка здесь уже невозможна: до применения их либо исправили,
    либо пропустили. Если что-то всё-таки не сошлось — не применяется
    ничего: половина класса с баллами, а половина без, хуже, чем отказ.
    """
    rows = parse(uploaded, exam_type=exam_type, group=group, date=date, fixes=fixes)
    broken = [row for row in rows if row.error and not row.skip]
    if broken:
        raise FileRejected("В файле остались строки с ошибками: " + ", ".join(f"№{row.index}" for row in broken))
    ready = [row for row in rows if not row.skip and not row.error]
    if not ready:
        raise FileRejected("Записывать нечего: все строки пропущены")

    uploaded.seek(0)
    skipped = [row for row in rows if row.skip]
    record = MockImport.objects.create(
        exam_type=exam_type,
        group=group,
        date=date,
        teacher=teacher,
        file=uploaded,
        file_name=getattr(uploaded, "name", "") or "",
        uploaded_by=actor if getattr(actor, "pk", None) else None,
        rows_total=len(rows),
        rows_applied=len(ready),
        rows_skipped=len(skipped),
        skipped_report="\n".join(
            f"№{row.index} · {row.raw_name or 'без ФИО'} · {ERROR_TITLES.get(row.error, 'пропущено человеком')}"
            for row in skipped
        ),
    )

    for row in ready:
        attempt = ExamAttempt(
            student_id=row.student,
            exam_type=exam_type,
            attempt_format=AttemptFormat.MOCK,
            source=AttemptSource.IMPORT,
            date=date,
            total_score=row.total,
            mock_import=record,
        )
        for name, value in row.sections.items():
            setattr(attempt, name, value)
        attempt.save()

    _record_journal(record, actor=actor)
    return record


def _record_journal(record: MockImport, *, actor) -> None:
    """Загрузка видна в журнале куратора — по строке на каждого ученика.

    Пробник не правит доменное поле, поэтому обычной записи журнала
    у него бы не было; событие пишется тем же способом, что звонок
    родителям и передача владельцу (фаза 62).
    """
    from core.audit import record_event

    text = f"{record.exam_type} · {record.date:%d.%m.%Y}" + (f" · учитель {record.teacher}" if record.teacher else "")
    for attempt in record.attempts.select_related("student"):
        record_event(student=attempt.student, code="mock_import", text=text, actor=actor)


# --- Результаты загрузки -----------------------------------------------------------


def results(record: MockImport) -> dict:
    """Страница результатов: кто сдавал, кто нет, средний по группе.

    Средний по группе считается здесь и уходит только сотруднику: ученику
    его не показывают ни на одном экране и ни в одном ответе — сравнений
    между детьми у нас нет.
    """
    from students.models import ExamGoal

    students = list(Student.objects.filter(group=record.group, is_active=True).order_by("last_name", "first_name"))
    # `all_objects`: у загрузки в архиве попытки тоже архивные, но страница
    # обязана показывать, что в ней было — иначе перед возвратом из архива
    # человек видит пустую таблицу и не понимает, что возвращает
    attempts = {row.student_id: row for row in ExamAttempt.all_objects.filter(mock_import=record)}
    # цель — запись справочника, а не строка: экзамен ищется по названию,
    # как в подборе вузов и в центре подготовки
    goals = {
        row.student_id: row.target_score
        for row in ExamGoal.objects.filter(
            student__in=students, exam__name__iexact=record.exam_type, target_score__isnull=False
        )
    }

    rows = []
    for student in students:
        attempt = attempts.get(student.pk)
        target = goals.get(student.pk)
        score = float(attempt.total_score) if attempt and attempt.total_score is not None else None
        rows.append(
            {
                "student": student.pk,
                "full_name": student.full_name,
                "total": score,
                "sections": (
                    {
                        name: float(getattr(attempt, name)) if attempt and getattr(attempt, name) is not None else None
                        for name in IELTS_SECTIONS
                    }
                    if record.exam_type == ExamType.IELTS
                    else {}
                ),
                "target": float(target) if target is not None else None,
                "below_target": bool(score is not None and target is not None and score < float(target)),
                "took": attempt is not None,
            }
        )

    scored = [row["total"] for row in rows if row["total"] is not None]
    average = round(sum(scored) / len(scored), 1) if scored else None
    return {
        **short(record),
        "average": average,
        "took": len(scored),
        "missed": len(rows) - len(scored),
        "sections": list(IELTS_SECTIONS) if record.exam_type == ExamType.IELTS else [],
        "results": rows,
        "skipped_report": [line for line in record.skipped_report.splitlines() if line.strip()],
    }


def short(record: MockImport) -> dict:
    """Строка списка «Пробники»."""
    return {
        "id": record.pk,
        "exam_type": record.exam_type,
        "group": record.group.code,
        "group_id": record.group_id,
        "date": record.date,
        "teacher": record.teacher,
        "file_name": record.file_name,
        "uploaded_by": (record.uploaded_by.full_name or record.uploaded_by.email) if record.uploaded_by_id else "",
        "created_at": record.created_at,
        "students": ExamAttempt.all_objects.filter(mock_import=record).count(),
        "rows_total": record.rows_total,
        "rows_skipped": record.rows_skipped,
        "status": record.status,
        "status_title": record.status_title,
    }


def remind(record: MockImport, *, actor, days: int = 7) -> list[int]:
    """Задача тем, кто пробник не сдавал: «Сдать пробник IELTS»."""
    from django.utils import timezone

    from roadmap.models import TaskCategory
    from roadmap.services import assign_to_students

    took = set(ExamAttempt.all_objects.filter(mock_import=record).values_list("student_id", flat=True))
    missing = [
        student for student in Student.objects.filter(group=record.group, is_active=True) if student.pk not in took
    ]
    if not missing:
        return []
    assign_to_students(
        missing,
        title=f"Сдать пробник {record.exam_type}",
        due_date=timezone.localdate() + dt.timedelta(days=days),
        category=TaskCategory.TEST,
        actor=actor,
    )
    return [student.pk for student in missing]


# --- Шаблон файла ------------------------------------------------------------------


def template_columns(exam_type: str) -> list[str]:
    """Заголовок шаблона под выбранный экзамен."""
    if exam_type == ExamType.IELTS:
        return ["ФИО", "Listening", "Reading", "Writing", "Speaking", "Балл", "Примечание"]
    return ["ФИО", "Балл", "Примечание"]


def template_rows(exam_type: str, students) -> list[list[Any]]:
    """Строки шаблона: ФИО учеников группы, баллы учитель проставит сам."""
    width = len(template_columns(exam_type)) - 1
    return [[student.full_name, *([""] * width)] for student in students]
