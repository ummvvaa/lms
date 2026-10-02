"""Состав подгрупп английского из файла школы (решение владельца, 02.10.2026).

Книга расписания говорит, из каких групп собрана подгруппа потока
(EEP-8-1 — из четырёх групп восьмой параллели), но не кто в ней учится.
Без состава урок такой подгруппы стоит у всех групп потока, а ученик
своего английского не видит. Файл школы — список «подгруппа — ученик —
группа»; по нему у каждой подгруппы появляется состав с даты.

Правила:

- подгруппа — по названию, только подгруппа внутри потока; кириллица,
  похожая на латиницу («ЕЕР-8-1», «ГЕ-10.1-2»), и пробелы не мешают;
- ученик — по ФИО среди учеников своей группы (колонка «Группа» или группа
  в скобках после ФИО) или, если её нет, среди групп потока подгруппы;
  неуверенное совпадение — ошибка строки, молча не угадывается. Ошибка
  говорит, что написать: у тёзок — группу в скобках из их групп, ученику
  другой группы — что подгруппа собрана не из неё, ненайденному — похожих
  из тех, кого файл ещё никуда не поставил. Группа в скобках не из
  подгруппы — явное слово файла: ученик записывается, урок подгруппы
  встаёт и в неделю его группы (предупреждение);
- у ученика одна подгруппа английского — EEP или GE: второй раз в файле —
  ошибка, кроме той же записи дважды в одной подгруппе (повтор учитывается
  один раз, предупреждение); подгруппы потоков из одного набора групп
  (EEP-8 и GE-8) взаимоисключающие, и при применении ученик уходит
  из прежней, даже если её нет в файле;
- любая ошибка строки останавливает применение: состав либо верный
  целиком, либо не пишется вовсе;
- ученики групп потока, которых нет в файле, и подгруппы, которых нет
  в файле, — предупреждения: их состав не трогается.

Раскладок файла две, формат для людей — `guides/SUBGROUP_MEMBERS.md`:

- **блоки, как ведёт их школа**: над нумерованным списком ФИО — заголовок
  «учитель, уровень, кабинет» («Тестова А, A2, 203 каб»), блоки стоят рядом
  и друг под другом, лист — параллель. Подгруппа блока — по названию
  в заголовке, если оно есть, иначе по кабинету среди подгрупп потоков;
  кабинет есть у нескольких подгрупп (201 — в 11.1 и 11.2) — решают
  группы учеников блока. Кабинеты расписания загрузка не меняет: кабинет
  в файле только указывает подгруппу. Лист без таких блоков (тесты,
  уровни, списки класса) пропускается и называется в отчёте;
- **колонки**: строка заголовков в первых десяти строках листа —
  «Подгруппа», «ФИО» (или «Фамилия» и «Имя»), необязательная «Группа».
  Лист без колонки «Подгруппа», названный как подгруппа («EEP-8-1»), —
  состав этой подгруппы.
"""

from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass, field

from django.db import transaction
from django.utils.translation import gettext as _

from academics import cache
from academics.calendar import today
from academics.cohorts import group_ids_of, set_members
from academics.models import Cohort, CohortKind, CohortMembership, Course
from students.models import Student, StudyGroup

#: где искать строку заголовков
HEADER_ROWS = 10

#: метка пропущенного листа среди находок чтения: в отчёт он идёт не ошибкой
SKIPPED = "\x00skip:"

#: кириллица, которую пишут вместо латиницы в названиях подгрупп («ЕЕР», «ГЕ»)
LOOKALIKE = str.maketrans("АВГЕКМНОРСТХ", "ABGEKMHOPCTX")  # i18n-skip: буквы для сравнения названий


def subgroup_key(name: str) -> str:
    """«ЕЕР 8 – 1» → «EEP8-1»: регистр, пробелы, тире и кириллица не мешают."""
    text = re.sub(r"[‐‑‒–—―]", "-", str(name or "").upper().translate(LOOKALIKE))
    return re.sub(r"\s+", "", text)


