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
    # --- Операции уровня управления (фаза 20) ---
    Command(
        "explain_list",
        "Объясни этот список",
        "Выделенные ученики → что общего, с чего начать, кто в приоритете",
        "selection",
        ALL_DIRECTORS,
    ),
    Command(
        "week_changes",
        "Что изменилось за неделю",
        "Сводка по вашему домену с выводами, а не перечислением",
        "none",
        ALL_DIRECTORS,
    ),
    Command(
        "focus_today",
        "На кого смотреть сегодня",
        "Короткий список с обоснованием по каждому",
        "none",
        ALL_DIRECTORS,
    ),
    Command(
        "bulk_tasks",
        "Поставить задачу выделенным",
        "Опишите словами, что нужно, — задача уйдёт предложением на всех выделенных",
        "text",
        ALL_DIRECTORS,
    ),
    Command(
        "prep_plan",
        "План подготовки к экзамену",
        "От текущего балла к целевому: часы, темы, дата следующего пробного",
        "selection",
        (EXAM, ADMIN),
    ),
    Command(
        "gap_to_tasks",
        "Пробелы портфолио в задачи",
        "Чего не хватает портфолио → задачи роадмапа со сроками",
        "selection",
        (TALENT, ADMIN),
    ),
    Command(
        "parent_letter",
        "Черновик письма родителю",
        "Факты из системы, без оценочных суждений",
        "selection",
        ALL_DIRECTORS,
    ),
    Command(
        "parse_university",
        "Разобрать вуз",
        "Название или ссылка → программы, требования и дедлайны. Записи заводятся неподтверждёнными",
        "text",
        (ADMISSION, ADMIN),
    ),
    Command(
        "parse_activity",
        "Разобрать активность",
        "Описание словами → категория, предмет и чего не хватает",
        "text",
        (TALENT, ADMIN),
    ),
    Command(
        "parse_certificate",
        "Прочитать грамоту",
        "Фото грамоты → соревнование, дата, результат",
        "image",
        (SPORT, TALENT, ADMIN),
    ),
    Command(
        "parse_score_screenshot",
        "Прочитать скриншот с баллами",
        "Скриншот результата → попытка экзамена",
        "image",
        (EXAM, ADMIN),
    ),
)

#: Заявлено, но не построено. Держим списком, а не кнопками: кнопка без
#: обработчика — дефект, а не обещание (см. `docs/DEFECTS.md`, B4).
#: В фазе 20 список опустел: разбор вуза, активности и изображений
#: построены и вернулись в реестр кнопками.
NOT_BUILT_YET: tuple[str, ...] = ()


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
    "bulk_action": "Массовая постановка задач",
    "gap_to_tasks": "Пробелы портфолио в задачи",
}


def title_of(code: str) -> str:
    """Человеческая подпись команды по её коду. Пустой код — пустая строка."""
    if not code:
        return ""
    command = get(code)
    if command is not None:
        return command.title
    return EXTRA_TITLES.get(code, "")
