"""Приёмка фазы 50: календарь и карусель поменялись местами.

Решение владельца: слева широкий календарь, справа узкая карусель.
Соотношение колонок прежнее, меняются только места блоков — и вместе
с этим уходит второй размер календаря: уменьшали его лишь потому, что
колонка была узкой.

Проверки по исходникам: размер и порядок из pytest не увидеть, но
поломки, которые эта фаза уже проходила (второй размер, календарь
справа, заголовок в размер экрана в узкой колонке), видны в тексте
файлов и ловятся дешевле, чем браузером. Живой вид — в `phase50.spec.ts`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def read(*parts: str) -> str:
    return (FRONTEND.joinpath(*parts)).read_text(encoding="utf-8")


def test_calendar_stands_before_the_carousel():
    """Календарь идёт первым, карусель — за ним.

    Порядок в разметке важен не только на широком экране: на планшетной
    ширине колонка одна, и первым встаёт тот, кто раньше в тексте.
    """
    home = read("screens", "dashboards", "StudentHome.tsx")
    top = home.split("className={`home__top")[1].split("</div>")[0]
    # с фазы 51 карточка календаря вынесена в общий компонент
    # (`components/CalendarCard.tsx`): у неё появились режимы телефона,
    # и та же карточка стоит у директора спорта
    assert top.index("<CalendarCard") < top.index("<CuesCarousel"), "календарь стоит первым"


def test_columns_keep_the_ratio_and_the_calendar_takes_the_wide_one():
    """Соотношение колонок прежнее: 1.35 к 1, широкая — первая."""
    css = read("screens", "dashboards", "home.css")
    top = css.split("\n.home__top {")[1].split("}")[0]
    assert "grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);" in top


def test_calendar_has_one_size():
    """Второго размера календаря нет ни в разметке, ни в стилях.

    Компактный вариант фазы 49 существовал ради узкой колонки. Колонка
    стала широкой, и уменьшать нечего: без карусели календарь
    растягивается, а шрифт, кружки и строки событий остаются теми же.
    """
    card = read("components", "CalendarCard.tsx")
    assert "wide" not in card, "второй размер календаря вернулся в разметку"
    css = read("screens", "dashboards", "home.css")
    assert "home__cal--wide" not in css, "второй размер календаря вернулся"
    # ни одного правила, которое меняло бы размер текста календаря
    # вместе с исчезновением карусели
    for rule in re.findall(r"\.home__top--calendar[^{]*\{([^}]*)\}", css):
        assert "font-size" not in rule, "без карусели календарь растягивается, а не растёт шрифтом"


def test_calendar_stretches_by_the_grid_share_not_by_the_font():
    """Сетка дней тянется долей карточки с полом и потолком.

    Рядом с каруселью доля упирается в пол и отдаёт остальное панели
    событий, без карусели дорастает до потолка — и шире становятся
    обе половины сразу, теми же буквами.
    """
    css = read("screens", "dashboards", "home.css")
    rules = [body for body in re.findall(r"(?m)^\.home__cal \{([^}]*)\}", css) if "grid-template-columns" in body]
    assert len(rules) == 1, "правило раскладки календаря должно быть одно"
    assert "display: grid" in rules[0]
    assert re.search(r"grid-template-columns:\s*clamp\(\d+px, \d+%, \d+px\) minmax\(0, 1fr\)", rules[0])


def test_event_row_fits_on_one_line():
    """Дата не переносится, а месяц в ней сокращён.

    «27 сентября» уносило строку на два ряда раньше, чем это делало
    название события, — и панель ближайших событий вмещала вдвое меньше.
    """
    css = read("screens", "dashboards", "home.css")
    when = css.split("\n.home__when {")[1].split("}")[0]
    assert "white-space: nowrap" in when
    card = read("components", "CalendarCard.tsx")
    months = card.split("const MONTHS = [")[1].split("]")[0]
    assert "'сент.'" in months and "'сентября'" not in months


def test_carousel_title_is_one_step_smaller_only_next_to_the_calendar():
    """В узкой колонке заголовок карусели мельче — размером заголовка карточки.

    Ниже 1100px блоки встают друг под друга, карусель идёт во всю ширину,
    и мельчить заголовок там незачем.
    """
    css = read("screens", "dashboards", "home.css")
    narrow = css.split("@media (min-width: 1101px) {")[1].split("\n}\n")[0]
    assert ".home__caro .hero__title" in narrow and "font-size: var(--type-card)" in narrow
