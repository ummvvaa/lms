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

Поля профилей пяти доменов, которые загружаются списком учеников с ключом
«почта или логин» (вкладка «Поля по CSV»), записаны здесь же, в
`FIELD_COLUMNS` (05.10.2026): какое поле, какого домена, как его называют
в файлах. До этого список таких полей и их сопоставление жили мимо реестра.
Тест сверяет его с профилями `core.domains`: поле профиля, которого здесь
нет, файлом не загружается.

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

from django.utils import translation
from django.utils.functional import lazy
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext

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
#: значение поля профиля: разбирается так же, как при вводе в карточке
#: (`core.audit.coerce`) — вариант из списка, да/нет, справочник, число в границах
VALUE = "value"

KIND_TITLES: dict[str, str] = {
    TEXT: gettext_lazy("текст"),
    PHONE: gettext_lazy("телефон"),
    EMAIL: gettext_lazy("почта"),
    DATE: gettext_lazy("дата"),
    SCORE: gettext_lazy("балл по шкале экзамена"),
    GPA: gettext_lazy("число 0–5"),
    LINK: gettext_lazy("ссылка"),
    PASSWORD: gettext_lazy("пароль"),
    NAME: gettext_lazy("ФИО"),
    VALUE: gettext_lazy("как в карточке: вариант из списка, да или нет, число в границах, дата, текст"),
}

# --- Куда ложится ---------------------------------------------------------------

PROFILE = "profile"  # профиль поступления
EXAM_PROFILE = "exam_profile"  # профиль экзаменов
ATTEMPT = "attempt"  # попытка экзамена
DOCUMENT = "document"  # документ-ссылка
CREDENTIAL = "credential"  # хранилище паролей
MATCH = "match"  # сопоставление с учеником, никуда не пишется
FIELD = "field"  # поле профиля любого домена: модель названа в записи

TARGET_TITLES: dict[str, str] = {
    PROFILE: gettext_lazy("профиль поступления"),
    EXAM_PROFILE: gettext_lazy("профиль экзаменов"),
    ATTEMPT: gettext_lazy("попытка экзамена"),
    DOCUMENT: gettext_lazy("документ-ссылка"),
    CREDENTIAL: gettext_lazy("хранилище паролей"),
    MATCH: gettext_lazy("сопоставление с учеником"),
    FIELD: gettext_lazy("поле профиля"),
}

#: Домены, в которые таблица поступления пишет **сверх своих**, от имени
#: владельца таблицы. Одна строка — одно исключение из правила «владелец
#: пишет только свои домены»: таблицу ведёт Асем, GPA и попытки в ней её
ADMISSION_TABLE_EXTRA_DOMAINS: tuple[str, ...] = ("exam",)


@dataclass(frozen=True)
class ColumnSpec:
    """Одна колонка таблицы: как найти, как разобрать, куда положить."""

    key: str
    #: заголовок колонки: он же заголовок шаблона и выгрузки — на языке
    #: того, кто выгружает; распознаётся на всех трёх (`header_variants`)
    title: str
    #: старые написания школы для распознавания — по-русски, без перевода
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
    #: модель профиля — для `FIELD`: `students.BehaviorProfile`
    model: str = ""

    @property
    def domain_title(self) -> str:
        from core.domains import DOMAINS

        return DOMAINS[self.domain].title if self.domain in DOMAINS else "—"

    @property
    def destination(self) -> str:
        """Куда ложится — словами для отчёта и документации."""
        if self.target in (PROFILE, EXAM_PROFILE):
            return _("{target}, поле «{field}»").format(target=TARGET_TITLES[self.target], field=self.field)
        if self.target == FIELD:
            return _("{target}, поле «{field}»").format(target=_model_title(self.model), field=self.field)
        if self.target == ATTEMPT:
            return f"{TARGET_TITLES[self.target]} {self.exam}-{self.slot}"
        if self.target == DOCUMENT:
            return f"{TARGET_TITLES[self.target]} «{self.doc_type}»"
        if self.target == CREDENTIAL:
            return f"{TARGET_TITLES[self.target]}, «{self.credential}»"
        return TARGET_TITLES[self.target]


