"""Каркас и кабинеты: тёмное меню, карусель, шесть кабинетов.

Часть проверок — по исходникам фронта: вид из pytest не проверить, но
поломки, которые каркас уже проходил (потерянный блок, вернувшаяся шапка,
одна колонка вместо двух), видны в тексте файлов и ловятся дешевле,
чем браузером. Остальное — обычные проверки поведения.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def read(*parts: str) -> str:
    return (FRONTEND.joinpath(*parts)).read_text(encoding="utf-8")


# --- Каркас ----------------------------------------------------------------


def test_sidebar_is_dark_in_both_themes():
    """Меню тёмное в обеих темах: фон — графит текста, активный пункт — акцент.

    Светлое меню с плитками (решение от 2026-09-01) отменено новым языком:
    тёмная полоса меню отделяет навигацию от содержимого. Цвет живёт
    токенами `--menu-*` — зашитый в компоненте цвет обошёл бы тему.
    """
    tokens = read("styles", "tokens.css")
    light, dark = tokens.split(":root[data-theme='dark']")
    assert "--menu-bg: #14130f;" in light, "фон меню — графит текста"
    assert "--menu-item: #a29a90;" in light and "--menu-user: #201e19;" in light
    assert "--menu-bg:" in dark and "--menu-item:" in dark, "у меню обязан быть тёмный двойник"
    assert "--nav-bg: #ffffff" not in tokens, "белого меню больше нет"


def test_active_menu_item_is_filled_with_the_accent():
    """Активный пункт залит акцентом целиком, плиток под иконками нет.

    Плитка под иконкой была приёмом светлого меню: на тёмной полосе
    «где я» держит сама заливка пункта, а второй слой только шумит.
    """
    shell = read("layout", "shell.css")
    active = shell.split(".navlink--active {")[1].split("}")[0]
    assert "background: var(--accent)" in active and "color: var(--on-accent)" in active
    assert "--nav-tile" not in shell, "плиток под иконками больше нет"
    assert "navlink__icon" not in read("layout", "Shell.tsx")


def test_sidebar_does_not_scroll_with_the_page():
    """Меню стоит на месте: прокручивается правая часть, а не страница.

    Липкого меню недостаточно: `overflow: hidden` на самой полосе — он
    нужен для сворачивания — отменяет прилипание, и список уезжает вместе
    со страницей. Поэтому прокрутку держит область содержимого.
    """
    shell = read("layout", "shell.css")
    fixed = shell.split("@media (min-width: 760px) {")[1].split("\n}")[0]
    assert "height: 100vh" in fixed and "overflow: hidden" in fixed
    assert "overflow-y: auto" in fixed, "прокручивается область содержимого"
    menu = shell.split(".shell__menu {")[1].split("}")[0]
    assert "overflow-y: auto" in menu, "длинный список прокручивается внутри меню"


def test_laptop_has_no_header_and_the_guide_lives_in_the_user_menu():
    """Шапки на ноутбуке нет: поиск — иконкой в строке логотипа,
    «Как начать» и уведомления — в меню пользователя.

    Единственный `<header>` — тёмная полоса телефона: по умолчанию она
    спрятана и показывается только в телефонном медиазапросе.
    """
    shell = read("layout", "Shell.tsx")
    assert shell.count("<header") == 1, "шапка одна — телефонная полоса"
    assert "<header className={`shell__top" in shell
    # сама подпись и список уведомлений живут в меню пользователя, не в каркасе
    assert "t('Как начать')" not in shell and "<Notifications" not in shell
    css = read("layout", "shell.css")
    hidden = re.search(r"(?m)^\.shell__top \{([^}]*)\}", css)
    assert hidden and "display: none" in hidden.group(1), "полоса спрятана по умолчанию"
    phone = css.split("@media (max-width: 759px) {")[1]
    assert "display: flex" in phone.split(".shell__top {")[1].split("}")[0]
    menu = read("components", "ProfileMenu.tsx")
    assert "t('Как начать')" in menu and "t('Уведомления')" in menu and "<Notifications" in menu


# --- Карусель и календарь --------------------------------------------------


def test_home_folds_what_is_empty_instead_of_showing_a_carousel():
    """Мест не осталось — карточка «Что закрыть» сворачивается в строку.

    Карусели и цветных полотен на главной ученика больше нет: подсказки
    лежат строками в правой колонке, и пустая карточка не занимает места
    (правило «пустой блок — строка»). Живой вид — `shell-and-cabinets.spec.ts`.
    """
    home = read("screens", "dashboards", "StudentHome.tsx")
    assert "folded: cueRows.length === 0" in home
    assert "CuesCarousel" not in home and "hero" not in home.lower().replace("herochip", "")


def test_home_holds_what_is_needed_today():
    """На главной — то, что нужно сегодня; каждая карточка в одном месте (решение владельца, 07.10.2026).

    Уроки, ДЗ к сдаче, задачи с галочкой, готовность с подписанными пустыми
    доменами, ближайшее и незакрытые места. Баллы, документы, вузы, эссе
    и подготовка — в своих разделах, на главной их нет.
    """
    home = read("screens", "dashboards", "StudentHome.tsx")
    for block in ("<LessonsToday />", "<HomeworkDue />", "<TasksBlock />", "<ReadinessBlock />"):
        assert block in home, block
    assert "useTaskStatus" in home and "streak_phrase" in home
    assert "readiness.skipped" in home
    for gone in ("PrepBlock", "EssaysBlock", "useMyUniversities", "useJourney", "useScholarshipOverview", "<StatRow>"):
        assert gone not in home, gone


# --- Экраны ученика --------------------------------------------------------


def test_portfolio_is_two_columns_with_forms_in_place():
    """Портфолио в две колонки, а внесение баллов открывается в карточке."""
    css = read("screens", "portfolio.css")
    assert ".portfolio__two" in css and "minmax(0, 2fr) minmax(0, 1fr)" in css
    screen = read("screens", "MyData.tsx")
    assert "label={t('Внести баллы')}" in screen
    # подсказки «откроется форма прямо здесь» больше нет: пояснений на экранах нет (27.09.2026)
    assert "Откроется форма прямо здесь" not in screen
    # документы — своей вкладкой, на «Обзоре» их второго списка нет (07.10.2026)
    assert "function DocumentsCard" not in screen and "<DocumentsTab />" in screen


def test_portfolio_pairs_have_a_quiet_label_and_a_plain_value():
    """Подпись — мелкой капителью, значение — обычным весом.

    Крупными и жирными остаются только числа в плитках: до фазы 49
    жирным было всё подряд, и значения наезжали друг на друга.
    """
    css = read("screens", "portfolio.css")
    # пары берут и общие формы карточки — их подпись и ширина живут в общем CSS
    shared = read("components", "ui.css")
    label = shared.split(".portfolio__k {")[1].split("}")[0]
    assert "text-transform: uppercase" in label and "var(--ink-3)" in label
    value = css.split(".portfolio__v {")[1].split("}")[0]
    assert "font-weight: 500" in value
    # длинное значение занимает всю ширину карточки, а не лезет на соседа
    assert ".portfolio__pair--wide" in shared and "grid-column: 1 / -1" in shared


def test_essay_editor_takes_the_screen_with_the_assistant():
    """Редактор эссе — две трети экрана, помощник — треть, пузырями."""
    screen = read("screens", "Essays.tsx")
    assert "const opened = essays.find" in screen, "открытое эссе занимает экран целиком"
    assert "essay__editorgrid" in screen
    css = read("screens", "screens.css")
    grid = css.split(".essay__editorgrid {")[1].split("}")[0]
    assert "minmax(0, 2fr) minmax(0, 1fr)" in grid
    assert ".essay__bubble--me" in css, "ответы ученика — своим цветом"


def test_journey_is_not_in_the_student_cabinet():
    """«Мой путь» убран из кабинета ученика (решение владельца, 07.10.2026): пункта нет, закрепления в профиле нет."""
    shell = read("layout", "Shell.tsx")
    assert "journey" not in shell
    profile = read("screens", "Profile.tsx")
    assert "journey.pinned" not in profile
    nav = read("layout", "nav.ts")
    assert "{ path: '/journey'" not in nav and "'/journey'" in nav.split("STUDENT_HIDDEN =")[1].split("\n")[0]
    # полосы «шаг выполнен — следующий…» на экранах больше нет: подсказок нет (27.09.2026)
    assert "StepDone" not in shell


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
        # с фазы 80 три дашборда собирает `CabinetBoard`: те же две колонки, но пустая
        # карточка — одна строка, и колонка без живых карточек не остаётся
        source = read("screens", "dashboards", screen)
        assert "CabinetColumns" in source or "CabinetBoard" in source, screen
