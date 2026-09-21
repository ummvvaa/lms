#!/usr/bin/env python3
"""Реестр находок обхода из манифеста (фаза 81).

Обходчик (`tests/screen-walk.spec.ts`) пишет в `shots/walk/<состояние>/manifest.json`
всё, что видел на экране: элементы, нажатия, ошибки, пустые блоки, ряды плиток,
переполнение. Этот сборщик переводит манифест в заготовку реестра
`docs/ui/screen-review.md`: находки, которые видны числом, он выписывает сам —
остальные дописываются руками, глядя на снимки.

Машинных находок пять видов:

- П-2: два и более блока подряд сообщают только «ничего нет»;
- П-5: ряд плиток не добит (три плюс одна);
- раскладка: страница или окно шире экрана;
- поведение: нажатие без единого следствия, разрушительное без подтверждения,
  ошибка в консоли, ответ не 2xx;
- пустой блок во весь рост: сообщает о пустоте и занимает больше 120 px.

Запуск:  python3 e2e/build_screen_review.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

E2E = Path(__file__).resolve().parent
DOCS = E2E.parent / "docs" / "ui"
STATES = {"empty": "пустая", "filled": "наполненная"}

ROLE_TITLES = {
    "student": "Ученик",
    "curator": "Куратор",
    "director_admission": "Асем · поступление",
    "director_exam": "Кымбат · экзамены",
    "director_behavior": "Салтанат · школа",
    "director_talent": "Арман · таланты",
    "director_sport": "Нурлыбек · спорт",
    "admin": "Администратор",
}

RULES = """Приёмы, которыми закрываются находки. Правило закрывает десятки мест сразу —
поэтому правится по правилу, а не по одному экрану.

**П-1. Один компонент пустого состояния.** Своих фраз «ничего нет» по файлам
не остаётся: карточка без данных сворачивается через `DataCard empty`, строка
внутри живой карточки пишется через `EmptyNote`. Язык один: «пока пусто» или
конкретная причина. Почему: сорок разных фраз об одном читаются как сорок
разных положений дел, а выглядят как недоделка.

**П-2. Блок целиком пустой — одна строка.** Нет ни одного значения — блок
сворачивается в строку «название — причина» с действием справа, если оно
у роли есть. Прочерк в строке остаётся только рядом с заполненными строками
того же блока. Почему: пустая карточка во весь рост занимает место живых,
а шесть таких подряд превращают экран в кладбище.

**П-3. Один факт — одно место.** Факт пишется там, где по нему есть кнопка.
В остальных местах его нет. Почему: «цель не поставлена» в плитке, в карточке,
в соседней карточке и в «Что требует внимания» — это одно и то же, сказанное
четыре раза, и ни разу не сказанное, что с этим делать.

**П-4. Пустое состояние говорит, кто заполняет и что сделать.** Строка
называет владельца («ведёт: Кымбат», «ставит ученик») и даёт действие: «Внести»,
если роль может сама, «Напомнить задачей», если не может. Почему: «Целей нет»
без ответа на «чьё это» заставляет куратора гадать, а не работать.

**П-5. Ряд плиток добивается или перестраивается.** Три плюс одна — нет:
либо ряд заполнен, либо плитки встают по две. Почему: одинокая плитка под
рядом читается как отдельный блок и ломает сетку.

**П-6. Экран нового ученика открывается не пустотой.** Сверху — то, что есть,
и одна строка «данных пока нет» с двумя действиями: внести самому или напомнить
ученику. Ниже — свёрнутые блоки. Почему: первое, что видит куратор первого
сентября, не должно выглядеть как поломка.