#: Все колонки таблицы Асем — в порядке поиска по заголовкам
COLUMNS: tuple[ColumnSpec, ...] = (  # i18n-skip: синонимы заголовков школы — для распознавания, без перевода
    ColumnSpec("name", gettext_lazy("ФИО"), ("фио", "ф.и.о", "ученик", "студент"), NAME, "", MATCH, required=True),
    ColumnSpec(
        "phone",
        gettext_lazy("Номер телефона"),
        ("номер телефона", "телефон"),
        PHONE,
        "admission",
        PROFILE,
        "student_phone",
    ),
    ColumnSpec(
        "common_app_email",
        gettext_lazy("Электронный адрес Common App"),
        ("электронный адрес common app", "почта common app", "common app email"),
        EMAIL,
        "admission",
        PROFILE,
        "common_app_email",
    ),
    ColumnSpec(
        "common_app_password",
        gettext_lazy("Пароль от Common App"),
        ("пароль от common app", "пароль common app"),
        PASSWORD,
        "admission",
        CREDENTIAL,
        credential="common_app",
    ),
    ColumnSpec(
        "email_password",
        gettext_lazy("Пароль от эл. адреса"),
        ("пароль от эл", "пароль от почт", "пароль эл"),
        PASSWORD,
        "admission",
        CREDENTIAL,
        credential="email",
    ),
    # личная почта ученика — текст в карточке, с логином не связана (фаза 71)
    ColumnSpec(
        "email",
        gettext_lazy("Электронный адрес"),
        ("электронный адрес", "почта", "email", "e-mail"),
        EMAIL,
        "admission",
        PROFILE,
        "personal_email",
    ),
    ColumnSpec(
        "drive_folder",
        gettext_lazy("Ссылка на папку студента"),
        ("папку студента", "папка студента", "гугл драйв", "drive"),
        LINK,
        "admission",
        PROFILE,
        "drive_folder_url",
    ),
    ColumnSpec(
        "passport_link",
        gettext_lazy("Ссылка на паспорт"),
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
        gettext_lazy("Срок годности паспорта"),
        ("срок годности паспорта", "срок паспорта", "годност"),
        DATE,
        "admission",
        PROFILE,
        "passport_expires_at",
    ),
    ColumnSpec(
        "gpa", gettext_lazy("Средний GPA"), ("средний gpa", "gpa", "средний балл"), GPA, "exam", EXAM_PROFILE, "gpa"
    ),
    ColumnSpec(
        "ielts_1", gettext_lazy("IELTS-1"), ("ielts-1", "ielts 1"), SCORE, "exam", ATTEMPT, exam="IELTS", slot=1
    ),
    ColumnSpec(
        "ielts_2", gettext_lazy("IELTS-2"), ("ielts-2", "ielts 2"), SCORE, "exam", ATTEMPT, exam="IELTS", slot=2
    ),
    ColumnSpec(
        "ielts_3", gettext_lazy("IELTS-3"), ("ielts-3", "ielts 3"), SCORE, "exam", ATTEMPT, exam="IELTS", slot=3
    ),
    ColumnSpec("sat_1", gettext_lazy("SAT-1"), ("sat-1", "sat 1"), SCORE, "exam", ATTEMPT, exam="SAT", slot=1),
    ColumnSpec("sat_2", gettext_lazy("SAT-2"), ("sat-2", "sat 2"), SCORE, "exam", ATTEMPT, exam="SAT", slot=2),
    ColumnSpec("sat_3", gettext_lazy("SAT-3"), ("sat-3", "sat 3"), SCORE, "exam", ATTEMPT, exam="SAT", slot=3),
    ColumnSpec(
        "transcript_link",
        gettext_lazy("Ссылка на табель"),
        ("ссылка на табел", "табел"),
        LINK,
        "documents",
        DOCUMENT,
        doc_type="transcript",
    ),
    ColumnSpec(
        "recommendation_link",
        gettext_lazy("Ссылка на рек. письмо"),
        ("рек. письмо", "рекоменд"),
        LINK,
        "documents",
        DOCUMENT,
        doc_type="recommendation",
    ),
)

# --- Поля профилей: файл со списком учеников ---------------------------------


