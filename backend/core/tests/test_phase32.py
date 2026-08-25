"""Приёмка фазы 32: внешний вид держится на том, что легко откатить молча.

Фаза переделывала только вид и движение, поэтому и проверять здесь надо
не поведение, а три вещи, которые ломаются от одной правки и не видны
в тестах логики:

* сброс стилей Tailwind включён — выключат его обратно, и разъедутся
  отступы, маркеры списков и жирность заголовков сразу на всех экранах;
* наборов плотности два и они действительно разные — иначе «плотно
  у директора, просторно у ученика» превращается в одинаково;
* движение не растягивается — потолок фазы 320 мс, и единственное
  исключение названо по имени.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
STYLES = ROOT / "frontend" / "src" / "styles"

#: Потолок фазы 32 для перехода и появления.
MAX_MS = 320

#: Единственная анимация длиннее потолка — затухание подсветки строки.
#: Это угасание цвета, а не движение: за 320 мс человек не успевает
#: заметить, какая из сорока строк изменилась.
SLOW_ALLOWED = {"--dur-flash"}


def read(name: str) -> str:
    return (STYLES / name).read_text(encoding="utf-8")


def test_tailwind_preflight_is_enabled():
    """Сброс стилей подключён, а не закомментирован.

    До фазы 32 строка была закомментирована, и компоненты реестра жили
    на слое-заплатке. Вернуть комментарий — значит разом сдвинуть каждый
    экран, и заметить это можно только глазами.
    """
    base = read("base.css")
    line = "@import 'tailwindcss/preflight.css' layer(base);"
    assert line in base, "сброс стилей Tailwind отключён"
    commented = [
        row.strip() for row in base.splitlines() if "preflight" in row and row.strip().startswith(("/*", "//", "* "))
    ]
    assert not commented, f"строка со сбросом закомментирована: {commented}"


def test_preflight_leftovers_are_written_out():
    """То, что снял сброс, задано своими правилами, а не умолчаниями.

    Отступ абзаца, маркер списка, подчёркивание ссылки и жирность
    заголовка вёрстка брала у браузера. Сброс их снимает — значит
    каждое должно быть написано.
    """
    base = read("base.css")
    for rule in (
        "p:not(:where([data-slot]))",
        "list-style: disc",
        "list-style: decimal",
        "text-decoration: underline",
    ):
        assert rule in base, f"после сброса не задано: {rule}"
    headings = re.search(r"h1,\s*h2,\s*h3,\s*h4,\s*h5,\s*h6\s*\{([^}]*)\}", base)
    assert headings and "font-weight" in headings.group(1), "заголовкам не вернули жирность"


def test_two_densities_and_they_differ():
    """Наборов плотности два, и у директора действительно плотнее.

    Один набор на всех — это «плотность есть в токенах, но её никто
    не видит»: ровно то состояние, из которого фаза выводила.
    """
    text = read("density.css")
    assert "[data-density='dense']" in text
    assert "[data-density='roomy']" in text
    dense, roomy = text.split("[data-density='roomy']")

    def value(block: str, name: str) -> float:
        found = re.search(rf"{name}:\s*([\d.]+)px", block)
        assert found, f"в наборе нет {name}"
        return float(found.group(1))

    for name in ("--type-body", "--type-screen", "--row-h", "--pad-card", "--control-h"):
        assert value(dense, name) < value(roomy, name), f"{name} у ученика не больше, чем у директора"


def test_density_is_chosen_by_role_not_by_screen():
    """Плотность ставится один раз по роли, а не размерами по экранам."""
    source = (ROOT / "frontend" / "src" / "density.ts").read_text(encoding="utf-8")
    assert "data-density" in source or "dataset.density" in source
    assert "student" in source, "плотность не зависит от роли"


def test_motion_stays_under_the_cap():
    """Ничего длиннее 320 мс, кроме названного по имени затухания."""
    text = read("motion.css")
    slow = {name: int(ms) for name, ms in re.findall(r"(--dur-[a-z]+):\s*(\d+)ms", text) if int(ms) > MAX_MS}
    assert set(slow) <= SLOW_ALLOWED, f"движение длиннее {MAX_MS} мс: {slow}"
    assert "--dur-slow" in text and int(re.search(r"--dur-slow:\s*(\d+)ms", text).group(1)) <= MAX_MS


def test_reduced_motion_is_respected():
    """Системная настройка «уменьшить движение» снимает переходы.

    И в CSS, и в сценариях на `motion`: у второго своя настройка,
    и правило в CSS до него не достаёт.
    """
    base = read("base.css")
    assert "prefers-reduced-motion" in base
    block = base.split("prefers-reduced-motion", 1)[1]
    assert "animation: none" in block and "transition: none" in block

    js = (ROOT / "frontend" / "src" / "motion.ts").read_text(encoding="utf-8")
    assert "useReducedMotion" in js, "сценарии движения не спрашивают системную настройку"