@dataclass
class Block:
    """Блок школы: заголовок «учитель, уровень, кабинет» и нумерованный список под ним."""

    sheet: str
    row: int
    header: str
    room: str
    #: название подгруппы, если оно написано в заголовке
    named: str = ""
    cohort: Cohort | None = None
    error: str = ""
    lines: list[Line] = field(default_factory=list)

    @property
    def where(self) -> str:
        return _("«{sheet}», блок «{header}»").format(sheet=self.sheet, header=self.header)


@dataclass
class Line:
    """Строка файла: что написано и чем это оказалось."""

    sheet: str
    row: int
    subgroup: str
    name: str
    group: str
    cohort: Cohort | None = None
    student: Student | None = None
    error: str = ""
    block: Block | None = None

    @property
    def where(self) -> str:
        if self.block is not None:
            return _("{block}, строка {row}").format(block=self.block.where, row=self.row)
        return _("«{sheet}», строка {row}").format(sheet=self.sheet, row=self.row)


@dataclass
class Plan:
    """Что сделает загрузка: строки, итог по подгруппам, ошибки и предупреждения."""

    lines: list[Line] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: подгруппа → ученики по файлу
    wanted: dict[int, list[int]] = field(default_factory=dict)
    cohorts: dict[int, Cohort] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)
    #: листы, где нет ни колонок, ни блоков: тесты, уровни, списки класса
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and bool(self.wanted)


# --- Чтение файла --------------------------------------------------------------


#: заголовок колонки → что в ней: слово внутри заголовка или его начало.
#: Порядок важен: «Подгруппа» проверяется раньше «Группы»
HEADER_WORDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("subgroup", "in", ("подгрупп", "англ", "english")),  # i18n-skip: заголовки колонок файла школы
    ("name", "in", ("фио", "ф.и.о", "ученик", "студент")),  # i18n-skip: заголовки колонок файла школы
    ("last", "start", ("фамилия",)),  # i18n-skip: заголовок колонки файла школы
    ("first", "start", ("имя",)),  # i18n-skip: заголовок колонки файла школы
    ("group", "start", ("группа", "класс")),  # i18n-skip: заголовки колонок файла школы
)


def _header_kind(title: str) -> str:
    text = str(title or "").strip().lower()
    for kind, how, words in HEADER_WORDS:
        if any((word in text) if how == "in" else (text == word or text.startswith(word + " ")) for word in words):
            return kind
    return ""


def _cell(kinds: dict[str, int], row: list, kind: str) -> str:
    column = kinds.get(kind)
    value = row[column] if column is not None and column < len(row) else None
    return "" if value is None else str(value).strip()


#: кабинет в заголовке блока: «203 каб», «каб. 203»
ROOM = re.compile(r"(\d{3})\s*каб|каб\.?\s*(\d{3})", re.IGNORECASE)  # i18n-skip: сокращение из файла школы