def _model_title(label: str) -> str:
    """«Профиль дисциплины» — имя модели профиля словами, из самой модели."""
    from django.apps import apps

    return str(apps.get_model(label)._meta.verbose_name).lower()


def _field_title(label: str, name: str) -> str:
    from core.labels import field_title

    return field_title(label, name)


#: заголовок колонки поля — его название из `core.domains`: один факт в одном месте
_lazy_field_title = lazy(_field_title, str)


def _field(key: str, model: str, name: str, domain: str, *aliases: str) -> ColumnSpec:
    label = f"students.{model}"
    return ColumnSpec(key, _lazy_field_title(label, name), aliases, VALUE, domain, FIELD, name, model=label)


#: Поля профилей, которых нет среди колонок таблицы поступления. Ключ ученика
#: в таком файле — почта или логин, сопоставление колонок человек правит руками
#: (`students.import_reading`); синонимы — как колонку называют в школьных списках
FIELD_COLUMNS: tuple[ColumnSpec, ...] = (  # i18n-skip: синонимы заголовков школы — для распознавания, без перевода
    # дисциплина
    _field("attendance_percent", "BehaviorProfile", "attendance_percent", "behavior", "посещаемость", "посещаемость %"),
    _field("remarks_count", "BehaviorProfile", "remarks_count", "behavior", "замечания", "замечаний"),
    _field("behavior_status", "BehaviorProfile", "status", "behavior", "статус дисциплины", "дисциплина"),
    _field("behavior_comment", "BehaviorProfile", "comment", "behavior", "комментарий по дисциплине"),
    # поступление
    _field("target_country", "AdmissionProfile", "target_country", "admission", "страна", "целевая страна"),
    _field("target_major", "AdmissionProfile", "target_major", "admission", "специальность", "направление"),
    _field("target_level", "AdmissionProfile", "target_level", "admission", "уровень", "уровень вузов"),
    _field("has_common_app", "AdmissionProfile", "has_common_app", "admission", "common app", "есть common app"),
    _field(
        "has_application_account",
        "AdmissionProfile",
        "has_application_account",
        "admission",
        "аккаунт подачи",
        "есть аккаунт подачи",
    ),
    _field("admission_status", "AdmissionProfile", "status", "admission", "статус поступления", "статус a/b/c"),
    # экзамены: текущий балл и цель — поля профиля, попытки IELTS-n и SAT-n — колонки таблицы выше
    _field("ielts_current", "ExamProfile", "ielts_current", "exam", "ielts", "ielts текущий"),
    _field("ielts_target", "ExamProfile", "ielts_target", "exam", "ielts цель", "цель ielts"),
    _field("sat_current", "ExamProfile", "sat_current", "exam", "sat", "sat текущий"),
    _field("sat_target", "ExamProfile", "sat_target", "exam", "sat цель", "цель sat"),
    _field("hours_per_week", "ExamProfile", "hours_per_week", "exam", "часов в неделю", "часы"),
    _field("exam_teacher", "ExamProfile", "teacher", "exam", "учитель", "преподаватель"),
    _field("next_mock_date", "ExamProfile", "next_mock_date", "exam", "следующий mock test", "дата mock test"),
    # таланты
    _field("main_track", "TalentProfile", "main_track", "talent", "трек", "основной трек"),
    _field("portfolio_status", "TalentProfile", "portfolio_status", "talent", "портфолио", "статус портфолио"),
    _field("talent_comment", "TalentProfile", "comment", "talent", "комментарий по талантам"),
    # спорт
    _field("sport_type", "SportProfile", "sport_type", "sport", "вид спорта", "спорт"),
    _field("sport_level", "SportProfile", "level", "sport", "уровень в спорте", "спортивный уровень"),
    _field("sport_rank", "SportProfile", "rank", "sport", "разряд", "звание"),
    _field("leadership_role", "SportProfile", "leadership_role", "sport", "роль в команде", "капитан"),
)


def field_target(spec: ColumnSpec) -> str:
    """Поле профиля, в которое ложится колонка: `students.ExamProfile.gpa`; не поле — пусто."""
    if spec.target == PROFILE:
        return f"students.AdmissionProfile.{spec.field}"
    if spec.target == EXAM_PROFILE:
        return f"students.ExamProfile.{spec.field}"
    if spec.target == FIELD:
        return f"{spec.model}.{spec.field}"
    return ""


