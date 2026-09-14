"""Реестр соответствий импорта: колонка → поле → домен → тип (фаза 71).

До 71-й разбор таблицы Асем знал свои колонки сам: обрывки заголовков
в одном словаре, порядок в кортеже, баллы в третьем, ссылки в четвёртом,
а применение — отдельным кодом на каждое место назначения. Добавить
колонку значило править четыре списка и разбор. Мастер, отчёт и проверка
держали по своей копии того же знания.

Теперь всё это — одна запись на колонку здесь. У записи:

* **как колонка называется в файле** — несколько написаний, ищем
  по вхождению в заголовок (заголовки приходят с переносами и хвостами);
* **поле и домен** — кому принадлежит то, что в ячейке;
* **тип значения** — как разбирать: телефон, почта, дата, число по шкале,
  ссылка, текст, пароль;
* **обязательна ли** — без ФИО строку не к кому отнести, остальное
  по желанию; пустая ячейка ничего не стирает — это общее правило,
  не свойство колонки: таблица заполнялась годами и пустота в ней
  значит «не знаю», а не «нет»;
* **куда ложится** — профиль поступления, профиль экзаменов, попытка
  экзамена, документ-ссылка, хранилище паролей.

Новая колонка в будущем — строка в `COLUMNS`, не правка разбора.
Порядок записей важен: «Электронный адрес Common app» должен найтись
раньше «Электронный адрес», иначе почта Common App легла бы в личную.

Права. Администратор пишет любые домены. Владелец домена — свои:
у Асем это поступление и документы. **Исключение одной строкой** —
`ADMISSION_TABLE_EXTRA_DOMAINS`: таблицу поступления ведёт Асем, и GPA
с попытками IELTS и SAT из неё она пишет в домен экзаменов от своего
имени, как с фазы 65. Куратор импорт не запускает вовсе.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# --- Типы значений ------------------------------------------------------------

TEXT = "text"
PHONE = "phone"
EMAIL = "email"
DATE = "date"
SCORE = "score"
GPA = "gpa"
LINK = "link"
PASSWORD = "password"
NAME = "name"

KIND_TITLES: dict[str, str] = {
    TEXT: "текст",
    PHONE: "телефон",
    EMAIL: "почта",
    DATE: "дата",
    SCORE: "балл по шкале экзамена",
    GPA: "число 0–5",
    LINK: "ссылка",
    PASSWORD: "пароль",
    NAME: "ФИО",
}

# --- Куда ложится ---------------------------------------------------------------

PROFILE = "profile"  # профиль поступления
EXAM_PROFILE = "exam_profile"  # профиль экзаменов
ATTEMPT = "attempt"  # попытка экзамена
DOCUMENT = "document"  # документ-ссылка
CREDENTIAL = "credential"  # хранилище паролей
MATCH = "match"  # сопоставление с учеником, никуда не пишется

TARGET_TITLES: dict[str, str] = {
    PROFILE: "профиль поступления",
    EXAM_PROFILE: "профиль экзаменов",
    ATTEMPT: "попытка экзамена",
    DOCUMENT: "документ-ссылка",
    CREDENTIAL: "хранилище паролей",
    MATCH: "сопоставление с учеником",
}

#: Домены, в которые таблица поступления пишет **сверх своих**, от имени
#: владельца таблицы. Одна строка — одно исключение из правила «владелец
#: пишет только свои домены»: таблицу ведёт Асем, GPA и попытки в ней её
ADMISSION_TABLE_EXTRA_DOMAINS: tuple[str, ...] = ("exam",)


@dataclass(frozen=True)
class ColumnSpec:
    """Одна колонка таблицы: как найти, как разобрать, куда положить."""

    key: str
    title: str
    aliases: tuple[str, ...]
    kind: str
    domain: str
    target: str
    #: имя поля профиля — для `PROFILE` и `EXAM_PROFILE`
    field: str = ""
    #: экзамен и номер результата — для `ATTEMPT`
    exam: str = ""
    slot: int = 0
    #: тип документа — для `DOCUMENT`
    doc_type: str = ""
    #: вид пароля — для `CREDENTIAL`
    credential: str = ""
    required: bool = False

    @property
    def domain_title(self) -> str:
        from core.domains import DOMAINS

        return DOMAINS[self.domain].title if self.domain in DOMAINS else "—"

    @property
    def destination(self) -> str:
        """Куда ложится — словами для отчёта и документации."""
        if self.target in (PROFILE, EXAM_PROFILE):
            return f"{TARGET_TITLES[self.target]}, поле «{self.field}»"
        if self.target == ATTEMPT:
            return f"{TARGET_TITLES[self.target]} {self.exam}-{self.slot}"
        if self.target == DOCUMENT:
            return f"{TARGET_TITLES[self.target]} «{self.doc_type}»"
        if self.target == CREDENTIAL:
            return f"{TARGET_TITLES[self.target]}, «{self.credential}»"
        return TARGET_TITLES[self.target]


#: Все колонки таблицы Асем — в порядке поиска по заголовкам
COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("name", "ФИО", ("фио", "ф.и.о", "ученик", "студент"), NAME, "", MATCH, required=True),
    ColumnSpec("phone", "Номер телефона", ("номер телефона", "телефон"), PHONE, "admission", PROFILE, "student_phone"),
    ColumnSpec(
        "common_app_email",
        "Электронный адрес Common App",
        ("электронный адрес common app", "почта common app", "common app email"),
        EMAIL,
        "admission",
        PROFILE,
        "common_app_email",
    ),
    ColumnSpec(
        "common_app_password",
        "Пароль от Common App",
        ("пароль от common app", "пароль common app"),
        PASSWORD,
        "admission",
        CREDENTIAL,
        credential="common_app",
    ),
    ColumnSpec(
        "email_password",
        "Пароль от эл. адреса",
        ("пароль от эл", "пароль от почт", "пароль эл"),
        PASSWORD,
        "admission",
        CREDENTIAL,
        credential="email",
    ),
    # личная почта ученика — текст в карточке, с логином не связана (фаза 71)
    ColumnSpec(
        "email",
        "Электронный адрес",
        ("электронный адрес", "почта", "email", "e-mail"),
        EMAIL,
        "admission",
        PROFILE,
        "personal_email",
    ),
    ColumnSpec(
        "drive_folder",
        "Ссылка на папку студента",
        ("папку студента", "папка студента", "гугл драйв", "drive"),
        LINK,
        "admission",
        PROFILE,
        "drive_folder_url",
    ),
    ColumnSpec(
        "passport_link",
        "Ссылка на паспорт",
        ("ссылка на паспорт", "паспорт ссылка"),
        LINK,
        "documents",
        DOCUMENT,
        doc_type="passport",
    ),
    # срок — своё поле профиля, не свойство документа: ссылки в таблице
    # может не быть, а срок есть (фаза 71)
    ColumnSpec(
        "passport_expiry",
        "Срок годности паспорта",
        ("срок годности паспорта", "срок паспорта", "годност"),
        DATE,
        "admission",
        PROFILE,
        "passport_expires_at",
    ),
    ColumnSpec("gpa", "Средний GPA", ("средний gpa", "gpa", "средний балл"), GPA, "exam", EXAM_PROFILE, "gpa"),
    ColumnSpec("ielts_1", "IELTS-1", ("ielts-1", "ielts 1"), SCORE, "exam", ATTEMPT, exam="IELTS", slot=1),
    ColumnSpec("ielts_2", "IELTS-2", ("ielts-2", "ielts 2"), SCORE, "exam", ATTEMPT, exam="IELTS", slot=2),
    ColumnSpec("ielts_3", "IELTS-3", ("ielts-3", "ielts 3"), SCORE, "exam", ATTEMPT, exam="IELTS", slot=3),
    ColumnSpec("sat_1", "SAT-1", ("sat-1", "sat 1"), SCORE, "exam", ATTEMPT, exam="SAT", slot=1),
    ColumnSpec("sat_2", "SAT-2", ("sat-2", "sat 2"), SCORE, "exam", ATTEMPT, exam="SAT", slot=2),
    ColumnSpec("sat_3", "SAT-3", ("sat-3", "sat 3"), SCORE, "exam", ATTEMPT, exam="SAT", slot=3),
    ColumnSpec(
        "transcript_link",
        "Ссылка на табель",
        ("ссылка на табел", "табел"),
        LINK,
        "documents",
        DOCUMENT,
        doc_type="transcript",
    ),
    ColumnSpec(
        "recommendation_link",
        "Ссылка на рек. письмо",
        ("рек. письмо", "рекоменд"),
        LINK,
        "documents",
        DOCUMENT,
        doc_type="recommendation",
    ),
)

BY_KEY: dict[str, ColumnSpec] = {spec.key: spec for spec in COLUMNS}

#: Заголовки, которые не колонки данных: их не надо называть «не распознана»
SERVICE_HEADERS: tuple[str, ...] = ("№", "n", "no", "#")


def spec_of(key: str) -> ColumnSpec:
    return BY_KEY[key]


def columns_of_domain(domain: str) -> tuple[ColumnSpec, ...]:
    return tuple(spec for spec in COLUMNS if spec.domain == domain)


def domains_of_columns(keys) -> set[str]:
    """Какие домены заполняют эти колонки; служебные («ФИО») не в счёт."""
    return {BY_KEY[key].domain for key in keys if key in BY_KEY and BY_KEY[key].domain}


# --- Заголовки ------------------------------------------------------------------


def _text(value) -> str:
    """Ячейка строкой: без переносов, без хвостов, без «None»."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _header_key(title: str) -> str:
    return _text(title).lower()


