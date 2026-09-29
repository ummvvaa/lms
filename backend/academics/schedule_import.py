"""Импорт расписания и сотрудников из книги школы (решение владельца, 29.09.2026).

Книга — шесть листов с постоянными заголовками, читаются по названию:
«Сотрудники», «Группы», «Предметы», «Звонки», «Подгруппы», «Уроки».
«Инструкция» и «Допущения» — для людей и пропускаются.

Предпросмотр и применение — один и тот же код: предпросмотр пишет всё
в транзакцию и откатывает её, поэтому цифры предпросмотра совпадают
с тем, что сделает «Применить». Разница одна: при предпросмотре не
выпускаются пароли и не заводятся строки уроков — это дорого, а счёт
уроков считается и без записи.

Повторный импорт того же файла ничего не удваивает: человек находится
по логину, ФИО или телефону, группа — по коду, предмет — по названию,
подгруппа и поток — по названию, журнал — по предмету, учителю и составу,
еженедельный урок — по журналу, дню и номеру.

Что правило, а что предупреждение:

- ошибка останавливает весь импорт: нет листа или колонки, ссылка
  на несуществующего сотрудника, группу или подгруппу, два человека
  в базе с одним ФИО;
- накладки кабинетов и учителей, время мимо звонков, роль, которую
  импорт не меняет, — предупреждения: файл школы бывает таким на деле.

Пароли открытым текстом возвращаются ровно один раз — в ответе
«Применить»; в журнал и в логи они не попадают.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction

from academics import cache
from academics import calendar as school_calendar
from academics.calendar import today
from academics.cohorts import group_cohort, make_stream
from academics.models import (
    AcademicYear,
    Bell,
    BellSchedule,
    Cohort,
    CohortKind,
    Course,
    Lesson,
    LessonSeries,
    LessonStatus,
    Scheme,
    StreamPart,
    Subject,
    TeacherProfile,
)
from academics.payloads import user_name
from academics.schedule import SCHEDULE_EVENT, materialize, series_dates
from accounts.models import Role, User
from core.audit import record_change
from core.domains import Source
from core.models import AuditLog
from students.models import GroupLanguage, Parallel, StudyGroup
from students.phones import normalize_kz

#: Еженедельный урок действует с начала года; строки уроков — со дня импорта
SERIES_START = dt.date(2026, 9, 1)

#: Лист → колонки, без которых импорт не идёт. Лишние колонки не мешают
SHEETS: dict[str, tuple[str, ...]] = {
    "Сотрудники": ("ID", "ФИО", "Фамилия", "Имя", "Отчество", "Роль", "Предметы", "Телефон", "Почта", "Логин"),
    "Группы": ("Группа", "Параллель", "Литера", "Язык обучения", "ID куратора", "Домашний кабинет"),
    "Предметы": ("Предмет",),
    "Звонки": ("Параллели", "Урок", "Начало", "Конец"),
    "Подгруппы": ("Подгруппа", "Параллель", "Предмет", "Из групп", "ID учителя", "Основной кабинет"),
    "Уроки": (
        "Параллель",
        "Группа",
        "Подгруппа",
        "День",
        "Урок",
        "Начало",
        "Конец",
        "Предмет",
        "ID учителя",
        "Кабинет",
        "Совместный урок",
    ),
}

#: Колонки, которых в старых книгах нет: пустое значение — умолчание
OPTIONAL: dict[str, tuple[str, ...]] = {"Предметы": ("Оценивание",)}

#: «Оценивание» на листе «Предметы» → схема предмета. «Без оценок» — существующая
#: схема «Только ФО», в табель не идёт (решение владельца, 29.09.2026); пусто — ФО, СОР, СОЧ
SCHEMES: dict[str, str] = {"фо, сор, соч": Scheme.KZ, "без оценок": Scheme.FO}

#: Роль в файле → роль учётки и нужен ли профиль учителя. `None` — администрация:
#: роли под неё нет, учётка заводится выключенной, роль назначает администратор
ROLES: dict[str, tuple[str | None, bool]] = {
    "учитель": (Role.TEACHER, True),
    "куратор": (Role.CURATOR, False),
    "учитель + куратор": (Role.CURATOR, True),
    "администрация": (None, False),
}

#: Роли, которые импорт меняет друг на друга. Остальные только называет в отчёте
SWITCHABLE = (Role.TEACHER, Role.CURATOR)

LANGUAGES = {"казахский": GroupLanguage.KK, "русский": GroupLanguage.RU}

WEEKDAYS = {"пн": 1, "вт": 2, "ср": 3, "чт": 4, "пт": 5, "сб": 6}
WEEKDAY_WORDS = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб"}

#: Предел размера файла: книга школы весит около 100 КБ
MAX_BYTES = 5 * 1024 * 1024


class ImportRefused(ValueError):
    """Импорт невозможен — текст объясняет почему."""


class _Rollback(Exception):
    """Откатить транзакцию предпросмотра или импорта с ошибками."""


# --- Чтение ячеек ----------------------------------------------------------------


def _text(value) -> str:
    """Ячейка строкой: число без «.0», пробелы схлопнуты."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())


def _int(value) -> int | None:
    text = _text(value)
    return int(text) if text.isdigit() else None


