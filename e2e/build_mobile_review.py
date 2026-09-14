"""Собрать `docs/ui/mobile-review.html` из снимков телефонной версии (фаза 74).

Снимки и подписи кладёт `tests/mobile-review.spec.ts` в `shots/mobile/`.
Здесь они сжимаются в JPEG (через `sips`, macOS) и вшиваются в один файл
base64 — файл открывается двойным кликом без сервера и без папки рядом.

Список замеченных поломок — `shots/mobile/notes.json`: список строк,
номера проставляются по порядку. Владелец говорит «чинить 3, 7, 12».

Запуск:  python3 build_mobile_review.py
"""

from __future__ import annotations

import base64
import html
import json
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots" / "mobile"
OUT = HERE.parent / "docs" / "ui" / "mobile-review.html"

#: качество JPEG: 75 везде, 85 — у таблиц директоров, где мелкие подписи
QUALITY_DEFAULT = 75
QUALITY_TABLES = 85


def quality_for(shot: dict) -> int:
    dense = shot["screen"] in ("Таблица", "Справочник", "Дедлайны", "Пользователи", "Архив")
    return QUALITY_TABLES if dense else QUALITY_DEFAULT


#: предел высоты JPEG — 65535 px; страница журнала выходит за него
MAX_SIDE = 60000


def to_jpeg_base64(png: Path, quality: int) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        jpg = Path(tmp) / (png.stem + ".jpg")
        height = int(
            subprocess.run(["sips", "-g", "pixelHeight", str(png)], capture_output=True, text=True, check=True)
            .stdout.rsplit(":", 1)[-1]
            .strip()
        )
        # сверхдлинная страница ужимается пропорционально до предела JPEG:
        # содержимое остаётся целиком, читаемость — в приближении
        resize = ["-Z", str(MAX_SIDE)] if height > MAX_SIDE else []
        subprocess.run(
            ["sips", *resize, "-s", "format", "jpeg", "-s", "formatOptions", str(quality), str(png), "--out", str(jpg)],
            check=True,
            capture_output=True,
        )
        return base64.b64encode(jpg.read_bytes()).decode("ascii")


def main() -> None:
    shots = json.loads((SHOTS / "manifest.json").read_text(encoding="utf-8"))
    notes_file = SHOTS / "notes.json"
    notes = json.loads(notes_file.read_text(encoding="utf-8")) if notes_file.exists() else []

    by_role: dict[str, list[dict]] = {}
    for shot in shots:
        by_role.setdefault(shot["roleTitle"], []).append(shot)

    parts = [
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Телефонная версия — разметка владельца</title>",
        "<style>",
        "body{font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px;background:#FBF8F4;color:#231F1C}",
        "h1{font-size:24px;margin:0 0 8px}h2{font-size:20px;margin:40px 0 12px;padding-top:24px;border-top:1px solid #EDE6DE}",
        "nav ol{columns:2;padding-left:20px}nav a{color:#0E7490}",
        ".shot{display:grid;grid-template-columns:420px 1fr;gap:24px;margin:0 0 32px;align-items:start}",
        ".shot img{width:390px;border:1px solid #EDE6DE;border-radius:8px;background:#fff}",
        ".cap{font-size:14px;color:#6B6460;margin:0 0 8px}.cap b{color:#231F1C}",
        ".note{min-height:120px;border:1px dashed #C9C0B6;border-radius:8px;padding:12px;background:#fff;color:#8A837D}",
        ".seeded{display:inline-block;padding:1px 8px;border-radius:12px;background:#FFF1E8;color:#B45309;font-size:12px}",
        ".bugs{background:#fff;border:1px solid #EDE6DE;border-radius:8px;padding:16px 24px}",
        ".bugs li{margin:4px 0}",
        "@media (max-width:900px){.shot{grid-template-columns:1fr}}",
        "</style></head><body>",
        "<h1>Телефонная версия: все экраны (390 × 844, масштаб 2)</h1>",
        f"<p class='cap'>Снимков: <b>{len(shots)}</b>. Каждый — страница целиком. Под снимком место для замечания.</p>",
    ]

    parts.append("<section class='bugs'><h2 style='border:0;margin-top:0;padding-top:0'>Что заметил сам</h2><ol>")
    for note in notes:
        parts.append(f"<li>{html.escape(note)}</li>")
    if not notes:
        parts.append("<li>—</li>")
    parts.append("</ol></section>")

    parts.append("<nav><h2>Оглавление</h2><ol>")
    for role, rows in by_role.items():
        anchor = "r-" + str(abs(hash(role)) % 10**6)
        parts.append(f"<li><a href='#{anchor}'>{html.escape(role)}</a> — {len(rows)}</li>")
    parts.append("</ol></nav>")

    for role, rows in by_role.items():
        anchor = "r-" + str(abs(hash(role)) % 10**6)
        parts.append(f"<h2 id='{anchor}'>{html.escape(role)}</h2>")
        for index, shot in enumerate(rows, start=1):
            # имя в манифесте и на диске различаются нормализацией кириллицы
            # (macOS хранит NFD): ищем файл по номеру, а не по полному имени
            png = next(SHOTS.glob(f"{shot['file'][:3]}-*.png"))
            data = to_jpeg_base64(png, quality_for(shot))
            seeded = " <span class='seeded'>снято на посеянных данных</span>" if shot.get("seeded") else ""
            parts.append(
                "<figure class='shot'>"
                f"<img loading='lazy' alt='' src='data:image/jpeg;base64,{data}'>"
                "<figcaption>"
                f"<p class='cap'><b>{html.escape(role)} · {html.escape(shot['screen'])}</b><br>"
                f"состояние: {html.escape(shot['state'])}<br>"
                f"адрес: <code>{html.escape(shot['url'])}</code>{seeded}</p>"
                f"<div class='note'>Замечание {html.escape(role)} · {index}:</div>"
                "</figcaption></figure>"
            )

    parts.append("</body></html>")
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"{OUT}: {len(shots)} снимков, {OUT.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