def read_columns(header: list[str]) -> dict[str, int]:
    """Сопоставить заголовки листа с колонками реестра.

    Один заголовок достаётся одной колонке: иначе «Электронный адрес»
    подошёл бы и личной почте, и почте Common App. Порядок — порядок
    реестра, и он это столкновение и разводит.
    """
    taken: set[int] = set()
    found: dict[str, int] = {}
    keys = [_header_key(title) for title in header]
    for spec in COLUMNS:
        for index, key in enumerate(keys):
            if index in taken or not key:
                continue
            if any(alias in key for alias in spec.aliases):
                found[spec.key] = index
                taken.add(index)
                break
    return found


def unknown_columns(header: list[str], found: dict[str, int]) -> list[str]:
    """Заголовки, которых реестр не знает, — для отчёта «не распознана, пропущена»."""
    taken = set(found.values())
    out = []
    for index, title in enumerate(header):
        text = _text(title)
        if not text or index in taken or text.lower() in SERVICE_HEADERS:
            continue
        out.append(text)
    return out


# --- Права ----------------------------------------------------------------------


def writable_domains(user) -> set[str]:
    """Какие домены этот человек вправе заполнять импортом.

    Администратор — любые. Владелец домена — свои и то, что реестр
    отдал его таблице сверх своих (`ADMISSION_TABLE_EXTRA_DOMAINS`).
    Куратор и ученик — ничего: импорт не их инструмент.
    """
    from core.domains import DOMAINS, ROLE_ADMIN, domains_of_role

    role = getattr(user, "role", "")
    if role == ROLE_ADMIN:
        return set(DOMAINS)
    own = {domain.code for domain in domains_of_role(role)}
    if not own:
        return set()
    if role == "director_admission":
        own |= set(ADMISSION_TABLE_EXTRA_DOMAINS)
    return own


