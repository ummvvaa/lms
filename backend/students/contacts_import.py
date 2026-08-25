"""Импорт контактов родителей файлом.

Отдельный путь от импорта доменных полей: там колонка правит одно поле
одной записи один-к-одному с учеником, а контактов у ученика несколько,
и строка файла — это целая новая запись, а не правка существующей.

Правила те же, что у остальных загрузок:

* ученик ищется по почте, ненайденная строка называется по номеру;
* строка с ошибкой не отменяет остальные;
* повторная загрузка того же файла не плодит дублей: контакт узнаётся
  по паре «ученик + телефон или почта»;
* всё, что применилось, ссылается на `ImportBatch` и отменяется целиком.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from core.domains import Source
from students.models import ContactChannel, ContactRelation, ParentContact, Student

#: Как колонки называют в школьных списках. Сравнение по вхождению
#: и без регистра: «Телефон мамы» и «e-mail родителя» находятся сами.
COLUMNS: dict[str, tuple[str, ...]] = {
    "student": ("почта ученика", "email ученика", "ученик", "student", "школьная почта"),
    "full_name": ("фио родителя", "родитель", "контакт", "опекун", "фио контакта", "представитель"),
    "relation": ("кем приходится", "родство", "кто", "relation", "степень родства"),
    "phone": ("телефон", "тел.", "phone", "моб"),
    "email": ("почта", "email", "e-mail", "мейл"),
    "preferred_channel": ("способ связи", "связь", "канал", "как связываться"),
    "note": ("примечание", "коммент", "note", "заметка"),
    "is_primary": ("основной", "главный", "primary"),
}

REQUIRED = ("student", "full_name")

#: Подписи колонок для отказа: человек читает «почта ученика»,
#: а не `student`
TITLES = {
    "student": "почта ученика",
    "full_name": "ФИО родителя",
    "relation": "кем приходится",
    "phone": "телефон",
    "email": "почта",
    "preferred_channel": "способ связи",
    "note": "примечание",
    "is_primary": "основной контакт",
}

#: Как в файле пишут родство. Ключ — значение колонки в базе
RELATION_WORDS: dict[str, tuple[str, ...]] = {
    ContactRelation.MOTHER: ("мама", "мать", "мам", "mother", "mom"),
    ContactRelation.FATHER: ("папа", "отец", "пап", "father", "dad"),
    ContactRelation.GUARDIAN: ("опекун", "попечитель", "guardian"),
    ContactRelation.GRANDPARENT: ("бабушка", "дедушка", "баб", "дед"),
    ContactRelation.RELATIVE: ("тётя", "дядя", "сестра", "брат", "родственник"),
}

CHANNEL_WORDS: dict[str, tuple[str, ...]] = {
    ContactChannel.PHONE: ("звонок", "телефон", "позвонить", "call"),
    ContactChannel.WHATSAPP: ("whatsapp", "вотсап", "ватсап"),
    ContactChannel.TELEGRAM: ("telegram", "телеграм", "тг"),
    ContactChannel.EMAIL: ("почта", "email", "e-mail", "письмо"),
}

TRUE_WORDS = {"да", "yes", "true", "1", "+", "основной", "y"}


def _relation_of(value: str) -> str:
    low = (value or "").strip().lower()
    if not low:
        return ContactRelation.OTHER
    for code, words in RELATION_WORDS.items():
        if any(word in low for word in words):
            return code
    return ContactRelation.OTHER


def _channel_of(value: str) -> str:
    low = (value or "").strip().lower()
    for code, words in CHANNEL_WORDS.items():
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
    full_name: str = ""
    relation: str = ""
    phone: str = ""
    email: str = ""
    preferred_channel: str = ""
    note: str = ""
    is_primary: bool = False
    #: new | exists | error
    status: str = "new"
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "student": self.student_id,
            "student_email": self.student_email,
            "student_name": self.student_name,
            "full_name": self.full_name,
            "relation": self.relation,
            "phone": self.phone,
            "email": self.email,
            "preferred_channel": self.preferred_channel,
            "note": self.note,
            "is_primary": self.is_primary,
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
        exists = [row for row in self.rows if row.status == "exists"]
        broken = [row for row in self.rows if row.status == "error"]
        return {
            "columns": self.columns,
            "missing_columns": self.missing_columns,
            "total": len(self.rows),
            "will_create": len(self.ready),
            "already_exist": len(exists),
            "with_errors": len(broken),
            "rows": [row.as_dict() for row in self.rows],
            "detail": self.detail(),
        }

    def detail(self) -> str:
        """Одна фраза вместо чтения таблицы."""
        if self.missing_columns:
            names = ", ".join(self.missing_columns)
            return f"В файле не нашлись обязательные колонки: {names}. Проверьте заголовок первой строки"
        exists = sum(1 for row in self.rows if row.status == "exists")
        broken = sum(1 for row in self.rows if row.status == "error")
        parts = [f"строк в файле: {len(self.rows)}", f"будет заведено контактов: {len(self.ready)}"]
        if exists:
            parts.append(f"уже есть: {exists}")
        if broken:
            parts.append(f"с ошибками: {broken}")
        return ", ".join(parts).capitalize()


def _find_columns(header: list[str]) -> dict[str, int]:
    """Сопоставить колонки файла полям.

    Порядок важен: «почта ученика» должна достаться ученику, а не
    контакту, поэтому ключ ученика ищется первым и по более длинной
    подсказке.
    """
    found: dict[str, int] = {}
    for name in ("student", "full_name", "relation", "phone", "preferred_channel", "note", "is_primary", "email"):
        hints = COLUMNS[name]
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
    """Разобрать файл контактов и сказать, что произойдёт."""
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

    for number, raw in enumerate(rows, start=2):  # 1 — заголовок
        row = Row(
            number=number,
            student_email=_cell(raw, columns.get("student")).lower(),
            full_name=_cell(raw, columns.get("full_name")),
            relation=_relation_of(_cell(raw, columns.get("relation"))),
            phone=_cell(raw, columns.get("phone")),
            email=_cell(raw, columns.get("email")).lower(),
            preferred_channel=_channel_of(_cell(raw, columns.get("preferred_channel"))),
            note=_cell(raw, columns.get("note")),
            is_primary=_cell(raw, columns.get("is_primary")).lower() in TRUE_WORDS,
        )
        if not any([row.student_email, row.full_name, row.phone, row.email]):
            continue  # пустой хвост файла — не ошибка

        found = students.get(row.student_email)
        if found is None:
            row.status = "error"
            row.reason = f"ученика с почтой «{row.student_email or 'пусто'}» в базе нет"
        else:
            row.student_id, row.student_name = found
            if not row.full_name:
                row.status, row.reason = "error", "не указано ФИО родителя"
            elif not row.phone and not row.email:
                row.status, row.reason = "error", "нет ни телефона, ни почты — связаться по контакту нечем"
            elif _already_there(row):
                row.status, row.reason = "exists", "такой контакт у ученика уже записан"

        preview.rows.append(row)

    return preview


def _already_there(row: Row) -> bool:
    """Контакт узнаётся по телефону или почте у того же ученика.

    Списки родителей присылают дважды так же регулярно, как списки
    классов, и второй «Ахметова Гульнара» с тем же телефоном — это
    не второй человек.
    """
    query = ParentContact.all_objects.filter(student_id=row.student_id)
    digits = re.sub(r"\D", "", row.phone)
    if digits:
        for existing in query.only("phone", "email"):
            if re.sub(r"\D", "", existing.phone) == digits:
                return True
    if row.email:
        return query.filter(email__iexact=row.email).exists()
    return False


@transaction.atomic
def apply_rows(*, rows: list[dict[str, Any]], actor=None, file_name: str = "") -> dict[str, Any]:
    """Завести контакты из проверенных строк.

    Каждая запись помечается загрузкой: отменить импорт целиком можно
    в истории загрузок, как и у остальных доменов.
    """
    from core.audit import apply_changes
    from core.models import ImportBatch

    batch = ImportBatch.objects.create(
        actor=actor,
        file_name=file_name,
        kind=ImportBatch.Kind.STUDENTS,
        domain_code="behavior",
        rows_total=len(rows),
    )

    created = 0
    skipped: list[dict[str, Any]] = []
    for raw in rows:
        student = Student.objects.filter(pk=raw.get("student")).first()
        full_name = (raw.get("full_name") or "").strip()
        if student is None or not full_name:
            skipped.append({"row": raw.get("number"), "reason": "нет ученика или ФИО"})
            continue

        contact = ParentContact(student=student)
        apply_changes(
            contact,
            {
                "full_name": full_name,
                "relation": raw.get("relation") or ContactRelation.OTHER,
                "phone": (raw.get("phone") or "").strip(),
                "email": (raw.get("email") or "").strip(),
                "preferred_channel": raw.get("preferred_channel") or "",
                "note": (raw.get("note") or "").strip(),
                "is_primary": bool(raw.get("is_primary")),
            },
            actor=actor,
            source=Source.IMPORT,
            import_batch=batch,
        )
        created += 1

    batch.rows_created = created
    batch.rows_failed = len(skipped)
    batch.note = "Отмена загрузки уберёт заведённые контакты"
    batch.save(update_fields=["rows_created", "rows_failed", "note"])

    return {
        "created": created,
        "skipped": skipped,
        "batch": batch.pk,
        "detail": f"Заведено контактов: {created}" + (f", пропущено строк: {len(skipped)}" if skipped else ""),
    }