#: Поле профиля → запись реестра: всё, что загружается файлом со списком учеников.
#: Шесть полей пишет и таблица поступления (телефон, почты, папка, срок паспорта, GPA)
FIELD_TARGETS: dict[str, ColumnSpec] = {
    field_target(spec): spec for spec in (*COLUMNS, *FIELD_COLUMNS) if field_target(spec)
}

BY_KEY: dict[str, ColumnSpec] = {spec.key: spec for spec in (*COLUMNS, *FIELD_COLUMNS)}

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


def title_variants(title) -> list[str]:
    """Заголовок на всех языках интерфейса: русский исходник и его переводы.

    Выгрузка пишет заголовки на языке того, кто выгружает, и файл,
    выгруженный на казахском, должен загружаться обратно. Поэтому
    распознавание сверяет заголовок файла с каждым переводом, а не
    только с тем, на котором говорит загружающий.
    """
    from core.i18n import INTERFACE_LANGUAGES, translate

    # ленивая строка на русском — это её исходник: русского каталога нет
    with translation.override("ru"):
        source = str(title)
    out: list[str] = []
    for lang in INTERFACE_LANGUAGES:
        text = translate(lang, source) if lang != "ru" else source
        if text and text not in out:
            out.append(text)
    return out


def header_variants(title) -> set[str]:
    """Нормализованные написания заголовка на трёх языках — для сравнения с файлом."""
    return {key for key in (_header_key(text) for text in title_variants(title)) if key}


def read_columns(header: list[str]) -> dict[str, int]:
    """Сопоставить заголовки листа с колонками реестра.

    Один заголовок достаётся одной колонке: иначе «Электронный адрес»
    подошёл бы и личной почте, и почте Common App. Порядок — порядок
    реестра, и он это столкновение и разводит.

    Колонка узнаётся по старым написаниям школы (`aliases`) и по своему
    заголовку на любом из трёх языков: файл, выгруженный шаблоном на
    казахском или английском, читается так же, как русский.
    """
    taken: set[int] = set()
    found: dict[str, int] = {}
    keys = [_header_key(title) for title in header]
    for spec in COLUMNS:
        names = (*spec.aliases, *sorted(header_variants(spec.title)))
        for index, key in enumerate(keys):
            if index in taken or not key:
                continue
            if any(name in key for name in names):
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


#: Кому открыт мастер импорта. Решение владельца после разбора кабинетов:
#: кураторы и директора вносят руками, файлом работают администратор
#: и Кымбат (у неё же пробники и банк заданий). Какие домены человек
#: вправе заполнить, по-прежнему говорит `writable_domains` — здесь только
#: вход; код разбора для остальных ролей не удалён
WIZARD_ROLES: tuple[str, ...] = ("admin", "director_exam")


def may_open_wizard(user) -> bool:
    return getattr(user, "role", "") in WIZARD_ROLES


def writable_domains(user) -> set[str]:
    """Какие домены этот человек вправе заполнять импортом.

    Администратор — любые. Владелец домена — свои и то, что реестр
    отдал его таблице сверх своих (`ADMISSION_TABLE_EXTRA_DOMAINS`).
    Куратор — домены, где он вносит данные за ученика, по своим группам.
    Ученик — ничего: импорт не его инструмент.
    """
    from core.domains import CURATOR_ENTER_DOMAINS, DOMAINS, ROLE_ADMIN, ROLE_CURATOR, domains_of_role

    role = getattr(user, "role", "")
    if role == ROLE_ADMIN:
        return set(DOMAINS)
    if role == ROLE_CURATOR:
        # куратор заполняет импортом те же домены, где вносит за ученика
        # руками; границу «свои группы» держит разбор листов
        return set(CURATOR_ENTER_DOMAINS)
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
    "gmail.ru": gettext_lazy("домен «gmail.ru» — у Gmail такого нет, вероятно «gmail.com»"),
    "gmail.co": gettext_lazy("домен «gmail.co» — похоже на обрезанный «gmail.com»"),
    "mail.ru.com": gettext_lazy("домен «mail.ru.com» — вероятно «mail.ru»"),
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
        return text, _("адрес начинается с «@» — перед ним потерялось имя ящика")
    low = text.lower()
    if "@" not in low or "." not in low.split("@")[-1]:
        return text, _("не похоже на адрес почты")
    domain = low.rsplit("@", 1)[-1]
    if domain.endswith(".con"):
        return text, _("домен оканчивается на «.con» — похоже на опечатку в «.com»")
    return text, str(EMAIL_SUSPECTS.get(domain, ""))


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
    return None, _("записано словами: «{text}» — дату впишите руками").format(text=text[:60])


