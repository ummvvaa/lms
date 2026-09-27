"""Контраст токенов обеих тем — по WCAG, по самому файлу токенов.

Основной текст к своему фону — не ниже 4,5 : 1, подписи, чипы состояний
и текст на акценте — не ниже 3 : 1; меню в тёмной теме отличимо от полотна,
карточка — от полотна. Считается из `tokens.css`, поэтому новое значение
токена проверяется само, без браузера.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path("/repo") if Path("/repo/frontend").is_dir() else Path(__file__).resolve().parents[3]
TOKENS = ROOT / "frontend" / "src" / "styles" / "tokens.css"

#: (текст, фон, порог): основной текст — 4,5; подписи и чипы — 3
PAIRS: tuple[tuple[str, str, float], ...] = (
    ("--ink", "--surface", 4.5),
    ("--ink", "--canvas", 4.5),
    ("--ink", "--surface-2", 4.5),
    ("--ink-2", "--surface", 4.5),
    ("--ink-2", "--canvas", 4.5),
    ("--ink-2", "--neutral-bg", 4.5),
    ("--ink-3", "--surface", 3),
    ("--ink-3", "--canvas", 3),
    ("--accent-ink", "--surface", 4.5),
    ("--accent-ink", "--accent-bg", 4.5),
    ("--menu-text", "--menu-bg", 4.5),
    ("--menu-item", "--menu-bg", 3),
    ("--on-accent", "--accent", 3),
    ("--good", "--good-bg", 3),
    ("--warn", "--warn-bg", 3),
    ("--bad", "--bad-bg", 3),
    ("--info", "--info-bg", 3),
    ("--good", "--surface", 3),
    ("--warn", "--surface", 3),
    ("--bad", "--surface", 3),
    ("--info", "--surface", 3),
)

#: поверхности, которые обязаны различаться: меню от полотна, карточка от полотна
DISTINCT: tuple[tuple[str, str, float], ...] = (
    ("--menu-bg", "--canvas", 1.15),
    ("--surface", "--canvas", 1.05),
)


def _block(source: str, selector: str) -> dict[str, str]:
    start = source.index(selector)
    end = source.index("}", start)
    return dict(re.findall(r"(--[a-z0-9-]+):\s*([^;]+);", source[start:end]))


def themes() -> dict[str, dict[str, str]]:
    source = TOKENS.read_text(encoding="utf-8")
    light = _block(source, ":root {")
    dark = _block(source, ":root[data-theme='dark']")
    return {"light": light, "dark": {**light, **dark}}


def _rgb(value: str, behind: tuple[float, float, float]) -> tuple[float, float, float]:
    value = value.strip()
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return tuple(int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]
    found = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)", value)
    assert found, f"непонятный цвет {value!r}"
    r, g, b = (int(found.group(i)) / 255 for i in (1, 2, 3))
    alpha = float(found.group(4) or 1)
    # полупрозрачный цвет смешивается с тем, что под ним
    return tuple(c * alpha + q * (1 - alpha) for c, q in zip((r, g, b), behind, strict=True))  # type: ignore[return-value]


def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(theme: dict[str, str], fg: str, bg: str) -> float:
    surface = _rgb(theme["--surface"], (1.0, 1.0, 1.0))
    back = _rgb(theme[bg], surface)
    front = _rgb(theme[fg], back)
    hi, lo = sorted((_luminance(front), _luminance(back)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("name", ["light", "dark"])
def test_text_keeps_contrast(name):
    theme = themes()[name]
    weak = [
        f"{fg} на {bg}: {contrast(theme, fg, bg):.2f} < {need}"
        for fg, bg, need in PAIRS
        if contrast(theme, fg, bg) < need
    ]
    assert not weak, f"тема {name}: " + "; ".join(weak)


@pytest.mark.parametrize("name", ["light", "dark"])
def test_surfaces_are_distinguishable(name):
    theme = themes()[name]
    weak = [
        f"{a} и {b}: {contrast(theme, a, b):.2f} < {need}" for a, b, need in DISTINCT if contrast(theme, a, b) < need
    ]
    assert not weak, f"тема {name}: " + "; ".join(weak)


def test_dark_theme_redefines_every_colour_token():
    """У каждого цветового токена светлой темы есть тёмный двойник."""
    source = TOKENS.read_text(encoding="utf-8")
    light = _block(source, ":root {")
    dark = _block(source, ":root[data-theme='dark']")
    colours = [
        name
        for name, value in light.items()
        if (value.strip().startswith("#") or value.strip().startswith("rgba"))
        and not name.startswith("--chart")
        and not name.startswith("--domain")
    ]
    missing = [name for name in colours if name not in dark]
    assert not missing, f"без тёмного значения: {missing}"


def test_no_old_token_names_remain():
    """Псевдонимов прежних имён в стилях и экранах не осталось."""
    src = ROOT / "frontend" / "src"
    old = re.compile(
        r"var\(--(brand|milk|ok|risk|nav-|hero-|on-hero|teal|indigo|sand|ink-60|ink-40|surface-mute|surface-hover|"
        r"on-brand|on-ink|row-head|row-hover|row-line|row-flash|radius-sm|radius-md|radius-lg|radius-tile|radius-hero)"
    )
    hits = []
    for path in list(src.rglob("*.css")) + list(src.rglob("*.tsx")):
        if "components/ui/" in str(path):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if old.search(line):
                hits.append(f"{path.relative_to(src)}:{number}")
    assert not hits, "старые имена токенов: " + ", ".join(hits[:20])
