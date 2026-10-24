"""Иконки меню: одна иконка — один смысл, в меню одной роли повторов нет (27.09.2026).

Читает `layout/nav.ts` как текст: константы пунктов, наборы ролей,
раскрытие `...DIRECTOR_COMMON` и одиночных констант, добавки `navFor`
(сводный вид, материалы, олимпиадная группа). Таблица «иконка → пункты»
живёт здесь, в `ICON_LABELS`: одна иконка — один смысл, пункт меню с новой
иконкой или новой подписью требует строки в таблице. Таблица в описании языка
интерфейса — её пересказ.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
NAV = ROOT / "frontend" / "src" / "layout" / "nav.ts"
ICONS = ROOT / "frontend" / "src" / "layout" / "icons.tsx"

#: подпись пункта — ключ перевода `tk('…')`: переводится при показе
ITEM = re.compile(r"\{ path: '(?P<path>[^']+)', label: tk\('(?P<label>[^']*)'\), icon: '(?P<icon>[a-zA-Z]+)'")
ROLES = (
    "student",
    "director_behavior",
    "director_admission",
    "director_exam",
    "director_talent",
    "director_sport",
    "curator",
    "teacher",
    "admin",
)

#: Иконка → пункты меню под ней. Одна иконка — один смысл (комментарий справа)
ICON_LABELS: dict[str, tuple[str, ...]] = {
    "usage": ("Использование",),  # действия в системе
    "home": ("Главная", "Дашборд"),  # главная роли
    "sun": ("Сегодня",),  # сегодняшний день
    "schedule": ("Расписание", "Мои уроки"),  # расписание уроков; «Мои уроки» — у директора с уроками
    "calendar": ("Календарь", "Освобождения"),  # календарь событий; освобождения — дни вне уроков
    "book": ("Оценки", "Журналы", "Предметы", "Предметы и треки"),  # предметы и оценки
    "cap": ("Экзамены", "Результаты экзаменов"),  # экзамены
    "route": ("Мой путь",),  # путь ученика
    "flag": ("Роадмап",),  # вехи плана
    "branch": ("Треки",),  # ветки
    "person": ("Портфолио", "Пользователи"),  # один человек
    "people": ("Ученики", "Группы", "Олимпиадная группа"),  # группа людей
    "idcard": ("Учителя",),  # сотрудник
    "target": ("Подбор вузов",),  # подбор
    "search": ("Каталог вузов",),  # поиск
    "heart": ("Избранное",),  # избранное
    "bookmark": ("Мои вузы",),  # свой список
    "checklist": ("План поступления", "Задачи", "Шаблоны задач"),  # задачи
    "check": ("Задачи сотрудникам",),  # поручение сотруднику с приёмкой
    "card": ("Стипендии", "Расходы на ИИ"),  # деньги
    "compass": ("Профтест",),  # выбор направления: тесты профориентации у ученика и учителя
    "doc": ("Эссе", "Конструктор эссе", "Эссе учеников"),  # эссе
    "docs": ("Документы",),  # документы
    "pencil": ("Подготовка",),  # тренировка
    "star": ("Достижения", "Достижения школы", "ТОП-30"),  # достижения и лучшие
    "openbook": ("Ресурсы",),  # что читают
    "folder": ("Материалы",),  # материалы
    "table": ("Таблица",),  # таблица
    "sparkle": ("Помощник",),  # помощник
    "bulb": ("Предложения",),  # предложения
    "news": ("Дайджест",),  # сводка
    "upload": ("Импорт",),  # загрузка файлом
    "clipboard": ("Mock Test",),  # Mock Test школы файлом
    "stopwatch": ("Mock Test онлайн",),  # Mock Test на платформе, на время
    "layers": ("Подгруппы и потоки",),  # составы
    "chart": ("Успеваемость",),  # успеваемость
    "report": ("Отчёты родителям", "Отчёты"),  # отчёты: родителям и все отчёты школы у директора
    "year": ("Учебный год",),  # четверти года
    "building": ("Справочник", "Справочник вузов"),  # вузы
    "clock": ("Дедлайны",),  # сроки
    "inbox": ("Очередь",),  # очередь
    "presence": ("Посещаемость",),  # посещаемость
    "history": ("Журнал изменений",),  # журнал действий
    "list": ("Правила обзвона", "Справочник экзаменов"),  # правила и списки-справочники
    "phone": ("Контакты родителей", "Родители"),  # родители и их контакты
    "alert": ("Риски",),  # риски
    "grid": ("Сводный вид",),  # сводный вид
    "ball": ("Виды спорта", "Спорт"),  # спорт
    "trophy": ("Соревнования", "Мероприятия"),  # соревнования и спортивные мероприятия
    "medal": ("Олимпиады",),  # олимпиада
    "megaphone": ("Сюжеты главной",),  # сюжеты
    "sliders": ("Настройки школы",),  # пороги и окна школы
    "box": ("Архив",),  # архив
    "homework": ("Проверка ДЗ", "Домашние задания"),  # домашнее задание со сдачей
}


def _blocks(text: str) -> dict[str, str]:
    """Тело каждой константы и каждого набора роли — по имени."""
    out: dict[str, str] = {}
    for match in re.finditer(
        r"^(?:export )?const (?P<name>[A-Z_]+)(?::[^=]+)? = (?P<body>\[.*?\n\]|\{[^\n]*\}|\{.*?\n\})",
        text,
        re.S | re.M,
    ):
        out[match.group("name")] = match.group("body")
    nav = re.search(r"export const NAV: Record<Role, NavItem\[\]> = \{(?P<body>.*?)\n\}\n", text, re.S)
    assert nav, "набор NAV не найден"
    for match in re.finditer(r"\n  (?P<role>[a-z_]+): \[(?P<body>.*?)\n  \],", nav.group("body"), re.S):
        out[f"role:{match.group('role')}"] = match.group("body")
    return out


def _items(blocks: dict[str, str], body: str) -> list[tuple[str, str, str]]:
    found = [(m.group("path"), m.group("label"), m.group("icon")) for m in ITEM.finditer(body)]
    for name in re.findall(r"\.\.\.([A-Z_]+)", body):
        found += _items(blocks, blocks[name])
    for name in re.findall(r"^\s+([A-Z_]+),$", body, re.M):
        found += _items(blocks, blocks[name])
    return found


def _hidden(text: str, role: str) -> set[str]:
    """Спрятанное и свёрнутое у директора (`DIRECTOR_HIDDEN`, `DIRECTOR_FOLDED`) в меню не встаёт."""
    gone = re.search(r"const DIRECTOR_GONE = \[(?P<body>[^\]]*)\]", text)
    out: set[str] = set()
    for name in ("DIRECTOR_HIDDEN", "DIRECTOR_FOLDED"):
        block = re.search(rf"const {name}[^=]*= \{{(?P<body>.*?)\n\}}", text, re.S)
        line = re.search(rf"^  {role}: \[(?P<body>[^\n]*)\],$", block.group("body"), re.M) if block else None
        if line:
            body = line.group("body")
            out |= set(re.findall(r"'([^']+)'", body))
            if "...DIRECTOR_GONE" in body and gone:
                out |= set(re.findall(r"'([^']+)'", gone.group("body")))
    return out


def menu_of(role: str) -> list[tuple[str, str, str]]:
    text = NAV.read_text(encoding="utf-8")
    blocks = _blocks(text)
    hidden = _hidden(text, role)
    items = [item for item in _items(blocks, blocks[f"role:{role}"]) if item[0] not in hidden]
    extras = re.search(r"export function navFor\(.*?\n\}\n", text, re.S).group(0)
    for path, label, icon in ITEM.findall(extras):
        if path in hidden:
            continue
        if path == "/overview" and role == "director_behavior":
            items.append((path, label, icon))
        if path == "/materials":
            items.append((path, label, icon))
        if path == "/olympiad-group" and role == "director_talent":
            items.append((path, label, icon))
    return items


def test_every_role_menu_has_no_repeated_icon():
    for role in ROLES:
        seen: dict[str, str] = {}
        for _path, label, icon in menu_of(role):
            assert icon not in seen, f"{role}: иконка «{icon}» у «{label}» и у «{seen[icon]}»"
            seen[icon] = label
        assert seen, f"{role}: меню пустое"


def test_icons_exist_and_the_speedometer_is_gone():
    icons = ICONS.read_text(encoding="utf-8")
    known = set(re.findall(r"^  ([a-zA-Z]+): ", icons, re.M))
    assert "dashboard" not in known, "спидометр вернулся"
    for role in ROLES:
        for _path, label, icon in menu_of(role):
            assert icon in known, f"{role}: у «{label}» нет иконки «{icon}» в icons.tsx"


def test_every_menu_item_has_its_icon_meaning():
    """Пункт меню — под иконкой своего смысла из `ICON_LABELS`, и у иконки один смысл."""
    for role in ROLES:
        for _path, label, icon in menu_of(role):
            assert icon in ICON_LABELS, f"иконки «{icon}» ({label}) нет в ICON_LABELS"
            assert label in ICON_LABELS[icon], f"«{label}» не записан за иконкой «{icon}» в ICON_LABELS"
    labels = [label for group in ICON_LABELS.values() for label in group]
    assert len(labels) == len(set(labels)), "подпись записана за двумя иконками"
