"""Дата на экране — по Алматы и по календарю, а не по UTC.

`new Date(местная полночь).toISOString().slice(0, 10)` в Алматы (UTC+5) отдаёт
вчерашний день: подпись недели в «Расписании» стояла «4–7 октября» над сеткой
«пн 5 – пт 9», а запрос недели уходил с воскресенья (D85). «Сегодня» берётся
из `todayAlmaty`, сдвиг на дни и понедельник недели — из `shiftDay` и
`mondayOf` (`frontend/src/lib/dates.ts`); больше нигде дата из времени UTC
не вырезается.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/frontend").is_dir() else Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"
DATES = SRC / "lib" / "dates.ts"

CUT = re.compile(r"toISOString\(\)\s*\.\s*(?:slice|substring|substr|split)\(")


def test_no_screen_cuts_a_date_out_of_utc_time():
    found = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.ts*")
        if path != DATES and CUT.search(path.read_text(encoding="utf-8"))
    )
    assert not found, f"дата вырезана из времени UTC — возьмите todayAlmaty, shiftDay или mondayOf: {found}"


def test_week_arithmetic_is_done_on_the_calendar_date():
    text = DATES.read_text(encoding="utf-8")
    for name in ("shiftDay", "mondayOf"):
        assert f"export function {name}(" in text
    # дата недели разбирается как UTC и собирается как UTC: пояс браузера в расчёт не входит
    body = text[text.index("export function shiftDay(") : text.index("export function daysFromToday(")]
    assert "T00:00:00Z" in body and "setUTCDate" in body and "getUTCDay" in body
    shared = (SRC / "screens" / "academics" / "shared.tsx").read_text(encoding="utf-8")
    assert "return mondayOf(iso)" in shared and "return shiftDay(iso, days)" in shared
