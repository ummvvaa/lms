"""Импорт соревнований файлом.

Отдельный путь от импорта доменных полей: там колонка правит одно поле
профиля, который у ученика один. Соревнований у ученика много, и строка
файла — это новая запись, а не правка существующей. Так же устроен
импорт контактов родителей (фаза 30).

Правила общие для всех загрузок: ученик ищется по почте, ненайденная
строка называется по номеру, кривая строка не отменяет остальные,
повторная загрузка того же файла не плодит дублей, а откат убирает
заведённое в архив.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from core.domains import Source
from directories.models import SportType
from students.models import Competition, SportLevel, Student

#: Как эти колонки называют в школьных списках. Сравнение по вхождению
#: и без регистра.
COLUMNS: dict[str, tuple[str, ...]] = {
    "student": ("почта ученика", "email ученика", "ученик", "student", "участник"),
    "name": ("соревнование", "название", "турнир", "старт", "competition"),
    "sport_type": ("вид спорта", "спорт", "sport"),
    "level": ("уровень", "level", "масштаб"),
    "date": ("дата", "когда", "date"),
    "result": ("результат", "место", "result"),
    "has_certificate": ("сертификат", "диплом", "грамота"),
    "proof_url": ("ссылка", "подтверждение", "url"),
}

REQUIRED = ("student", "name")

TITLES = {
    "student": "почта ученика",
    "name": "название соревнования",
    "sport_type": "вид спорта",
    "level": "уровень",
    "date": "дата",
    "result": "результат",
    "has_certificate": "сертификат",
    "proof_url": "ссылка",
}

#: Как в файле пишут уровень.
LEVEL_WORDS: dict[str, tuple[str, ...]] = {
    SportLevel.SCHOOL: ("школ",),
    SportLevel.CITY: ("город", "район"),
    SportLevel.REGIONAL: ("област", "регион", "край"),
    SportLevel.NATIONAL: ("республик", "国", "нацио", "страна", "казахстан"),
    SportLevel.INTERNATIONAL: ("междунар", "интернацио", "мир", "world"),
}

TRUE_WORDS = {"да", "yes", "true", "1", "+", "есть"}


def _level_of(value: str) -> str:
    low = (value or "").strip().lower()
    for code, words in LEVEL_WORDS.items():
        if any(word in low for word in words):
            return code
    return ""


@dataclass
class Row:
    """Одна строка файла после разбора."""

    number: int
    student_email: str = ""
    student_id: int | None = None
    student_name: str = ""
    name: str = ""
    sport_type_id: int | None = None
    sport_type_name: str = ""
    level: str = ""
    date: str = ""
    result: str = ""
    has_certificate: bool = False
    proof_url: str = ""
    #: new | exists | error
    status: str = "new"
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "student": self.student_id,
            "student_email": self.student_email,
            "student_name": self.student_name,
            "name": self.name,
            "sport_type": self.sport_type_id,
            "sport_type_name": self.sport_type_name,
            "level": self.level,
            "date": self.date,
            "result": self.result,
            "has_certificate": self.has_certificate,
            "proof_url": self.proof_url,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class Preview:
    """Что произойдёт при применении файла."""

    columns: dict[str, str] = field(default_factory=dict)
    rows: list[Row] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)

    @property
    def ready(self) -> list[Row]:
        return [row for row in self.rows if row.status == "new"]

    def as_dict(self) -> dict[str, Any]:
        exists = sum(1 for row in self.rows if row.status == "exists")
        broken = sum(1 for row in self.rows if row.status == "error")
        return {
            "columns": self.columns,
            "missing_columns": self.missing_columns,
            "total": len(self.rows),
            "will_create": len(self.ready),
            "already_exist": exists,
            "with_errors": broken,
            "rows": [row.as_dict() for row in self.rows],
            "detail": self.detail(),
        }

    def detail(self) -> str:
        if self.missing_columns:
            names = ", ".join(self.missing_columns)
            return f"В файле не нашлись обязательные колонки: {names}. Проверьте заголовок первой строки"
        exists = sum(1 for row in self.rows if row.status == "exists")
        broken = sum(1 for row in self.rows if row.status == "error")
        parts = [f"строк в файле: {len(self.rows)}", f"будет заведено выступлений: {len(self.ready)}"]
        if exists:
            parts.append(f"уже есть: {exists}")
        if broken:
            parts.append(f"с ошибками: {broken}")
        return ", ".join(parts).capitalize()


def _find_columns(header: list[str]) -> dict[str, int]:
    """Сопоставить колонки файла полям; занятая колонка второй раз не берётся."""
    found: dict[str, int] = {}
    for name in ("student", "name", "sport_type", "level", "date", "result", "has_certificate", "proof_url"):
        for index, title in enumerate(header):
            low = (title or "").strip().lower()
            if not low or index in found.values():
                continue
            if any(hint in low for hint in COLUMNS[name]):
                found[name] = index
                break
    return found


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return (row[index] or "").strip()


def build_preview(*, header: list[str], rows: list[list[str]]) -> Preview:
    """Разобрать файл соревнований и сказать, что произойдёт."""
    columns = _find_columns(header)
    missing = [name for name in REQUIRED if name not in columns]
    preview = Preview(
        columns={name: header[index] for name, index in columns.items()},
        missing_columns=[TITLES[name] for name in missing],
    )
    if missing:
        return preview

    students = {
        email.lower(): (pk, f"{last} {first}".strip())
        for pk, email, last, first in Student.objects.values_list("pk", "email", "last_name", "first_name")
    }
    sports = {row.name.strip().lower(): row for row in SportType.objects.all()}

    for number, raw in enumerate(rows, start=2):  # 1 — заголовок
        row = Row(
            number=number,
            student_email=_cell(raw, columns.get("student")).lower(),
            name=_cell(raw, columns.get("name")),
            level=_level_of(_cell(raw, columns.get("level"))),
            date=_cell(raw, columns.get("date")),
            result=_cell(raw, columns.get("result")),
            has_certificate=_cell(raw, columns.get("has_certificate")).lower() in TRUE_WORDS,
            proof_url=_cell(raw, columns.get("proof_url")),
        )
        if not any([row.student_email, row.name, row.result]):
            continue  # пустой хвост файла — не ошибка

        sport_text = _cell(raw, columns.get("sport_type"))
        found = students.get(row.student_email)
        if found is None:
            row.status = "error"
            row.reason = f"ученика с почтой «{row.student_email or 'пусто'}» в базе нет"
        elif not row.name:
            row.status, row.reason = "error", "не указано название соревнования"
        else:
            row.student_id, row.student_name = found
            if sport_text:
                # справочник импорт не пополняет: опечатка завела бы
                # четвёртый «футбол» и справочник перестал бы им быть
                sport = sports.get(sport_text.strip().lower())
                if sport is None:
                    row.status = "error"
                    row.reason = f"вида спорта «{sport_text}» нет в справочнике — заведите его или поправьте файл"
                else:
                    row.sport_type_id, row.sport_type_name = sport.pk, sport.name
            if row.status == "new" and _already_there(row):
                row.status, row.reason = "exists", "это выступление уже записано"

        preview.rows.append(row)

    return preview


def _already_there(row: Row) -> bool:
    """Выступление узнаётся по паре «ученик + название + дата»."""
    query = Competition.all_objects.filter(student_id=row.student_id, name__iexact=row.name.strip())
    if row.date:
        query = query.filter(date=row.date)
    return query.exists()


@transaction.atomic
def apply_rows(*, rows: list[dict[str, Any]], actor=None, file_name: str = "") -> dict[str, Any]:
    """Завести выступления из проверенных строк."""
    from core.audit import apply_changes
    from core.models import ImportBatch

    batch = ImportBatch.objects.create(
        actor=actor,
        file_name=file_name,
        kind=ImportBatch.Kind.STUDENTS,
        domain_code="sport",
        rows_total=len(rows),
    )

    created = 0
    skipped: list[dict[str, Any]] = []
    for raw in rows:
        student = Student.objects.filter(pk=raw.get("student")).first()
        name = (raw.get("name") or "").strip()
        if student is None or not name:
            skipped.append({"row": raw.get("number"), "reason": "нет ученика или названия"})
            continue

        competition = Competition(student=student)
        apply_changes(
            competition,
            {
                "name": name,
                "sport_type": SportType.objects.filter(pk=raw.get("sport_type")).first(),
                "level": raw.get("level") or "",
                "date": raw.get("date") or None,
                "result": (raw.get("result") or "").strip(),
                "has_certificate": bool(raw.get("has_certificate")),
                "proof_url": (raw.get("proof_url") or "").strip(),
            },
            actor=actor,
            source=Source.IMPORT,
            import_batch=batch,
        )
        created += 1

    batch.rows_created = created
    batch.rows_failed = len(skipped)
    batch.note = "Отмена загрузки уберёт заведённые выступления"
    batch.save(update_fields=["rows_created", "rows_failed", "note"])

    return {
        "created": created,
        "skipped": skipped,
        "batch": batch.pk,
        "detail": f"Заведено выступлений: {created}" + (f", пропущено строк: {len(skipped)}" if skipped else ""),
    }
