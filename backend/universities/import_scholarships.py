"""Загрузка стипендий файлом — у администратора, за домен «Поступление».

Порядок тот же, что у требований вузов: файл → сопоставление колонок →
пробный прогон (в базу ничего не пишется) → применение. Ключ строки —
название и организатор: список стипендий присылают дважды всегда, и второй
раз он не должен заводить дубли.

Записи приходят с плашкой «не подтверждено» (инвариант №14): проверяет их
директор по поступлению по официальной странице.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from core.labels import field_title
from universities.models import CatalogSource, FundingType, ProgramLevel, Scholarship, University

#: Поля стипендии, доступные для сопоставления. Подписи — из реестра доменов
#: (инвариант №2): колонка в файле и колонка в таблице называются одинаково.
SCHOLARSHIP_FIELDS = (
    "name",
    "organizer",
    "country",
    "level",
    "funding_type",
    "amount_min",
    "amount_max",
    "currency",
    "for_international",
    "for_merit",
    "for_need",
    "deadline",
    "url",
    "requirements",
    "description",
)

TARGET_FIELDS: dict[str, str] = {
    **{name: field_title("universities.Scholarship", name) for name in SCHOLARSHIP_FIELDS},
    "university": field_title("universities.University", "name"),
}

DECIMAL_FIELDS = {"amount_min", "amount_max"}
BOOL_FIELDS = {"for_international", "for_merit", "for_need"}
DATE_FIELDS = {"deadline"}
TRUE_WORDS = {"1", "true", "yes", "да", "y", "+", "есть", "нужно"}

#: Как в файле называют тип финансирования. Слова, а не коды: выгрузку
#: собирает человек, и «полное» он напишет по-русски.
FUNDING_WORDS = {
    "full": FundingType.FULL,
    "полное": FundingType.FULL,
    "полностью": FundingType.FULL,
    "partial": FundingType.PARTIAL,
    "частичное": FundingType.PARTIAL,
    "tuition": FundingType.TUITION,
    "обучение": FundingType.TUITION,
    "только обучение": FundingType.TUITION,
}

LEVEL_WORDS = {
    "bachelor": ProgramLevel.BACHELOR,
    "бакалавриат": ProgramLevel.BACHELOR,
    "master": ProgramLevel.MASTER,
    "магистратура": ProgramLevel.MASTER,
    "foundation": ProgramLevel.FOUNDATION,
}

DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y")


@dataclass
class ScholarshipImportReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "errors": self.errors,
            "rows": self.rows[:30],
        }


def _coerce(name: str, raw: str) -> Any:
    """Значение клетки под колонку. Непонятное отклоняет строку словами."""
    raw = (raw or "").strip()
    title = TARGET_FIELDS.get(name, name)
    if name in BOOL_FIELDS:
        return raw.lower() in TRUE_WORDS
    if raw == "":
        return None
    if name in DECIMAL_FIELDS:
        cleaned = raw.replace(" ", "").replace(" ", "").replace(",", ".")
        for sign in ("$", "€", "₸", "£"):
            cleaned = cleaned.replace(sign, "")
        try:
            return Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"«{title}»: ожидалась сумма, получено «{raw}»") from exc
    if name in DATE_FIELDS:
        for fmt in DATE_FORMATS:
            try:
                return dt.datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"«{title}»: непонятная дата «{raw}», ждём 2026-05-01 или 01.05.2026")
    if name == "funding_type":
        value = FUNDING_WORDS.get(raw.lower())
        if value is None:
            raise ValueError(f"«{title}»: неизвестный тип «{raw}» — полное, частичное или только обучение")
        return value
    if name == "level":
        value = LEVEL_WORDS.get(raw.lower())
        if value is None:
            raise ValueError(f"«{title}»: неизвестный уровень «{raw}» — бакалавриат, магистратура или foundation")
        return value
    return raw


@transaction.atomic
def import_scholarships(
    *, header: list[str], rows: list[list[str]], mapping: dict[str, str], dry_run: bool = False
) -> ScholarshipImportReport:
    """Загрузить стипендии. Ключ — название плюс организатор."""
    report = ScholarshipImportReport()
    index = {name: i for i, name in enumerate(header)}
    reverse = {target: column for column, target in mapping.items() if target}
    if "name" not in reverse:
        report.errors.append("Не сопоставлена обязательная колонка: название стипендии")
        return report

    for number, row in enumerate(rows, start=2):

        def cell(target: str, _row: list[str] = row) -> str:
            column = reverse.get(target)
            if column is None:
                return ""
            i = index.get(column)
            return _row[i] if i is not None and i < len(_row) else ""

        name = cell("name").strip()
        if not name:
            report.errors.append(f"строка {number}: пустое название стипендии")
            continue

        try:
            values = {
                target: _coerce(target, cell(target))
                for target in SCHOLARSHIP_FIELDS
                if target != "name" and target in reverse
            }
        except ValueError as exc:
            report.errors.append(f"строка {number}: {exc}")
            continue

        university = None
        university_name = cell("university").strip()
        if university_name:
            university = University.objects.filter(name__iexact=university_name).first()
            if university is None:
                report.errors.append(
                    f"строка {number}: вуза «{university_name}» нет в справочнике — "
                    "заведите его или оставьте колонку пустой"
                )
                continue

        organizer = (values.get("organizer") or "").strip() if values.get("organizer") else ""
        clean = {key: value for key, value in values.items() if value is not None}
        clean["organizer"] = organizer
        if university is not None:
            clean["university"] = university

        existing = Scholarship.objects.filter(name__iexact=name, organizer__iexact=organizer).first()
        if existing is None:
            Scholarship.objects.create(
                name=name,
                data_source=CatalogSource.IMPORT,
                # загруженная запись не проверена человеком (инвариант №14)
                is_verified=False,
                **clean,
            )
            report.created += 1
            state = "заведётся"
        else:
            changed = [key for key, value in clean.items() if getattr(existing, key) != value]
            for key, value in clean.items():
                setattr(existing, key, value)
            if changed:
                existing.is_verified = False
                existing.data_source = CatalogSource.IMPORT
                existing.save()
                report.updated += 1
                state = "обновится: " + ", ".join(TARGET_FIELDS.get(key, key) for key in changed)
            else:
                report.unchanged += 1
                state = "уже есть"

        report.rows.append({"row": number, "name": name, "state": state})

    if dry_run:
        transaction.set_rollback(True)
    return report
