"""Стили общих компонентов живут в общих файлах, а не в CSS отдельных экранов.

Общий компонент (`components/`, `layout/`) рисуется на любом экране, и его
стили обязаны грузиться вместе с ним — из `components/*.css`, `layout/*.css`
или `styles/*.css`. Класс общего компонента, описанный в CSS экрана, —
болезнь, всплывавшая в 69-й, 73-й и 75-й: раскладка есть на одном экране
и отсутствует на другом, а находится это только глазами.

Унаследованный долг перечислялся поимённо и перенесён целиком: в CSS
экранов остались только классы самих экранов. Новый такой класс тест
не пропустит.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/frontend").is_dir() else Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"

#: имя класса в духе БЭМ: блок, элемент через `__`, модификатор через `--`
CLASS = r"[a-z][a-z0-9-]*(?:__[a-z0-9-]+)?(?:--[a-z0-9-]+)?"

#: классы общих компонентов, которые пока описаны в CSS экранов. Долг
#: закрыт: всё перенесено в `components/*.css`, новых тест не пустит
LEGACY: frozenset[str] = frozenset()


def classes_in(path: Path) -> set[str]:
    return set(re.findall(r"\." + f"({CLASS})", path.read_text(encoding="utf-8")))


def used_by_shared_components() -> set[str]:
    used: set[str] = set()
    for folder in ("components", "layout"):
        for path in (SRC / folder).glob("*.tsx"):
            text = path.read_text(encoding="utf-8")
            used |= set(re.findall(r"[\"'` ](" + CLASS + r")[\"'` ]", text))
    # только элементы и модификаторы — у них однозначное имя
    return {name for name in used if "__" in name or "--" in name}


def test_shared_component_styles_live_in_shared_files():
    """Класс общего компонента описан в общем CSS, а не в CSS экрана."""
    shared: set[str] = set()
    for folder in ("components", "layout", "styles"):
        for path in (SRC / folder).glob("*.css"):
            shared |= classes_in(path)
    screen_defined: dict[str, set[str]] = {}
    for path in (SRC / "screens").rglob("*.css"):
        for name in classes_in(path):
            screen_defined.setdefault(name, set()).add(str(path.relative_to(SRC)))

    used = used_by_shared_components()
    stray = {name for name in used if name in screen_defined and name not in shared}
    new = sorted(stray - LEGACY)
    assert not new, "стили общего компонента в CSS экрана: " + ", ".join(
        f"{name} ({', '.join(sorted(screen_defined[name]))})" for name in new
    )
    # долг только уменьшается: перенесённое вычёркивается из списка
    gone = sorted(LEGACY - stray)
    assert not gone, f"уже перенесено, уберите из LEGACY: {gone}"


def test_phone_fixes_are_in_shared_css():
    """Плашка, свёрнутая панель и экран «нет связи» — в `ui.css`."""
    css = (SRC / "components" / "ui.css").read_text(encoding="utf-8")
    for name in (".notice__body {", ".fold__head {", ".offline {"):
        assert name in css, name
    # строка-сводка плашки не задаёт дорожке ширину — иначе страница едет вбок
    body = css[css.index(".notice__body {") : css.index(".notice__line {")]
    assert "grid-template-columns: minmax(0, 1fr)" in body
