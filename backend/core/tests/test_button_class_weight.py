"""Класс поверх кнопки реестра не проигрывает правилу её варианта.

Размеры и цвета кнопки реестра задают правила `body [data-slot='button']
[data-variant=…]` весом (0,2,1) (`components/patterns.css`). Класс экрана на
той же кнопке весит (0,1,0) и молча проигрывает: в сетке расписания карточки
уроков потеряли полосу подгруппы и потока и фон замены, в эссе пропала
подсветка верного ответа, в матрице документов — цвет состояния.

Тест собирает классы, которые экраны ставят на `<Button className=…>`, и ищет
правила CSS, где такой класс стоит в последней части селектора и задаёт вид
(фон, рамку, цвет, размер, поля). Правило легче варианта — находка. Нынешние
места записаны долгом поимённо и только вычёркиваются.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/frontend").is_dir() else Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"

#: вес правила варианта кнопки реестра: (id, классы и атрибуты, теги)
VARIANT_WEIGHT = (0, 2, 1)

#: свойства, которые задаёт правило варианта или размера
VISUAL = re.compile(
    r"(?:^|;|\s)(background|border(?:-[a-z]+)*|color|height|min-height|padding(?:-[a-z]+)*|border-radius|font-size|font-weight|gap)\s*:"
)

#: классы, которые ставятся на кнопку не строкой в `className`, а функцией
#: (`chipClass` карточки урока, `SelectField`) — их тест строкой не найдёт
BUILT_BY_CODE = {
    "les",
    "les--sub1",
    "les--sub2",
    "les--stream",
    "les--changed",
    "les--off",
    "les--conflict",
    "selfield",
}

#: долг (D21): классы, у которых вид перебивает вариант кнопки, — сегодня они
#: только меняют размер или цвет надписи, состояние не теряют. Список только
#: сокращается: поправили правило — вычеркните
LEGACY: frozenset[str] = frozenset(
    {
        "aw__fab",
        "aw__quickbtn",
        "aw__tool",
        "aw__tool--icon",
        "cadm__ibtn",
        "calfeed__more",
        "calfeed__row",
        "login__hint",
        "mat__title",
        "mydocs__ibtn",
        "mydocs__more",
        "mywork__pill",
        "notice__more",
        "notif__all",
        "prep__lessonhead",
        "res__read",
        "rowmenu__action",
        "rowmenu__button",
        "squeue__hint",
        "tblcard__name",
        "tipbar__action",
        "wk__add",
        "wk__more",
    }
)

#: модификаторы того же блока, которые стоят не на кнопке: квадратик
#: легенды матрицы документов — `<span>`, вариант кнопки его не касается
NOT_ON_A_BUTTON = {"cdocs__cell--key"}

CLASS = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:__[a-z0-9]+(?:-[a-z0-9]+)*)?(?:--[a-z0-9]+(?:-[a-z0-9]+)*)?$")


def _opening_tags(text: str, tag: str):
    """Открывающие теги `<Button …>` целиком, с выражениями в фигурных скобках."""
    for match in re.finditer(rf"<{tag}\b", text):
        depth = 0
        for end in range(match.end(), len(text)):
            char = text[end]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            elif char == ">" and depth == 0:
                yield text[match.start() : end + 1]
                break


def _class_value(tag: str) -> str:
    """Значение атрибута `className` открывающего тега: строка или выражение."""
    found = re.search(r"className=", tag)
    if not found:
        return ""
    rest = tag[found.end() :]
    if rest.startswith(("'", '"')):
        return rest[1 : rest.index(rest[0], 1)]
    if rest.startswith("{"):
        depth = 0
        for end, char in enumerate(rest):
            depth += char == "{"
            depth -= char == "}"
            if depth == 0:
                return rest[: end + 1]
    return ""


def button_classes() -> dict[str, set[str]]:
    """Класс → файлы, где он стоит на `<Button className=…>`."""
    out: dict[str, set[str]] = {}
    for path in SRC.rglob("*.tsx"):
        if "components/ui/" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        # модификатор состояния часто собирается в переменной рядом с тегом
        # (`essay__opt${cls}`): к классу кнопки добавляются все его модификаторы из файла
        in_file = set(re.findall(r"[a-z][a-z0-9-]*__[a-z0-9-]+(?:--[a-z0-9-]+)?", text))
        for tag in _opening_tags(text, "Button"):
            value = _class_value(tag)
            for literal in re.findall(r"""['"`]([^'"`]*)['"`]""", value) or [value]:
                for word in re.sub(r"\$\{[^}]*\}", " ", literal).split():
                    if CLASS.match(word) and ("__" in word or "--" in word or word in BUILT_BY_CODE):
                        base = word.split("--")[0]
                        for name in {word} | {n for n in in_file if n.startswith(base + "--")}:
                            out.setdefault(name, set()).add(path.relative_to(SRC).as_posix())
    for name in BUILT_BY_CODE:
        out.setdefault(name, set()).add("(собирается кодом)")
    for name in NOT_ON_A_BUTTON:
        out.pop(name, None)
    return out


def _rules(css: str):
    """Пары «список селекторов — объявления», включая правила внутри @media."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = match.group(1).strip()
        if selectors.startswith("@"):
            continue
        yield [s.strip() for s in selectors.split(",") if s.strip()], match.group(2)


def specificity(selector: str) -> tuple[int, int, int]:
    """Вес селектора приблизительно, как считает браузер: :where — ноль."""
    text = re.sub(r":where\([^)]*\)", "", selector)
    text = re.sub(r"::[a-z-]+", "", text)
    ids = len(re.findall(r"#[\w-]+", text))
    classes = len(re.findall(r"\.[\w-]+", text)) + len(re.findall(r"\[[^\]]*\]", text))
    classes += len(re.findall(r"(?<!:):[a-z-]+", text))
    bare = re.sub(r"\[[^\]]*\]|\.[\w-]+|#[\w-]+|:[a-z-]+(\([^)]*\))?", " ", text)
    tags = len(re.findall(r"(?:^|[\s>+~])([a-z][a-z0-9]*)", bare))
    return ids, classes, tags


def _last_part(selector: str) -> str:
    parts = re.split(r"\s*[\s>+~]\s*(?![^\[]*\])", selector.strip())
    return parts[-1] if parts else selector


def light_rules() -> dict[str, list[str]]:
    """Класс кнопки → селекторы правил, которые задают вид и легче варианта."""
    wanted = button_classes()
    found: dict[str, list[str]] = {}
    for path in SRC.rglob("*.css"):
        for selectors, body in _rules(path.read_text(encoding="utf-8")):
            if not VISUAL.search(body):
                continue
            # правило списка выигрывает, если хоть один его селектор тяжелее варианта
            if any(specificity(s) >= VARIANT_WEIGHT for s in selectors):
                continue
            for selector in selectors:
                last = _last_part(selector)
                for name in re.findall(r"\.([\w-]+)", last):
                    if name in wanted:
                        found.setdefault(name, []).append(f"{path.relative_to(SRC).as_posix()}: {selector}")
    return found


def test_the_weight_calculation_matches_the_browser():
    assert specificity("body [data-slot='button'][data-variant='ghost']") == (0, 2, 1)
    assert specificity(".les--sub1") == (0, 1, 0)
    assert specificity("body [data-slot='button'][data-variant].les--sub1") == (0, 3, 1)
    assert specificity(".cdocs__cell--pending.cdocs__cell--key") == (0, 2, 0)
    assert specificity(".x:hover") == (0, 2, 0)


def test_class_on_a_registry_button_outweighs_its_variant():
    """Состояние на кнопке реестра (цвет урока, верный ответ, клетка документа) видно."""
    light = light_rules()
    new = {name: rules for name, rules in light.items() if name not in LEGACY}
    assert (
        not new
    ), "класс поверх Button легче правила варианта (0,2,1) — добавьте селектор с [data-variant]: " + "; ".join(
        f"{name}: {rules[0]}" for name, rules in sorted(new.items())
    )
    fixed = sorted(name for name in LEGACY if name not in light)
    assert not fixed, f"уже поправлено, вычеркните из LEGACY: {fixed}"


def test_lesson_card_keeps_its_colours_over_the_ghost_button():
    """Карточка урока — `ghost`: полоса подгруппы и потока и фон замены тяжелее его."""
    css = (SRC / "screens" / "academics" / "academics.css").read_text(encoding="utf-8")
    for modifier in ("--sub1", "--sub2", "--stream", "--changed", "--off"):
        assert f"body [data-slot='button'][data-variant].les{modifier}" in css, modifier
