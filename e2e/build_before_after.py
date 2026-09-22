"""Файл «было / стало» для владельца: снимки до и после правок (фаза 81).

Обход снят дважды: до правок (`shots/walk/<состояние>/`) и после
(`shots/walk-after/<состояние>/`). Здесь пары складываются в один HTML,
который открывается двойным кликом — снимки вшиты в файл, папка рядом
не нужна, как в обзоре телефонной версии фазы 74.

Запуск:  python3 build_before_after.py   (HTML и PDF)
"""

from __future__ import annotations

import base64
import html
import json
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEFORE = HERE / "shots" / "walk"
AFTER = HERE / "shots" / "walk-after"
OUT = HERE.parent / "docs" / "ui" / "screen-review.html"

#: ширина картинки в файле и качество JPEG: пара снимков на страницу — 700 px хватает
WIDTH, QUALITY = 700, 72

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


#: предел стороны JPEG — 65535 px; журнал и длинные списки выходят за него
MAX_SIDE = 60000


def jpeg(png: Path) -> str | None:
    """Снимок в JPEG под ширину файла. Не поддался — пропускаем, а не падаем."""
    with tempfile.TemporaryDirectory() as tmp:
        jpg = Path(tmp) / (png.stem + ".jpg")
        try:
            height = int(
                subprocess.run(["sips", "-g", "pixelHeight", str(png)], capture_output=True, text=True, check=True)
                .stdout.rsplit(":", 1)[-1]
                .strip()
            )
        except (subprocess.CalledProcessError, ValueError):
            return None
        # сверхдлинная страница ужимается пропорционально до предела формата
        resize = ["-Z", str(MAX_SIDE)] if height > MAX_SIDE else ["--resampleWidth", str(WIDTH)]
        try:
            subprocess.run(
                ["sips", *resize, "-s", "format", "jpeg", "-s", "formatOptions", str(QUALITY),
                 str(png), "--out", str(jpg)],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError:
            return None
        return base64.b64encode(jpg.read_bytes()).decode("ascii")


def shots(root: Path, state: str) -> dict[tuple[str, str, int], str]:
    """Снимки по ключу «роль, адрес, ширина»."""
    path = root / state / "manifest.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text("utf-8"))
    return {(r["role"], r["url"], r["width"]): r["shot"] for r in rows}


def main() -> None:
    pairs = []
    for state in ("empty", "filled"):
        before, after = shots(BEFORE, state), shots(AFTER, state)
        for key, shot in after.items():
            old = before.get(key)
            if not old:
                continue
            old_png, new_png = BEFORE / state / old, AFTER / state / shot
            if not old_png.exists() or not new_png.exists():
                continue
            if old_png.read_bytes() == new_png.read_bytes():
                continue  # экран не изменился — в файл не идёт
            role, url, width = key
            old_jpeg, new_jpeg = jpeg(old_png), jpeg(new_png)
            if old_jpeg is None or new_jpeg is None:
                continue
            pairs.append({
                "role": ROLE_TITLES.get(role, role),
                "url": url,
                "width": width,
                "state": "пустая школа" if state == "empty" else "наполненная школа",
                "before": old_jpeg,
                "after": new_jpeg,
            })

    body = []
    for n, pair in enumerate(pairs, 1):
        body.append(f"""
      <section class="pair">
        <h2>{n}. {html.escape(pair['role'])} · <code>{html.escape(pair['url'])}</code></h2>
        <p class="meta">{pair['width']} px · {pair['state']}</p>
        <div class="row">
          <figure><figcaption>было</figcaption><img src="data:image/jpeg;base64,{pair['before']}" alt=""></figure>
          <figure><figcaption>стало</figcaption><img src="data:image/jpeg;base64,{pair['after']}" alt=""></figure>
        </div>
      </section>""")

    OUT.write_text(f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Обход экранов: было и стало</title>
<style>
  body {{ font: 15px/1.5 -apple-system, system-ui, sans-serif; color: #231F1C; background: #FBF8F4; margin: 0; padding: 32px; }}
  h1 {{ font-size: 28px; margin: 0 0 8px; }}
  .lead {{ color: #6b625c; margin: 0 0 32px; max-width: 70ch; }}
  .pair {{ background: #fff; border: 1px solid #EDE6DE; border-radius: 12px; padding: 20px; margin-bottom: 24px; break-inside: avoid; }}
  h2 {{ font-size: 17px; margin: 0 0 4px; }}
  .meta {{ color: #6b625c; font-size: 13px; margin: 0 0 12px; }}
  .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  figure {{ margin: 0; }}
  figcaption {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #6b625c; margin-bottom: 6px; }}
  img {{ width: 100%; border: 1px solid #EDE6DE; border-radius: 8px; display: block; }}
  code {{ font-size: 14px; background: #F5F0EA; padding: 1px 5px; border-radius: 4px; }}
</style></head><body>
<h1>Обход экранов: было и стало</h1>
<p class="lead">Слева — как экран выглядел до правок фазы 81, справа — после. В файл попали
только те экраны, которые действительно изменились: {len(pairs)}. Полный реестр находок
со статусами — <code>docs/ui/screen-review.md</code>.</p>
{''.join(body)}
</body></html>""", "utf-8")
    print(f"{OUT.name}: пар {len(pairs)}")

    # PDF — тем же печатником, что у обзора телефонной версии (фаза 74)
    pdf = OUT.with_suffix(".pdf")
    try:
        subprocess.run(
            ["node", str(HERE / "print_mobile_review.mjs"), str(OUT), str(pdf)],
            check=True, capture_output=True,
        )
        print(f"{pdf.name}: готов")
    except subprocess.CalledProcessError as error:
        print("PDF не собрался:", error.stderr.decode()[:200])


if __name__ == "__main__":
    main()