# --- Разбор ячеек ---------------------------------------------------------------

#: Опечатки в домене почты, которые видно глазом, но не программой:
#: писать на такой адрес бессмысленно, а чинить его импортом мы не вправе.
#: Сверяется домен целиком — «gmail.com» не должен ловиться на «gmail.co»
EMAIL_SUSPECTS: dict[str, str] = {
    "gmail.ru": "домен «gmail.ru» — у Gmail такого нет, вероятно «gmail.com»",
    "gmail.co": "домен «gmail.co» — похоже на обрезанный «gmail.com»",
    "mail.ru.com": "домен «mail.ru.com» — вероятно «mail.ru»",
}


def parse_phone(raw) -> str | None:
    """Телефон к виду `+7XXXXXXXXXX`; не разбирается — `None`.

    В таблице встречается всё: `87753730924.0` (Excel сделал из номера
    число), `=77715019917` (формула, чтобы ноль не съелся), пробелы,
    скобки и дефисы. Формат один, поэтому и правило одно.
    """
    text = _text(raw)
    if not text:
        return None
    text = text.lstrip("=").strip()
    # хвост «.0» от числового формата Excel — не часть номера
    text = re.sub(r"\.0+$", "", text)
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10 and digits[0] == "7":
        return "+7" + digits
    return None


