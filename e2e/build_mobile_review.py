"""Собрать `docs/ui/mobile-review.html` из снимков телефонной версии (фаза 74).

Снимки и подписи кладёт `tests/mobile-review.spec.ts` в `shots/mobile/`.
Здесь они сжимаются в JPEG (через `sips`, macOS) и вшиваются в один файл
base64 — файл открывается двойным кликом без сервера и без папки рядом.

Список замеченных поломок — `shots/mobile/notes.json`: список строк,
номера проставляются по порядку. Владелец говорит «чинить 3, 7, 12».

Запуск:  python3 build_mobile_review.py — собирает и HTML, и PDF (через Playwright, `print_mobile_review.mjs`)
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

#: обычный экран — ширина 585 px (полтора масштаба), JPEG 65: файл на 127
#: страниц целиком иначе весит под сотню мегабайт. Плотные экраны — таблицы,
#: справочники, списки — 780 px и JPEG 85: там мелкие подписи, и они должны читаться
QUALITY_DEFAULT, WIDTH_DEFAULT = 65, 585
QUALITY_TABLES, WIDTH_TABLES = 85, 780
DENSE = ("Таблица", "Справочник", "Дедлайны", "Пользователи", "Архив", "Журнал", "Ученики", "Контакты родителей")


def quality_for(shot: dict) -> tuple[int, int]:
    dense = shot["screen"] in DENSE or shot["screen"].startswith("Импорт · шаг")
    return (QUALITY_TABLES, WIDTH_TABLES) if dense else (QUALITY_DEFAULT, WIDTH_DEFAULT)


#: предел высоты JPEG — 65535 px; страница журнала выходит за него
MAX_SIDE = 60000


def to_jpeg_base64(png: Path, quality: int, width: int) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        jpg = Path(tmp) / (png.stem + ".jpg")
        height = int(
            subprocess.run(["sips", "-g", "pixelHeight", str(png)], capture_output=True, text=True, check=True)
            .stdout.rsplit(":", 1)[-1]
            .strip()
        )
        # сверхдлинная страница ужимается пропорционально до предела JPEG:
        # содержимое остаётся целиком, читаемость — в приближении
        # ширина в файле — 780 px: столько и есть у экрана 390 в масштабе 2;
        # снимок шире значит горизонтальный выезд, и он ужимается в те же 780
        resize = ["-Z", str(MAX_SIDE)] if height > MAX_SIDE else ["--resampleWidth", str(width)]
        subprocess.run(
            ["sips", *resize, "-s", "format", "jpeg", "-s", "formatOptions", str(quality), str(png), "--out", str(jpg)],
            check=True,
            capture_output=True,
        )
        return base64.b64encode(jpg.read_bytes()).decode("ascii")


# --- PDF ----------------------------------------------------------------------

#: страница A4 с полями 8 мм: ширина ≈ 194 мм ≈ 733 px при 96 dpi, высота ≈ 281 мм
PDF_WIDTH = 733
PDF_PAGE_HEIGHT = 1000
#: первый кусок — под подписью и полем для замечания
PDF_FIRST_HEIGHT = 820
PDF_OUT = HERE.parent / "docs" / "ui" / "mobile-review.pdf"
PDF_HTML = HERE / "shots" / "mobile" / "print.html"


def pdf_chunks(png: Path, quality: int) -> list[str]:
    """Снимок под печать: ширина страницы, длинный режется на куски по высоте листа.

    Chromium не переносит одну картинку через границу страницы — сжал бы
    километровую таблицу в нечитаемую полоску. Куски — отдельные картинки,
    каждая целиком на своей странице; первый идёт под подписью.
    """
    with tempfile.TemporaryDirectory() as tmp:
        # основа — PNG: у JPEG предел высоты 65535 px, а журнал куратора длиннее;
        # в JPEG уходят уже куски по высоте листа
        base = Path(tmp) / "base.png"
        subprocess.run(
            ["sips", "--resampleWidth", str(PDF_WIDTH), "-s", "format", "png", str(png), "--out", str(base)],
            check=True,
            capture_output=True,
        )
        height = int(
            subprocess.run(["sips", "-g", "pixelHeight", str(base)], capture_output=True, text=True, check=True)
            .stdout.rsplit(":", 1)[-1]
            .strip()
        )
        # смещение у `sips` — 16-битное: ниже 65535 px резать нечем. Для нижних
        # кусков режем перевёрнутую картинку от верха и переворачиваем кусок обратно
        flipped = Path(tmp) / "flipped.png"
        if height > 60000:
            subprocess.run(["sips", "--flip", "vertical", str(base), "--out", str(flipped)], check=True, capture_output=True)
        chunks = []
        offset = 0
        index = 0
        while offset < height:
            # первый кусок короче: над ним подпись и место под замечание,
            # иначе он не помещается на лист и уезжает на следующий
            limit = PDF_FIRST_HEIGHT if index == 0 else PDF_PAGE_HEIGHT
            piece = min(limit, height - offset)
            # хвост короче листа `sips` не вырезает — берём полный лист от конца,
            # нахлёст с предыдущим куском безвреден
            if piece < limit and offset > 0:
                offset, piece = max(0, height - PDF_PAGE_HEIGHT), min(PDF_PAGE_HEIGHT, height)
            out = Path(tmp) / f"chunk{index}.jpg"
            if offset + piece > 60000:
                source, top, flip = flipped, height - offset - piece, ["--flip", "vertical"]
            else:
                source, top, flip = base, offset, []
            # ноль `sips` считает «смещение не задано» и режет из середины —
            # первый кусок берём с 1 px, потеря незаметна
            top = max(1, top)
            subprocess.run(
                [
                    "sips", "--cropOffset", str(top), "0", "-c", str(piece), str(PDF_WIDTH), *flip,
                    "-s", "format", "jpeg", "-s", "formatOptions", str(quality), str(source), "--out", str(out),
                ],
                check=True,
                capture_output=True,
            )
            chunks.append(base64.b64encode(out.read_bytes()).decode("ascii"))
            offset += piece
            index += 1
        return chunks


def build_pdf(shots: list[dict], notes: list[str], by_role: dict[str, list[dict]]) -> None:
    """Тот же обзор — в PDF: список поломок, оглавление, снимок с подписью на своей странице."""
    parts = [
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>",
        "<title>Телефонная версия — обзор</title><style>",
        "@page{size:A4;margin:8mm}",
        "body{font:12px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#231F1C}",
        "h1{font-size:20px;margin:0 0 6px}h2{font-size:16px;margin:0 0 8px}",
        "ol{padding-left:18px}li{margin:3px 0}",
        ".sheet{break-before:page}.cap{font-size:12px;color:#6B6460;margin:0 0 6px}.cap b{color:#231F1C;font-size:13px}",
        ".note{border:1px dashed #C9C0B6;border-radius:6px;padding:8px;color:#8A837D;min-height:40px;margin:6px 0 8px}",
        f"img{{display:block;width:{PDF_WIDTH}px;max-width:100%;border:1px solid #EDE6DE}}",
        ".more{break-before:page}.seeded{color:#B45309}",
        "</style></head><body>",
        "<h1>Телефонная версия: все экраны (390 × 844, масштаб 2)</h1>",
        f"<p class='cap'>Снимков: <b>{len(shots)}</b>. Каждый — страница целиком; длинные экраны продолжаются на следующих листах.</p>",
        "<h2>Что заметил сам</h2><ol>",
        *[f"<li>{html.escape(note)}</li>" for note in notes],
        "</ol><h2>Оглавление</h2><ol>",
        *[f"<li>{html.escape(role)} — {len(rows)}</li>" for role, rows in by_role.items()],
        "</ol>",
    ]
    for role, rows in by_role.items():
        for index, shot in enumerate(rows, start=1):
            png = next(SHOTS.glob(f"{shot['file'][:3]}-*.png"))
            quality, _ = quality_for(shot)
            chunks = pdf_chunks(png, quality)
            seeded = " · <span class='seeded'>снято на посеянных данных</span>" if shot.get("seeded") else ""
            parts.append(
                "<section class='sheet'>"
                f"<p class='cap'><b>{html.escape(role)} · {html.escape(shot['screen'])}</b><br>"
                f"состояние: {html.escape(shot['state'])} · адрес: <code>{html.escape(shot['url'])}</code>{seeded}</p>"
                f"<div class='note'>Замечание {html.escape(role)} · {index}:</div>"
                f"<img src='data:image/jpeg;base64,{chunks[0]}'>"
            )
            for chunk in chunks[1:]:
                parts.append(f"<img class='more' src='data:image/jpeg;base64,{chunk}'>")
            parts.append("</section>")
    parts.append("</body></html>")
    PDF_HTML.write_text("".join(parts), encoding="utf-8")
    subprocess.run(
        ["node", str(HERE / "print_mobile_review.mjs"), str(PDF_HTML), str(PDF_OUT)],
        check=True,
        cwd=HERE,
    )
    print(f"{PDF_OUT}: {PDF_OUT.stat().st_size // 1024} КБ")


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
            data = to_jpeg_base64(png, *quality_for(shot))
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
    build_pdf(shots, notes, by_role)


if __name__ == "__main__":
    main()
