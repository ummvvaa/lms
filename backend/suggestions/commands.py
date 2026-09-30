"""Именованные действия в интерфейсе.

Не чат, а кнопки: у каждой понятно, что она делает и над чем.
Общие для всех директоров и специальные по ролям — состав из задания.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy

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
        gettext_lazy("Вставить как есть"),
        gettext_lazy("Текст из мессенджера или письма → разбор → предпросмотр"),
        "text",
        ALL_DIRECTORS,
    ),
    # файлы грузит только администратор (фаза 35): у директоров кнопки
    # нет ни здесь, ни на экране импорта — они вставляют текст
    Command(
        "upload_file",
        gettext_lazy("Загрузить файл"),
        gettext_lazy("XLSX или CSV → разбор → предпросмотр"),
        "file",
        (ADMIN,),
    ),
    Command(
        "digest",
        gettext_lazy("Дайджест на сегодня"),
        gettext_lazy("Что изменилось в вашем домене"),
        "none",
        ALL_DIRECTORS,
    ),
    Command(
        "explain_match",
        gettext_lazy("Объясни соответствие"),
        gettext_lazy("Ученик и программа → чего не хватает и что даст больше всего"),
        "selection",
        ALL_DIRECTORS,
    ),
    # --- Асем ---
    Command(
        "check_balance",
        gettext_lazy("Проверить баланс списка"),
        gettext_lazy("Соотношение reach / target / safety у ученика"),
        "selection",
        (ADMISSION, ADMIN),
    ),
    # --- Кымбат ---
    Command(
        "parse_mock",
        gettext_lazy("Разобрать Mock Test"),
        gettext_lazy("Баллы строками → секции, сравнение с прошлым"),
        "text",
        (EXAM, ADMIN),
    ),
    # --- Операции уровня управления (фаза 20) ---
    Command(
        "explain_list",
        gettext_lazy("Объясни этот список"),
        gettext_lazy("Выделенные ученики → что общего, с чего начать, кто в приоритете"),
        "selection",
        ALL_DIRECTORS,
    ),
    Command(
        "week_changes",
        gettext_lazy("Что изменилось за неделю"),
        gettext_lazy("Сводка по вашему домену с выводами, а не перечислением"),
        "none",
        ALL_DIRECTORS,
    ),
    Command(
        "focus_today",
        gettext_lazy("На кого смотреть сегодня"),
        gettext_lazy("Короткий список с обоснованием по каждому"),
        "none",
        ALL_DIRECTORS,
    ),
    Command(
        "bulk_tasks",
        gettext_lazy("Поставить задачу выделенным"),
        gettext_lazy("Опишите словами, что нужно, — задача уйдёт предложением на всех выделенных"),
        "text",
        ALL_DIRECTORS,
    ),
    Command(
        "prep_plan",
        gettext_lazy("План подготовки к экзамену"),
        gettext_lazy("От текущего балла к целевому: часы, темы, дата следующего Mock Test"),
        "selection",
        (EXAM, ADMIN),
    ),
    Command(
        "gap_to_tasks",
        gettext_lazy("Пробелы портфолио в задачи"),
        gettext_lazy("Чего не хватает портфолио → задачи роадмапа со сроками"),
        "selection",
        (TALENT, ADMIN),
    ),
    Command(
        "parse_university",
        gettext_lazy("Разобрать вуз"),
        gettext_lazy("Название или ссылка → программы, требования и дедлайны. Записи заводятся неподтверждёнными"),
        "text",
        (ADMISSION, ADMIN),
    ),
    Command(
        "verify_requirements",
        gettext_lazy("Сверить требования с сайтом"),
        gettext_lazy("Программа → пороги с официального сайта, со ссылкой и цитатой. Расхождение уходит предложением"),
        "selection",
        (ADMISSION, ADMIN),
    ),
    Command(
        "parse_activity",
        gettext_lazy("Разобрать активность"),
        gettext_lazy("Описание словами → категория, предмет и чего не хватает"),
        "text",
        (TALENT, ADMIN),
    ),
    Command(
        "parse_certificate",
        gettext_lazy("Прочитать грамоту"),
        gettext_lazy("Фото грамоты → соревнование, дата, результат"),
        "image",
        (SPORT, TALENT, ADMIN),
    ),
    Command(
        "parse_score_screenshot",
        gettext_lazy("Прочитать скриншот с баллами"),
        gettext_lazy("Скриншот результата → попытка экзамена"),
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
        {"code": c.code, "title": str(c.title), "hint": str(c.hint), "input_kind": c.input_kind}
        for c in COMMANDS
        if role in c.roles
    ]


def get(code: str) -> Command | None:
    return next((c for c in COMMANDS if c.code == code), None)


#: Подписи команд, которых нет среди кнопок: предложение могло прийти
#: фоновой сверкой или из уже убранной кнопки, а в списке «ждёт решения»
#: человек всё равно должен читать слова, а не код.
EXTRA_TITLES = {
    "web_sync": gettext_lazy("Фоновая сверка дедлайнов"),
    "import": gettext_lazy("Загрузка файла"),
    "manual": gettext_lazy("Заведено руками"),
    "bulk_action": gettext_lazy("Массовая постановка задач"),
    "gap_to_tasks": gettext_lazy("Пробелы портфолио в задачи"),
}


def title_of(code: str) -> str:
    """Человеческая подпись команды по её коду. Пустой код — пустая строка."""
    if not code:
        return ""
    command = get(code)
    if command is not None:
        return str(command.title)
    return str(EXTRA_TITLES.get(code, ""))
