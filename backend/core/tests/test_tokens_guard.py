"""Пиксели в стилях экранов — только из переменных размеров.

Размеры нового языка живут в четырёх файлах: `styles/tokens.css` (скругления,
тени), `styles/density.css` (высоты, поля, разрывы, шрифт), `styles/motion.css`
(движение) и `components/language.css` (общие компоненты, собранные по образцам).
Число в пикселях, написанное мимо них в CSS экрана или в инлайновом `style`,
не переключается вместе с плотностью и не меняется одним движением: так
у каждой карточки снова появляется свой отступ.

Цвета стережёт `test_production.py::test_frontend_components_take_colors_only_from_tokens`,
шаг сетки в отступах — `test_error_boundaries_and_nav_groups.py::test_spacing_uses_the_scale`.
Здесь — все остальные пиксели.

Как считается долг (то же делает `current_debt()`, запуск —
`docker compose exec backend python -m core.tests.test_tokens_guard`):

* берутся `frontend/src/**/*.css`, кроме четырёх домашних файлов выше,
  и все `frontend/src/**/*.tsx`;
* в CSS вырезаются комментарии и условия медиазапросов (`@media (...)` —
  пороги ширины пишутся числом по праву), затем считается каждый литерал
  `<число>px`, кроме `0px`, `1px` и `2px` — линии и обводки;
* в `*.tsx` считаются только инлайновые стили `style={{…}}`: строки
  с `px` и голые числа (React дописывает `px` сам), кроме безразмерных
  свойств вроде `opacity`, `zIndex`, `flex`, `fontWeight`, `lineHeight`;
* в `*.tsx` вне `components/ui/` считаются размеры Tailwind-утилит
  в квадратных скобках: `max-w-[440px]`, `h-[18.4px]`. Файлы реестра
  shadcn исключены: их размеры приходят из реестра, а не пишутся здесь;
* проценты, `vh`, `vw`, `rem`, `em`, `ms` долгом не считаются.

Долг записан по файлам: путь от `frontend/src` → число позиций. Файл без
записи обязан быть чистым, записанный — не хуже записанного, а закрытое
вычёркивается (`test_the_debt_only_shrinks`). Сокращать долг — переносить
число в переменную `density.css` или `language.css` и уменьшать запись.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/frontend").is_dir() else Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"

#: где пиксели живут по праву: переменные размеров, движение, общие компоненты
HOME = frozenset(
    {
        "styles/tokens.css",
        "styles/density.css",
        "styles/motion.css",
        "components/language.css",
    }
)

#: файлы реестра shadcn: размеры в их классах приходят из реестра
REGISTRY = "components/ui/"

#: линии и обводки: ноль, один и два пикселя — не долг
ALLOWED = frozenset({0.0, 1.0, 2.0})

#: свойства, чьё число React оставляет без `px` — это не размер
UNITLESS = frozenset(
    {
        "animationIterationCount",
        "aspectRatio",
        "borderImageOutset",
        "borderImageSlice",
        "borderImageWidth",
        "boxFlex",
        "boxFlexGroup",
        "boxOrdinalGroup",
        "columnCount",
        "columns",
        "flex",
        "flexGrow",
        "flexPositive",
        "flexShrink",
        "flexNegative",
        "flexOrder",
        "gridArea",
        "gridRow",
        "gridRowEnd",
        "gridRowSpan",
        "gridRowStart",
        "gridColumn",
        "gridColumnEnd",
        "gridColumnSpan",
        "gridColumnStart",
        "fontWeight",
        "lineClamp",
        "lineHeight",
        "opacity",
        "order",
        "orphans",
        "scale",
        "tabSize",
        "widows",
        "zIndex",
        "zoom",
        "fillOpacity",
        "floodOpacity",
        "stopOpacity",
        "strokeDasharray",
        "strokeDashoffset",
        "strokeMiterlimit",
        "strokeOpacity",
        "strokeWidth",
    }
)

#: литерал в пикселях: не часть слова и не часть другого числа
PX = re.compile(r"(?<![\w.-])-?(\d+(?:\.\d+)?)px\b")
#: то же внутри скобок Tailwind, где пробелов нет: `calc(100vh-48px)`
PX_ANY = re.compile(r"(\d+(?:\.\d+)?)px")
#: голое число в инлайновом стиле: `marginTop: 12`
BARE = re.compile(r"\b([a-zA-Z]+)\s*:\s*(-?\d+(?:\.\d+)?)(?=\s*[,}\n]|\s*$)")
#: размер Tailwind-утилиты в квадратных скобках: `max-w-[440px]`, `h-[18.4px]`
BRACKET = re.compile(r"-\[([^\]\s]*\d[^\]\s]*px[^\]\s]*)\]")
COMMENT = re.compile(r"/\*.*?\*/", re.S)
MEDIA = re.compile(r"@media[^{]*")


def _blank(match: re.Match[str]) -> str:
    """Убрать текст, сохранив переносы строк: номера строк в находках остаются верными."""
    return "\n" * match.group(0).count("\n")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def css_pixels(text: str) -> list[str]:
    """Пиксельные литералы CSS-файла вне линий и медиазапросов: `строка: литерал`."""
    text = MEDIA.sub(_blank, COMMENT.sub(_blank, text))
    return [
        f"{_line_of(text, match.start())}: {match.group(0)}"
        for match in PX.finditer(text)
        if float(match.group(1)) not in ALLOWED
    ]


def style_blocks(text: str) -> list[tuple[int, str]]:
    """Тела инлайновых стилей `style={{…}}` с номером строки начала."""
    blocks: list[tuple[int, str]] = []
    position = 0
    while True:
        start = text.find("style={{", position)
        if start < 0:
            return blocks
        depth = 0
        end = start + len("style=")
        for end in range(start + len("style="), len(text)):
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
                if depth == 0:
                    break
        blocks.append((_line_of(text, start), text[start + len("style={{") : end - 1]))
        position = end + 1


def tsx_pixels(text: str, registry: bool) -> list[str]:
    """Пиксели в инлайновых стилях и — вне реестра — в скобках Tailwind."""
    hits: list[str] = []
    for line, body in style_blocks(text):
        for match in PX.finditer(body):
            if float(match.group(1)) not in ALLOWED:
                hits.append(f"{line}: {match.group(0)}")
        for match in BARE.finditer(body):
            name, value = match.group(1), match.group(2)
            if name not in UNITLESS and abs(float(value)) not in ALLOWED:
                hits.append(f"{line}: {name}: {value}")
    if not registry:
        for match in BRACKET.finditer(text):
            for pixel in PX_ANY.finditer(match.group(1)):
                if float(pixel.group(1)) not in ALLOWED:
                    hits.append(f"{_line_of(text, match.start())}: [{match.group(1)}]")
    return hits


def current_debt() -> dict[str, list[str]]:
    """Находки по файлам: путь от `frontend/src` → список `строка: литерал`."""
    found: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.css")):
        rel = path.relative_to(SRC).as_posix()
        if rel in HOME:
            continue
        hits = css_pixels(path.read_text("utf-8"))
        if hits:
            found[rel] = hits
    for path in sorted(SRC.rglob("*.tsx")):
        rel = path.relative_to(SRC).as_posix()
        hits = tsx_pixels(path.read_text("utf-8"), registry=rel.startswith(REGISTRY))
        if hits:
            found[rel] = hits
    return found


#: долг по файлам на 2026-09-26: путь от `frontend/src` → число пиксельных
#: литералов. Заполнен `current_debt()`, не руками. Только уменьшается
DEBT: dict[str, int] = {
    "components/ConfirmDialog.tsx": 1,
    "components/CredentialsBox.tsx": 1,
    "components/EnrollPanel.tsx": 1,
    "components/ExamGoals.tsx": 1,
    "components/ImportHistory.tsx": 1,
    "components/Modal.tsx": 4,
    "components/PlatformMocks.tsx": 1,
    "components/ProgramList.tsx": 2,
    "components/RequirementsImport.tsx": 1,
    "components/RowsImport.tsx": 2,
    "components/ScholarshipsImport.tsx": 1,
    "components/StudyGroups.tsx": 2,
    "components/TheoryManager.tsx": 2,
    "components/assistant-widget.css": 49,
    "components/badges.css": 10,
    "components/jobs.css": 9,
    "components/patterns.css": 85,
    "components/queue.css": 25,
    "components/ui.css": 372,
    "layout/shell.css": 91,
    "screens/AiPanels.tsx": 1,
    "screens/Archive.tsx": 1,
    "screens/Assistant.tsx": 6,
    "screens/Catalog.tsx": 1,
    "screens/Digest.tsx": 2,
    "screens/EssayContent.tsx": 6,
    "screens/Essays.tsx": 1,
    "screens/ImportScreen.tsx": 6,
    "screens/Journey.tsx": 1,
    "screens/MailTemplates.tsx": 1,
    "screens/MyData.tsx": 1,
    "screens/Prep.tsx": 1,
    "screens/Selection.tsx": 5,
    "screens/Spend.tsx": 3,
    "screens/StudentCard.tsx": 1,
    "screens/SuggestionPreview.tsx": 1,
    "screens/TableScreen.tsx": 2,
    "screens/Users.tsx": 8,
    "screens/archive.css": 18,
    "screens/assistant.css": 42,
    "screens/card.css": 8,
    "screens/career.css": 17,
    "screens/catalog.css": 8,
    "screens/dashboards/OverviewDashboard.tsx": 4,
    "screens/dashboards/cabinet.css": 14,
    "screens/dashboards/home.css": 66,
    "screens/directory-list.css": 13,
    "screens/directory.css": 30,
    "screens/materials.css": 35,
    "screens/onboarding.css": 11,
    "screens/portfolio.css": 39,
    "screens/prep.css": 65,
    "screens/quiz.css": 12,
    "screens/resources.css": 16,
    "screens/roadmap.css": 13,
    "screens/scholarships.css": 15,
    "screens/screens.css": 254,
    "screens/sections/Deadlines.tsx": 10,
    "screens/sections/Groups.tsx": 5,
    "screens/sections/Top30.tsx": 2,
    "screens/sections/Tracks.tsx": 4,
    "screens/table.css": 9,
    "screens/universities.css": 28,
    "styles/base.css": 54,
}


def test_pixels_outside_the_variables_are_only_the_listed_debt():
    """Файл без записи в долге чист, записанный — не хуже записанного."""
    found = current_debt()
    worse = {rel: hits for rel, hits in found.items() if len(hits) > DEBT.get(rel, 0)}
    assert not worse, (
        "пиксели мимо переменных размеров: "
        + "; ".join(
            f"{rel} ({len(hits)}, в долге {DEBT.get(rel, 0)}): {', '.join(hits[:4])}" for rel, hits in worse.items()
        )
        + ". Размер — переменной в density.css или language.css; порог ширины — только в @media"
    )


def test_the_debt_only_shrinks():
    """Закрытое вычёркивается из списка, сокращённое — записывается новым числом."""
    found = current_debt()
    paid = {rel: len(found.get(rel, [])) for rel in DEBT if len(found.get(rel, [])) < DEBT[rel]}
    assert not paid, "долг сокращён — впишите в DEBT новые числа (ноль — вычеркните): " + ", ".join(
        f"{rel}: {DEBT[rel]} → {count}" for rel, count in sorted(paid.items())
    )


def test_the_scan_catches_a_planted_pixel():
    """Сама проверка ловит подложенный пиксель — иначе она ничего не значит."""
    assert css_pixels(".x { padding: 12px }") == ["1: 12px"]
    assert css_pixels(".x { border: 1px solid; margin: 0 2px -1px }") == []
    assert css_pixels("@media (max-width: 759px) {\n  .x { gap: 8px }\n}") == ["2: 8px"]
    assert css_pixels("/* 40px */\n.x { width: calc(100% - 40px) }") == ["2: 40px"]
    assert css_pixels(".x { width: 100%; height: 100vh; font-size: 0.9rem }") == []
    assert tsx_pixels("<div style={{ marginTop: 12, opacity: 0.5, zIndex: 10 }} />", False) == ["1: marginTop: 12"]
    assert tsx_pixels("<div style={{ width: '440px', height: 1 }} />", False) == ["1: 440px"]
    assert tsx_pixels("<div style={{ width: `${size}%`, transform: `translateX(-${i * 100}%)` }} />", False) == []
    assert tsx_pixels("<div\n  style={{\n    width: size,\n    padding: 6,\n  }}\n/>", False) == ["2: padding: 6"]
    assert tsx_pixels('<Sheet className="sm:max-w-[720px]" />', False) == ["1: [720px]"]
    assert tsx_pixels('<Sheet className="sm:max-w-[720px]" />', True) == []
    assert tsx_pixels('<div className="border-[1px] h-[calc(100vh-48px)]" />', False) == ["1: [calc(100vh-48px)]"]


if __name__ == "__main__":
    # пересчёт долга для вставки в DEBT
    for rel, hits in sorted(current_debt().items()):
        print(f'    "{rel}": {len(hits)},')
