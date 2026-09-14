"""Фаза 76: стили общих компонентов живут в общих файлах.

Общий компонент (`components/`, `layout/`) рисуется на любом экране, и его
стили обязаны грузиться вместе с ним — из `components/*.css`, `layout/*.css`
или `styles/*.css`. Класс общего компонента, описанный в CSS экрана, —
болезнь, всплывавшая в 69-й, 73-й и 75-й: раскладка есть на одном экране
и отсутствует на другом, а находится это только глазами.

Унаследованный долг перечислен поимённо (D45): новый такой класс тест
не пропустит, а старые уходят по мере переноса — список должен только
уменьшаться.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/frontend").is_dir() else Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"

#: имя класса в духе БЭМ: блок, элемент через `__`, модификатор через `--`
CLASS = r"[a-z][a-z0-9-]*(?:__[a-z0-9-]+)?(?:--[a-z0-9-]+)?"

#: классы общих компонентов, которые пока описаны в CSS экранов (D45).
#: Только элементы и модификаторы: голое имя блока («card», «toolbar»)
#: слишком часто совпадает со словом в строке, чтобы ловить его регуляркой
LEGACY = frozenset(
    {
        "calcell--picked",
        "calcell__day--today",
        "calcell__dots",
        "calfeed__body",
        "calfeed__group",
        "calfeed__month",
        "calfeed__more",
        "calfeed__row",
        "calfeed__title",
        "calfeed__weekday",
        "calfeed__when",
        "cchip--on",
        "cfilters__spacer",
        "goals__create",
        "goals__input",
        "handout__check",
        "handout__counts",
        "handout__field",
        "handout__part",
        "handout__total",
        "handout__warn",
        "home__cal",
        "home__calday--marked",
        "home__calday--today",
        "home__calgrid",
        "home__calhead",
        "home__calnav",
        "home__calpanel",
        "home__calweekday",
        "home__cardhead",
        "home__cardtitle",
        "home__panelhead",
        "home__when",
        "imp__cleanup",
        "mat__bigtitle",
        "mat__comment",
        "mat__complain",
        "mat__desc",
        "mat__meta",
        "mat__single",
        "password-rules__ok",
        "password-rules__todo",
        "prog__actions",
        "prog__check",
        "prog__field",
        "prog__form",
        "prog__grid",
        "prog__name",
        "prog__part",
        "prog__parts",
        "prog__round",
        "prog__row",
        "propose__form",
        "rowmenu__action",
        "rowmenu__item",
        "rowmenu__panel",
        "rowmenu__sep",
        "squeue__actions",
        "squeue__body",
        "squeue__bulk",
        "squeue__editinput",
        "squeue__row",
        "squeue__what",
        "toolbar__spacer",
        "users__check",
        "users__file",
        "users__form",
        "users__link",
        "users__off",
        "users__password",
        "users__wrap",
        "wizard__domains",
        "wizard__group",
        "wizard__off",
        "wizard__step--done",
        "wizard__step--on",
        "wizard__steps",
        "wizard__sum",
    }
)


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


def test_phone_fixes_of_phase_76_are_in_shared_css():
    """Плашка, свёрнутая панель и экран «нет связи» — в `ui.css`."""
    css = (SRC / "components" / "ui.css").read_text(encoding="utf-8")
    for name in (".notice__body {", ".fold__head {", ".offline {"):
        assert name in css, name
    # строка-сводка плашки не задаёт дорожке ширину — иначе страница едет вбок
    body = css[css.index(".notice__body {") : css.index(".notice__line {")]
    assert "grid-template-columns: minmax(0, 1fr)" in body
