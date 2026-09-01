"""Приёмка фазы 33: то, из-за чего белел экран и разъезжалась шапка, не возвращается.

Проверяем по исходникам фронта: логику вида нечем проверить из pytest,
а вот три класса поломок этой фазы видны в тексте файлов и ловятся
дешевле, чем браузером.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def sources(suffix: str = ".tsx") -> dict[Path, str]:
    return {
        path: path.read_text(encoding="utf-8")
        for path in FRONTEND.rglob(f"*{suffix}")
        if path.name != "schema.ts" and "node_modules" not in path.parts
    }


def test_error_boundaries_wrap_app_and_screen():
    """Граница ошибок стоит вокруг приложения и вокруг содержимого экрана.

    Без неё любое исключение при рендере размонтирует всё дерево, и человек
    видит белую страницу — так в фазе 32 сломался переход в профиль.
    """
    main = (FRONTEND / "main.tsx").read_text(encoding="utf-8")
    shell = (FRONTEND / "layout" / "Shell.tsx").read_text(encoding="utf-8")
    assert '<ErrorBoundary scope="app">' in main, "внешней границы ошибок нет в main.tsx"
    assert '<ErrorBoundary scope="screen">' in shell and "<Outlet />" in shell, "границы вокруг экрана нет в Shell.tsx"
    boundary = (FRONTEND / "components" / "ErrorBoundary.tsx").read_text(encoding="utf-8")
    assert "componentDidCatch" in boundary and "console.error" in boundary
    assert "captureException" in boundary, "ошибка не уходит в Sentry, когда он подключён"


def test_menu_group_labels_live_inside_groups():
    """Подпись группы меню стоит только внутри `DropdownMenuGroup`.

    `Menu.GroupLabel` из Base UI без группы бросает исключение при рендере —
    ровно так и появился белый экран. Проверяем каждым файлом: подписей
    без открытой группы быть не должно.
    """
    broken = []
    for path, text in sources().items():
        if path.parts[-2] == "ui":
            continue
        depth = 0
        for line in text.splitlines():
            depth += line.count("<DropdownMenuGroup") - line.count("</DropdownMenuGroup>")
            if "<DropdownMenuLabel" in line and depth <= 0:
                broken.append(path.name)
    assert not broken, f"подпись группы вне группы: {sorted(set(broken))}"


def test_buttons_and_badges_come_from_the_registry():
    """Собственных классов кнопки и чипа в разметке не осталось (долг R1 фазы 32).

    Половина на `Button`, половина на `.btn` — худший из вариантов: два вида
    одной кнопки на соседних экранах.
    """
    left = []
    for path, text in sources().items():
        if path.parts[-2] == "ui":
            continue
        for match in re.finditer(r"className=(?:\"[^\"]*|\{`[^`]*)\b(btn|chip)\b", text):
            left.append(f"{path.name}: {match.group(0)[:60]}")
    assert not left, f"остались свои классы кнопок и чипов: {left[:10]}"
    css = "\n".join(p.read_text(encoding="utf-8") for p in FRONTEND.rglob("*.css"))
    assert re.search(r"^\.btn\b", css, re.M) is None, "правила `.btn` остались в стилях"
    assert re.search(r"^\.chip\b", css, re.M) is None, "правила `.chip` остались в стилях"


def test_popups_go_through_portals():
    """Колокольчик и меню профиля всплывают через портал, а не раздвигают шапку."""
    notif = (FRONTEND / "components" / "Notifications.tsx").read_text(encoding="utf-8")
    menu = (FRONTEND / "components" / "ProfileMenu.tsx").read_text(encoding="utf-8")
    assert "<Popover" in notif and "notif__back" not in notif
    assert "<DropdownMenu" in menu and "pmenu__back" not in menu
    shell_css = (FRONTEND / "layout" / "shell.css").read_text(encoding="utf-8")
    # с фазы 48 шапка в две колонки: «кто вошёл» уехал вниз бокового меню,
    # где живут блок пользователя, меню профиля и колокольчик
    assert "grid-template-columns: minmax(0, 420px) minmax(120px, 1fr)" in shell_css
    assert "<ProfileMenu user={" in (FRONTEND / "layout" / "Shell.tsx").read_text(encoding="utf-8")


def test_spacing_uses_the_scale():
    """Отступы — только со шкалы 4/8/12/16/24/32 (и кратные 8 выше).

    Произвольное число в `padding` — первый шаг к тому, что каждая карточка
    снова устроена по-своему.
    """
    allowed = {0, 1, 2, 4, 8, 12, 16, 24, 32, 40, 48, 56, 64}
    offenders = []
    for path in FRONTEND.rglob("*.css"):
        if path.name in ("tokens.css", "density.css", "motion.css"):
            continue
        for match in re.finditer(
            r"^\s*(padding|margin|gap|row-gap|column-gap)[a-z-]*:\s*([^;{}]+);", path.read_text(encoding="utf-8"), re.M
        ):
            for value in re.findall(r"(?<![-\w])(\d+(?:\.\d+)?)px", match.group(2)):
                if float(value) not in allowed:
                    offenders.append(f"{path.name}: {match.group(0).strip()}")
    assert not offenders, f"отступы вне шкалы: {offenders[:10]}"


def test_nav_items_are_grouped():
    """У каждого пункта меню есть группа, и группа — из объявленного набора.

    С фазы 48 наборов два: у сотрудника «Работа · Данные · Настройки»,
    у ученика «Основное · Поступление · Работа». Пункт без группы
    в меню не встаёт вовсе — это и проверяем.
    """
    nav = (FRONTEND / "layout" / "nav.ts").read_text(encoding="utf-8")
    groups = "main|admission|work|data|settings"
    items = re.findall(rf"\{{ path: '[^']+', label: '[^']*', icon: '[a-zA-Z]+'(, group: '({groups})')?[^}}]*\}}", nav)
    assert len(items) > 20, "пункты меню не разобрались"
    ungrouped = [item for item in items if not item[0]]
    assert not ungrouped, f"пункты без группы: {len(ungrouped)}"
    assert "NAV_GROUPS" in nav and nav.count("key: '") >= 5
