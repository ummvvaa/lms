"""Страж перевода сервера: русская строка в коде — либо перевод, либо объяснённое исключение.

Разбирает код приложений по синтаксическому дереву и находит каждую строку
с кириллицей. Строка допустима, если она:

- аргумент перевода: `gettext`/`_`, `gettext_lazy`, `ngettext`, `pgettext`,
  `gettext_noop`, `render(lang, "…")`, `translate(lang, "…")` — сама или веткой
  `a if x else "…"`, `x or "…"`;
- docstring;
- `help_text=` — подсказка служебной админки Django, людям школы не видна;
- текст записи в лог (`log.info("…")`);
- в команде `manage.py` (`management/commands/`) — инструмент владельца в терминале;
- на строке, где стоит `# i18n-skip: <почему>`, или внутри оператора, на первой
  строке которого эта пометка (словарь синонимов, промпт ИИ, данные);
- в файле, где в начале стоит `# i18n-skip-file: <почему>`.

Кроме того, ошибка — перевод из кусков (`_(f"…{x}")`, `_("…" + x)`: такой строки
нет в каталоге) и `gettext` на уровне модуля (застынет на языке загрузки —
нужен `gettext_lazy`).

Отчёт — `python manage.py i18n_check [путь…]`; ноль нарушений проверяет
`core/tests/test_server_i18n.py`.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path

CYRILLIC = re.compile(r"[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]")
SKIP_LINE = re.compile(r"#\s*i18n-skip:\s*\S")
SKIP_FILE = re.compile(r"#\s*i18n-skip-file:\s*\S")

#: вызов перевода → номера аргументов, которые сами строки перевода
TRANSLATE_ARGS: dict[str, tuple[int, ...]] = {
    "_": (0,),
    "gettext": (0,),
    "gettext_lazy": (0,),
    "_lazy": (0,),
    "gettext_noop": (0,),
    "ngettext": (0, 1),
    "ngettext_lazy": (0, 1),
    "pgettext": (1,),
    "pgettext_lazy": (1,),
    "npgettext": (1, 2),
    "npgettext_lazy": (1, 2),
    "render": (1,),
    "translate": (1,),
    # формы числа через черту: core.phrasing
    "tn": (1,),
    "plural": (1,),
    "counted": (1,),
}
#: переводы, которые считаются сразу, — им нельзя стоять на уровне модуля
EAGER = {"_", "gettext", "ngettext", "pgettext", "npgettext"}
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}


def backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def app_sources(root: Path | None = None) -> list[Path]:
    """Код приложений без тестов, миграций и служебных папок."""
    root = root or backend_root()
    skip = {"tests", "migrations", "staticfiles", "media", "private", "locale", "__pycache__"}
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if not skip & set(path.relative_to(root).parts) and path.name != "conftest.py"
    ]


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    text: str
    reason: str

    def __str__(self) -> str:
        flat = " ".join(self.text.split())
        return f"{self.path}:{self.line}: {self.reason}: «{flat[:70]}»"


def _callee(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _skip_lines(source: str) -> tuple[set[int], set[int]]:
    """Строки с пометкой `# i18n-skip:` и те из них, где пометка стоит одна, без кода."""
    lines: set[int] = set()
    alone: set[int] = set()
    text = source.splitlines()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT and SKIP_LINE.search(token.string):
            lines.add(token.start[0])
            if not text[token.start[0] - 1][: token.start[1]].strip():
                alone.add(token.start[0])
    return lines, alone


def check_source(source: str, name: str = "<код>") -> list[Violation]:
    """Нарушения в одном файле."""
    head = "\n".join(source.splitlines()[:30])
    if SKIP_FILE.search(head):
        return []
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    skipped, alone = _skip_lines(source)
    # `_` — ленивый перевод, если файл так его объявил: `gettext_lazy as _` или `_ = gettext_lazy`
    lazy_underscore = any(
        (isinstance(node, ast.ImportFrom) and any(a.name == "gettext_lazy" and a.asname == "_" for a in node.names))
        or (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_" for t in node.targets)
            and isinstance(node.value, ast.Name)
            and node.value.id == "gettext_lazy"
        )
        for node in tree.body
    )
    eager = EAGER - {"_"} if lazy_underscore else EAGER
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    found: list[Violation] = []

    def statement_of(node: ast.AST) -> ast.AST:
        while node in parents and not isinstance(node, ast.stmt):
            node = parents[node]
        return node

    def marked(node: ast.AST) -> bool:
        if getattr(node, "lineno", None) in skipped:
            return True
        # пометка охватывающего оператора: на его первой или последней строке
        # (black переносит хвостовой комментарий за закрывающую скобку)
        # или отдельной строкой прямо над ним
        current = node
        while current in parents:
            current = parents[current]
            if isinstance(current, ast.stmt) and (
                current.lineno in skipped or current.end_lineno in skipped or current.lineno - 1 in alone
            ):
                return True
        return False

    def translated(node: ast.AST) -> bool:
        """Строка стоит на месте строки перевода — сама или ветвью `?:` / `or`.

        Кусок f-строки внутри вызова перевода уже назван «переводом из кусков».
        """
        child, parent = node, parents.get(node)
        if isinstance(parent, ast.JoinedStr):
            child, parent = parent, parents.get(parent)
            return isinstance(parent, ast.Call) and _callee(parent) in TRANSLATE_ARGS
        while isinstance(parent, ast.IfExp | ast.BoolOp):
            if isinstance(parent, ast.IfExp) and parent.test is child:
                return False
            child, parent = parent, parents.get(parent)
        if isinstance(parent, ast.Call) and _callee(parent) in TRANSLATE_ARGS:
            return any(
                index < len(parent.args) and parent.args[index] is child for index in TRANSLATE_ARGS[_callee(parent)]
            )
        return False

    def allowed_context(node: ast.AST) -> bool:
        parent = parents.get(node)
        if isinstance(parent, ast.keyword) and parent.arg == "help_text":
            return True
        current = node
        while current in parents:
            current = parents[current]
            if isinstance(current, ast.Call):
                func = current.func
                if isinstance(func, ast.Attribute) and func.attr in LOG_METHODS:
                    owner = ast.unparse(func.value).lower()
                    if "log" in owner:
                        return True
            if isinstance(current, ast.stmt):
                break
        return False

    # `label, _, name = …` внутри функции делает `_` локальной переменной, и `_("…")`
    # в той же функции падает TypeError. Генераторы — своя область, их не считаем
    comprehensions = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        inner = set()
        for node in ast.walk(function):
            if isinstance(node, comprehensions):
                inner |= {id(child) for child in ast.walk(node)}
        stores = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Name)
            and node.id == "_"
            and isinstance(node.ctx, ast.Store)
            and id(node) not in inner
        ]
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call) and _callee(node) == "_"]
        if stores and calls:
            found.append(Violation(name, stores[0].lineno, "_", "переменная _ затеняет перевод в этой функции"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _callee(node) in TRANSLATE_ARGS:
            for index in TRANSLATE_ARGS[_callee(node)]:
                if index < len(node.args) and isinstance(node.args[index], ast.JoinedStr | ast.BinOp):
                    if not marked(node):
                        found.append(Violation(name, node.lineno, ast.unparse(node.args[index]), "перевод из кусков"))
            if _callee(node) in eager and isinstance(statement_of(node), ast.stmt):
                scope = node
                while scope in parents and not isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
                    scope = parents[scope]
                if not isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) and not marked(node):
                    found.append(
                        Violation(
                            name, node.lineno, ast.unparse(node)[:80], "gettext на уровне модуля — нужен gettext_lazy"
                        )
                    )
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str) and CYRILLIC.search(node.value)):
            continue
        if id(node) in docstrings or translated(node) or allowed_context(node) or marked(node):
            continue
        found.append(Violation(name, node.lineno, node.value, "строка мимо перевода"))
    return sorted(found, key=lambda v: v.line)


def check_paths(paths: list[Path] | None = None, root: Path | None = None) -> list[Violation]:
    root = root or backend_root()
    violations: list[Violation] = []
    for path in paths or app_sources(root):
        relative = path.relative_to(root)
        if "management" in relative.parts and "commands" in relative.parts:
            continue
        violations += check_source(path.read_text(encoding="utf-8"), str(relative))
    return violations


def translatable_strings(paths: list[Path] | None = None, root: Path | None = None) -> set[tuple[str, str | None]]:
    """Строки перевода в коде: (msgid, msgid_plural) — то, что должно быть в каталоге."""
    root = root or backend_root()
    found: set[tuple[str, str | None]] = set()
    for path in paths or app_sources(root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _callee(node) in TRANSLATE_ARGS):
                continue
            indexes = TRANSLATE_ARGS[_callee(node)]
            args = [node.args[i] if i < len(node.args) else None for i in indexes]
            texts = [a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None for a in args]
            if len(texts) == 2 and texts[0] and texts[1]:
                found.add((texts[0], texts[1]))
            elif texts[0]:
                found.add((texts[0], None))
    return found
