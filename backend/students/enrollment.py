"""Заведение учеников списком: карточка, учётная запись, временный пароль.

Двойная работа — завести почту в одном месте, а ученика руками в другом —
на двухстах пятидесяти людях превращается в неделю. Здесь из одной строки
файла появляется всё сразу и за один заход.

Правила, которые здесь соблюдаются:

* строка либо создаёт всё, либо не создаёт ничего — карточка без учётной
  записи это ученик, который не может войти, а запись без карточки —
  человек, которому нечего показать;
* повторная загрузка того же файла ничего не дублирует: ученик узнаётся
  по почте, и строка помечается как уже заведённая;
* строки с ошибками не отменяют остальные — одна опечатка в двухсотой
  строке не должна стоить дня работы (то же правило, что и в импорте
  доменных полей).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.db import transaction

from accounts.models import Role, User
from accounts.naming import NameRejected, check_full_name
from students.models import Student, StudyGroup

#: Что ищем в заголовке файла. Ключ — поле, значения — как его называют
#: в школьных списках. Сравнение по вхождению и без регистра: «ФИО
#: ученика» и «e-mail (школьный)» должны находиться сами.
COLUMNS: dict[str, tuple[str, ...]] = {
    "full_name": ("фио", "ф.и.о", "имя", "ученик", "фамилия", "name", "student"),
    "email": ("почта", "email", "e-mail", "мейл", "мэйл", "логин"),
    "grade": ("класс", "grade", "параллель"),
    "group": ("группа", "group", "литера", "класс-группа"),
}

#: Обязательные поля. Без них строка не создаёт ничего: ученик без почты
#: не войдёт, а без имени его не найти в списке.
REQUIRED = ("full_name", "email")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-Я]{2,}$")


@dataclass
class Row:
    """Одна строка файла после разбора."""

    number: int
    full_name: str = ""
    email: str = ""
    grade: str = ""
    group: str = ""
    #: new | exists | error
    status: str = "new"
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "full_name": self.full_name,
            "email": self.email,
            "grade": self.grade,
            "group": self.group,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class Preview:
    """Что будет, если применить: сколько создастся, что пропустится."""

    columns: dict[str, str] = field(default_factory=dict)
    rows: list[Row] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)

    @property
    def ready(self) -> list[Row]:
        return [row for row in self.rows if row.status == "new"]

    @property
    def existing(self) -> list[Row]:
        return [row for row in self.rows if row.status == "exists"]

    @property
    def broken(self) -> list[Row]:
        return [row for row in self.rows if row.status == "error"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "missing_columns": self.missing_columns,
            "total": len(self.rows),
            "will_create": len(self.ready),
            "already_exist": len(self.existing),
            "with_errors": len(self.broken),
            "rows": [row.as_dict() for row in self.rows],
            "detail": self.detail(),
        }

    def detail(self) -> str:
        """Одна фраза о том, что произойдёт. Её читают вместо таблицы."""
        if self.missing_columns:
            names = ", ".join(self.missing_columns)
            return f"В файле не нашлись обязательные колонки: {names}. Проверьте заголовок первой строки"
        parts = [f"строк в файле: {len(self.rows)}", f"будет заведено: {len(self.ready)}"]
        if self.existing:
            parts.append(f"уже есть: {len(self.existing)}")
        if self.broken:
            parts.append(f"с ошибками: {len(self.broken)}")
        return ", ".join(parts).capitalize()


def _find_columns(header: list[str]) -> dict[str, int]:
    """Сопоставить колонки файла полям. Первая подходящая — она и есть."""
    found: dict[str, int] = {}
    for index, title in enumerate(header):
        low = (title or "").strip().lower()
        if not low:
            continue
        for field_name, hints in COLUMNS.items():
            if field_name in found:
                continue
            if any(hint in low for hint in hints):
                found[field_name] = index
                break
    return found


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return (row[index] or "").strip()


def _default_graduation_year(grade: str) -> int:
    """Год выпуска по классу: 11-й выпускается в этом учебном году.

    Считаем от текущего года: до июня выпуск в этом году, после — в
    следующем. Точное значение директор поправит в карточке, но пустым
    оно быть не может — по нему считается всё остальное.
    """
    today = date.today()
    base = today.year if today.month <= 6 else today.year + 1
    try:
        number = int(re.sub(r"\D", "", grade) or 11)
    except ValueError:
        number = 11
    number = min(max(number, 1), 11)
    return base + (11 - number)


def build_preview(*, header: list[str], rows: list[list[str]]) -> Preview:
    """Разобрать файл и сказать, что произойдёт при применении."""
    columns = _find_columns(header)
    missing = [name for name in REQUIRED if name not in columns]
    titles = {
        "full_name": "ФИО",
        "email": "почта",
        "grade": "класс",
        "group": "группа",
    }
    preview = Preview(
        columns={name: header[index] for name, index in columns.items()},
        missing_columns=[titles[name] for name in missing],
    )
    if missing:
        return preview

    known_emails = {value.lower() for value in Student.all_objects.values_list("email", flat=True) if value}
    known_users = {value.lower() for value in User.objects.values_list("email", flat=True) if value}
    seen: set[str] = set()

    for number, raw in enumerate(rows, start=2):  # 1 — строка заголовка
        row = Row(
            number=number,
            full_name=_cell(raw, columns.get("full_name")),
            email=_cell(raw, columns.get("email")).lower(),
            grade=_cell(raw, columns.get("grade")),
            group=_cell(raw, columns.get("group")),
        )
        if not any([row.full_name, row.email, row.grade, row.group]):
            continue  # пустая строка в конце файла — не ошибка

        if not row.full_name:
            row.status, row.reason = "error", "не указано ФИО"
        elif not row.email:
            row.status, row.reason = "error", "не указана почта"
        elif not EMAIL_RE.match(row.email):
            row.status, row.reason = "error", f"почта «{row.email}» не похожа на адрес"
        elif row.email in seen:
            row.status, row.reason = "error", "эта почта встречается в файле дважды"
        elif row.email in known_emails or row.email in known_users:
            row.status, row.reason = "exists", "такой ученик уже заведён"
        else:
            try:
                check_full_name(row.full_name)
            except NameRejected as error:
                row.status, row.reason = "error", str(error)

        seen.add(row.email)
        preview.rows.append(row)

    return preview


def _split_name(full_name: str) -> tuple[str, str, str]:
    """«Ахметова Алия Ерлановна» → фамилия, имя, отчество."""
    parts = [part for part in re.split(r"\s+", full_name.strip()) if part]
    last = parts[0] if parts else ""
    first = parts[1] if len(parts) > 1 else ""
    middle = " ".join(parts[2:]) if len(parts) > 2 else ""
    return last, first, middle


def _group_for(code: str, grade: int) -> StudyGroup | None:
    """Учебная группа по коду. Нет такой — заводим: список её и приносит."""
    code = (code or "").strip()
    if not code:
        return None
    group = StudyGroup.all_objects.filter(code__iexact=code).first()
    if group is not None:
        return group
    return StudyGroup.objects.create(code=code, grade=grade)


@transaction.atomic
def enroll(*, rows: list[dict[str, Any]], actor=None, send_mail: bool = True) -> dict[str, Any]:
    """Завести учеников из проверенных строк.

    Одна транзакция на весь заход: если что-то пойдёт не так на середине,
    в базе не должно остаться половины класса без учётных записей.

    Возвращает список выданных паролей открытым текстом — ровно один раз
    и только тому, кто нажал кнопку. На сервере они не сохраняются.
    """
    from accounts import temporary
    from students.linking import link_student

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for raw in rows:
        email = (raw.get("email") or "").strip().lower()
        full_name = (raw.get("full_name") or "").strip()
        if not email or not full_name:
            skipped.append({"email": email, "reason": "нет почты или ФИО"})
            continue
        if (
            Student.all_objects.filter(email__iexact=email).exists()
            or User.objects.filter(email__iexact=email).exists()
        ):
            skipped.append({"email": email, "reason": "уже заведён"})
            continue

        last, first, middle = _split_name(full_name)
        grade_text = str(raw.get("grade") or "")
        try:
            grade = int(re.sub(r"\D", "", grade_text) or 11)
        except ValueError:
            grade = 11
        grade = min(max(grade, 1), 11)

        student = Student.objects.create(
            last_name=last,
            first_name=first,
            middle_name=middle,
            email=email,
            grade=grade,
            group=_group_for(str(raw.get("group") or ""), grade),
            graduation_year=_default_graduation_year(grade_text),
        )
        _make_profiles(student)

        user = User.objects.create_user(email=email, password=None, full_name=full_name, role=Role.STUDENT)
        password = temporary.issue(user)
        link_student(student)

        sent = temporary.send_letter(user, password) if send_mail else False
        created.append(
            {
                "student": student.pk,
                "user": user.pk,
                "full_name": full_name,
                "email": email,
                "password": password,
                "sent": sent,
            }
        )

    letters = sum(1 for row in created if row["sent"])
    return {
        "created": len(created),
        "skipped": skipped,
        "rows": created,
        "letters": letters,
        "hours": _ttl_hours(),
        "detail": _detail(len(created), letters, len(skipped)),
    }


def _ttl_hours() -> int:
    from accounts import temporary

    return temporary.ttl_hours()


def _detail(created: int, letters: int, skipped: int) -> str:
    if not created:
        return "Никого не завели: все строки уже есть в базе или содержат ошибки"
    parts = [f"Заведено учеников: {created}"]
    if letters:
        parts.append(f"письма с временным паролем ушли: {letters}")
    else:
        parts.append("письма не отправлялись — скачайте список паролей и раздайте лично")
    if skipped:
        parts.append(f"пропущено: {skipped}")
    return ". ".join(parts)


def _make_profiles(student: Student) -> None:
    """Пять профилей: карточка без них наполовину пуста и ломает списки."""
    from students.models import (
        AdmissionProfile,
        BehaviorProfile,
        ExamProfile,
        SportProfile,
        TalentProfile,
    )

    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.get_or_create(student=student)
