"""Именованные действия в интерфейсе.

Не чат, а кнопки: у каждой понятно, что она делает и над чем.
Общие для всех директоров и специальные по ролям — состав из задания.
"""

from __future__ import annotations

from dataclasses import dataclass

BEHAVIOR = "director_behavior"
ADMISSION = "director_admission"
EXAM = "director_exam"
TALENT = "director_talent"
SPORT = "director_sport"
ADMIN = "admin"

ALL_DIRECTORS = (BEHAVIOR, ADMISSION, EXAM, TALENT, SPORT, ADMIN)


@dataclass(frozen=True)
class Command:
    """Кнопка: код, подпись, что принимает на вход."""

    code: str
    title: str
    hint: str
    #: text | file | image | selection | none
    input_kind: str
    roles: tuple[str, ...]


COMMANDS: tuple[Command, ...] = (
    # --- общие ---
    Command(
        "paste_as_is",
        "Вставить как есть",
        "Текст из мессенджера или письма → разбор → предпросмотр",
        "text",
        ALL_DIRECTORS,
    ),
    Command("upload_file", "Загрузить файл", "XLSX или CSV → разбор → предпросмотр", "file", ALL_DIRECTORS),
    Command("digest", "Дайджест на сегодня", "Что изменилось в вашем домене", "none", ALL_DIRECTORS),
    Command(
        "explain_match",
        "Объясни соответствие",
        "Ученик и программа → чего не хватает и что даст больше всего",
        "selection",
        ALL_DIRECTORS,
    ),
    # --- Асем ---
    Command(
        "check_balance",
        "Проверить баланс списка",
        "Соотношение reach / target / safety у ученика",
        "selection",
        (ADMISSION, ADMIN),
    ),
    # --- Кымбат ---
    Command("parse_mock", "Разобрать мок", "Баллы строками → секции, сравнение с прошлым", "text", (EXAM, ADMIN)),
)

#: Заявлено в фазе 5, но не построено. Держим списком, а не кнопками:
#: кнопка без обработчика — дефект, а не обещание (см. `docs/DEFECTS.md`, B4).
NOT_BUILT_YET = (
    "bulk_action",
    "prep_plan",
    "gap_to_tasks",
    "parse_university",
    "parse_activity",
    "parse_certificate",
)


def for_role(role: str) -> list[dict]:
    """Кнопки, доступные роли."""
    return [
        {"code": c.code, "title": c.title, "hint": c.hint, "input_kind": c.input_kind}
        for c in COMMANDS
        if role in c.roles
    ]


def get(code: str) -> Command | None:
    return next((c for c in COMMANDS if c.code == code), None)


#: Подписи команд, которых нет среди кнопок: предложение могло прийти
#: фоновой сверкой или из уже убранной кнопки, а в списке «ждёт решения»
#: человек всё равно должен читать слова, а не код.
EXTRA_TITLES = {
    "web_sync": "Фоновая сверка дедлайнов",
    "import": "Загрузка файла",
    "manual": "Заведено руками",
}


def title_of(code: str) -> str:
    """Человеческая подпись команды по её коду. Пустой код — пустая строка."""
    if not code:
        return ""
    command = get(code)
    if command is not None:
        return command.title
    return EXTRA_TITLES.get(code, "")