def parse_email(raw) -> tuple[str, str]:
    """Почта и предупреждение о её виде. Пустое предупреждение — всё чисто.

    Только о виде адреса: с логином ученика почта из таблицы не сверяется
    (фаза 71) — это его личная почта, а не вход в систему.
    """
    text = _text(raw)
    if not text:
        return "", ""
    if text.startswith("@"):
        return text, "адрес начинается с «@» — перед ним потерялось имя ящика"
    low = text.lower()
    if "@" not in low or "." not in low.split("@")[-1]:
        return text, "не похоже на адрес почты"
    domain = low.rsplit("@", 1)[-1]
    if domain.endswith(".con"):
        return text, "домен оканчивается на «.con» — похоже на опечатку в «.com»"
    return text, EMAIL_SUSPECTS.get(domain, "")


def parse_date(raw) -> tuple[dt.date | None, str]:
    """Дата из ячейки. Текст вместо даты — предупреждение, поле пустое."""
    if isinstance(raw, dt.datetime):
        return raw.date(), ""
    if isinstance(raw, dt.date):
        return raw, ""
    text = _text(raw)
    if not text:
        return None, ""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(text, pattern).date(), ""
        except ValueError:
            continue
    return None, f"записано словами: «{text[:60]}» — дату впишите руками"


def parse_score(raw, exam: str) -> tuple[Decimal | None, str]:
    """Балл экзамена по шкале из реестра доменов. Текст — пропуск с предупреждением."""
    from core.domains import scale_of

    text = _text(raw)
    if not text:
        return None, ""
    try:
        value = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None, f"в ячейке {exam} не балл, а текст: «{text[:60]}»"
    scale = scale_of(exam)
    if scale is None:
        return None, f"шкала {exam} неизвестна"
    if not scale.holds(value):
        return None, f"{exam} {value} не по шкале: от {scale.minimum} до {scale.maximum} шагом {scale.step}"
    return value, ""


def parse_gpa(raw) -> tuple[Decimal | None, str]:
    """Средний балл аттестата: 0–5, как в реестре у поля GPA."""
    text = _text(raw)
    if not text:
        return None, ""
    try:
        value = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None, f"в ячейке GPA не число, а текст: «{text[:60]}»"
    if not (Decimal("0") <= value <= Decimal("5")):
        return None, f"GPA {value} вне шкалы 0–5"
    return value, ""


def parse_link(raw) -> tuple[str, str]:
    """Ссылка на документ вне системы."""
    text = _text(raw)
    if not text:
        return "", ""
    if not text.lower().startswith(("http://", "https://")):
        return "", f"ссылка не похожа на адрес: «{text[:60]}»"
    return text, ""


def parse_cell(spec: ColumnSpec, raw) -> tuple[object, str, bool]:
    """Разобрать ячейку по типу колонки: (значение, предупреждение, ошибка ли).

    Ошибка — только у телефона: строку с неразборчивым номером человек
    должен увидеть на шаге проверки, остальное — предупреждение, и ячейка
    просто пропускается.
    """
    if spec.kind == PHONE:
        text = _text(raw)
        if not text:
            return None, "", False
        phone = parse_phone(text)
        if phone is None:
            return None, f"телефон «{text[:40]}» не разбирается", True
        return phone, "", False
    if spec.kind == EMAIL:
        value, warning = parse_email(raw)
        return value or None, f"{spec.title}: {warning}" if warning else "", False
    if spec.kind == DATE:
        value, warning = parse_date(raw)
        return value, f"{spec.title.lower()}: {warning}" if warning else "", False
    if spec.kind == SCORE:
        value, warning = parse_score(raw, spec.exam)
        return value, warning, False
    if spec.kind == GPA:
        value, warning = parse_gpa(raw)
        return value, warning, False
    if spec.kind == LINK:
        value, warning = parse_link(raw)
        return value or None, f"{spec.title}: {warning}" if warning else "", False
    if spec.kind in (PASSWORD, TEXT, NAME):
        text = _text(raw)
        return text or None, "", False
    return None, f"{spec.title}: тип «{spec.kind}» реестр разбирать не умеет", False


# --- Для документации ----------------------------------------------------------


def as_rows() -> list[dict]:
    """Реестр строками — из них собирается таблица в `ADMISSION_IMPORT.md`.

    Документация обязана совпадать с кодом: тест сверяет её с этим списком.
    """
    return [
        {
            "title": spec.title,
            "aliases": ", ".join(f"«{alias}»" for alias in spec.aliases),
            "domain": spec.domain_title,
            "kind": KIND_TITLES[spec.kind],
            "destination": spec.destination,
            "required": "да" if spec.required else "нет",
        }
        for spec in COLUMNS
    ]
