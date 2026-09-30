"""Импорт требований вузов из XLSX/CSV с сопоставлением колонок.

Директор по поступлению уже ведёт эти таблицы в своих файлах — забираем
их как есть, а не заставляем перенабирать.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.functional import lazy
from django.utils.translation import gettext as _

from core.labels import field_title
from universities.models import AdmissionRequirement, Program, ProgramLevel, University

#: Поля требований, доступные для сопоставления. Подписи берутся из реестра
#: доменов, а не пишутся здесь второй раз (инвариант №2): иначе колонка
#: в импорте и колонка в таблице начнут называться по-разному.
REQUIREMENT_FIELDS = (
    "min_gpa",
    "min_ielts",
    "min_toefl",
    "min_sat",
    "min_act",
    "required_subjects",
    "portfolio_required",
    "portfolio_note",
    "notes",
    "source_url",
)

#: Подпись считается при чтении, а не при загрузке модуля: словарь уходит
#: на экран сопоставления, и подписи в нём — на языке того, кто загружает
_title = lazy(field_title, str)

TARGET_FIELDS: dict[str, str] = {
    "university": _title("universities.University", "name"),
    "program": _title("universities.Program", "name"),
    "level": _title("universities.Program", "level"),
    **{name: _title("universities.AdmissionRequirement", name) for name in REQUIREMENT_FIELDS},
}

DECIMAL_FIELDS = {"min_gpa", "min_ielts"}
INT_FIELDS = {"min_toefl", "min_sat", "min_act"}
BOOL_FIELDS = {"portfolio_required"}
TRUE_WORDS = {"1", "true", "yes", "да", "y", "+", "есть", "нужно"}  # i18n-skip: значения ячейки для распознавания


@dataclass
class RequirementImportReport:
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


def _coerce(field_name: str, raw: str) -> Any:
    raw = (raw or "").strip()
    if field_name in BOOL_FIELDS:
        return raw.lower() in TRUE_WORDS
    if raw == "":
        return None
    if field_name in DECIMAL_FIELDS:
        try:
            return Decimal(raw.replace(",", "."))
        except InvalidOperation as exc:
            raise ValueError(
                _("«{field}»: ожидалось число, получено «{value}»").format(
                    field=TARGET_FIELDS.get(field_name, field_name), value=raw
                )
            ) from exc
    if field_name in INT_FIELDS:
        try:
            return int(float(raw.replace(",", ".")))
        except ValueError as exc:
            raise ValueError(
                _("«{field}»: ожидалось число, получено «{value}»").format(
                    field=TARGET_FIELDS.get(field_name, field_name), value=raw
                )
            ) from exc
    return raw


@transaction.atomic
def import_requirements(
    *, header: list[str], rows: list[list[str]], mapping: dict[str, str], dry_run: bool = False
) -> RequirementImportReport:
    """Загрузить требования. Ключ — пара «вуз + программа»."""
    report = RequirementImportReport()
    index = {name: i for i, name in enumerate(header)}

    reverse = {target: column for column, target in mapping.items() if target}
    if "university" not in reverse or "program" not in reverse:
        report.errors.append(_("Не сопоставлены обязательные колонки: вуз и программа"))
        return report

    for number, row in enumerate(rows, start=2):

        def cell(target: str, _row: list[str] = row) -> str:
            column = reverse.get(target)
            if column is None:
                return ""
            i = index.get(column)
            return _row[i] if i is not None and i < len(_row) else ""

        university_name = cell("university").strip()
        program_name = cell("program").strip()
        if not university_name or not program_name:
            report.errors.append(_("строка {number}: пустой вуз или программа").format(number=number))
            continue

        try:
            values = {
                target: _coerce(target, cell(target))
                for target in TARGET_FIELDS
                if target not in ("university", "program", "level") and target in reverse
            }
        except ValueError as exc:
            report.errors.append(_("строка {number}: {error}").format(number=number, error=exc))
            continue

        university, _created = University.objects.get_or_create(
            name=university_name, defaults={"country": cell("country") or "—"}
        )
        level = (cell("level") or ProgramLevel.BACHELOR).strip().lower()
        if level not in dict(ProgramLevel.choices):
            level = ProgramLevel.BACHELOR
        program, _created = Program.objects.get_or_create(university=university, name=program_name, level=level)

        requirement = AdmissionRequirement.objects.filter(program=program).first()
        clean = {k: v for k, v in values.items() if v is not None}
        clean["checked_at"] = timezone.now()

        if requirement is None:
            AdmissionRequirement.objects.create(program=program, **clean)
            report.created += 1
            state = _("создано")
        else:
            changed = [k for k, v in clean.items() if k != "checked_at" and getattr(requirement, k) != v]
            for key, value in clean.items():
                setattr(requirement, key, value)
            requirement.save()
            if changed:
                report.updated += 1
                state = _("обновлено: {fields}").format(fields=", ".join(changed))
            else:
                report.unchanged += 1
                state = _("без изменений")

        report.rows.append({"row": number, "program": str(program), "state": state})

    if dry_run:
        transaction.set_rollback(True)
    return report
