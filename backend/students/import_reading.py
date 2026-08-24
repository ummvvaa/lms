"""Разбор загруженного файла: что в нём и что из этого будет загружено.

Раньше директор видел техническую таблицу соответствий: колонка файла →
`students.ExamProfile.ielts_current`. Прочитать по ней, что произойдёт
с данными двухсот пятидесяти детей, невозможно.

Теперь перед применением он читает объяснение обычными словами: какие
колонки узнаны и куда лягут, какие пропущены и почему, сколько строк
привяжется к ученикам и что в файле выглядит подозрительно.

Разделение труда жёсткое:

* **колонки сопоставляют** правила, а модель — предлагает; её вариант
  подставляется в форму, но директор переназначает любую колонку сам;
* **подозрительное ищет код**: диапазоны, пустые ячейки, дубли и разные
  форматы дат считаются точно, и номер строки в них настоящий. Модели
  такие вещи доверять нельзя — она ошибётся на одной строке из ста,
  и это будет незаметно;
* **формулирует модель** — из уже посчитанных фактов. Нет ключа —
  тот же экран собирается правилами, суше и с пометкой об этом.

В модель уходят только заголовки и несколько строк-образцов, а имена
учеников заменяются номерами: весь файл отправлять и дороже, и незачем.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.domains import DOMAINS, PROFILE_MODELS, domain_of_role, iter_field_specs, spec_of_field
from students.models import Student

#: Сколько строк-образцов уходит в модель. Трёх хватает, чтобы понять
#: формат колонки, и мало, чтобы это стоило денег.
SAMPLE_ROWS = 3

#: Колонка с ключом ученика: по ней строка привязывается к карточке.
STUDENT_KEY = "student"

#: Как называют колонку с почтой в школьных списках.
STUDENT_HINTS = ("почта", "email", "e-mail", "мейл", "логин", "фио", "ученик", "student")

#: Сколько подозрительных строк называем поимённо. Дальше — числом:
#: список на сто номеров никто не читает.
MAX_NAMED_ROWS = 5


@dataclass
class Column:
    """Одна колонка файла после разбора."""

    title: str
    index: int
    #: `students.ExamProfile.ielts_current`, `student` или пусто
    target: str = ""
    field_title: str = ""
    #: почему пропущена: unknown | foreign_domain | пусто
    skip_reason: str = ""
    foreign_domain: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "index": self.index,
            "target": self.target,
            "field_title": self.field_title,
            "skip_reason": self.skip_reason,
            "foreign_domain": self.foreign_domain,
        }


@dataclass
class Reading:
    """Разбор файла целиком — то, из чего собирается экран предпросмотра."""

    columns: list[Column] = field(default_factory=list)
    total_rows: int = 0
    matched: int = 0
    unmatched: list[str] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""
    offline: bool = True
    note: str = ""

    @property
    def mapping(self) -> dict[str, str]:
        """Сопоставление для `build_preview`: колонка → куда класть."""
        return {column.title: column.target for column in self.columns if column.target}

    def as_dict(self) -> dict[str, Any]:
        return {
            "columns": [column.as_dict() for column in self.columns],
            "mapping": self.mapping,
            "total_rows": self.total_rows,
            "matched": self.matched,
            "unmatched": self.unmatched[:MAX_NAMED_ROWS],
            "unmatched_count": len(self.unmatched),
            "warnings": self.warnings,
            "text": self.text,
            "offline": self.offline,
            "note": self.note,
        }


# --- Каталог полей ---------------------------------------------------------


def catalogue(role: str) -> list[dict[str, str]]:
    """Поля, в которые этой роли можно писать. Из реестра, не из вьюхи.

    Только профильные модели: файл со списком учеников кладёт значения
    в их профили. Записи справочника (вуз, программа, требования) грузятся
    своим импортом и в этот список попадать не должны.
    """
    domain = domain_of_role(role)
    rows: list[dict[str, str]] = []
    for current, model, spec in iter_field_specs():
        if model.label not in PROFILE_MODELS:
            continue
        if domain is not None and current.code != domain.code:
            continue
        rows.append(
            {
                "target": f"{model.label}.{spec.name}",
                "title": spec.title,
                "short": spec.short or spec.title,
                "range": spec.range_hint,
            }
        )
    return rows


def _domain_of_target(target: str) -> str:
    label, _, name = target.rpartition(".")
    for domain in DOMAINS.values():
        for model in domain.models:
            if model.label == label and any(f.name == name for f in model.fields):
                return domain.code
    return ""


# --- Сопоставление правилами ----------------------------------------------


def _normalize(text: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> set[str]:
    return {word for word in _normalize(text).split() if len(word) > 1}


def _score(column_title: str, label: str) -> float:
    """Насколько заголовок колонки похож на подпись поля.

    Считаем по словам, а не по вхождению строки: «IELTS текущий» и
    «Минимальный балл IELTS» пересекаются подстрокой, но значат разное,
    и такая ошибка кладёт чужие числа в чужую колонку.
    """
    left, right = _tokens(column_title), _tokens(label)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return len(left & right) / len(left | right)


#: Ниже этого совпадение считаем случайным. Половина общих слов — это
#: «Специальность» против «Целевая специальность», и это то, что нужно.
MATCH_THRESHOLD = 0.5


def rules_mapping(header: list[str], role: str) -> list[Column]:
    """Сопоставить колонки по названиям полей из реестра.

    Сначала ищем среди своих полей, потом среди чужих: колонка, похожая
    и на своё поле, и на чужое, должна лечь в своё — иначе директор
    увидит «эту колонку ведёт другой домен» там, где ведёт её он сам.
    """
    own = {row["target"] for row in catalogue(role)}
    # ищем только среди профилей учеников: в файле со списком класса
    # не может быть колонки про требования вуза, а лишний кандидат
    # уводит сопоставление не туда
    everything = {
        f"{model.label}.{spec.name}": (domain.code, spec)
        for domain, model, spec in iter_field_specs()
        if model.label in PROFILE_MODELS
    }

    columns: list[Column] = []
    used: set[str] = set()
    for index, title in enumerate(header):
        column = Column(title=title, index=index)
        low = _normalize(title)
        if not low:
            columns.append(column)
            continue

        if any(hint in low for hint in STUDENT_HINTS):
            column.target = STUDENT_KEY
            column.field_title = "ученик — по этой колонке ищем карточку"
            columns.append(column)
            continue

        best, best_score = "", 0.0
        for target, (_domain_code, spec) in everything.items():
            if target in used:
                continue
            score = max(_score(title, spec.title), _score(title, spec.short or spec.title))
            # своё поле при равном счёте выигрывает у чужого
            if target in own:
                score += 0.01
            if score > best_score:
                best, best_score = target, score

        if not best or best_score < MATCH_THRESHOLD:
            column.skip_reason = "unknown"
            columns.append(column)
            continue

        domain_code, spec = everything[best]
        if best not in own:
            column.skip_reason = "foreign_domain"
            column.foreign_domain = DOMAINS[domain_code].title if domain_code in DOMAINS else domain_code
            column.field_title = spec.title
            columns.append(column)
            continue

        used.add(best)
        column.target = best
        column.field_title = spec.title
        columns.append(column)

    return columns


# --- Проверки значений: считает код, а не модель ---------------------------

DATE_FORMATS = (
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "ГГГГ-ММ-ДД"),
    (re.compile(r"^\d{2}\.\d{2}\.\d{4}$"), "ДД.ММ.ГГГГ"),
    (re.compile(r"^\d{2}/\d{2}/\d{4}$"), "ДД/ММ/ГГГГ"),
)


def _as_number(value: str) -> float | None:
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def inspect(columns: list[Column], rows: list[list[str]]) -> list[dict[str, Any]]:
    """Что в файле выглядит подозрительно — с настоящими номерами строк.

    Номер строки считается от единицы вместе с заголовком: человек
    открывает файл в Excel и ищет ту же строку, что видит на экране.
    """
    warnings: list[dict[str, Any]] = []

    for column in columns:
        if not column.target or column.target == STUDENT_KEY:
            continue
        label, _, name = column.target.rpartition(".")
        try:
            spec = spec_of_field(label, name)
        except Exception:  # поля могло не оказаться — тогда просто не проверяем
            continue

        out_of_range: list[int] = []
        empty: list[int] = []
        formats: dict[str, int] = {}

        for number, row in enumerate(rows, start=2):
            raw = (row[column.index] if column.index < len(row) else "") or ""
            raw = raw.strip()
            if not raw:
                empty.append(number)
                continue

            value = _as_number(raw)
            if value is not None and (spec.minimum is not None or spec.maximum is not None):
                if (spec.minimum is not None and value < spec.minimum) or (
                    spec.maximum is not None and value > spec.maximum
                ):
                    out_of_range.append(number)

            for pattern, title in DATE_FORMATS:
                if pattern.match(raw):
                    formats[title] = formats.get(title, 0) + 1
                    break

        if out_of_range:
            warnings.append(
                {
                    "kind": "out_of_range",
                    "column": column.title,
                    "field_title": spec.title,
                    "rows": out_of_range[:MAX_NAMED_ROWS],
                    "count": len(out_of_range),
                    "text": (
                        f"«{column.title}»: значение вне допустимого ({spec.range_hint}) "
                        f"в {_rows_phrase(out_of_range)}"
                    ),
                }
            )
        if empty and len(empty) < len(rows):
            warnings.append(
                {
                    "kind": "empty",
                    "column": column.title,
                    "field_title": spec.title,
                    "rows": empty[:MAX_NAMED_ROWS],
                    "count": len(empty),
                    "text": f"«{column.title}»: пусто в {_rows_phrase(empty)} — эти строки не изменятся",
                }
            )
        if len(formats) > 1:
            names = ", ".join(sorted(formats))
            warnings.append(
                {
                    "kind": "mixed_dates",
                    "column": column.title,
                    "field_title": spec.title,
                    "rows": [],
                    "count": len(formats),
                    "text": f"«{column.title}»: в одном столбце разные форматы дат ({names}) — проверьте файл",
                }
            )

    duplicates = _duplicate_rows(columns, rows)
    if duplicates:
        warnings.append(
            {
                "kind": "duplicates",
                "column": "",
                "field_title": "",
                "rows": duplicates[:MAX_NAMED_ROWS],
                "count": len(duplicates),
                "text": f"Один и тот же ученик встречается дважды: {_rows_phrase(duplicates)}",
            }
        )
    return warnings


def _rows_phrase(numbers: list[int]) -> str:
    """«строках 12, 30 и 41» или «строке 12» — по-русски, не списком."""
    named = [str(number) for number in numbers[:MAX_NAMED_ROWS]]
    tail = f" и ещё {len(numbers) - MAX_NAMED_ROWS}" if len(numbers) > MAX_NAMED_ROWS else ""
    if len(named) == 1:
        return f"строке {named[0]}{tail}"
    return "строках " + ", ".join(named[:-1]) + " и " + named[-1] + tail


def _duplicate_rows(columns: list[Column], rows: list[list[str]]) -> list[int]:
    key = next((column for column in columns if column.target == STUDENT_KEY), None)
    if key is None:
        return []
    seen: dict[str, int] = {}
    doubled: list[int] = []
    for number, row in enumerate(rows, start=2):
        value = (row[key.index] if key.index < len(row) else "").strip().lower()
        if not value:
            continue
        if value in seen:
            doubled.append(number)
        else:
            seen[value] = number
    return doubled


def _match_students(columns: list[Column], rows: list[list[str]]) -> tuple[int, list[str]]:
    """Сколько строк привяжется к карточкам и кто не нашёлся."""
    key = next((column for column in columns if column.target == STUDENT_KEY), None)
    if key is None:
        return 0, []

    values = [(row[key.index] if key.index < len(row) else "").strip().lower() for row in rows]
    known = {
        value.lower()
        for value in Student.objects.filter(email__in=[v for v in values if v]).values_list("email", flat=True)
    }
    matched = sum(1 for value in values if value and value in known)
    missing = [value for value in values if value and value not in known]
    return matched, missing


# --- Сборка объяснения -----------------------------------------------------


def read(
    *,
    header: list[str],
    rows: list[list[str]],
    role: str,
    actor=None,
    mapping: dict[str, str] | None = None,
) -> Reading:
    """Прочитать файл и объяснить, что будет загружено.

    `mapping` — сопоставление, которое директор уже поправил руками.
    Оно всегда главнее: модель предлагает только тогда, когда человек
    ещё ничего не выбрал.
    """
    if mapping:
        columns = _columns_from_mapping(header, mapping, role)
    else:
        columns = rules_mapping(header, role)
        columns = _ask_model_for_mapping(columns, rows, role, actor)

    reading = Reading(columns=columns, total_rows=len(rows))
    reading.matched, reading.unmatched = _match_students(columns, rows)
    reading.warnings = inspect(columns, rows)
    reading.text, reading.offline, reading.note = _explain(reading, role=role, actor=actor, rows=rows)
    return reading


def _columns_from_mapping(header: list[str], mapping: dict[str, str], role: str) -> list[Column]:
    """Колонки по выбору человека: что он назначил, то и грузим."""
    own = {row["target"]: row for row in catalogue(role)}
    columns: list[Column] = []
    for index, title in enumerate(header):
        column = Column(title=title, index=index)
        target = (mapping.get(title) or "").strip()
        if target == STUDENT_KEY:
            column.target = STUDENT_KEY
            column.field_title = "ученик — по этой колонке ищем карточку"
        elif target in own:
            column.target = target
            column.field_title = own[target]["title"]
        elif target:
            # человек выбрал поле чужого домена: применение его отбросит,
            # и сказать об этом надо здесь, а не после загрузки
            column.skip_reason = "foreign_domain"
            code = _domain_of_target(target)
            column.foreign_domain = DOMAINS[code].title if code in DOMAINS else code
        else:
            column.skip_reason = "unknown"
        columns.append(column)
    return columns


def _facts(reading: Reading) -> str:
    """Факты для модели — те же, что лягут в сухой текст правилами."""
    lines = [f"Строк в файле: {reading.total_rows}."]
    loaded = [c for c in reading.columns if c.target and c.target != STUDENT_KEY]
    if loaded:
        lines.append("Загружу: " + ", ".join(f"«{c.title}» → {c.field_title}" for c in loaded) + ".")
    foreign = [c for c in reading.columns if c.skip_reason == "foreign_domain"]
    for column in foreign:
        lines.append(
            f"Колонку «{column.title}» пропущу: поле «{column.field_title}» ведёт домен «{column.foreign_domain}»."
        )
    unknown = [c for c in reading.columns if c.skip_reason == "unknown"]
    if unknown:
        lines.append("Не распознал колонки: " + ", ".join(f"«{c.title}»" for c in unknown) + ".")
    lines.append(f"Привяжется к существующим ученикам строк: {reading.matched}.")
    if reading.unmatched:
        lines.append(f"Не нашлись в базе: {len(reading.unmatched)}.")
    for warning in reading.warnings:
        lines.append(warning["text"] + ".")
    return "\n".join(lines)


RULES = """Ты объясняешь директору школы, что произойдёт при загрузке файла.

