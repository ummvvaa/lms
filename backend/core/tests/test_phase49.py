"""Приёмка фазы 49: макет v2 — светлый каркас, карусель, шесть кабинетов.

Часть проверок — по исходникам фронта: вид из pytest не проверить, но
поломки, которые эта фаза уже проходила (потерянный блок, тёмное меню,
одна колонка вместо двух), видны в тексте файлов и ловятся дешевле,
чем браузером. Остальное — обычные проверки поведения.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def read(*parts: str) -> str:
    return (FRONTEND.joinpath(*parts)).read_text(encoding="utf-8")


# --- Каркас ----------------------------------------------------------------


def test_sidebar_is_light_in_both_themes():
    """Меню светлое, а в тёмной теме — тёмное, но не чёрная панель.

    Тёмная панель фаз 32–48 отменена решением владельца: она спорила
    с содержимым. Цвет живёт токенами — зашитый в компоненте цвет
    вернул бы прежнюю панель мимо темы.
    """
    tokens = read("styles", "tokens.css")
    light = tokens.split(":root[data-theme='dark']")[0]
    assert "--nav-bg: #ffffff;" in light, "меню в светлой теме должно быть белым"
    dark = tokens.split(":root[data-theme='dark']")[1]
    assert "--nav-bg:" in dark, "у меню обязан быть тёмный двойник"
    # плитка под иконкой пункта — тоже токеном, в обеих темах
    for part in (light, dark):
        assert "--nav-tile-bg:" in part and "--nav-tile-active-bg:" in part


def test_nav_icon_sits_in_a_tile():
    """Иконка пункта — в скруглённой плитке, у активного она залита акцентом."""
    shell = read("layout", "shell.css")
    assert "background: var(--nav-tile-bg)" in shell
    assert ".navlink--active .navlink__icon" in shell
    assert "background: var(--nav-tile-active-bg)" in shell


def test_sidebar_does_not_scroll_with_the_page():
    """Меню стоит на месте: прокручивается правая часть, а не страница.

    Липкого меню недостаточно: `overflow: hidden` на самой полосе — он
    нужен для сворачивания — отменяет прилипание, и список уезжает вместе
    со страницей. Поэтому прокрутку держит область содержимого.
    """
    shell = read("layout", "shell.css")
    fixed = shell.split("@media (min-width: 901px) {")[1].split("\n}")[0]
    assert "height: 100vh" in fixed and "overflow: hidden" in fixed
    assert "overflow-y: auto" in fixed, "прокручивается область содержимого"
    menu = shell.split(".shell__menu {")[1].split("}")[0]
    assert "overflow-y: auto" in menu, "длинный список прокручивается внутри меню"


def test_header_holds_only_search_and_the_guide():
    """В шапке — поиск и «Как начать». Имя и колокольчик живут внизу меню."""
    shell = read("layout", "Shell.tsx")
    header = shell.split('<header className="shell__top">')[1].split("</header>")[0]
    assert "SearchBox" in header and "Как начать" in header
    assert "Notifications" not in header and "ProfileMenu" not in header


# --- Карусель и календарь --------------------------------------------------


def test_carousel_is_part_of_the_common_set():
    """Карусель собрана в общем наборе, а не отдельно на главной."""
    patterns = read("components", "patterns.tsx")
    assert "export function Carousel" in patterns
    # листается сама и останавливается под курсором
    assert "CAROUSEL_INTERVAL" in patterns
    assert "onMouseEnter" in patterns and "setPaused(true)" in patterns


def test_home_drops_the_carousel_when_there_is_nothing_to_close():
    """Мест не осталось — карусели нет, и календарь занимает её место.

    С фазы 50 календарь при этом не меняет размера: он растягивается
    на всю ширину, а размеры текста стережёт `test_phase50`.
    """
    home = read("screens", "dashboards", "StudentHome.tsx")
    assert "rows.length > 0 && <CuesCarousel" in home
    css = read("screens", "dashboards", "home.css")
    assert ".home__top--calendar" in css


def test_home_kept_tasks_and_readiness():
    """Задания на сегодня и разбивка готовности остаются на главной.

    Переделка вида уже уносила эти блоки в фазе 48. Образец задаёт
    характер, а не право удалять построенное, — поэтому страж.
    """
    home = read("screens", "dashboards", "StudentHome.tsx")
    assert "<TodayPanel />" in home
    assert "ReadinessBlock" in home and "readiness.skipped" in home
    assert "PrepBlock" in home and "EssaysBlock" in home


# --- Экраны ученика --------------------------------------------------------


def test_portfolio_is_two_columns_with_forms_in_place():
    """Портфолио в две колонки, а внесение баллов открывается в карточке."""
    css = read("screens", "portfolio.css")
    assert ".portfolio__two" in css and "minmax(0, 2fr) minmax(0, 1fr)" in css
    screen = read("screens", "MyData.tsx")
    assert "label={t('Внести баллы')}" in screen
    assert "Откроется форма прямо здесь, без перехода" in screen
    # чек-лист документов грузит файл прямо из строки
    assert "function DocumentsCard" in screen and "uploadDocument.mutate" in screen


def test_portfolio_pairs_have_a_quiet_label_and_a_plain_value():
    """Подпись — мелкой капителью, значение — обычным весом.

    Крупными и жирными остаются только числа в плитках: до фазы 49
    жирным было всё подряд, и значения наезжали друг на друга.
    """
    css = read("screens", "portfolio.css")
    label = css.split(".portfolio__k {")[1].split("}")[0]
    assert "text-transform: uppercase" in label and "var(--ink-40)" in label
    value = css.split(".portfolio__v {")[1].split("}")[0]
    assert "font-weight: 500" in value
    # длинное значение занимает всю ширину карточки, а не лезет на соседа
    assert ".portfolio__pair--wide" in css and "grid-column: 1 / -1" in css


def test_essay_editor_takes_the_screen_with_the_assistant():
    """Редактор эссе — две трети экрана, помощник — треть, пузырями."""
    screen = read("screens", "Essays.tsx")
    assert "const opened = essays.find" in screen, "открытое эссе занимает экран целиком"
    assert "essay__editorgrid" in screen
    css = read("screens", "screens.css")
    grid = css.split(".essay__editorgrid {")[1].split("}")[0]
    assert "minmax(0, 2fr) minmax(0, 1fr)" in grid
    assert ".essay__bubble--me" in css, "ответы ученика — своим цветом"


def test_journey_leaves_the_menu_when_it_is_done():
    """Пять шагов пройдены — пункт уходит из меню, возврат из профиля."""
    shell = read("layout", "Shell.tsx")
    assert "journey.data?.complete" in shell and "'/journey'" in shell
    profile = read("screens", "Profile.tsx")
    assert "journey.pinned" in profile and "Показать шаги пути" in profile
    # следующий шаг догоняет на экране предыдущего
    step = read("components", "StepDone.tsx")
    assert "Шаг выполнен" in step and "steps.slice(index + 1)" in step


# --- Кабинеты руководителей ------------------------------------------------


@pytest.mark.parametrize(
    "screen,marker",
    [
        ("ExamDashboard.tsx", "Мок просел"),
        ("AdmissionDashboard.tsx", "Баланс списков"),
        ("BehaviorDashboard.tsx", "Кому позвонить сегодня"),
        ("TalentDashboard.tsx", "Материалы на проверке"),
        ("SportDashboard.tsx", "Календарь стартов"),
        ("AdminDashboard.tsx", "Требует ваших действий"),
    ],
)
def test_six_cabinets_are_six_different_screens(screen: str, marker: str):
    """У каждого кабинета своё главное, а не один экран с подменой данных."""
    source = read("screens", "dashboards", screen)
    assert marker in source, f"{screen}: нет того, ради чего этот экран открывают"


def test_five_cabinets_share_the_queue_and_the_admin_does_not():
    """Очередь подтверждений — у пятерых; администратору подтверждать нечего."""
    for screen in (
        "ExamDashboard.tsx",
        "AdmissionDashboard.tsx",
        "BehaviorDashboard.tsx",
        "TalentDashboard.tsx",
        "SportDashboard.tsx",
    ):
        assert "PendingQueue" in read("screens", "dashboards", screen), screen
    assert "PendingQueue" not in read("screens", "dashboards", "AdminDashboard.tsx")


def test_admin_actions_are_wired_to_real_requests():
    """Кнопки «Требует ваших действий» делают то, что написано."""
    admin = read("screens", "dashboards", "AdminDashboard.tsx")
    for hook in ("useInviteUsers", "useBulkUsers", "useUnlockLogin"):
        assert hook in admin, f"кнопка без запроса: {hook}"


def test_director_table_opens_read_only():
    """Таблица директора открывается на чтение, ручной ввод — кнопкой."""
    table = read("screens", "TableScreen.tsx")
    assert "useState(true)" in table.split("const [locked, setLocked] =")[1][:40]
    assert "Значения меняет ученик, вы подтверждаете их в очереди" in table
    assert "Внести вручную" in table


def test_cabinets_never_leave_the_right_third_empty():
    """У кабинета две колонки: справа то, на что директор оглядывается."""
    css = read("screens", "dashboards", "cabinet.css")
    assert "minmax(0, 2fr) minmax(0, 1fr)" in css
    for screen in (
        "ExamDashboard.tsx",
        "AdmissionDashboard.tsx",
        "BehaviorDashboard.tsx",
        "TalentDashboard.tsx",
        "SportDashboard.tsx",
        "AdminDashboard.tsx",
    ):
        assert "CabinetColumns" in read("screens", "dashboards", screen), screen
