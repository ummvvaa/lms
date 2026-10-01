"""Сборка разбита по экранам, а стили остаются одним файлом в прежнем порядке.

Экраны грузятся по маршруту (`lazy` в `App.tsx`): одна сборка на все роли
весила 2,4 МБ, и ученик скачивал журналы, импорт и обзор школы. Стили при
этом не делятся (`cssCodeSplit: false`) и подключаются сразу: файл стилей,
доступный только через ленивый экран, попал бы в конец общего CSS — после
`base.css` — и при равном весе тихо переиграл бы общие правила.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/frontend").is_dir() else Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"

#: экраны до входа: нужны раньше, чем известна роль, и грузятся сразу
EAGER_SCREENS = {"Login", "LinkLogin", "SetPassword", "ChangePassword", "ConfirmEmail"}

STATIC_IMPORT = re.compile(r"""^\s*import\s+(?!type\b)(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]""", re.M)
ANY_CSS_IMPORT = re.compile(r"""^\s*import\s+['"]([^'"]+\.css)['"]""", re.M)


def _resolve(base: Path, spec: str) -> Path | None:
    if spec.startswith("@/"):
        path = SRC / spec[2:]
    elif spec.startswith("."):
        path = Path(os.path.normpath(base.parent / spec))
    else:
        return None
    for candidate in (path, Path(f"{path}.ts"), Path(f"{path}.tsx"), path / "index.ts", path / "index.tsx"):
        if candidate.is_file():
            return candidate
    return None


def css_of_first_page() -> list[Path]:
    """Стили, которые сборка кладёт в общий файл до ленивых экранов, — по порядку."""
    seen: set[Path] = set()
    order: list[Path] = []

    def visit(path: Path) -> None:
        if path in seen:
            return
        seen.add(path)
        for spec in STATIC_IMPORT.findall(path.read_text(encoding="utf-8")):
            target = _resolve(path, spec)
            if target is None:
                continue
            if target.suffix == ".css":
                if target not in seen:
                    seen.add(target)
                    order.append(target)
            else:
                visit(target)

    visit(SRC / "main.tsx")
    return order


def test_every_style_loads_with_the_first_page():
    """Файл стилей, импортированный экраном, стоит и в `screenStyles.ts`."""
    first = set(css_of_first_page())
    imported: dict[Path, str] = {}
    for path in SRC.rglob("*.ts*"):
        for spec in ANY_CSS_IMPORT.findall(path.read_text(encoding="utf-8")):
            target = _resolve(path, spec)
            if target is not None:
                imported.setdefault(target, path.relative_to(SRC).as_posix())
    late = sorted(f"{css.relative_to(SRC)} (из {where})" for css, where in imported.items() if css not in first)
    assert not late, f"стили приедут с экраном и встанут после base.css — допишите в screenStyles.ts: {late}"


def test_base_styles_stay_last():
    """`base.css` последним, как до разбиения: тема и сброс поверх стилей экранов."""
    order = css_of_first_page()
    assert order[-1] == SRC / "styles" / "base.css"
    assert order.index(SRC / "screens" / "screens.css") > order.index(SRC / "screens" / "academics" / "academics.css")


def test_screens_load_by_route():
    """Экраны за входом — ленивые: статический импорт экрана тянет его в общий файл."""
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    eager = set(re.findall(r"^import (\w+)(?:, \{[^}]*\})? from '\./screens/", app, re.M))
    assert eager <= EAGER_SCREENS, f"экран снова в общем файле: {sorted(eager - EAGER_SCREENS)}"
    assert len(re.findall(r"= lazy\(\(\) => import\('\./screens/", app)) > 50
    config = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert "cssCodeSplit: false" in config
    main = (SRC / "main.tsx").read_text(encoding="utf-8")
    assert "vite:preloadError" in main, "после выката открытая вкладка не перезагрузится на новую сборку"