**П-7. Формы говорят, что от человека нужно.** У загрузки — форматы и предел
размера, у поля — подпись, у пустого списка выбора — причина, почему он пуст,
и ссылка туда, где это заводится. Почему: форма, которая молчит, заставляет
пробовать наугад."""


#: как закрыта находка: по сути, а не по номеру — номера меняются от прогона к прогону
STATUSES: tuple[tuple[str, str], ...] = (
    ("3 блока подряд", "исправлено: блоки свёрнуты в строки (П-2)"),
    ("2 блока подряд", "исправлено: блоки свёрнуты в строки (П-2)"),
    ("пустой блок во весь рост", "исправлено: блок сворачивается в строку (П-2)"),
    ("ряд плиток не добит", "исправлено: в узкой колонке плитки встают по две (П-5)"),
    ("same key", "исправлено: `order_by()` до `distinct`/`values` — дубли в фильтре и на дашборде"),
    ("TypeError", "исправлено: сервер отдаёт `consequences` всегда, окно не падает"),
    ("Необработанная ошибка", "исправлено: то же окно архива"),
    ("localStorage", "исправлено: чтение хранилища через `lib/storage` не роняет каркас"),
    ("«Удалить навсегда»", "исправлено: окно подтверждения больше не падает"),
    ("«Скрыть»", "не трогаем: скрытие обратимо и видно сразу, подтверждение здесь лишнее"),
    ("«Отклонить»", "не трогаем: отклонение открывает поле причины в той же строке"),
    ("«Открыть помощника»", "отложено: D48 — виджет помощника не отвечает на нажатие"),
    ("«+»", "отложено: D48 — кнопки виджета помощника"),
    ("«⤢»", "отложено: D48 — кнопки виджета помощника"),
    ("«×»", "отложено: D48 — кнопки виджета помощника"),
    ("«Привязать»", "отложено: D49 — привязка почты молчит на пустом поле"),
    ("экран не ответил", "не трогаем: обходчик жал подсказку-вопросик, а не кнопку"),
    ("нажимаемых элементов больше предела", "не трогаем: предел обхода, а не экрана"),
    ("нажатие «", "проверено глазами: сортировка и фильтры работают, обходчик не видит смены порядка"),
    ("Failed to load resource", "отложено: D51 — карточка шлёт запрос, на который у роли нет прав (403 в консоли, экран работает)"),
    ("«Удалить»", "не трогаем: удаление строки идёт через предпросмотр в меню строки"),
    ("«Выгрузить»", "отложено: D51 — тот же 403 в консоли при открытии предпросмотра"),
    ("Base UI", "отложено: D50 — предупреждение библиотеки о вложенной кнопке"),
)


def status_of(text: str) -> str:
    for mark, status in STATUSES:
        if mark in text:
            return status
    return ""


#: высота, выше которой пустой блок занимает место зря (свёрнутый — одна строка)
FOLDED_LIMIT = 120


def normal(url: str) -> str:
    """Адрес без номера ученика: в двух состояниях школы он разный, экран тот же."""
    return re.sub(r"/\d+", "/{id}", url)


def load(state: str) -> list[dict]:
    path = E2E / "shots" / "walk" / state / "manifest.json"
    rows = json.loads(path.read_text("utf-8")) if path.exists() else []
    for row in rows:
        row["url"] = normal(row["url"])
    return rows


#: элементы, повторное нажатие по которым ничего не меняет по делу
CAROUSEL = ("сюжет ", "предыдущий", "следующий", "прошлый месяц", "следующий месяц")

#: длина, после которой «имя» — это не кнопка, а подсказка или целая строка списка:
#: обходчик жмёт и их, но находкой их молчание не считается
NAME_LIMIT = 40


def unfolded_run(blocks: list[dict]) -> tuple[int, list[dict]]:
    """Сколько развёрнутых пустых блоков идут подряд — и какие.

    Свёрнутый пустой блок (одна строка, фаза 80) нарушением не считается: он
    как раз то, чем должна кончиться правка. Считаются только те, что стоят
    во весь рост и сообщают «ничего нет».
    """
    run = 0
    best = 0
    chain: list[dict] = []
    best_chain: list[dict] = []
    for block in blocks:
        if block["empty"] and block["height"] > FOLDED_LIMIT:
            run += 1
            chain.append(block)
            if run > best:
                best, best_chain = run, list(chain)
        else:
            run = 0
            chain = []
    return best, best_chain


def findings_of(screen: dict, idle_in_filled: set[tuple[str, str, str]] | None = None) -> list[tuple[str, str, str]]:
    """Находки одного экрана: (вид, правило, одна строка сути)."""
    out: list[tuple[str, str, str]] = []
    empty_blocks = [b for b in screen["blocks"] if b["empty"]]
    run, chain = unfolded_run(screen["blocks"])

    if run >= 2:
        titles = ", ".join(f"«{b['title']}»" for b in chain[:4])
        out.append(("пустота", "П-2", f"{run} блока подряд стоят во весь рост и сообщают только «ничего нет»: {titles}"))

    tall = [b for b in empty_blocks if b["height"] > FOLDED_LIMIT]
    if tall and run < 2:
        b = tall[0]
        out.append(("пустота", "П-2", f"пустой блок во весь рост ({b['height']} px): «{b['title']}» — «{b['phrase']}»"))

    for row in screen["tileRows"]:
        if row == 3 and len(screen["tileRows"]) > 1:
            out.append(("раскладка", "П-5", f"ряд плиток не добит: {screen['tileRows']}"))
            break

    if screen["overflow"] > 1:
        out.append(("раскладка", "—", f"страница шире экрана на {screen['overflow']} px"))

    tabs = {e["name"] for e in screen["elements"] if e["kind"] == "вкладка"}
    for click in screen["clicks"]:
        name = click["name"]
        if click["opened"] == "зависло" and len(name) <= NAME_LIMIT:
            out.append(("ошибка", "—", f"экран не ответил за 25 с после нажатия «{name}»"))
        if click["opened"] == "предел":
            out.append(("раскладка", "—", f"нажимаемых элементов больше предела: {click['note']}"))
        idle = click["opened"] == "ничего"
        # повторное нажатие по выбранной вкладке и по чипу пустого фильтра ничего
        # не меняет по делу: это не поломка
        known = (
            name in tabs
            or click["opened"] == "уже выбрано"
            or name.lower().startswith(CAROUSEL)
            or len(name) > NAME_LIMIT
        )
        # на пустой школе сортировка колонок и фильтры пустого списка не меняют
        # ничего по делу; находка — только то, что молчит и на наполненной
        if idle and not known and idle_in_filled is not None:
            known = (screen["role"], screen["url"], name) not in idle_in_filled
        if idle and not known:
            # «молчит» — мягкая находка: так выглядит и сортировка таблицы, и переход
            # в новую вкладку, которых обходчик не видит. Проверяется глазами
            out.append(("молчит", "—", f"нажатие «{name}»: ни окна, ни запроса, ни видимого изменения"))
        if click.get("note") and click["opened"] not in ("зависло", "предел"):
            out.append(("ошибка", "—", f"«{name}»: {click['note']}"))
        for error in click["errors"]:
            out.append(("ошибка", "—", f"ошибка консоли при «{click['name']}»: {error[:90]}"))

    for error in screen["pageErrors"]:
        out.append(("ошибка", "—", f"исключение страницы: {error[:90]}"))
    for error in screen["consoleErrors"]:
        out.append(("ошибка", "—", f"ошибка консоли при открытии: {error[:90]}"))
    for bad in screen["badResponses"]:
        out.append(("ошибка", "—", f"ответ не 2xx при открытии: {bad}"))
    return out


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    coverage: dict[tuple[str, str], dict] = {}
    number = 0

    filled = load("filled")
    idle_in_filled = {
        (s["role"], s["url"], c["name"])
        for s in filled
        for c in s["clicks"]
        if c["opened"] == "ничего"
    }

    for state, state_title in STATES.items():
        for screen in load(state):
            key = (screen["role"], screen["url"])
            seen = coverage.setdefault(key, {"widths": set(), "states": set(), "elements": 0, "clicks": 0})
            seen["widths"].add(screen["width"])
            seen["states"].add(state_title)
            seen["elements"] = max(seen["elements"], len(screen["elements"]))
            seen["clicks"] += len(screen["clicks"])
            # пустую школу сверяем с наполненной: молчащее нажатие там и там — находка
            for kind, rule, text in findings_of(screen, idle_in_filled if state == "empty" and filled else None):
                number += 1
                rows.append(
                    {
                        "id": f"Н-{number:03d}",
                        "role": screen["role"],
                        "url": screen["url"],
                        "width": screen["width"],
                        "state": state_title,
                        "kind": kind,
                        "rule": rule,
                        "text": text,
                        "shot": f"walk/{state}/{screen['shot']}",
                    }
                )

    by_role: dict[str, int] = defaultdict(int)
    by_kind: dict[str, int] = defaultdict(int)
    for row in rows:
        by_role[row["role"]] += 1
        by_kind[row["kind"]] += 1

    statuses = STATUSES

    out = [
        "# Обход экранов: реестр находок",
        "",
        "Собран из манифеста обходчика (`e2e/tests/screen-walk.spec.ts`) сборщиком",
        "`e2e/build_screen_review.py`. Машинные находки выписаны числом; находки,",
        "которые видно только глазом, дописаны ниже руками — у них номера с той же",
        "нумерации. Снимки — в `e2e/shots/walk/<состояние>/`.",
        "",
        f"Находок машинных: {len(rows)}. По ролям: "
        + ", ".join(f"{ROLE_TITLES.get(r, r)} — {n}" for r, n in sorted(by_role.items(), key=lambda x: -x[1]))
        + ".",
        "По видам: " + ", ".join(f"{k} — {n}" for k, n in sorted(by_kind.items(), key=lambda x: -x[1])) + ".",
        "",
        "## Таблица",
        "",
        "| № | Экран | Роль | Ширина | Школа | Суть | Правило | Статус |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        out.append(
            f"| {row['id']} | `{row['url']}` | {ROLE_TITLES.get(row['role'], row['role'])} | {row['width']} | "
            f"{row['state']} | {row['text'][:110]} | {row['rule']} | {status_of(row['text'])} |"
        )

    out += ["", "## Правила", "", RULES, ""]
    out += ["", "## Находки", ""]
    for row in rows:
        out += [
            f"### {row['id']} · {ROLE_TITLES.get(row['role'], row['role'])} · `{row['url']}`",
            f"- Роль: {row['role']}. Ширина: {row['width']}. Школа: {row['state']}",
            f"- Вид: {row['kind']}",
            f"- Что не так: {row['text']}",
            f"- Снимок: `{row['shot']}`",
            f"- Правило: {row['rule']}",
            f"- Статус: {status_of(row['text']) or 'не закрыто'}",
            "",
        ]

    out += ["## Покрытие", "", "| Адрес | Роль | Ширины | Состояния | Элементов | Нажатий |", "| --- | --- | --- | --- | --- | --- |"]
    for (role, url), seen in sorted(coverage.items()):
        widths = ", ".join(str(w) for w in sorted(seen["widths"]))
        states = ", ".join(sorted(seen["states"]))
        out.append(f"| `{url}` | {ROLE_TITLES.get(role, role)} | {widths} | {states} | {seen['elements']} | {seen['clicks']} |")
    out.append("")
    out.append(f"Адресов пройдено: {len(coverage)}. Нажатий всего: {sum(s['clicks'] for s in coverage.values())}.")
    out.append("")

    (DOCS / "screen-review.md").write_text("\n".join(out), "utf-8")
    print(f"находок {len(rows)}, адресов {len(coverage)}, нажатий {sum(s['clicks'] for s in coverage.values())}")


if __name__ == "__main__":
    main()
