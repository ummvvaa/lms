"""Цвет показателя с сервера — из набора цветов интерфейса.

Кабинеты и корзины куратора слали прежние имена (`brand`, `teal`, `indigo`,
`ok`, `risk`), а интерфейс знает только `good`, `warn`, `bad`, `info`,
`neutral`, `accent` (`Tone` в `components/ui.tsx`): 19 из 27 показателей
кабинетов рисовались серыми молча. Тест сверяет каждый цвет из кода сервера
с этим набором — новый показатель с неизвестным цветом не пройдёт.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/repo") if Path("/repo/frontend").is_dir() else Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"


def interface_tones() -> set[str]:
    text = (ROOT / "frontend" / "src" / "components" / "ui.tsx").read_text(encoding="utf-8")
    union = re.search(r"export type Tone = ([^\n]+)", text).group(1)
    return set(re.findall(r"'([a-z]+)'", union))


def server_tones() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        for tone in re.findall(r'"tone": "([a-z]+)"', path.read_text(encoding="utf-8")):
            found.setdefault(tone, set()).add(path.relative_to(BACKEND).as_posix())
    return found


def test_every_tone_the_server_sends_is_known_to_the_interface():
    known = interface_tones()
    assert {"good", "warn", "bad", "info", "neutral", "accent"} <= known
    unknown = {tone: files for tone, files in server_tones().items() if tone not in known}
    assert not unknown, f"цвета, которых нет в Tone интерфейса: {unknown}"


def test_curator_buckets_use_interface_tones():
    from students.attention import BUCKETS

    known = interface_tones()
    assert all(bucket.tone in known for bucket in BUCKETS), [b.tone for b in BUCKETS]
