"""Пустые состояния — один компонент и один язык (фаза 81).

Обход экранов показал восемьдесят семь собственных фраз «ничего нет», написанных
по файлам вразнобой: «Заметок пока нет», «Пробников ещё не было», «Здесь пусто.
Строки появятся, когда…». Разные слова об одном читаются как разные положения
дел, а выглядят как недоделка.

Правило П-1: карточка без данных сворачивается через `DataCard empty`, строка
внутри живой карточки пишется через `EmptyNote`. Здесь сторожится не текст,
а способ вывода: свой абзац «здесь ничего нет» мимо общего компонента.

Долг закрыт весь — и у ученика с куратором, и у директоров с администратором,
поэтому список долга пуст. Правило стража: долг только уменьшается, новых
файлов со своими абзацами пустоты не появляется.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"

#: фразы, которыми интерфейс сообщает «показывать нечего»
PHRASES = (
    "пока нет",
    "пока пусто",
    "ничего нет",
    "ещё не было",
    "ещё нет",
    "нет данных",
    "не заведено",
    "нет записей",
    "ничего не ждёт",
    "нет ни одного",
    "список пуст",
    "здесь пусто",
    "не осталось",
)

#: где живёт сам общий компонент
HOME = {"components/ui.tsx", "components/Empty.tsx", "components/EmptyDashboard.tsx"}

#: файлы, где свой абзац пустоты ещё остался. Список только укорачивается:
#: на 2026-09-21 он пуст — весь фронт переведён на общий компонент
DEBT: set[str] = set()

PARAGRAPH = re.compile(r"<p className=\"muted[^\"]*\">\{t\('([^']*)'\)\}</p>")


def _own_empty_paragraphs() -> dict[str, list[str]]:
    """Свои абзацы пустоты по файлам: путь → фразы."""
    found: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.tsx")):
        rel = str(path.relative_to(SRC))
        if rel in HOME:
            continue
        for text in PARAGRAPH.findall(path.read_text("utf-8")):
            if any(phrase in text.lower() for phrase in PHRASES):
                found.setdefault(rel, []).append(text)
    return found


def test_no_new_empty_texts_outside_the_shared_component():
    found = _own_empty_paragraphs()
    new = {rel: texts for rel, texts in found.items() if rel not in DEBT}
    assert not new, (
        "свой текст пустого состояния мимо общего компонента: "
        + "; ".join(f"{rel}: {', '.join(texts)}" for rel, texts in new.items())
        + ". Возьмите `EmptyNote` (строка в живой карточке) или `DataCard empty` (карточка целиком)"
    )


def test_the_debt_only_shrinks():
    """Файл из долга, который уже переведён, вычёркивается из списка."""
    found = _own_empty_paragraphs()
    paid = DEBT - set(found)
    assert not paid, f"переведено — вычеркните из DEBT: {sorted(paid)}"


def test_the_shared_component_says_who_fills_and_what_to_do():
    """П-4: у пустого состояния есть место для владельца и для действия."""
    source = (SRC / "components" / "ui.tsx").read_text("utf-8")
    assert "export function EmptyNote" in source
    for prop in ("what", "who", "action"):
        assert f"  {prop}" in source, f"у EmptyNote нет поля {prop}"
    assert "emptyAction" in source, "свёрнутая карточка должна уметь показывать действие"