Тебе передают посчитанные факты. Пересказать их надо так, как сказал бы
коллега: тремя-пятью предложениями, без списков и без канцелярита.

Правила, нарушать нельзя:
- опирайся ТОЛЬКО на переданные факты, ничего не добавляй от себя;
- номера строк повторяй ровно те, что переданы, — по ним человек пойдёт
  в файл проверять;
- не обещай, что данные верные: ты видишь три строки из файла, а не весь;
- ничего не советуй применять или не применять — решает человек."""


def _explain(reading: Reading, *, role: str, actor=None, rows: list[list[str]]) -> tuple[str, bool, str]:
    """Текст объяснения: моделью, а без ключа — правилами."""
    facts = _facts(reading)
    from suggestions.llm import LLMUnavailable, complete

    sample = _sample_for_model(reading, rows)
    try:
        answer = complete(
            system=RULES,
            user=f"Факты:\n{facts}\n\nОбразцы строк (имена заменены номерами):\n{sample}",
            purpose="import_reading",
            actor=actor,
            role=role,
            max_tokens=500,
        )
    except LLMUnavailable:
        return facts, True, _simple_note()

    text = (answer.content or "").strip()
    if not text:
        return facts, True, _simple_note()
    return text, False, ""


def _simple_note() -> str:
    from suggestions.assistant import _simple_mode_note

    return _simple_mode_note()


def _sample_for_model(reading: Reading, rows: list[list[str]]) -> str:
    """Несколько строк файла с обезличенным ключом ученика.

    Имя и почта заменяются номером: модель разбирает формат колонок,
    а не читает список детей.
    """
    key = next((column for column in reading.columns if column.target == STUDENT_KEY), None)
    lines = []
    for number, row in enumerate(rows[:SAMPLE_ROWS], start=1):
        cells = []
        for index, value in enumerate(row):
            if key is not None and index == key.index:
                cells.append(f"ученик {number}")
            else:
                cells.append(str(value))
        lines.append("; ".join(cells))
    return "\n".join(lines)


def _ask_model_for_mapping(columns: list[Column], rows: list[list[str]], role: str, actor) -> list[Column]:
    """Спросить модель про колонки, которые правила не узнали.

    Ответ модели — предложение: он подставляется в форму, а директор
    переназначает любую колонку сам. Поля чужого домена сюда не попадают
    вовсе — их состав берётся из реестра по роли.
    """
    unknown = [column for column in columns if column.skip_reason == "unknown"]
    if not unknown:
        return columns

    from suggestions.llm import LLMUnavailable, complete

    fields = catalogue(role)
    if not fields:
        return columns

    schema = {
        "type": "object",
        "properties": {
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "заголовок колонки из файла"},
                        "target": {"type": "string", "description": "поле из списка или пусто"},
                    },
                    "required": ["title"],
                },
            }
        },
        "required": ["columns"],
    }
    catalogue_text = "\n".join(f"{row['target']} — {row['title']}" for row in fields)
    unknown_text = "\n".join(f"«{column.title}»" for column in unknown)

    try:
        answer = complete(
            system=(
                "Ты сопоставляешь колонки школьного файла с полями системы.\n"
                "Правила: выбирай только из переданного списка полей; если подходящего "
                "нет — оставь `target` пустым. Ничего не выдумывай: неверное "
                "сопоставление испортит данные, а пустое поле человек заполнит сам."
            ),
            user=(
                f"Поля системы:\n{catalogue_text}\n\n"
                f"Нераспознанные колонки:\n{unknown_text}\n\n"
                f"Образцы строк:\n{_sample_for_model(Reading(columns=columns), rows)}"
            ),
            purpose="import_mapping",
            actor=actor,
            role=role,
            schema=schema,
            max_tokens=600,
        )
    except LLMUnavailable:
        return columns

    allowed = {row["target"]: row for row in fields}
    taken = {column.target for column in columns if column.target}
    for guess in (answer.parsed or {}).get("columns") or []:
        # схема схемой, а ответ приходит какой пришёл: модель может
        # вернуть список строк вместо объектов. Пропускаем молча —
        # сопоставление и без её подсказки останется рабочим
        if not isinstance(guess, dict):
            continue
        title = (guess.get("title") or "").strip().strip("«»")
        target = (guess.get("target") or "").strip()
        if not title or target not in allowed or target in taken:
            continue
        for column in columns:
            if column.title == title and column.skip_reason == "unknown":
                column.target = target
                column.field_title = allowed[target]["title"]
                column.skip_reason = ""
                taken.add(target)
                break
    return columns
