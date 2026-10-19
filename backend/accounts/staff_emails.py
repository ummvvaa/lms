"""Почты сотрудников из файла школы: сопоставить с учётными записями и вписать.

Школа ведёт список сотрудников в книге «№, ФИО, Почта». Сотрудники в LMS
заведены листом «Сотрудники» импорта расписания: у части — логин
«имя.фамилия» без почты, ФИО короче (без отчества) и с ошибками. Команда
`manage.py staff_emails <файл>` строит план (`plan`) и по `--apply`
записывает его (`apply`), как `keep_subjects`.

Правила (решение владельца, 19.10.2026):

* строка файла ищется среди учётных записей не-учеников: сначала точно
  по почте, затем по ФИО тем же нечётким сравнением, что у учеников
  (`suggestions.name_matching`: кириллица–латиница, основы слов, пороги
  `CONFIDENT` и отрыв от второго кандидата). Сравнение в обе стороны:
  в файле ФИО с отчеством, в LMS — часто два слова;
* найдена без почты — почта вписывается, логин остаётся и работает,
  временный пароль не трогается; та же почта — ничего; другая почта,
  неуверенное совпадение, два близких кандидата, занятая почта —
  в список «не уверен / конфликт», ничего не применяется;
* не найдена — заводится учитель с этой почтой, без пароля и логина:
  вход — через приглашение «Выслать письма» у администратора;
* отключённой учётке почта вписывается, строка помечается «доступ
  отключён» — рассылка такую сама пропустит;
* писем команда не шлёт; каждое изменение — в `AuditLog` с источником
  `import`; повторный запуск ничего не меняет.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.db import transaction

from accounts.models import Role, User

#: колонки листа — как их называет школа
NAME_COLUMN, EMAIL_COLUMN = "ФИО", "Почта"  # i18n-skip: заголовки книги школы

#: причины попадания в «не уверен / конфликт» — вывод команды в терминал
NO_NAME = "нет ФИО"  # i18n-skip: вывод команды
BAD_EMAIL = "почта не похожа на адрес"  # i18n-skip: вывод команды
EMAIL_TWICE = "та же почта уже встречалась в файле"  # i18n-skip: вывод команды
EMAIL_OF_STUDENT = "почта у ученика, не у сотрудника"  # i18n-skip: вывод команды
EMAIL_OF_OTHER = "почта занята другой учётной записью"  # i18n-skip: вывод команды
OTHER_EMAIL = "в LMS другая почта"  # i18n-skip: вывод команды
PERSON_TWICE = "та же учётная запись уже подобрана другой строке файла"  # i18n-skip: вывод команды
UNSURE = "совпадение по ФИО не уверенное"  # i18n-skip: вывод команды
AMBIGUOUS = "несколько похожих учётных записей"  # i18n-skip: вывод команды

#: действия плана
FILL, SAME, CREATE, UNSURE_KIND = "fill", "same", "create", "unsure"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Row:
    """Строка файла: номер строки в книге, ФИО и почта как записаны."""

    number: int
    full_name: str
    email: str


@dataclass(frozen=True)
class Candidate:
    user: User
    score: float


@dataclass
class Item:
    """Строка файла с решением: что с ней делать и почему."""

    row: Row
    kind: str
    user: User | None = None
    why: str = ""
    candidates: list[Candidate] = field(default_factory=list)


@dataclass
class Plan:
    fill: list[Item] = field(default_factory=list)
    same: list[Item] = field(default_factory=list)
    create: list[Item] = field(default_factory=list)
    unsure: list[Item] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, item: Item) -> None:
        {FILL: self.fill, SAME: self.same, CREATE: self.create, UNSURE_KIND: self.unsure}[item.kind].append(item)


def _text(value) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def read(path: str) -> tuple[list[Row], list[str]]:
    """Прочитать книгу: первый лист, колонки «ФИО» и «Почта» по заголовку."""
    from openpyxl import load_workbook

    errors: list[str] = []
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = [_text(cell) for cell in (next(rows, None) or ())]
    missing = [column for column in (NAME_COLUMN, EMAIL_COLUMN) if column not in header]
    if missing:
        columns = ", ".join(f"«{c}»" for c in missing)
        errors.append(f"На листе «{sheet.title}» нет колонок: {columns}")  # i18n-skip: вывод команды
        return [], errors
    name_at, email_at = header.index(NAME_COLUMN), header.index(EMAIL_COLUMN)
    out: list[Row] = []
    for number, values in enumerate(rows, start=2):
        full_name = _text(values[name_at]) if name_at < len(values) else ""
        email = _text(values[email_at]).lower() if email_at < len(values) else ""
        if not full_name and not email:
            continue
        out.append(Row(number=number, full_name=full_name, email=email))
    return out, errors


def _score(a: str, b: str) -> float:
    """Сходство ФИО в обе стороны: лишнее отчество с любой стороны не штрафуется."""
    from suggestions.name_matching import similarity

    return max(similarity(a, b), similarity(b, a))


def _rank(full_name: str, people: list[User]) -> list[Candidate]:
    """Кандидаты по ФИО по убыванию сходства — порогом и отрывом, как у учеников."""
    from suggestions.name_matching import FLOOR, LAG

    scored = [
        Candidate(person, score)
        for person in people
        if person.full_name and (score := _score(full_name, person.full_name)) >= FLOOR
    ]
    scored.sort(key=lambda c: (-c.score, c.user.full_name))
    if scored:
        cutoff = scored[0].score - LAG
        scored = [c for c in scored if c.score >= cutoff]
    return scored[:5]


def _confident(candidates: list[Candidate]) -> bool:
    from suggestions.name_matching import CONFIDENT

    if not candidates or candidates[0].score < CONFIDENT:
        return False
    if len(candidates) == 1:
        return True
    return candidates[0].score - candidates[1].score >= 0.08


def plan(rows: list[Row]) -> Plan:
    """Решить по каждой строке файла, ничего не записывая."""
    from students.models import Student

    result = Plan()
    people = [p for p in User.objects.exclude(role=Role.STUDENT).order_by("pk") if not p.is_probe]
    by_email = {p.email.lower(): p for p in people if p.email}
    student_emails = {e.lower() for e in Student.all_objects.exclude(email="").values_list("email", flat=True)}
    student_emails |= {
        e.lower() for e in User.objects.filter(role=Role.STUDENT, email__isnull=False).values_list("email", flat=True)
    }
    seen_emails: set[str] = set()
    picked: set[int] = set()

    for row in rows:
        if not row.full_name:
            result.add(Item(row, UNSURE_KIND, why=NO_NAME))
            continue
        if not EMAIL_RE.match(row.email):
            result.add(Item(row, UNSURE_KIND, why=BAD_EMAIL))
            continue
        if row.email in seen_emails:
            result.add(Item(row, UNSURE_KIND, why=EMAIL_TWICE))
            continue
        seen_emails.add(row.email)
        if row.email in student_emails:
            result.add(Item(row, UNSURE_KIND, why=EMAIL_OF_STUDENT))
            continue

        exact = by_email.get(row.email)
        if exact is not None:
            picked.add(exact.pk)
            result.add(Item(row, SAME, user=exact))
            continue

        candidates = _rank(row.full_name, people)
        if not candidates:
            result.add(Item(row, CREATE))
            continue
        if not _confident(candidates):
            why = AMBIGUOUS if len(candidates) > 1 else UNSURE
            result.add(Item(row, UNSURE_KIND, why=why, candidates=candidates))
            continue
        user = candidates[0].user
        if user.pk in picked:
            result.add(Item(row, UNSURE_KIND, user=user, why=PERSON_TWICE, candidates=candidates[:1]))
            continue
        picked.add(user.pk)
        if user.email:
            result.add(Item(row, UNSURE_KIND, user=user, why=OTHER_EMAIL, candidates=candidates[:1]))
            continue
        result.add(Item(row, FILL, user=user, candidates=candidates[:1]))
    return result


@transaction.atomic
def apply(result: Plan, *, actor=None) -> dict[str, int]:
    """Записать план: вписать почты, завести новых. Каждое изменение — в журнал."""
    from accounts.services import create_user
    from core.audit import record_change
    from core.domains import Source

    for item in result.fill:
        user = item.user
        record_change(
            instance=user, field_name="email", old_value="", new_value=item.row.email, actor=actor, source=Source.IMPORT
        )
        user.email = item.row.email
        user.save(update_fields=["email"])
    for item in result.create:
        user = create_user(email=item.row.email, full_name=item.row.full_name[:200], role=Role.TEACHER)
        record_change(
            instance=user, field_name="role", old_value="", new_value=user.role, actor=actor, source=Source.IMPORT
        )
        item.user = user
    return {"filled": len(result.fill), "created": len(result.create)}