def _time(value) -> dt.time | None:
    if isinstance(value, dt.datetime):
        return value.time().replace(second=0, microsecond=0)
    if isinstance(value, dt.time):
        return value.replace(second=0, microsecond=0)
    match = re.fullmatch(r"(\d{1,2})[:.](\d{2})", _text(value))
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    return dt.time(hours, minutes) if hours < 24 and minutes < 60 else None


def _key(text: str) -> str:
    """Ключ сравнения: без регистра и лишних пробелов."""
    return " ".join((text or "").split()).casefold()


def _list(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;]", text or "") if part.strip() and part.strip() != "—"]


def _parallels(text: str) -> list[int]:
    """«8–9» → [8, 9]; «10» → [10]; «8, 9» → [8, 9]."""
    found = [int(n) for n in re.findall(r"\d+", text or "")]
    if len(found) == 2 and re.search(r"[–—-]", text) and found[0] < found[1]:
        return list(range(found[0], found[1] + 1))
    return found


# --- Разбор книги -----------------------------------------------------------------


@dataclass
class Staff:
    row: int
    code: str
    full_name: str
    last_name: str
    first_name: str
    role_text: str
    subjects: list[str]
    phone: str
    email: str
    login: str


@dataclass
class GroupRow:
    row: int
    code: str
    parallel: int | None
    letter: str
    language: str
    curator: str
    home_room: str


@dataclass
class SubjectRow:
    row: int
    title: str
    #: «Оценивание» как в файле, без регистра; пусто — колонки нет или ячейка пустая
    grading: str


@dataclass
class BellRow:
    row: int
    label: str
    parallels: list[int]
    number: int | None
    starts: dt.time | None
    ends: dt.time | None


@dataclass
class SubgroupRow:
    row: int
    name: str
    parallel: int | None
    subject: str
    groups: list[str]
    teacher: str
    room: str


@dataclass
class LessonRow:
    row: int
    parallel: int | None
    group: str
    subgroup: str
    weekday: int | None
    slot: int | None
    starts: dt.time | None
    ends: dt.time | None
    subject: str
    teacher: str
    room: str
    joint: str


@dataclass
class Book:
    staff: list[Staff] = field(default_factory=list)
    groups: list[GroupRow] = field(default_factory=list)
    subjects: list[SubjectRow] = field(default_factory=list)
    bells: list[BellRow] = field(default_factory=list)
    subgroups: list[SubgroupRow] = field(default_factory=list)
    lessons: list[LessonRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def fingerprint(data: bytes) -> str:
    """Отпечаток файла: «Применить» принимает только тот, что видели в предпросмотре."""
    return hashlib.sha256(data).hexdigest()


def _rows(sheet, title: str, errors: list[str]):
    """Строки листа словарями «колонка → значение» с номером строки файла."""
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None) or ()
    names = [_text(cell) for cell in header]
    missing = [column for column in SHEETS[title] if column not in names]
    if missing:
        errors.append(f"На листе «{title}» нет колонок: " + ", ".join(f"«{c}»" for c in missing))
        return
    index = {name: names.index(name) for name in (*SHEETS[title], *OPTIONAL.get(title, ())) if name in names}
    for number, values in enumerate(rows, start=2):
        if not any(_text(v) for v in values):
            continue
        cells = {name: (values[i] if i < len(values) else None) for name, i in index.items()}
        yield number, {name: None for name in OPTIONAL.get(title, ())} | cells


def parse(data: bytes) -> Book:
    """Прочитать книгу. Ошибки формата — в `Book.errors`, до базы дело не доходит."""
    import zipfile

    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    book = Book()
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (InvalidFileException, KeyError, OSError, ValueError, zipfile.BadZipFile):
        book.errors.append("Файл не читается как книга Excel (.xlsx)")
        return book
    missing = [title for title in SHEETS if title not in workbook.sheetnames]
    if missing:
        book.errors.append("В файле нет листов: " + ", ".join(f"«{t}»" for t in missing))
        return book

    for number, cells in _rows(workbook["Сотрудники"], "Сотрудники", book.errors):
        book.staff.append(
            Staff(
                row=number,
                code=_text(cells["ID"]),
                full_name=_text(cells["ФИО"]),
                last_name=_text(cells["Фамилия"]),
                first_name=_text(cells["Имя"]),
                role_text=_key(cells["Роль"] and str(cells["Роль"]).replace("+", " + ")),
                subjects=_list(_text(cells["Предметы"])),
                phone=_text(cells["Телефон"]),
                email=_text(cells["Почта"]).lower(),
                login=_text(cells["Логин"]).lower(),
            )
        )
    for number, cells in _rows(workbook["Группы"], "Группы", book.errors):
        book.groups.append(
            GroupRow(
                row=number,
                code=_text(cells["Группа"]).upper(),
                parallel=_int(cells["Параллель"]),
                letter=_text(cells["Литера"]),
                language=_key(_text(cells["Язык обучения"])),
                curator=_text(cells["ID куратора"]),
                home_room=_text(cells["Домашний кабинет"]),
            )
        )
    for number, cells in _rows(workbook["Предметы"], "Предметы", book.errors):
        book.subjects.append(
            SubjectRow(
                row=number,
                title=_text(cells["Предмет"]),
                grading=re.sub(r"\s*,\s*", ", ", _key(_text(cells["Оценивание"]))),
            )
        )
    for number, cells in _rows(workbook["Звонки"], "Звонки", book.errors):
        label = _text(cells["Параллели"])
        book.bells.append(
            BellRow(
                row=number,
                label=label,
                parallels=_parallels(label),
                number=_int(cells["Урок"]),
                starts=_time(cells["Начало"]),
                ends=_time(cells["Конец"]),
            )
        )
    for number, cells in _rows(workbook["Подгруппы"], "Подгруппы", book.errors):
        book.subgroups.append(
            SubgroupRow(
                row=number,
                name=_text(cells["Подгруппа"]),
                parallel=_int(cells["Параллель"]),
                subject=_text(cells["Предмет"]),
                groups=[code.upper() for code in _list(_text(cells["Из групп"]))],
                teacher=_text(cells["ID учителя"]),
                room=_text(cells["Основной кабинет"]),
            )
        )
    for number, cells in _rows(workbook["Уроки"], "Уроки", book.errors):
        book.lessons.append(
            LessonRow(
                row=number,
                parallel=_int(cells["Параллель"]),
                group=_text(cells["Группа"]).upper(),
                subgroup=_text(cells["Подгруппа"]),
                weekday=WEEKDAYS.get(_key(_text(cells["День"]))[:2]),
                slot=_int(cells["Урок"]),
                starts=_time(cells["Начало"]),
                ends=_time(cells["Конец"]),
                subject=_text(cells["Предмет"]),
                teacher=_text(cells["ID учителя"]),
                room=_text(cells["Кабинет"]),
                joint=_text(cells["Совместный урок"]),
            )
        )
    workbook.close()
    return book


