# i18n-skip-file: инструмент владельца — причины отказа и подсказки выгрузки читает он сам в терминале
"""Каталоги переводов для вычитки человеком: выгрузка в xlsx и загрузка обратно.

Два каталога, ключ в обоих — русская строка:
- интерфейс — словари фронта `frontend/src/i18n/kk.ts` и `en.ts`;
- сервер — `backend/locale/<язык>/LC_MESSAGES/django.po` (Django gettext).

Носитель языка в школе правит казахский в таблице, а команда `i18n_import`
переносит правки в каталоги — после проверки, что подстановки `{имя}` и формы
числа не сломаны; серверный каталог после этого компилируется в `.mo`.

Работает в контуре разработки: словари фронта — исходники, в боевом образе
их нет. Путь к ним — `I18N_FRONTEND_DIR` (в dev-контуре примонтирован
на запись), иначе рядом с репозиторием.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

LANGS = ("kk", "en")
#: сколько форм числа бывает у перевода: у казахского и английского до двух
MAX_FORMS = 2

_QUOTED = r"'(?:[^'\\\n]|\\.)*'" + "|" + r'"(?:[^"\\\n]|\\.)*"'
_ENTRY = re.compile(rf"^  ({_QUOTED}|[\w$А-Яа-яЁё-]+):\s+({_QUOTED}),[ \t]*$", re.M)
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _repo_root() -> Path:
    mounted = Path("/repo")
    return mounted if (mounted / "frontend").is_dir() else Path(__file__).resolve().parents[2]


def frontend_src() -> Path:
    """Исходники фронта: по ним ищется, где встречается строка."""
    return _repo_root() / "frontend" / "src"


def frontend_dictionaries() -> Path:
    """Папка словарей фронта: `I18N_FRONTEND_DIR` или `frontend/src/i18n` репозитория."""
    configured = os.environ.get("I18N_FRONTEND_DIR")
    return Path(configured) if configured else frontend_src() / "i18n"


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "b": "\b", "f": "\f", "v": "\v"}
_ESCAPE = re.compile(r"\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)", re.S)


def _unescape(match: re.Match) -> str:
    code = match.group(1)
    if code[0] in "ux" and len(code) > 1:
        return chr(int(code[1:].strip("{}"), 16))
    return _ESCAPES.get(code, code)


def unquote(raw: str) -> str:
    """Строка из исходника TS как JS её прочтёт: кавычки сняты, `\\n` — перенос строки."""
    if raw[:1] in ("'", '"'):
        return _ESCAPE.sub(_unescape, raw[1:-1])
    return raw


def quote(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"


def placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER.findall(text))


@dataclass
class Dictionary:
    """Словарь фронта: шапка файла (комментарий и объявление) и записи."""

    path: Path
    head: str
    entries: dict[str, str] = field(default_factory=dict)

    @classmethod
    def read(cls, path: Path) -> Dictionary:
        text = path.read_text(encoding="utf-8")
        start = text.index("= {") + len("= {")
        head = text[:start]
        entries = {unquote(key): unquote(value) for key, value in _ENTRY.findall(text[start:])}
        return cls(path=path, head=head, entries=entries)

    def write(self) -> None:
        """Записать отсортированно, по записи в строке: так дифф правок читается."""
        lines = [f"  {quote(key)}: {quote(value)}," for key, value in sorted(self.entries.items())]
        self.path.write_text(self.head + "\n" + "\n".join(lines) + "\n}\n", encoding="utf-8")


def read_dictionaries(folder: Path | None = None) -> dict[str, Dictionary]:
    folder = folder or frontend_dictionaries()
    return {lang: Dictionary.read(folder / f"{lang}.ts") for lang in LANGS}


#: вызов перевода → номер аргумента с ключом; у форм числа ключ — второй аргумент
KEY_ARG = {"t": 0, "tk": 0, "tn": 1, "plural": 1, "counted": 1}
PLURAL_CALLS = frozenset({"tn", "plural", "counted"})
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def key_literals(source: str) -> list[tuple[str, str, int]]:
    """Ключи вызовов перевода в исходнике TS: (вызов, ключ, строка).

    Маленький разбор вместо регулярного выражения: пропускает комментарии,
    строки и шаблонные строки (код внутри `${…}` разбирается), ведёт стек
    скобок и помнит, чей это вызов и какой по счёту аргумент. Ключ —
    строковый литерал на месте ключа, в том числе ветвью `a ? 'x' : 'y'`
    или `x ?? 'y'`, как у правила `i18n-keys`.
    """
    found: list[tuple[str, str, int]] = []
    # стек: [имя вызова или None, номер аргумента]; шаблонные строки — отметкой "`"
    stack: list[list] = []
    i, n, line = 0, len(source), 1
    last_ident = None
    while i < n:
        ch = source[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if source.startswith("//", i):
            end = source.find("\n", i)
            i = n if end < 0 else end
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            end = n if end < 0 else end + 2
            line += source.count("\n", i, end)
            i = end
            last_ident = None
            continue
        if ch in "'\"":
            j = i + 1
            while j < n and source[j] != ch and source[j] != "\n":
                j += 2 if source[j] == "\\" else 1
            raw = source[i : j + 1]
            if stack and stack[-1][0] in KEY_ARG and stack[-1][1] == KEY_ARG[stack[-1][0]]:
                found.append((stack[-1][0], unquote(raw), line))
            i = j + 1
            last_ident = None
            continue
        if ch == "`" or (ch == "}" and stack and stack[-1][0] == "${"):
            if ch == "}":
                stack.pop()
            # тело шаблонной строки до конца или до `${`
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == "`":
                    break
                if source.startswith("${", j):
                    break
                j += 1
            line += source.count("\n", i, j)
            if j < n and source[j] == "`":
                i = j + 1
            else:
                stack.append(["${", 0])
                i = j + 2
            last_ident = None
            continue
        match = _IDENT.match(source, i)
        if match:
            last_ident = match.group()
            i = match.end()
            continue
        if ch == "(":
            stack.append([last_ident, 0])
        elif ch in "[{":
            stack.append([None, 0])
        elif ch in ")]}":
            if stack:
                stack.pop()
        elif ch == "," and stack:
            stack[-1][1] += 1
        if not ch.isspace():
            last_ident = None
        i += 1
    return found


def _sources(src: Path):
    for path in sorted(src.rglob("*.ts*")):
        if "i18n" in path.parts or path.name == "schema.ts":
            continue
        yield path, path.read_text(encoding="utf-8")


def frontend_usages(src: Path | None = None) -> dict[str, list[str]]:
    """Ключ → где встречается («screens/Plan.tsx:42»), по вызовам перевода."""
    src = src or frontend_src()
    found: dict[str, list[str]] = {}
    for path, text in _sources(src):
        for _call, key, line in key_literals(text):
            if key:
                found.setdefault(key, []).append(f"{path.relative_to(src)}:{line}")
    return found


def plural_keys(src: Path | None = None) -> set[str]:
    """Ключи форм числа — из вызовов `tn`, `plural`, `counted`."""
    src = src or frontend_src()
    return {key for _path, text in _sources(src) for call, key, _line in key_literals(text) if call in PLURAL_CALLS}


def check_translation(key: str, value: str, *, is_plural: bool) -> str | None:
    """Что не так с переводом ключа, или None. Пустой перевод — тоже ошибка."""
    if not value.strip() and key.strip():
        return "пустой перевод"
    if placeholders(value) != placeholders(key):
        wanted = ", ".join(sorted(placeholders(key))) or "без подстановок"
        return f"подстановки не совпадают с исходной строкой ({wanted})"
    forms = value.count("|") + 1
    if is_plural and forms > MAX_FORMS:
        return f"форм числа больше {MAX_FORMS}"
    if not is_plural and forms != key.count("|") + 1:
        return "лишняя черта «|»"
    return None


# --- серверный каталог (Django gettext) ---------------------------------------


def server_locale() -> Path:
    """Папка переводов сервера: `backend/locale`."""
    return Path(__file__).resolve().parents[1] / "locale"


def po_path(lang: str, locale: Path | None = None) -> Path:
    return (locale or server_locale()) / lang / "LC_MESSAGES" / "django.po"


def read_po(lang: str, locale: Path | None = None):
    """Каталог сервера на языке `lang` (`polib.POFile`). polib — зависимость разработки."""
    import polib

    return polib.pofile(str(po_path(lang, locale)), wrapwidth=0)


def server_entries(locale: Path | None = None) -> dict[str, dict]:
    """Ключ → переводы kk/en и места в коде: как словари фронта, для выгрузки и проверок."""
    rows: dict[str, dict] = {}
    for lang in LANGS:
        for entry in read_po(lang, locale):
            if entry.obsolete or not entry.msgid:
                continue
            row = rows.setdefault(entry.msgid, {"kk": "", "en": "", "where": []})
            row[lang] = entry.msgstr
            if not row["where"]:
                row["where"] = [f"{path}:{line}" if line else path for path, line in entry.occurrences]
    return rows


def compile_server(locale: Path | None = None) -> None:
    """`.po` → `.mo`: сервер читает скомпилированный каталог."""
    for lang in LANGS:
        catalog = read_po(lang, locale)
        catalog.save_as_mofile(str(po_path(lang, locale).with_suffix(".mo")))