def _number(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and float(value).is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def read_blocks(title: str, rows: list[list], known: set[str]) -> list[Block]:
    """Блоки листа: номер «1» слева, ФИО справа, нумерация подряд; заголовок — над первой строкой.

    Блок без кабинета и без названия подгруппы в заголовке — не блок
    подгруппы (лист уровней, где над списком только имя учителя).
    """
    blocks: list[Block] = []
    width = max((len(row) for row in rows), default=0)
    for column in range(1, width):
        index = 0
        while index < len(rows):
            row = rows[index]
            left = row[column - 1] if column - 1 < len(row) else None
            if _number(left) != 1 or not _text(row[column] if column < len(row) else None):
                index += 1
                continue
            header = _text(rows[index - 1][column]) if index > 0 and column < len(rows[index - 1]) else ""
            names = []
            while index < len(rows) and column < len(rows[index]) and _number(rows[index][column - 1]) is not None:
                name = _text(rows[index][column])
                if not name:
                    break
                names.append((index + 1, name))
                index += 1
            room = ROOM.search(header)
            named = next((word for word in re.split(r"[,;\s]+", header) if subgroup_key(word) in known), "")
            if not room and not named:
                continue
            block = Block(
                sheet=title,
                row=index - len(names),
                header=header,
                room=(room.group(1) or room.group(2)) if room else "",
                named=named,
            )
            block.lines = [Line(sheet=title, row=r, subgroup=named, name=n, group="", block=block) for r, n in names]
            blocks.append(block)
    return blocks


def read(content: bytes, known: set[str] | None = None) -> tuple[list[Line], list[str]]:
    """Строки файла по листам. Ошибка — когда читать нечего.

    `known` — ключи подгрупп: лист без колонки «Подгруппа» берётся как состав
    подгруппы, только если называется как она.
    """
    from openpyxl import load_workbook

    try:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # битый файл — не повод для 500
        return [], [_("Файл не читается: нужен Excel (.xlsx)")]
    lines: list[Line] = []
    problems: list[str] = []
    for sheet in book.worksheets:
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        found = None
        for index, row in enumerate(rows[:HEADER_ROWS]):
            kinds = {_header_kind(cell): column for column, cell in reversed(list(enumerate(row))) if cell}
            if "name" in kinds or "last" in kinds:
                found = index, kinds
                break
        if found is None:
            # не колонки — значит, блоки школы; нет и их — лист не про подгруппы
            blocks = read_blocks(sheet.title, rows, known or set())
            if blocks:
                lines.extend(line for block in blocks for line in block.lines)
            else:
                problems.append(SKIPPED + sheet.title)
            continue
        header, kinds = found
        if "subgroup" not in kinds and known is not None and subgroup_key(sheet.title) not in known:
            problems.append(
                _("Лист «{sheet}»: нет колонки «Подгруппа», а название листа — не подгруппа").format(sheet=sheet.title)
            )
            continue

        for offset, row in enumerate(rows[header + 1 :], start=header + 2):
            name = _cell(kinds, row, "name") or " ".join(
                x for x in (_cell(kinds, row, "last"), _cell(kinds, row, "first")) if x
            )
            subgroup = _cell(kinds, row, "subgroup") if "subgroup" in kinds else sheet.title
            if not name and not _cell(kinds, row, "subgroup"):
                continue
            lines.append(
                Line(sheet=sheet.title, row=offset, subgroup=subgroup, name=name, group=_cell(kinds, row, "group"))
            )
    if not lines:
        real = [text for text in problems if not text.startswith(SKIPPED)]
        return [], real or [
            _("В файле нет ни блоков подгрупп, ни колонок «Подгруппа» и «ФИО» — образец в описании формата")
        ]
    return lines, problems


# --- Сопоставление -------------------------------------------------------------


def _stream_subgroups() -> dict[str, Cohort]:
    rows = Cohort.objects.filter(kind=CohortKind.SUBGROUP, stream__isnull=False).select_related("stream", "subject")
    return {subgroup_key(c.name): c for c in rows}


def _groups() -> dict[str, StudyGroup]:
    return {subgroup_key(g.code): g for g in StudyGroup.objects.all()}


def _group_of(text: str, groups: dict[str, StudyGroup]) -> StudyGroup | None:
    """Группа по ячейке: код целиком или словом в ячейке («8 KIOTO»)."""
    found = groups.get(subgroup_key(text))
    if found is not None:
        return found
    for word in re.split(r"[\s,;/]+", text):
        found = groups.get(subgroup_key(word))
        if found is not None:
            return found
    return None


def plan(content: bytes) -> Plan:
    """Прочитать файл и сопоставить: ничего не пишет."""
    from suggestions.name_matching import find

    out = Plan()
    subgroups = _stream_subgroups()
    lines, problems = read(content, set(subgroups))
    out.skipped = [text[len(SKIPPED) :] for text in problems if text.startswith(SKIPPED)]
    out.errors.extend(text for text in problems if not text.startswith(SKIPPED))
    out.lines = lines
    groups = _groups()
    pupils_of: dict[tuple, list[Student]] = {}

    def pupils(scope: tuple) -> list[Student]:
        if scope not in pupils_of:
            pupils_of[scope] = list(Student.objects.filter(group_id__in=scope, is_active=True).select_related("group"))
        return pupils_of[scope]

    for line in lines:
        if line.block is not None and all(line.block is not b for b in out.blocks):
            out.blocks.append(line.block)
    for block in out.blocks:
        _resolve_block(block, subgroups, pupils, find)
    _refuse_shared_subgroups(out.blocks)
    out.errors.extend(block.error for block in out.blocks if block.error)

    codes = {group.pk: group.code for group in groups.values()}
    groups_of: dict[int, tuple] = {}

    def groups_of_cohort(cohort: Cohort) -> tuple:
        if cohort.pk not in groups_of:
            groups_of[cohort.pk] = tuple(group_ids_of(cohort))
        return groups_of[cohort.pk]

    seen: dict[int, Line] = {}
    unresolved: list[tuple[Line, tuple]] = []
    for line in lines:
        if line.block is not None:
            if line.block.cohort is None:
                continue  # ошибка блока уже названа один раз, по строкам её не повторяем
            cohort = line.block.cohort
        else:
            cohort = subgroups.get(subgroup_key(line.subgroup))
        if cohort is None:
            line.error = _("{where}: подгруппы «{subgroup}» нет среди подгрупп потоков").format(
                where=line.where, subgroup=line.subgroup or _("пусто")
            )
            continue
        line.cohort = cohort
        if not line.name:
            line.error = _("{where}: не указан ученик").format(where=line.where)
            continue
        _group_from_name(line, groups)
        group = None
        if line.group:
            group = _group_of(line.group, groups)
            if group is None:
                line.error = _("{where}: группы «{group}» нет").format(where=line.where, group=line.group)
                continue
            scope: tuple = (group.pk,)
        else:
            scope = groups_of_cohort(cohort)
        outcome = find(line.name, students=pupils(scope))
        if not (outcome.is_confident and outcome.best):
            # объясняется после прохода: похожих ищем среди тех, кого файл ещё никуда не поставил
            unresolved.append((line, scope))
            continue
        student = next(s for s in pupils(scope) if s.pk == outcome.best.student_id)
        line.student = student
        earlier = seen.get(student.pk)
        if earlier is not None:
            if earlier.cohort.pk == cohort.pk and _same_spelling(earlier.name, line.name):
                # та же запись дважды в одной подгруппе — повтор в файле, ученик учтётся один раз
                out.warnings.append(
                    _("{where}: «{name}» стоит второй раз ({earlier}) — учтён один раз").format(
                        where=line.where, name=line.name, earlier=earlier.where
                    )
                )
                continue
            # у ученика одна подгруппа английского — EEP или GE, не обе
            line.error = _twice(line, earlier, student.full_name)
            continue
        if group is not None and group.pk not in groups_of_cohort(cohort):
            # группа в скобках не из подгруппы — явное слово файла: ученик ходит сюда из другой параллели
            out.warnings.append(
                _(
                    "{where}: «{name}» из {group}, а эта группа не входит в {subgroup}: "
                    "урок подгруппы встанет и в неделю {group}"
                ).format(where=line.where, name=line.name, group=group.code, subgroup=cohort.name)
            )
        seen[student.pk] = line
        out.cohorts[cohort.pk] = cohort
        out.wanted.setdefault(cohort.pk, []).append(student.pk)
    everyone: list[Student] = []
    for line, scope in unresolved:
        if not everyone:
            everyone = list(Student.objects.filter(is_active=True).select_related("group"))
        line.error = _explain_missing(line, scope, pupils(scope), everyone, seen, codes, find)
    out.errors.extend(line.error for line in lines if line.error)
    _warn_about_the_rest(out, subgroups)
    return out


def _names(candidates) -> str:
    return ", ".join(f"{c.full_name} ({c.group_code})" if c.group_code else c.full_name for c in candidates[:3])


def _same_spelling(one: str, other: str) -> bool:
    """Одна и та же запись: регистр, «ё» и лишние пробелы не в счёт."""

    def norm(text: str) -> str:
        return " ".join(text.casefold().replace("ё", "е").split())  # i18n-skip: буквы для сравнения записей

    return norm(one) == norm(other)


def _twice(line: Line, earlier: Line, student: str) -> str:
    return _(
        "{where}: «{name}» — тот же ученик, что «{earlier_name}» ({earlier}, {subgroup}): {student}. "
        "У ученика одна подгруппа; если это разные ученики, напишите ФИО как в LMS"
    ).format(
        where=line.where,
        name=line.name,
        earlier_name=earlier.name,
        earlier=earlier.where,
        subgroup=earlier.cohort.name,
        student=student,
    )


def _similar_free(name: str, free: list[Student], find) -> str:
    """Похожие среди тех, кого файл ещё никуда не поставил: по сходству ФИО и по общему слову.

    В файле школы фамилию пишут то по отцу, то по паспорту («Тестұлы Дамир»
    против «Сериков Дамир»), и сходство всего ФИО тогда низкое; общее имя
    или фамилия у ученика без подгруппы — уже подсказка.
    """
    from suggestions.name_matching import tokens

    picked = [(c.full_name, c.group_code) for c in find(name, students=free).candidates]
    words = set(tokens(name))
    for student in free:
        pair = (student.full_name, student.group.code if student.group_id else None)
        if pair not in picked and words & set(tokens(student.full_name)):
            picked.append(pair)
    return ", ".join(f"{full} ({code})" if code else full for full, code in picked[:5])


def _explain_missing(line: Line, scope: tuple, known, everyone, seen: dict[int, Line], codes, find) -> str:
    """Почему строка не сопоставилась и что написать в файле, чтобы сопоставилась.

    Молча ученик не угадывается никогда: здесь только текст ошибки.
    """
    from suggestions.name_matching import CONFIDENT

    inside = find(line.name, students=known)
    best = inside.best
    if best is not None and best.confidence >= CONFIDENT:
        # двое почти одинаково похожих — тёзки: решает группа или полное ФИО
        close = [c for c in inside.candidates if best.confidence - c.confidence < 0.08]
        groups = sorted({c.group_code for c in close if c.group_code})
        if len(groups) > 1 and not line.group:
            return _(
                "{where}: «{name}» — подходят несколько: {names}. "
                "Допишите в скобках группу нужного ученика — одну из: {groups}"
            ).format(where=line.where, name=line.name, names=_names(close), groups=", ".join(groups))
        return _("{where}: «{name}» — подходят несколько: {names}. Напишите ФИО полностью, как в LMS").format(
            where=line.where, name=line.name, names=_names(close)
        )
    outside = find(line.name, students=[s for s in everyone if s.group_id not in scope])
    if outside.is_confident and outside.best and outside.best.group_code:
        found = outside.best
        earlier = seen.get(found.student_id)
        if earlier is not None:
            return _twice(line, earlier, found.full_name)
        if line.group:
            return _("{where}: «{name}» — ученик {found}, а не {written}: исправьте группу").format(
                where=line.where, name=line.name, found=found.group_code, written=line.group
            )
        return _(
            "{where}: «{name}» — ученик {found}, а {subgroup} собрана из групп {groups}. "
            "Если ученик ходит сюда, допишите группу: «{name} ({found})»; если нет — перенесите строку в его подгруппу"
        ).format(
            where=line.where,
            name=line.name,
            found=found.group_code,
            subgroup=line.cohort.name,
            groups=", ".join(sorted(codes[pk] for pk in scope if pk in codes)),
        )
    if free := _similar_free(line.name, [s for s in known if s.pk not in seen], find):
        return _(
            "{where}: ученик «{name}» не найден. Похожие из тех, кого ещё нет в файле: {names} — "
            "если это кто-то из них, напишите ФИО как в LMS"
        ).format(where=line.where, name=line.name, names=free)
    return _(
        "{where}: ученик «{name}» не найден — напишите ФИО как в LMS; "
        "если ученика в LMS нет, заведите его или уберите строку"
    ).format(where=line.where, name=line.name)


#: «Каирова Диана (OXFORD)» — тёзку уточняют группой в скобках после ФИО
NAME_WITH_GROUP = re.compile(r"^(?P<name>.*?)\s*[(\[]\s*(?P<group>[^)\]]+?)\s*[)\]]\s*$")


def _group_from_name(line: Line, groups: dict[str, StudyGroup]) -> None:
    """Группа в скобках после ФИО становится группой строки, если это код группы."""
    if line.group:
        return
    match = NAME_WITH_GROUP.match(line.name)
    if match and _group_of(match["group"], groups) is not None:
        line.name, line.group = match["name"].strip(), match["group"].strip()


def _resolve_block(block: Block, subgroups: dict[str, Cohort], pupils, find) -> None:
    """Подгруппа блока: названная в заголовке, иначе по кабинету, при нескольких — по ученикам."""
    if block.named:
        block.cohort = subgroups[subgroup_key(block.named)]
        return
    candidates = [c for c in subgroups.values() if c.room.strip() == block.room]
    if not candidates:
        block.error = _("{where}: нет подгруппы потока с кабинетом {room}").format(where=block.where, room=block.room)
        return
    if len(candidates) == 1:
        block.cohort = candidates[0]
        return
    # кабинет у нескольких подгрупп (201 — в 11.1 и в 11.2): решают группы учеников блока
    scores = []
    for cohort in candidates:
        known = pupils(tuple(group_ids_of(cohort)))
        hits = sum(1 for line in block.lines if find(line.name, students=known).is_confident)
        scores.append((hits, cohort))
    scores.sort(key=lambda pair: (-pair[0], pair[1].name))
    if scores[0][0] == 0 or scores[0][0] == scores[1][0]:
        block.error = _(
            "{where}: кабинет {room} у нескольких подгрупп ({names}) — допишите название подгруппы в заголовок блока"
        ).format(where=block.where, room=block.room, names=", ".join(sorted(c.name for c in candidates)))
        return
    block.cohort = scores[0][1]


def _refuse_shared_subgroups(blocks: list[Block]) -> None:
    """Два блока в одну подгруппу — ошибка: один из них, значит, не на своём месте."""
    by_cohort: dict[int, list[Block]] = {}
    for block in blocks:
        if block.cohort is not None:
            by_cohort.setdefault(block.cohort.pk, []).append(block)
    for same in by_cohort.values():
        if len(same) < 2:
            continue
        for block in same:
            others = ", ".join(f"«{b.header}»" for b in same if b is not block)
            block.error = _("{where}: в подгруппу {subgroup} ведёт и блок {others}").format(
                where=block.where, subgroup=block.cohort.name, others=others
            )
            block.cohort = None


def alternatives(cohorts) -> list[Cohort]:
    """Подгруппы потоков, взаимоисключающие с этими: потоки из того же набора групп.

    EEP-8 и GE-8 — разные потоки и предметы, но из одних групп и в одно
    время: ученик ходит в одну подгруппу из всех их подгрупп.
    """
    sets = {frozenset(group_ids_of(c.stream)) for c in cohorts if c.stream_id}
    return [
        c
        for c in Cohort.objects.filter(kind=CohortKind.SUBGROUP, stream__isnull=False).select_related("stream")
        if frozenset(group_ids_of(c.stream)) in sets
    ]


def _warn_about_the_rest(out: Plan, subgroups: dict[str, Cohort]) -> None:
    """Кого и что файл не назвал: эти составы загрузка не трогает."""
    missing = sorted(c.name for c in alternatives(out.cohorts.values()) if c.pk not in out.wanted)
    if missing:
        out.warnings.append(_("Подгрупп нет в файле, их состав не меняется: {names}").format(names=", ".join(missing)))
    listed = {sid for ids in out.wanted.values() for sid in ids}
    group_ids: set[int] = set()
    for cohort in out.cohorts.values():
        group_ids.update(group_ids_of(cohort))
    for group in StudyGroup.objects.filter(pk__in=group_ids).order_by("code"):
        left = [
            s.full_name
            for s in Student.objects.filter(group=group, is_active=True).order_by("last_name", "first_name")
            if s.pk not in listed
        ]
        if left:
            out.warnings.append(
                _("{group}: нет в файле, английского в расписании у них не будет — {names}").format(
                    group=group.code, names=", ".join(left)
                )
            )


# --- Отчёт и применение --------------------------------------------------------


def year_start() -> dt.date:
    """Начало учебного года — дата состава по умолчанию: журналы прошлых уроков получают своих учеников."""
    from academics import calendar as school_calendar

    try:
        return school_calendar.load().year.starts
    except Exception:  # учебного года ещё нет — с сегодняшнего дня
        return today()


def report(out: Plan, since: dt.date) -> dict:
    """Что покажет экран: по подгруппам — сколько учеников, кто придёт и кто уйдёт."""
    rows = []
    for pk, ids in out.wanted.items():
        cohort = out.cohorts[pk]
        current = set(
            CohortMembership.objects.filter(cohort=cohort, until__isnull=True).values_list("student_id", flat=True)
        )
        rows.append(
            {
                "id": pk,
                "name": cohort.name,
                "stream": cohort.stream.name if cohort.stream_id else "",
                "subject": cohort.subject.title if cohort.subject_id else "",
                "students": len(ids),
                "joined": len(set(ids) - current),
                "left": len(current - set(ids)),
            }
        )
    rows.sort(key=lambda row: row["name"])
    teachers = {
        course.cohort_id: course.teacher.full_name
        for course in Course.objects.filter(cohort__in=[b.cohort for b in out.blocks if b.cohort]).select_related(
            "teacher"
        )
        if course.teacher_id
    }
    blocks = [
        {
            "sheet": block.sheet,
            "header": block.header,
            "subgroup": block.cohort.name if block.cohort else "",
            "teacher": teachers.get(block.cohort.pk, "") if block.cohort else "",
            "students": len(block.lines),
        }
        for block in out.blocks
    ]
    return {
        "blocks": blocks,
        "skipped": out.skipped,
        "since": since,
        "lines": len(out.lines),
        "matched": sum(len(ids) for ids in out.wanted.values()),
        "subgroups": rows,
        "errors": out.errors[:200],
        "errors_total": len(out.errors),
        "warnings": out.warnings,
        "ok": out.ok,
    }


@transaction.atomic
def apply(out: Plan, since: dt.date, *, actor=None) -> None:
    """Записать составы с даты. Ученик файла уходит из прежней подгруппы, которой нет в файле."""
    from academics import schedule
    from core import stored_text
    from core.domains import Source

    if not out.ok:
        raise ValueError("план с ошибками не применяется")  # i18n-skip: страж кода, экран сюда не доходит
    listed = {sid for ids in out.wanted.values() for sid in ids}
    # прежняя подгруппа из тех же групп (EEP ↔ GE), которой нет в файле: ученик переехал — закрываем
    others = [c.pk for c in alternatives(out.cohorts.values()) if c.pk not in out.wanted]
    stale = CohortMembership.objects.filter(student_id__in=listed, until__isnull=True, cohort_id__in=others)
    stale.update(until=since)
    for pk, ids in out.wanted.items():
        set_members(out.cohorts[pk], ids, since)
        schedule.log_change(
            stored_text.store(
                stored_text.COHORT_CHANGED, name=out.cohorts[pk].name, count=len(ids), date=f"{since:%d.%m.%Y}"
            ),
            actor=actor,
            source=Source.IMPORT,
        )
    cache.invalidate()
