"""Заведение учеников списком: карточка, учётная запись, временный пароль.

Двойная работа — завести почту в одном месте, а ученика руками в другом —
на двухстах пятидесяти людях превращается в неделю. Здесь из одной строки
файла появляется всё сразу и за один заход.

Правила, которые здесь соблюдаются:

* строка либо создаёт всё, либо не создаёт ничего — карточка без учётной
  записи это ученик, который не может войти, а запись без карточки —
  человек, которому нечего показать;
* повторная загрузка того же файла ничего не дублирует: ученик узнаётся
  по почте, а без почты — по ФИО в той же группе, и строка помечается
  как уже заведённая;
* почта необязательна: у 8–10 её нет — учётная запись получает логин
  «имя.фамилия» (`accounts.logins`), им ученик и входит;
* группа обязательна и должна быть заведена: параллель у группы,
  и ученик без неё не получил бы ни своих разделов, ни года выпуска.
* строки с ошибками не отменяют остальные — одна опечатка в двухсотой
  строке не должна стоить дня работы (то же правило, что и в импорте
  доменных полей).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.utils.translation import gettext as _

from accounts.models import Role, User
from accounts.naming import NameRejected, check_full_name
from students.models import Student, StudyGroup

#: Что ищем в заголовке файла. Ключ — поле, значения — как его называют
#: в школьных списках. Сравнение по вхождению и без регистра: «ФИО
#: ученика» и «e-mail (школьный)» должны находиться сами.
COLUMNS: dict[str, tuple[str, ...]] = {  # i18n-skip: синонимы заголовков для распознавания
    "full_name": ("фио", "ф.и.о", "имя", "ученик", "фамилия", "name", "student"),
    "email": ("почта", "email", "e-mail", "мейл", "мэйл"),
    # колонка «класс» не читается: параллель — у группы, а не у ученика
    "group": ("группа", "group", "литера", "класс-группа"),
}

#: Обязательные колонки. Без имени ученика не найти в списке, без группы
#: у него нет параллели. Почта — нет: у 8–10 её нет, им заводится логин.
REQUIRED = ("full_name", "group")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-Я]{2,}$")  # i18n-skip: регулярное выражение


@dataclass
class Row:
    """Одна строка файла после разбора."""

    number: int
    full_name: str = ""
    email: str = ""
    group: str = ""
    #: логин, который получит учётная запись без почты
    login: str = ""
    #: new | exists | error
    status: str = "new"
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "full_name": self.full_name,
            "email": self.email,
            "group": self.group,
            "login": self.login,
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
            return _("В файле не нашлись обязательные колонки: {names}. Проверьте заголовок первой строки").format(
                names=names
            )
        parts = [
            _("строк в файле: {count}").format(count=len(self.rows)),
            _("будет заведено: {count}").format(count=len(self.ready)),
        ]
        if self.existing:
            parts.append(_("уже есть: {count}").format(count=len(self.existing)))
        if self.broken:
            parts.append(_("с ошибками: {count}").format(count=len(self.broken)))
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


def build_preview(*, header: list[str], rows: list[list[str]]) -> Preview:
    """Разобрать файл и сказать, что произойдёт при применении."""
    from accounts.logins import make_login

    columns = _find_columns(header)
    missing = [name for name in REQUIRED if name not in columns]
    titles = {
        "full_name": _("ФИО"),
        "email": _("почта"),
        "group": _("группа"),
    }
    preview = Preview(
        columns={name: header[index] for name, index in columns.items()},
        missing_columns=[titles[name] for name in missing],
    )
    if missing:
        return preview

    known_emails = {value.lower() for value in Student.all_objects.values_list("email", flat=True) if value}
    known_users = {value.lower() for value in User.objects.values_list("email", flat=True) if value}
    groups = {group.code.lower(): group for group in StudyGroup.objects.all()}
    seen: set[str] = set()
    logins: set[str] = set()

    for number, raw in enumerate(rows, start=2):  # 1 — строка заголовка
        row = Row(
            number=number,
            full_name=_cell(raw, columns.get("full_name")),
            email=_cell(raw, columns.get("email")).lower(),
            group=_cell(raw, columns.get("group")),
        )
        if not any([row.full_name, row.email, row.group]):
            continue  # пустая строка в конце файла — не ошибка

        group = groups.get(row.group.lower())
        last_name, first_name, _middle = _split_name(row.full_name)
        # без почты ученик узнаётся по фамилии и имени в своей группе
        key = row.email or f"{last_name.lower()}|{first_name.lower()}|{row.group.lower()}"
        if not row.full_name:
            row.status, row.reason = "error", _("не указано ФИО")
        elif not row.group:
            row.status, row.reason = "error", _("не указана группа")
        elif group is None:
            row.status, row.reason = (
                "error",
                _("группы «{group}» нет — заведите её с параллелью на вкладке «Учебные группы»").format(
                    group=row.group
                ),
            )
        elif row.email and not EMAIL_RE.match(row.email):
            row.status, row.reason = "error", _("почта «{email}» не похожа на адрес").format(email=row.email)
        elif key in seen:
            row.status, row.reason = (
                "error",
                _("эта почта встречается в файле дважды") if row.email else _("этот ученик встречается в файле дважды"),
            )
        elif (row.email and (row.email in known_emails or row.email in known_users)) or (
            not row.email and _known_by_name(row.full_name, group)
        ):
            row.status, row.reason = "exists", _("такой ученик уже заведён")
        else:
            try:
                check_full_name(row.full_name)
            except NameRejected as error:
                row.status, row.reason = "error", str(error)
        if row.status == "new" and not row.email:
            last, first, _middle = _split_name(row.full_name)
            row.login = make_login(first, last, taken=logins)
            logins.add(row.login)

        seen.add(key)
        preview.rows.append(row)

    return preview


def _known_by_name(full_name: str, group: StudyGroup) -> bool:
    """Ученик без почты узнаётся по ФИО в своей группе — так повтор файла не дублирует."""
    last, first, _middle = _split_name(full_name)
    return Student.all_objects.filter(group=group, last_name__iexact=last, first_name__iexact=first).exists()


def _split_name(full_name: str) -> tuple[str, str, str]:
    """«Ахметова Алия Ерлановна» → фамилия, имя, отчество."""
    parts = [part for part in re.split(r"\s+", full_name.strip()) if part]
    last = parts[0] if parts else ""
    first = parts[1] if len(parts) > 1 else ""
    middle = " ".join(parts[2:]) if len(parts) > 2 else ""
    return last, first, middle


@transaction.atomic
def enroll(*, rows: list[dict[str, Any]], actor=None, send_mail: bool = True) -> dict[str, Any]:
    """Завести учеников из проверенных строк.

    Одна транзакция на весь заход: если что-то пойдёт не так на середине,
    в базе не должно остаться половины класса без учётных записей.

    Возвращает список выданных паролей открытым текстом — ровно один раз
    и только тому, кто нажал кнопку. На сервере они не сохраняются.
    Письмо уходит только тем, у кого есть почта.
    """
    from accounts import temporary
    from accounts.logins import make_login
    from core.parallels import graduation_year_for
    from students.linking import adopt_group_language, link_student

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    groups = {group.code.lower(): group for group in StudyGroup.objects.all()}

    for raw in rows:
        email = (raw.get("email") or "").strip().lower() or None
        full_name = (raw.get("full_name") or "").strip()
        group = groups.get(str(raw.get("group") or "").strip().lower())
        who = email or full_name
        if not full_name:
            skipped.append({"email": who, "reason": _("нет ФИО")})
            continue
        if group is None:
            skipped.append({"email": who, "reason": _("нет такой группы — заведите её с параллелью")})
            continue
        if email and (
            Student.all_objects.filter(email__iexact=email).exists()
            or User.objects.filter(email__iexact=email).exists()
        ):
            skipped.append({"email": email, "reason": _("уже заведён")})
            continue
        if not email and _known_by_name(full_name, group):
            skipped.append({"email": full_name, "reason": _("уже заведён")})
            continue

        last, first, middle = _split_name(full_name)
        student = Student.objects.create(
            last_name=last,
            first_name=first,
            middle_name=middle,
            email=email,
            group=group,
            graduation_year=graduation_year_for(group.parallel),
        )
        _make_profiles(student)

        login = None if email else make_login(first, last)
        user = User.objects.create_user(email=email, login=login, password=None, full_name=full_name, role=Role.STUDENT)
        password = temporary.issue(user)
        if email:
            link_student(student)
        else:
            # без почты связывать не по чему — связываем сразу, строка одна
            student.user = user
            student.save(update_fields=["user"])
            adopt_group_language(user, student)

        sent = temporary.send_letter(user, password) if send_mail else False
        created.append(
            {
                "student": student.pk,
                "user": user.pk,
                "full_name": full_name,
                "email": email or "",
                "login": user.handle,
                "group": group.code,
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
        return _("Никого не завели: все строки уже есть в базе или содержат ошибки")
    parts = [_("Заведено учеников: {count}").format(count=created)]
    if letters:
        parts.append(_("письма с временным паролем ушли: {count}").format(count=letters))
    else:
        parts.append(_("письма не отправлялись — скачайте список паролей и раздайте лично"))
    if skipped:
        parts.append(_("пропущено: {count}").format(count=skipped))
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
