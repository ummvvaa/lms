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
    Command("bulk_action", "Массовое действие", "Над выделенными учениками", "selection", ALL_DIRECTORS),
    Command("digest", "Дайджест на сегодня", "Что изменилось в вашем домене", "none", ALL_DIRECTORS),
    Command(
        "explain_list",
        "Объясни этот список",
        "Почему эти ученики здесь и что с ними делать",
        "selection",
        ALL_DIRECTORS,
    ),
    # --- Асем ---
    Command(
        "parse_university",
        "Разобрать вуз",
        "Название или ссылка → раунды, дедлайны, требования",
        "text",
        (ADMISSION, ADMIN),
    ),
    Command(
        "check_balance",
        "Проверить баланс списка",
        "Соотношение reach / target / safety",
        "selection",
        (ADMISSION, ADMIN),
    ),
    # --- Кымбат ---
    Command("parse_mock", "Разобрать мок", "Баллы или скрин → секции, сравнение с прошлым", "text", (EXAM, ADMIN)),
    Command("prep_plan", "План подготовки", "Что делать до следующей сдачи", "selection", (EXAM, ADMIN)),
    # --- Арман ---
    Command(
        "parse_activity", "Разобрать активность", "Описание → категория, сила, чего не хватает", "text", (TALENT, ADMIN)
    ),
    Command("gap_to_tasks", "Gap → задачи", "Из пробелов портфолио — конкретные задачи", "selection", (TALENT, ADMIN)),
    # --- Нурлыбек ---
    Command(
        "parse_certificate", "Распознать сертификат", "Фото → соревнование, дата, результат", "image", (SPORT, ADMIN)
    ),
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