# --- Отчёт ------------------------------------------------------------------------


@dataclass
class Section:
    code: str
    title: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "title": self.title,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
        }


@dataclass
class Report:
    fingerprint: str
    applied: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    sections: dict[str, Section] = field(default_factory=dict)
    curator_changes: list[dict] = field(default_factory=list)
    needs_role: list[dict] = field(default_factory=list)
    roles_kept: list[dict] = field(default_factory=list)
    stale_series: list[str] = field(default_factory=list)
    groups_outside: list[str] = field(default_factory=list)
    skipped_bells: int = 0
    lessons_from: dt.date | None = None
    lessons_to_create: int = 0
    series_without_teacher: int = 0
    credentials: list[dict] = field(default_factory=list)

    def section(self, code: str, title: str) -> Section:
        return self.sections.setdefault(code, Section(code, title))

    def warn(self, kind: str, text: str) -> None:
        self.warnings.append({"kind": kind, "text": text})

    def as_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "applied": self.applied,
            "errors": self.errors,
            "warnings": self.warnings,
            "sections": [s.as_dict() for s in self.sections.values()],
            "curator_changes": self.curator_changes,
            "needs_role": self.needs_role,
            "roles_kept": self.roles_kept,
            "stale_series": self.stale_series,
            "groups_outside": self.groups_outside,
            "skipped_bells": self.skipped_bells,
            "lessons_from": self.lessons_from,
            "lessons_to_create": self.lessons_to_create,
            "series_without_teacher": self.series_without_teacher,
            "credentials": self.credentials,
            "detail": self.detail(),
        }

    def detail(self) -> str:
        if self.errors:
            return f"Импорт не выполнен: ошибок {len(self.errors)}"
        made = sum(s.created for s in self.sections.values())
        changed = sum(s.updated for s in self.sections.values())
        head = "Импорт выполнен" if self.applied else "Предпросмотр"
        return f"{head}: создаётся {made}, обновляется {changed}, предупреждений {len(self.warnings)}"


# --- Запись -----------------------------------------------------------------------


def preview(data: bytes) -> dict:
    """Что сделает импорт — без единой записи в базе."""
    return _run(data, actor=None, commit=False)


def apply(data: bytes, *, actor, expected: str) -> dict:
    """Применить файл, который видели в предпросмотре. Всё или ничего."""
    if expected != fingerprint(data):
        raise ImportRefused("Файл не тот, что в предпросмотре: загрузите его заново и проверьте")
    return _run(data, actor=actor, commit=True)


def _run(data: bytes, *, actor, commit: bool) -> dict:
    if len(data) > MAX_BYTES:
        raise ImportRefused("Файл больше 5 МБ — это не книга расписания")
    report = Report(fingerprint=fingerprint(data))
    book = parse(data)
    report.errors.extend(book.errors)
    if report.errors:
        return report.as_dict()
    try:
        with transaction.atomic():
            _Writer(book, report, actor=actor, commit=commit).run()
            if report.errors or not commit:
                raise _Rollback
    except _Rollback:
        report.credentials = []
    else:
        report.applied = True
    cache.invalidate()
    return report.as_dict()


