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
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, gettext_noop

from core.domains import Source
from directories.models import SportType
from students.import_registry import header_variants
from students.lookup import key_map
from students.models import Competition, SportLevel, Student

#: Как эти колонки называют в школьных списках. Сравнение по вхождению
#: и без регистра.
COLUMNS: dict[str, tuple[str, ...]] = {  # i18n-skip: синонимы заголовков для распознавания
    "student": ("почта ученика", "email ученика", "логин", "ученик", "student", "участник"),
    "name": ("соревнование", "название", "турнир", "старт", "competition"),
    "sport_type": ("вид спорта", "спорт", "sport"),
    "level": ("уровень", "level", "масштаб"),
    "date": ("дата", "когда", "date"),
    "result": ("результат", "место", "result"),
    "has_certificate": ("сертификат", "диплом", "грамота"),
    "proof_url": ("ссылка", "подтверждение", "url"),
}

REQUIRED = ("student", "name")

#: Подписи колонок для отказа; заголовок, записанный подписью на любом
#: из трёх языков, тоже узнаётся (`header_variants`)
TITLES = {
    "student": gettext_lazy("почта ученика"),
    "name": gettext_lazy("название соревнования"),
    "sport_type": gettext_lazy("вид спорта"),
    "level": gettext_lazy("уровень"),
    "date": gettext_lazy("дата"),
    "result": gettext_lazy("результат"),
    "has_certificate": gettext_lazy("сертификат"),
    "proof_url": gettext_lazy("ссылка"),
}

#: Как в файле пишут уровень.
LEVEL_WORDS: dict[str, tuple[str, ...]] = {  # i18n-skip: слова из файла для распознавания
    SportLevel.SCHOOL: ("школ",),
    SportLevel.CITY: ("город", "район"),
    SportLevel.REGIONAL: ("област", "регион", "край"),
    SportLevel.NATIONAL: ("республик", "国", "нацио", "страна", "казахстан"),
    SportLevel.INTERNATIONAL: ("междунар", "интернацио", "мир", "world"),
}

TRUE_WORDS = {"да", "yes", "true", "1", "+", "есть"}  # i18n-skip: значения ячейки для распознавания


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
            return _("В файле не нашлись обязательные колонки: {columns}. Проверьте заголовок первой строки").format(
                columns=names
            )
        exists = sum(1 for row in self.rows if row.status == "exists")
        broken = sum(1 for row in self.rows if row.status == "error")
        parts = [
            _("строк в файле: {count}").format(count=len(self.rows)),
            _("будет заведено выступлений: {count}").format(count=len(self.ready)),
        ]
        if exists:
            parts.append(_("уже есть: {count}").format(count=exists))
        if broken:
            parts.append(_("с ошибками: {count}").format(count=broken))
        return ", ".join(parts).capitalize()


def _find_columns(header: list[str]) -> dict[str, int]:
    """Сопоставить колонки файла полям; занятая колонка второй раз не берётся."""
    found: dict[str, int] = {}
    for name in ("student", "name", "sport_type", "level", "date", "result", "has_certificate", "proof_url"):
        hints = (*COLUMNS[name], *sorted(header_variants(TITLES[name])))
        for index, title in enumerate(header):
            low = (title or "").strip().lower()
            if not low or index in found.values():
                continue
            if any(hint in low for hint in hints):
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
        missing_columns=[str(TITLES[name]) for name in missing],
    )
    if missing:
        return preview

    # почта или логин: у 8–10 почты нет (`students.lookup`)
    students = key_map()
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
            row.reason = _("ученика с почтой или логином «{key}» в базе нет").format(
                key=row.student_email or _("пусто")
            )
        elif not row.name:
            row.status, row.reason = "error", _("не указано название соревнования")
        else:
            row.student_id, row.student_name = found
            if sport_text:
                # справочник импорт не пополняет: опечатка завела бы
                # четвёртый «футбол» и справочник перестал бы им быть
                sport = sports.get(sport_text.strip().lower())
                if sport is None:
                    row.status = "error"
                    row.reason = _("вида спорта «{sport}» нет в справочнике — заведите его или поправьте файл").format(
                        sport=sport_text
                    )
                else:
                    row.sport_type_id, row.sport_type_name = sport.pk, sport.name
            if row.status == "new" and _already_there(row):
                row.status, row.reason = "exists", _("это выступление уже записано")

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
        kind=ImportBatch.Kind.COMPETITIONS,
        domain_code="sport",
        rows_total=len(rows),
    )

    created = 0
    skipped: list[dict[str, Any]] = []
    for raw in rows:
        student = Student.objects.filter(pk=raw.get("student")).first()
        name = (raw.get("name") or "").strip()
        if student is None or not name:
            skipped.append({"row": raw.get("number"), "reason": _("нет ученика или названия")})
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
    batch.note = gettext_noop("Отмена загрузки уберёт заведённые выступления")  # хранится исходником
    batch.save(update_fields=["rows_created", "rows_failed", "note"])

    return {
        "created": created,
        "skipped": skipped,
        "batch": batch.pk,
        "detail": (
            _("Заведено выступлений: {created}, пропущено строк: {skipped}").format(
                created=created, skipped=len(skipped)
            )
            if skipped
            else _("Заведено выступлений: {created}").format(created=created)
        ),
    }
