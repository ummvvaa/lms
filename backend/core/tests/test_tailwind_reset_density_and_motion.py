"""Приёмка переделки вида и движения: внешний вид держится на том, что легко откатить молча.

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


def test_sizes_live_in_one_scale_as_variables():
    """Размерный ряд один на все роли и задан переменными, а не числами по экранам.

    Экраны берут размеры через `var(--type-*)`, `var(--pad-card)`,
    `var(--row-h)`: правка одного числа в `density.css` меняет весь продукт,
    а второго набора плотности нет — образцы ученика и куратора нарисованы
    одним рядом.
    """
    text = read("density.css")
    assert "data-density" not in text, "второго набора плотности быть не должно"
    names = ("--type-screen", "--type-figure", "--type-body", "--type-note", "--pad-card", "--row-h", "--control-h")
    for name in names:
        assert re.search(rf"{name}:\s*[\d.]+px", text), f"в ряду нет {name}"
    # телефон меняет только то, во что надо попадать пальцем
    phone = text.split("@media (max-width: 759px)")[1]
    assert "--control-h: 44px" in phone and "--row-h" in phone


def test_density_is_not_chosen_by_role():
    """Переключателя плотности по роли больше нет: атрибут не ставится нигде."""
    assert not (ROOT / "frontend" / "src" / "density.ts").exists()
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "applyDensity" not in app and "data-density" not in app


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


def _animated_slots() -> dict[str, str]:
    """Части реестра shadcn, у которых в разметке появление или явная длительность."""
    out: dict[str, str] = {}
    for path in sorted((ROOT / "frontend" / "src" / "components" / "ui").glob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'data-slot="([a-z-]+)"', text):
            # className той же части: до следующей части или функции
            tail = re.split(r'data-slot="|\nfunction ', text[match.end() : match.end() + 1500])[0]
            classes = re.search(r"className=(?:\{cn\(\s*)?['\"]([^'\"]*)['\"]", tail)
            if classes and re.search(r"\banimate-in\b|\bduration-\d+", classes.group(1)):
                out[match.group(1)] = path.name
    return out


def test_registry_motion_takes_tokens():
    """Окна и меню shadcn двигаются нашими токенами, а не числами из утилит.

    Правка в самом компоненте не переживёт `shadcn add`, поэтому длительность
    назначает `motion.css` по `data-slot`. Новый компонент с появлением —
    строка в том же правиле.
    """
    motion = read("motion.css")
    slots = _animated_slots()
    assert {"dialog-content", "dropdown-menu-content", "sheet-content"} <= set(slots), slots
    missing = sorted(slot for slot in slots if f"[data-slot='{slot}']" not in motion)
    assert not missing, f"длительность из утилиты, а не из токена: {missing}"
    for slot in slots:
        rule = motion.split(f"[data-slot='{slot}']", 1)[1].split("}", 1)[0]
        assert re.search(r"--tw-duration:\s*var\(--dur-[a-z]+\)", rule), slot

    base = read("base.css")
    assert "--default-transition-duration: var(--dur-fast)" in base