class _Writer:
    """Один проход по книге: листы по порядку, всё в одной транзакции."""

    def __init__(self, book: Book, report: Report, *, actor, commit: bool) -> None:
        self.book = book
        self.report = report
        self.actor = actor if getattr(actor, "pk", None) else None
        self.commit = commit
        self.day = today()
        self.year: AcademicYear | None = None
        self.subjects: dict[str, Subject] = {}
        self.staff: dict[str, User] = {}
        self.groups: dict[str, StudyGroup] = {}
        self.subgroups: dict[str, Cohort] = {}
        self.grids: dict[int, dict[int, tuple[dt.time, dt.time]]] = {}
        self.touched_series: set[int] = set()
        self.missing_bells: dict[tuple, list[str]] = defaultdict(list)
        self.new_series: list[LessonSeries] = []

    def error(self, text: str) -> None:
        self.report.errors.append(text)

    def run(self) -> None:
        self.year = school_calendar.current_year()
        if self.year is None:
            self.error("Нет текущего учебного года: заведите его на странице «Учебный год»")
            return
        self._subjects()
        self._staff()
        self._groups()
        self._bells()
        self._subgroups()
        if self.report.errors:
            return
        self._lessons()
        self._missing_bells()
        self._stale()
        self._conflicts()
        if self.report.errors:
            return
        self._materialize()
        if self.commit:
            self._log()

    # --- Предметы ---

    def _subjects(self) -> None:
        section = self.report.section("subjects", "Предметы")
        known = {_key(s.title): s for s in Subject.objects.all()}
        for row in self.book.subjects:
            title = row.title
            if not title:
                continue
            if row.grading and row.grading not in SCHEMES:
                self.error(
                    f"«Предметы», строка {row.row}: оценивание «{row.grading}» — нужно «ФО, СОР, СОЧ» или «без оценок»"
                )
                continue
            scheme = SCHEMES.get(row.grading, Scheme.KZ)
            found = known.get(_key(title))
            if found is None:
                found = Subject.objects.create(
                    code=self._subject_code(title),
                    title=title[:100],
                    short_title=title[:32],
                    scheme=scheme,
                    order=100,
                )
                known[_key(title)] = found
                section.created += 1
                if not row.grading:
                    self.report.warn(
                        "subject", f"Новый предмет «{title}»: оценивание в файле не указано — ФО, СОР и СОЧ, проверьте"
                    )
            else:
                section.unchanged += 1
                # схему заведённого предмета импорт не меняет — только называет расхождение
                if row.grading and found.scheme != scheme:
                    self.report.warn(
                        "scheme",
                        f"Предмет «{found.title}»: в LMS — «{found.get_scheme_display()}», "
                        f"в файле — «{Scheme(scheme).label}»; схема не меняется",
                    )
        self.subjects = known

    def _subject_code(self, title: str) -> str:
        from accounts.logins import latin

        base = re.sub(r"[^a-z0-9]+", "-", latin(title).lower()).strip("-")[:28] or "subject"
        code, number = base, 1
        while Subject.objects.filter(code=code).exists():
            number += 1
            code = f"{base}-{number}"
        return code

    def subject(self, title: str, where: str) -> Subject | None:
        found = self.subjects.get(_key(title))
        if found is None:
            self.error(f"{where}: предмета «{title}» нет ни в файле, ни в LMS")
        return found

    # --- Сотрудники ---

    def _staff(self) -> None:
        section = self.report.section("staff", "Сотрудники")
        people = list(User.objects.exclude(role=Role.STUDENT))
        by_login = {p.login.lower(): p for p in people if p.login}
        by_name: dict[str, list[User]] = defaultdict(list)
        by_phone: dict[str, list[User]] = defaultdict(list)
        for person in people:
            if person.full_name:
                by_name[_key(person.full_name)].append(person)
            if person.phone:
                by_phone[person.phone].append(person)
        taken_logins: set[str] = set()
        codes: set[str] = set()
        for row in self.book.staff:
            where = f"«Сотрудники», строка {row.row}"
            if not row.code or not row.full_name:
                self.error(f"{where}: нет ID или ФИО")
                continue
            if row.code in codes:
                self.error(f"{where}: ID {row.code} встречается дважды")
                continue
            codes.add(row.code)
            if row.role_text not in ROLES:
                self.error(f"{where}: роль «{row.role_text}» не из списка: " + ", ".join(ROLES))
                continue
            phone = normalize_kz(row.phone)
            if phone and not re.fullmatch(r"\+7\d{10}", phone):
                self.report.warn("phone", f"{row.full_name}: телефон «{row.phone}» не похож на номер — не записан")
                phone = ""
            user, why = self._match(row, phone, by_login, by_name, by_phone)
            if why:
                self.error(f"{where}: {why}")
                continue
            if user is None:
                user = self._create(row, phone, taken_logins)
                if user is None:
                    continue
                section.created += 1
            elif self._update(user, row, phone):
                section.updated += 1
            else:
                section.unchanged += 1
            self.staff[row.code] = user

    def _match(self, row: Staff, phone: str, by_login, by_name, by_phone) -> tuple[User | None, str]:
        """Уже заведённый человек: по логину, по ФИО, по телефону. Не угадываем."""
        if row.login and row.login in by_login:
            return by_login[row.login], ""
        named = by_name.get(_key(row.full_name), [])
        if len(named) > 1:
            return None, f"в LMS несколько сотрудников с ФИО «{row.full_name}» — оставьте одного"
        if named:
            return named[0], ""
        phoned = by_phone.get(phone, []) if phone else []
        if len(phoned) > 1:
            return None, f"в LMS несколько сотрудников с телефоном {phone}"
        return (phoned[0] if phoned else None), ""

    def _create(self, row: Staff, phone: str, taken: set[str]) -> User | None:
        from accounts.logins import LOGIN_RE, make_login

        role, _profile = ROLES[row.role_text]
        email = row.email or None
        if email and User.objects.filter(email__iexact=email).exists():
            self.error(f"«Сотрудники», строка {row.row}: почта {email} уже занята другой учётной записью")
            return None
        login = None
        if not email:
            login = row.login if row.login and LOGIN_RE.match(row.login) else ""
            if not login or login in taken or User.objects.filter(login__iexact=login).exists():
                wanted = login or "без логина"
                login = make_login(row.first_name, row.last_name, taken=taken)
                self.report.warn("login", f"{row.full_name}: логин «{wanted}» занят или неверен — выдан «{login}»")
            taken.add(login)
        admin_staff = role is None
        user = User.objects.create_user(
            email=email,
            login=login,
            password=None,
            full_name=row.full_name[:200],
            phone=phone,
            # администрации роли нет: учётка выключена, роль и доступ даёт администратор
            role=role or Role.TEACHER,
            is_active=not admin_staff,
        )
        record_change(
            instance=user, field_name="role", old_value="", new_value=user.role, actor=self.actor, source=Source.IMPORT
        )
        self._profile(user, row)
        if admin_staff:
            self.report.needs_role.append(
                {"full_name": user.full_name, "login": user.handle, "position": ", ".join(row.subjects)}
            )
        elif self.commit:
            from accounts import temporary

            password = temporary.issue(user)
            self.report.credentials.append(
                {
                    "full_name": user.full_name,
                    "email": user.email,
                    "login": user.handle,
                    "password": password,
                    "expires_at": user.temp_password_expires_at,
                    "group": "",
                }
            )
        return user

    def _update(self, user: User, row: Staff, phone: str) -> bool:
        """ФИО, телефон, предметы и роль учитель ↔ куратор. Логин, почту и вход не трогаем."""
        changed = False
        wanted_role, _profile = ROLES[row.role_text]
        fields: dict[str, str] = {}
        if row.full_name and user.full_name != row.full_name:
            fields["full_name"] = row.full_name[:200]
        if phone and user.phone != phone:
            fields["phone"] = phone
        if wanted_role is not None and wanted_role != user.role:
            if user.role in SWITCHABLE:
                fields["role"] = wanted_role
            else:
                self.report.roles_kept.append(
                    {"full_name": user_name(user), "role": user.get_role_display(), "file": row.role_text}
                )
        elif wanted_role is None and user.role in SWITCHABLE:
            self.report.roles_kept.append(
                {"full_name": user_name(user), "role": user.get_role_display(), "file": row.role_text}
            )
        for name, value in fields.items():
            record_change(
                instance=user,
                field_name=name,
                old_value=getattr(user, name),
                new_value=value,
                actor=self.actor,
                source=Source.IMPORT,
            )
            setattr(user, name, value)
        if fields:
            user.save(update_fields=list(fields))
            changed = True
        if self._profile(user, row):
            changed = True
        return changed

    def _profile(self, user: User, row: Staff) -> bool:
        """Профиль учителя с предметами из файла. Возвращает, поменялось ли что-то."""
        _role, needs_profile = ROLES[row.role_text]
        if not needs_profile:
            return False
        wanted = []
        for title in row.subjects:
            found = self.subjects.get(_key(title))
            if found is None:
                self.report.warn("subject", f"{row.full_name}: предмета «{title}» нет на листе «Предметы» — пропущен")
            else:
                wanted.append(found)
        profile, created = TeacherProfile.objects.get_or_create(user=user)
        now = set(profile.subjects.values_list("pk", flat=True))
        if {s.pk for s in wanted} == now:
            return created
        profile.subjects.set(wanted)
        return True

    def person(self, code: str, where: str) -> User | None:
        if not code:
            return None
        found = self.staff.get(code)
        if found is None:
            self.error(f"{where}: сотрудника с ID {code} нет на листе «Сотрудники»")
        return found

    # --- Группы ---

    def _groups(self) -> None:
        from accounts.curators import AssignmentRefused, assign, curator_of

        section = self.report.section("groups", "Группы")
        seen: set[str] = set()
        for row in self.book.groups:
            where = f"«Группы», строка {row.row}"
            if not row.code or row.code in seen:
                self.error(f"{where}: нет кода группы или он повторяется")
                continue
            seen.add(row.code)
            if row.parallel not in Parallel.values:
                self.error(f"{where}: параллель должна быть от 8 до 11")
                continue
            language = LANGUAGES.get(row.language)
            if language is None:
                self.error(f"{where}: язык «{row.language}» — нужен «казахский» или «русский»")
                continue
            wanted = {
                "parallel": row.parallel,
                "letter": row.letter[:4],
                "language": language,
                "home_room": row.home_room[:40],
            }
            group = StudyGroup.objects.filter(code__iexact=row.code).first()
            is_new = group is None
            if is_new:
                group = StudyGroup.objects.create(code=row.code[:16], **wanted)
                section.created += 1
            else:
                diff = {name: value for name, value in wanted.items() if getattr(group, name) != value}
                if "parallel" in diff:
                    self.report.warn(
                        "parallel", f"Группа {group.code}: параллель меняется {group.parallel} → {row.parallel}"
                    )
                for name, value in diff.items():
                    record_change(
                        instance=group,
                        field_name=name,
                        old_value=getattr(group, name),
                        new_value=value,
                        actor=self.actor,
                        source=Source.IMPORT,
                    )
                    setattr(group, name, value)
                if diff:
                    group.save(update_fields=list(diff))
                    section.updated += 1
                else:
                    section.unchanged += 1
            group_cohort(group)
            self.groups[row.code] = group

            curator = self.person(row.curator, where)
            if curator is None:
                continue
            if curator.role != Role.CURATOR:
                self.report.warn(
                    "curator",
                    f"Группа {group.code}: {user_name(curator)} — не куратор в LMS, куратором не назначен",
                )
                continue
            current = curator_of(group, self.day)
            if current is not None and current.curator_id == curator.pk:
                continue
            since = self.day if current is not None else self.year.starts
            if current is not None and since <= current.since:
                since = current.since + dt.timedelta(days=1)
            if not is_new:
                self.report.curator_changes.append(
                    {
                        "group": group.code,
                        "parallel": group.parallel,
                        "was": user_name(current.curator) if current else "",
                        "will": user_name(curator),
                        "since": since,
                    }
                )
            try:
                assign(group=group, curator=curator, since=since, actor=self.actor)
            except AssignmentRefused as error:
                self.report.warn("curator", f"Группа {group.code}: {error}")
        in_file = set(self.groups)
        self.report.groups_outside = sorted(
            g.code for g in StudyGroup.objects.filter(is_active=True) if g.code.upper() not in in_file
        )

    def group(self, code: str, where: str) -> StudyGroup | None:
        found = self.groups.get(code.upper())
        if found is None:
            self.error(f"{where}: группы {code} нет на листе «Группы»")
        return found

    # --- Звонки ---

    def _bells(self) -> None:
        section = self.report.section("bells", "Звонки")
        grids: dict[str, list[BellRow]] = defaultdict(list)
        for row in self.book.bells:
            if not row.parallels:
                self.error(f"«Звонки», строка {row.row}: не понятно, каких параллелей звонки «{row.label}»")
                continue
            if row.number is None:
                # «обед» и другие перемены — не урок, в звонки не идут
                self.report.skipped_bells += 1
                continue
            if row.starts is None or row.ends is None or row.starts >= row.ends:
                self.error(f"«Звонки», строка {row.row}: неверное время урока")
                continue
            grids[row.label].append(row)
        for rows in grids.values():
            parallels = rows[0].parallels
            span = f"{parallels[0]}–{parallels[-1]}" if len(parallels) > 1 else str(parallels[0])
            title = f"Звонки {span}"
            schedule, created = BellSchedule.objects.get_or_create(year=self.year, title=title)
            changed = created
            for row in rows:
                bell = Bell.objects.filter(schedule=schedule, number=row.number).first()
                if bell is None:
                    Bell.objects.create(
                        year=self.year, schedule=schedule, number=row.number, starts=row.starts, ends=row.ends
                    )
                    changed = True
                elif (bell.starts, bell.ends) != (row.starts, row.ends):
                    bell.starts, bell.ends = row.starts, row.ends
                    bell.save(update_fields=["starts", "ends"])
                    changed = True
                for parallel in parallels:
                    self.grids.setdefault(parallel, {})[row.number] = (row.starts, row.ends)
            extra = Bell.objects.filter(schedule=schedule).exclude(number__in=[r.number for r in rows])
            if extra.exists():
                self.report.warn(
                    "bells", f"{title}: в LMS есть уроки сверх файла — {', '.join(str(b.number) for b in extra)}"
                )
            groups = [g for g in self.groups.values() if g.parallel in parallels]
            others = BellSchedule.objects.filter(year=self.year, is_default=False).exclude(pk=schedule.pk)
            for other in others:
                other.groups.remove(*groups)
            if set(schedule.groups.values_list("pk", flat=True)) != {g.pk for g in groups}:
                schedule.groups.set(groups)
                changed = changed or not created
            if created:
                section.created += 1
            elif changed:
                section.updated += 1
            else:
                section.unchanged += 1
        for parallel in sorted({g.parallel for g in self.groups.values()} - set(self.grids)):
            self.report.warn("bells", f"Для {parallel} параллели звонков в файле нет — уроки пойдут по общим звонкам")

    # --- Подгруппы ---

    def _subgroups(self) -> None:
        section = self.report.section("subgroups", "Подгруппы и потоки")
        for row in self.book.subgroups:
            where = f"«Подгруппы», строка {row.row}"
            subject = self.subject(row.subject, where)
            groups = [self.group(code, where) for code in row.groups]
            self.person(row.teacher, where)
            if subject is None or not row.name or not groups or any(g is None for g in groups):
                if not row.name or not groups:
                    self.error(f"{where}: нужны название подгруппы и группы потока")
                continue
            stream, stream_state = self._stream(_stream_name(row.name), groups)
            if stream_state == "created":
                section.created += 1
            elif stream_state == "updated":
                section.updated += 1
            number_match = re.search(r"(\d+)$", row.name)
            wanted = {
                "stream": stream,
                "subject": subject,
                "number": int(number_match.group(1)) if number_match else None,
                "room": row.room[:40],
            }
            cohort = Cohort.objects.filter(kind=CohortKind.SUBGROUP, name=row.name[:120]).first()
            if cohort is None:
                cohort = Cohort.objects.create(
                    kind=CohortKind.SUBGROUP,
                    name=row.name[:120],
                    short_name=row.name[:60],
                    rule="по файлу школы",
                    **wanted,
                )
                section.created += 1
            else:
                diff = {name: value for name, value in wanted.items() if getattr(cohort, name) != value}
                for name, value in diff.items():
                    setattr(cohort, name, value)
                if diff:
                    cohort.save(update_fields=list(diff))
                    section.updated += 1
                else:
                    section.unchanged += 1
            self.subgroups[_key(row.name)] = cohort

    def _stream(self, name: str, groups: list[StudyGroup]) -> tuple[Cohort, str]:
        """Поток из групп по названию: есть — сверить части, нет — завести."""
        parts = [group_cohort(g) for g in groups]
        stream = Cohort.objects.filter(kind=CohortKind.STREAM, name=name[:120]).first()
        if stream is None:
            return make_stream(name=name, parts=parts), "created"
        now = set(StreamPart.objects.filter(stream=stream).values_list("part_id", flat=True))
        if now == {p.pk for p in parts}:
            return stream, "same"
        return make_stream(name=name, parts=parts, stream=stream), "updated"

    # --- Уроки ---

    def _lessons(self) -> None:
        section = self.report.section("lessons", "Уроки в неделю")
        units: list[dict] = []
        joint: dict[str, list[LessonRow]] = defaultdict(list)
        for row in self.book.lessons:
            where = f"«Уроки», строка {row.row}"
            if bool(row.group) == bool(row.subgroup):
                self.error(f"{where}: заполните либо «Группа», либо «Подгруппа»")
                continue
            if row.weekday is None or row.slot is None:
                self.error(f"{where}: не понятны день или номер урока")
                continue
            if row.joint:
                joint[row.joint].append(row)
                continue
            unit = self._unit(row, [row])
            if unit is not None:
                units.append(unit)
        for code, rows in joint.items():
            first = rows[0]
            shape = {(r.weekday, r.slot, _key(r.subject), r.teacher, _key(r.room)) for r in rows}
            if len(shape) > 1:
                self.error(f"«Уроки», совместный урок {code}: день, урок, предмет, учитель и кабинет должны совпадать")
                continue
            if any(r.subgroup for r in rows):
                self.error(f"«Уроки», совместный урок {code}: собирается из групп, не из подгрупп")
                continue
            unit = self._unit(first, rows)
            if unit is not None:
                unit["joint"] = code
                units.append(unit)
        if self.report.errors:
            return
        self.units = units
        seen: set[tuple[int, int, int]] = set()
        for unit in units:
            key = (unit["cohort"].pk, unit["weekday"], unit["slot"])
            if key in seen:
                self.report.warn("group", f"{unit['label']}: у состава два урока в {unit['when']}")
            seen.add(key)
            state = self._series(unit)
            if state == "created":
                section.created += 1
            elif state == "updated":
                section.updated += 1
            else:
                section.unchanged += 1
            if unit["teacher"] is None:
                self.report.series_without_teacher += 1

    def _unit(self, row: LessonRow, rows: list[LessonRow]) -> dict | None:
        """Урок недели: состав, предмет, учитель, день, номер, кабинет, время."""
        where = f"«Уроки», строка {row.row}"
        subject = self.subject(row.subject, where)
        teacher = self.person(row.teacher, where)
        if row.teacher and teacher is None:
            return None
        if row.subgroup:
            cohort = self.subgroups.get(_key(row.subgroup))
            if cohort is None:
                self.error(f"{where}: подгруппы {row.subgroup} нет на листе «Подгруппы»")
                return None
            groups = [g for g in self.groups.values() if g.pk in _stream_group_ids(cohort)]
            name = row.subgroup
        else:
            groups = [self.group(r.group, f"«Уроки», строка {r.row}") for r in rows]
            if any(g is None for g in groups):
                return None
            if len(groups) == 1:
                cohort = group_cohort(groups[0])
            else:
                cohort, _state = self._stream(" + ".join(sorted(g.code for g in groups)), groups)
            name = " + ".join(g.code for g in groups)
        if subject is None:
            return None
        parallel = row.parallel or (groups[0].parallel if groups else None)
        grid = self.grids.get(parallel or 0, {})
        bell = grid.get(row.slot)
        when = f"{WEEKDAY_WORDS[row.weekday]} {row.starts:%H:%M}" if row.starts else f"{WEEKDAY_WORDS[row.weekday]}"
        if grid and bell is None:
            # сводится в одну строку на параллель и номер (`_missing_bells`)
            span = f"{row.starts:%H:%M}–{row.ends:%H:%M}" if row.starts and row.ends else ""
            self.missing_bells[(parallel, row.slot, span)].append(f"{name} {WEEKDAY_WORDS[row.weekday]}")
        elif bell and row.starts and (row.starts, row.ends) != bell:
            self.report.warn(
                "time",
                f"{name}, {WEEKDAY_WORDS[row.weekday]} {row.slot} урок: в файле {row.starts:%H:%M}–{row.ends:%H:%M}, "
                f"по звонкам {bell[0]:%H:%M}–{bell[1]:%H:%M}",
            )
        return {
            "cohort": cohort,
            "subject": subject,
            "teacher": teacher,
            "weekday": row.weekday,
            "slot": row.slot,
            "room": row.room[:40],
            "starts": row.starts or (bell[0] if bell else None),
            "ends": row.ends or (bell[1] if bell else None),
            "label": f"{name} {subject.title}",
            "when": when,
            "joint": "",
        }

    def _series(self, unit: dict) -> str:
        """Журнал и еженедельный урок: найти по ключу или завести."""
        course = Course.objects.filter(subject=unit["subject"], teacher=unit["teacher"], cohort=unit["cohort"]).first()
        if course is None:
            course = Course.objects.create(subject=unit["subject"], teacher=unit["teacher"], cohort=unit["cohort"])
        series = (
            LessonSeries.objects.filter(course=course, weekday=unit["weekday"], slot=unit["slot"], ends__gte=self.day)
            .order_by("-starts")
            .first()
        )
        if series is None:
            series = LessonSeries.objects.create(
                course=course,
                weekday=unit["weekday"],
                slot=unit["slot"],
                room=unit["room"],
                starts=SERIES_START,
                ends=self.year.ends,
                created_by=self.actor,
            )
            self.new_series.append(series)
            self.touched_series.add(series.pk)
            return "created"
        self.touched_series.add(series.pk)
        if series.room == unit["room"]:
            return "same"
        series.room = unit["room"]
        series.save(update_fields=["room"])
        Lesson.objects.filter(series=series, date__gte=self.day, status=LessonStatus.PLANNED).update(room=unit["room"])
        return "updated"

    def _missing_bells(self) -> None:
        """Урок с номером, которого нет в звонках его параллели: время у него не покажется."""
        for (parallel, slot, span), where in sorted(self.missing_bells.items()):
            shown = ", ".join(where[:6]) + (f" и ещё {len(where) - 6}" if len(where) > 6 else "")
            self.report.warn(
                "time",
                f"{slot} урока{f' ({span})' if span else ''} нет в звонках {parallel} параллели — "
                f"уроков в неделю: {len(where)} ({shown}). Добавьте звонок на листе «Звонки»",
            )

    def _stale(self) -> None:
        """Еженедельные уроки в LMS, которых нет в файле: не удаляются, только называются."""
        rows = (
            LessonSeries.objects.filter(ends__gte=self.day, course__archived_at__isnull=True)
            .exclude(pk__in=self.touched_series)
            .select_related("course__subject", "course__cohort", "course__teacher")
            .order_by("course__cohort__name", "weekday", "slot")
        )
        for series in rows:
            course = series.course
            self.report.stale_series.append(
                f"{course.subject.title} · {course.cohort.name} · {WEEKDAY_WORDS.get(series.weekday, '')} "
                f"{series.slot} урок · {user_name(course.teacher) or 'учитель не назначен'}"
            )

    def _conflicts(self) -> None:
        """Накладки кабинетов и учителей по времени из файла — предупреждения."""
        by_day: dict[int, list[dict]] = defaultdict(list)
        for unit in getattr(self, "units", []):
            if unit["starts"] and unit["ends"]:
                by_day[unit["weekday"]].append(unit)
        for weekday, units in sorted(by_day.items()):
            units.sort(key=lambda u: (u["starts"], u["label"]))
            for i, a in enumerate(units):
                for b in units[i + 1 :]:
                    if b["starts"] >= a["ends"]:
                        break
                    when = f"{WEEKDAY_WORDS[weekday]} {max(a['starts'], b['starts']):%H:%M}"
                    if a["room"] and _key(a["room"]) == _key(b["room"]):
                        self.report.warn(
                            "room", f"Накладка кабинета · каб. {a['room']} · {when}: {a['label']} / {b['label']}"
                        )
                    if a["teacher"] is not None and a["teacher"] == b["teacher"]:
                        self.report.warn(
                            "teacher",
                            f"Накладка учителя · {user_name(a['teacher'])} · {when}: {a['label']} / {b['label']}",
                        )

    def _materialize(self) -> None:
        """Строки уроков новых еженедельных — со дня импорта, не с 1 сентября."""
        calendar = school_calendar.load(self.year)
        if not calendar.quarters:
            self.report.warn("year", "У учебного года нет четвертей — строки уроков не заведутся")
        since = max(self.day, SERIES_START)
        self.report.lessons_from = since
        for series in self.new_series:
            if self.commit:
                self.report.lessons_to_create += materialize(series, calendar, since=since, actor=self.actor)
            else:
                self.report.lessons_to_create += len(series_dates(series, calendar, since=since))

    def _log(self) -> None:
        """След импорта в журнале расписания. Паролей в нём нет."""
        parts = [f"{s.title.lower()}: +{s.created}, изменено {s.updated}" for s in self.report.sections.values()]
        AuditLog.objects.create(
            actor=self.actor,
            actor_role=getattr(self.actor, "role", "") or "",
            model_label="academics.Lesson",
            object_id="",
            field_name=SCHEDULE_EVENT,
            domain_code="academics",
            old_value="",
            new_value=("Импорт расписания из файла — " + "; ".join(parts))[:2000],
            source=Source.IMPORT,
        )
        for change in self.report.curator_changes:
            AuditLog.objects.create(
                actor=self.actor,
                actor_role=getattr(self.actor, "role", "") or "",
                model_label="students.StudyGroup",
                object_id=change["group"],
                domain_code="",
                field_name="curator",
                old_value=change["was"],
                new_value=change["will"],
                source=Source.IMPORT,
            )


def _stream_name(subgroup: str) -> str:
    """«EEP-8-1» → «EEP-8»: поток — название подгруппы без номера."""
    match = re.fullmatch(r"(.+?)[-\s]*\d+", subgroup)
    return match.group(1) if match else f"{subgroup} · поток"


def _stream_group_ids(cohort: Cohort) -> set[int]:
    from academics.cohorts import group_ids_of

    return set(group_ids_of(cohort))
