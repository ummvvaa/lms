"""Приёмка фазы 51: телефонная версия.

Ниже 640px интерфейс перестраивается: боковое меню уступает место
нижнему бару из четырёх разделов роли, календарь получает два режима,
формы идут в один столбец, а строки таблиц разворачиваются в карточки.

Здесь — то, что видно в исходниках и стоит дешевле браузера: реестр
четвёрок, подписи из меню, один компонент списка на весь фронт,
пороги ширины в одном числе. Живой вид, размеры и жесты — в
`e2e/tests/phase51.spec.ts` на 390×844 под каждой из семи ролей.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"

ROLES = (
    "student",
    "director_behavior",
    "director_admission",
    "director_exam",
    "director_talent",
    "director_sport",
    "admin",
)


def read(*parts: str) -> str:
    return FRONTEND.joinpath(*parts).read_text(encoding="utf-8")


def tabs_block() -> str:
    nav = read("layout", "nav.ts")
    return nav.split("export const TABS: Record<Role, string[]> = {")[1].split("\n}")[0]


def test_every_role_has_four_tabs():
    """У каждой из семи ролей объявлена своя четвёрка разделов.

    Пятая кнопка бара — «Ещё»: роль без четвёрки получила бы бар
    из одной кнопки, то есть меню, спрятанное целиком.
    """
    block = tabs_block()
    for role in ROLES:
        line = re.search(rf"{role}: \[([^\]]*)\]", block)
        assert line, f"нет четвёрки у роли {role}"
        paths = re.findall(r"'([^']+)'", line.group(1))
        assert len(paths) == 4, f"{role}: разделов в баре {len(paths)}, а нужно четыре"


def test_tabs_point_at_real_sections():
    """Раздел бара существует в навигации этой роли.

    Опечатка в адресе давала бы кнопку, ведущую в никуда, — и заметить
    это можно было бы только пальцем на телефоне.
    """
    nav = read("layout", "nav.ts")
    block = tabs_block()
    for role in ROLES:
        line = re.search(rf"{role}: \[([^\]]*)\]", block)
        for path in re.findall(r"'([^']+)'", line.group(1)):
            assert f"path: '{path}'" in nav, f"{role}: раздела {path} нет в навигации"


def test_tab_labels_come_from_the_menu():
    """Подписи бара берутся из пунктов меню, а не из своего словаря.

    Раздел, который на ноутбуке называется «Роадмап», обязан называться
    так же и на телефоне: человек ходит и оттуда и отсюда.
    """
    bar = read("layout", "MobileNav.tsx")
    assert "item.short ?? item.label" in bar, "подпись бара — из пункта меню"
    assert "Record<string, string>" not in bar, "у бара завёлся свой словарь подписей"


def test_short_labels_are_declared_in_the_registry():
    """Сокращение живёт у пункта меню, а не в компоненте бара."""
    nav = read("layout", "nav.ts")
    assert "short?: string" in nav
    assert "short: 'Вузы'" in nav


def test_phone_width_is_one_number():
    """Порог телефона — одно число в коде и то же в стилях.

    Два источника разъехались бы в первую правку: разметка перестроилась
    бы на одной ширине, а режимы календаря — на другой.
    """
    phone = read("phone.ts")
    assert "export const PHONE_WIDTH = 640" in phone
    assert "max-width: ${PHONE_WIDTH}px" in phone


def test_bar_is_hidden_above_the_phone_width():
    """Бар не рисуется шире 640: там своё меню.

    Правило «спрятан по умолчанию, показан в медиазапросе», а не наоборот:
    забытый медиазапрос тогда прячет бар, а не рисует его на ноутбуке.
    """
    css = read("layout", "shell.css")
    hidden = re.search(r"(?m)^\.tabbar \{([^}]*)\}", css)
    assert hidden and "display: none" in hidden.group(1)
    phone = css.split("@media (max-width: 640px) {")[1]
    assert ".tabbar {" in phone and "position: fixed" in phone


def test_screen_keeps_room_for_the_bar():
    """Под баром не остаётся содержимого, до которого не дотянуться.

    Запас считается из тех же токенов, что и высота бара с кнопкой
    помощника: два набора чисел разошлись бы при первой правке.
    """
    tokens = read("styles", "tokens.css")
    assert "--tabbar-h:" in tokens and "--tabbar-clear:" in tokens
    assert "env(safe-area-inset-bottom" in tokens, "полоса жеста домой не учтена"
    css = read("layout", "shell.css")
    pad = re.search(r"\.shell__screen \{[^}]*\}", css.split("@media (max-width: 640px) {")[1])
    assert pad and "var(--tabbar-clear)" in pad.group(0) and "var(--fab-clear)" in pad.group(0)
    fab = read("components", "assistant-widget.css")
    assert "var(--tabbar-clear)" in fab, "кнопка помощника садится на бар"


def test_calendar_mode_is_remembered_per_role():
    """Режим календаря лежит в памяти браузера ключом с ролью."""
    card = read("components", "CalendarCard.tsx")
    assert "localStorage.setItem(storageKey" in card
    home = read("screens", "dashboards", "StudentHome.tsx")
    sport = read("screens", "dashboards", "SportDashboard.tsx")
    assert 'storageKey="calendar.mode.student"' in home
    assert 'storageKey="calendar.mode.director_sport"' in sport


def test_calendar_modes_live_only_on_the_phone():
    """Переключателя режимов шире 640 нет вовсе — ни в разметке, ни в стилях.

    На ноутбуке и планшете календарь остаётся тем, чем стал в фазе 50.
    """
    card = read("components", "CalendarCard.tsx")
    assert "const phone = usePhone()" in card
    # ветка ноутбука отдаёт разметку фаз 49–50 и уходит из функции раньше
    assert "if (!phone)" in card
    desktop = card.split("if (!phone)")[1].split("/* --- телефон")[0]
    for phone_only in ("calmode", "calfeed", "calcell"):
        assert phone_only not in desktop, f"{phone_only} просочился в ветку ноутбука"
    css = read("screens", "dashboards", "home.css")
    for phone_only in (".calfeed", ".calcell", ".calmode"):
        outside = re.search(rf"(?m)^{re.escape(phone_only)}[ ,{{]", css)
        assert not outside, f"{phone_only} объявлен вне телефонной ветки"


def test_feed_shows_only_what_is_ahead():
    """В ленте только будущее: прошедшие события с телефона не нужны."""
    card = read("components", "CalendarCard.tsx")
    assert "events.filter((event) => event.date >= today)" in card


def test_one_select_for_the_whole_interface():
    """Список формы — один компонент на весь фронт.

    Разное поведение списков в разных разделах — источник дефектов
    на годы: на телефоне один открывался бы листом, другой — окном
    браузера в углу экрана.
    """
    hits = []
    for path in sorted(FRONTEND.rglob("*.tsx")):
        if path.name in ("native-select.tsx", "SelectField.tsx"):
            continue
        if re.search(r"<NativeSelect(?![A-Za-z])", path.read_text(encoding="utf-8")):
            hits.append(path.name)
    assert not hits, f"мимо общего компонента списка: {hits}"


def test_table_row_becomes_a_card_by_its_own_labels():
    """Подпись ячейки на телефоне — та же, что в шапке колонки.

    Второй словарь подписей разъехался бы с первым: в шапке одно слово,
    в карточке другое.
    """
    table = read("components", "DataTable.tsx")
    assert "data-label={index === 0 ? undefined : column.title}" in table
    assert "data-head={index === 0 ? '' : undefined}" in table
    css = read("components", "ui.css")
    phone = css.split("@media (max-width: 640px) {")
    assert any("content: attr(data-label)" in block for block in phone[1:])


def test_manual_entry_grid_is_not_offered_on_the_phone():
    """Правка таблицы с телефона не предлагается.

    Ходьба стрелками, вставка прямоугольником и растягивание значения —
    работа за столом. Кнопка «Внести вручную» вела бы в сетку, в которую
    пальцем не попасть, а таблица директора и так открывается на чтение.
    """
    screen = read("screens", "TableScreen.tsx")
    assert "phone ? undefined : locked ?" in screen
    assert "tblcard__pairs" in screen, "карточек вместо строк на телефоне нет"


def test_form_submit_sticks_to_the_bottom():
    """Кнопка отправки видна, не долистывая длинную форму до конца."""
    css = read("components", "ui.css")
    phone = css.split("@media (max-width: 640px) {")
    rules = [block for block in phone[1:] if ".propose__actions" in block]
    assert rules, "правил телефонной формы нет"
    assert any("position: sticky" in block for block in rules)


def test_validation_error_stands_under_its_field():
    """Отказ формы адресован полю, а не всплывает над кнопками."""
    form = read("components", "RowForm.tsx")
    assert "{ field: string; text: string }" in form
    assert "problem?.field === field.name" in form