def parse_score(raw, exam: str) -> tuple[Decimal | None, str]:
    """Балл экзамена по шкале из реестра доменов. Текст — пропуск с предупреждением."""
    from core.domains import scale_of

    text = _text(raw)
    if not text:
        return None, ""
    try:
        value = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None, _("в ячейке {exam} не балл, а текст: «{text}»").format(exam=exam, text=text[:60])
    scale = scale_of(exam)
    if scale is None:
        return None, _("шкала {exam} неизвестна").format(exam=exam)
    if not scale.holds(value):
        return None, _("{exam} {value} не по шкале: от {minimum} до {maximum} шагом {step}").format(
            exam=exam, value=value, minimum=scale.minimum, maximum=scale.maximum, step=scale.step
        )
    return value, ""


def parse_gpa(raw) -> tuple[Decimal | None, str]:
    """Средний балл аттестата: 0–5, как в реестре у поля GPA."""
    text = _text(raw)
    if not text:
        return None, ""
    try:
        value = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None, _("в ячейке GPA не число, а текст: «{text}»").format(text=text[:60])
    if not (Decimal("0") <= value <= Decimal("5")):
        return None, _("GPA {value} вне шкалы 0–5").format(value=value)
    return value, ""


def parse_link(raw) -> tuple[str, str]:
    """Ссылка на документ вне системы."""
    text = _text(raw)
    if not text:
        return "", ""
    if not text.lower().startswith(("http://", "https://")):
        return "", _("ссылка не похожа на адрес: «{text}»").format(text=text[:60])
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
            return None, _("телефон «{text}» не разбирается").format(text=text[:40]), True
        return phone, "", False
    if spec.kind == EMAIL:
        value, warning = parse_email(raw)
        return value or None, _column_warning(spec.title, warning), False
    if spec.kind == DATE:
        value, warning = parse_date(raw)
        return value, _column_warning(str(spec.title).lower(), warning), False
    if spec.kind == SCORE:
        value, warning = parse_score(raw, spec.exam)
        return value, warning, False
    if spec.kind == GPA:
        value, warning = parse_gpa(raw)
        return value, warning, False
    if spec.kind == LINK:
        value, warning = parse_link(raw)
        return value or None, _column_warning(spec.title, warning), False
    if spec.kind in (PASSWORD, TEXT, NAME):
        text = _text(raw)
        return text or None, "", False
    return None, _("{column}: тип «{kind}» реестр разбирать не умеет").format(column=spec.title, kind=spec.kind), False


def _column_warning(column, warning: str) -> str:
    """«Колонка: что не так» — предупреждение с названием колонки; нет предупреждения — пусто."""
    if not warning:
        return ""
    return _("{column}: {warning}").format(column=column, warning=warning)


# --- Для документации ----------------------------------------------------------


def as_rows(columns: tuple[ColumnSpec, ...] = COLUMNS) -> list[dict]:
    """Реестр строками — из них собираются таблицы в `guides/`.

    `COLUMNS` — таблица поступления (`ADMISSION_IMPORT.md`), `FIELD_COLUMNS` —
    поля профилей (`FIELDS_IMPORT.md`). Документация обязана совпадать
    с кодом: тест сверяет её с этим списком.
    """
    return [
        {
            "title": str(spec.title),
            "aliases": ", ".join(f"«{alias}»" for alias in spec.aliases),
            "domain": spec.domain_title,
            "kind": str(KIND_TITLES[spec.kind]),
            "destination": spec.destination,
            "required": pgettext("answer", "да") if spec.required else pgettext("answer", "нет"),
        }
        for spec in columns
    ]
