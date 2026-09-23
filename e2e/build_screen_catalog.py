#!/usr/bin/env python3
"""Каталог экранов: PDF на роль и оглавление.

Снимки кладёт обходчик в режиме каталога (`WALK_MODE=catalog`, см. шапку
`tests/screen-walk.spec.ts`) в `shots/catalog/<состояние>/`, манифест —
`catalog.json` там же. Здесь снимки складываются в `docs/ui/screens/`:

- по файлу на роль; не влез в 20 МБ — режется по ширинам (`kurator-1440.pdf`),
  ширина не влезла — ещё и по состоянию школы (`administrator-390-polnaya.pdf`);
- одна страница — один снимок. Заголовок — сверху, в своей полосе; снимок
  ниже полосы и вписан целиком. Высокий снимок уменьшается, полоса стоит;
- рядом `index.md`: строка на каждый снимок и на каждый адрес из `routes.ts`,
  который не снялся, — с причиной.

PDF пишется здесь же, без сторонних библиотек: страница — полоса заголовка
и картинка, размер страницы подбирается под снимок, JPEG ложится в файл как
есть (`DCTDecode`). Шрифт с кириллицей (Verdana) вшивается целиком, поэтому
адреса в файле ищутся поиском. Это прошлые ошибки обзора фазы 81, которых
при такой вёрстке не бывает: вёрстка HTML печатью переносила заголовок
поверх снимка и оставляла пустые страницы.

Сборщик проверяет сам себя, читая готовые файлы, а не свои списки: страниц
столько, сколько снимков у роли; на каждой ровно одна картинка, и она ниже
полосы заголовка; каждый адрес из `routes.ts` есть в оглавлении. Проверка
не прошла — выход с ошибкой.

Запуск руками (в прогон не входит):  python3 e2e/build_screen_catalog.py
"""

from __future__ import annotations

import io
import json
import os
import re
import struct
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

#: снимки свои и длинные: журнал на телефоне — 95 млн точек, это не «бомба распаковки»
Image.MAX_IMAGE_PIXELS = None

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots" / "catalog"
ROUTES_TS = HERE / "helpers" / "routes.ts"
OUT = HERE.parent / "docs" / "ui" / "screens"

#: снимки: JPEG с качеством 75 и шириной до 1400 точек (телефон — 780, как снят)
QUALITY = 75
MAX_WIDTH = 1400
#: предел файла: не влез — режем по ширинам
LIMIT_BYTES = 20 * 1024 * 1024
#: предел стороны страницы PDF — 14 400 пунктов (200 дюймов), стороны JPEG — 65 535 точек
MAX_PAGE = 14_400
MAX_SIDE = 65_000
#: снимок телефона выше этого ложится в натуральную величину экрана
TALL = 30_000

#: порядок и подписи
STATES = {"filled": "наполненная", "empty": "пустая"}
#: хвост имени файла, если роль режется ещё и по состоянию школы
STATE_FILES = {"filled": "polnaya", "empty": "pustaya"}
WIDTHS = (1440, 390)
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
ROLE_FILES = {
    "student": "uchenik",
    "curator": "kurator",
    "director_admission": "asem",
    "director_exam": "kymbat",
    "director_behavior": "saltanat",
    "director_talent": "arman",
    "director_sport": "nurlybek",
    "admin": "administrator",
}

FONTS = {
    "regular": [
        os.environ.get("CATALOG_FONT", ""),
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "bold": [
        os.environ.get("CATALOG_FONT_BOLD", ""),
        "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}

#: цвета полосы заголовка — токены дизайн-системы
GRAPHITE = (0x23, 0x1F, 0x1C)
MUTED = (0x6B, 0x62, 0x5C)
ACCENT = (0xB4, 0x53, 0x09)
BAND = (0xF5, 0xF0, 0xEA)
LINE = (0xED, 0xE6, 0xDE)

#: вёрстка страницы в пунктах: 0,75 пункта на точку — снимок в натуральную величину
SCALE = 0.75
MARGIN = 24
GAP = 12


# ── список адресов ────────────────────────────────────────────────────────


def read_routes() -> dict[str, list[str]]:
    """Адреса из `routes.ts`: сборщик сверяется с самим списком, а не с манифестом."""
    text = ROUTES_TS.read_text("utf-8")
    body = text.split("export const ROUTES", 1)[1].split("\n};", 1)[0]
    routes: dict[str, list[str]] = {}
    role = ""
    for line in body.splitlines():
        head = re.match(r"^  (\w+): \[", line)
        if head:
            role = head.group(1)
            routes[role] = []
            continue
        item = re.match(r'^    "([^"]+)",', line)
        if item and role:
            routes[role].append(item.group(1))
    return routes


# ── шрифт ──────────────────────────────────────────────────────────────────


@dataclass
class Font:
    """TrueType-шрифт для PDF: глифы по кодам, ширины, метрики."""

    path: Path
    data: bytes
    units: int
    cmap: dict[int, int]
    advances: list[int]
    bbox: tuple[int, int, int, int]
    ascent: int
    descent: int
    cap: int
    name: str
    used: dict[int, str] = field(default_factory=dict)

    @classmethod
    def load(cls, candidates: list[str]) -> Font:
        path = next((Path(p) for p in candidates if p and Path(p).exists()), None)
        if path is None:
            sys.exit(f"нет шрифта с кириллицей: {[p for p in candidates if p]}")
        data = path.read_bytes()
        count = struct.unpack(">H", data[4:6])[0]
        tables: dict[str, tuple[int, int]] = {}
        for i in range(count):
            tag, _, offset, length = struct.unpack(">4sIII", data[12 + 16 * i : 28 + 16 * i])
            tables[tag.decode("latin1")] = (offset, length)

        head = tables["head"][0]
        units = struct.unpack(">H", data[head + 18 : head + 20])[0]
        bbox = struct.unpack(">4h", data[head + 36 : head + 44])
        hhea = tables["hhea"][0]
        ascent, descent = struct.unpack(">hh", data[hhea + 4 : hhea + 8])
        metrics = struct.unpack(">H", data[hhea + 34 : hhea + 36])[0]
        glyphs = struct.unpack(">H", data[tables["maxp"][0] + 4 : tables["maxp"][0] + 6])[0]
        hmtx = tables["hmtx"][0]
        advances = [struct.unpack(">H", data[hmtx + 4 * i : hmtx + 4 * i + 2])[0] for i in range(metrics)]
        advances += [advances[-1]] * (glyphs - metrics)
        cap = ascent
        if "OS/2" in tables:
            os2 = tables["OS/2"][0]
            if struct.unpack(">H", data[os2 : os2 + 2])[0] >= 2:
                cap = struct.unpack(">h", data[os2 + 88 : os2 + 90])[0]
        name = re.sub(r"[^A-Za-z0-9-]", "", path.stem) or "Font"
        return cls(path, data, units, cls._cmap(data, tables["cmap"][0]), advances, bbox, ascent, descent, cap, name)

    @staticmethod
    def _cmap(data: bytes, base: int) -> dict[int, int]:
        """Коды символов → номера глифов: подтаблица Windows Unicode, формат 4."""
        count = struct.unpack(">H", data[base + 2 : base + 4])[0]
        for i in range(count):
            platform, encoding, offset = struct.unpack(">HHI", data[base + 4 + 8 * i : base + 12 + 8 * i])
            table = base + offset
            if (platform, encoding) != (3, 1) or struct.unpack(">H", data[table : table + 2])[0] != 4:
                continue
            segments = struct.unpack(">H", data[table + 6 : table + 8])[0] // 2
            ends = table + 14
            starts = ends + 2 * segments + 2
            deltas = starts + 2 * segments
            ranges = deltas + 2 * segments
            out: dict[int, int] = {}
            for s in range(segments):
                end = struct.unpack(">H", data[ends + 2 * s : ends + 2 * s + 2])[0]
                start = struct.unpack(">H", data[starts + 2 * s : starts + 2 * s + 2])[0]
                delta = struct.unpack(">h", data[deltas + 2 * s : deltas + 2 * s + 2])[0]
                shift = struct.unpack(">H", data[ranges + 2 * s : ranges + 2 * s + 2])[0]
                for code in range(start, min(end, 0xFFFE) + 1):
                    if shift == 0:
                        glyph = (code + delta) & 0xFFFF
                    else:
                        at = ranges + 2 * s + shift + 2 * (code - start)
                        glyph = struct.unpack(">H", data[at : at + 2])[0]
                        if glyph:
                            glyph = (glyph + delta) & 0xFFFF
                    if glyph:
                        out[code] = glyph
            return out
        sys.exit("в шрифте нет таблицы Unicode (Windows, формат 4)")

    def glyph(self, char: str) -> int:
        gid = self.cmap.get(ord(char), self.cmap.get(ord("?"), 0))
        self.used.setdefault(gid, char)
        return gid

    def width(self, text: str, size: float) -> float:
        return sum(self.advances[self.cmap.get(ord(c), 0)] for c in text) * size / self.units

    def encode(self, text: str) -> str:
        return "".join(f"{self.glyph(c):04X}" for c in text)


# ── PDF ────────────────────────────────────────────────────────────────────


def pdf_text(text: str) -> bytes:
    """Строка PDF в UTF-16 — для закладок и свойств файла."""
    return b"<FEFF" + text.encode("utf-16-be").hex().upper().encode() + b">"


def rgb(color: tuple[int, int, int]) -> str:
    return " ".join(f"{c / 255:.3f}" for c in color)


@dataclass
class Page:
    """Одна страница каталога: заголовок и снимок."""

    number: int
    lines: list[tuple[str, str, float, tuple[int, int, int]]]  # (текст, шрифт, кегль, цвет)
    outline: str
    jpeg: bytes
    pixels: tuple[int, int]


class Writer:
    """Минимальный PDF: страницы с полосой заголовка и одной картинкой."""

    def __init__(self, fonts: dict[str, Font]) -> None:
        self.fonts = fonts
        self.objects: list[bytes | None] = []
        self.font_refs: dict[str, int] = {}

    def reserve(self) -> int:
        self.objects.append(None)
        return len(self.objects)

    def put(self, number: int, body: bytes) -> int:
        self.objects[number - 1] = body
        return number

    def add(self, body: bytes) -> int:
        return self.put(self.reserve(), body)

    def stream(self, head: str, data: bytes, compress: bool = True) -> int:
        if compress:
            data = zlib.compress(data, 9)
            head += " /Filter /FlateDecode"
        return self.add(f"<< {head} /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream")

    @staticmethod
    def wrap(font: Font, text: str, size: float, width: float) -> list[str]:
        """Перенос по словам: полоса не шире страницы, текст не наезжает на поля."""
        words = text.split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            probe = f"{current} {word}".strip()
            if current and font.width(probe, size) > width:
                lines.append(current)
                current = word
            else:
                current = probe
        if current:
            lines.append(current)
        return lines

    def page(self, pages_ref: int, page: Page) -> tuple[int, int]:
        """Страница: размер под снимок, полоса сверху, снимок ниже полосы."""
        px_w, px_h = page.pixels
        image_w = px_w * SCALE
        page_w = max(image_w + 2 * MARGIN, 520)
        inner = page_w - 2 * MARGIN

        # полоса заголовка: строки с переносом, высота — по числу строк
        laid: list[tuple[str, Font, float, tuple[int, int, int]]] = []
        for text, face, size, color in page.lines:
            font = self.fonts[face]
            for part in self.wrap(font, text, size, inner):
                laid.append((part, font, size, color))
        band = 14 + sum(size * 1.45 for _, _, size, _ in laid) + 10

        # снимок вписывается целиком: высокий уменьшается, полоса остаётся на месте
        scale = SCALE
        room = MAX_PAGE - band - GAP - 2 * MARGIN
        if px_h * scale > room:
            scale = room / px_h
        draw_w, draw_h = px_w * scale, px_h * scale
        page_h = band + GAP + draw_h + 2 * MARGIN
        band_y = page_h - band

        ops = [
            f"{rgb(BAND)} rg 0 {band_y:.2f} {page_w:.2f} {band:.2f} re f",
            f"{rgb(LINE)} RG 0.75 w 0 {band_y:.2f} m {page_w:.2f} {band_y:.2f} l S",
        ]
        y = page_h - 14
        for text, font, size, color in laid:
            y -= size * 1.1
            face = "F1" if font is self.fonts["regular"] else "F2"
            ops.append(f"BT {rgb(color)} rg /{face} {size:.1f} Tf {MARGIN:.2f} {y:.2f} Td <{font.encode(text)}> Tj ET")
            y -= size * 0.35
        x = (page_w - draw_w) / 2
        image_y = MARGIN
        ops.append(f"q {draw_w:.2f} 0 0 {draw_h:.2f} {x:.2f} {image_y:.2f} cm /Im0 Do Q")
        ops.append(f"{rgb(LINE)} RG 0.75 w {x:.2f} {image_y:.2f} {draw_w:.2f} {draw_h:.2f} re S")
        content = self.stream("", "\n".join(ops).encode())

        image = self.add(
            f"<< /Type /XObject /Subtype /Image /Width {px_w} /Height {px_h} /ColorSpace /DeviceRGB "
            f"/BitsPerComponent 8 /Filter /DCTDecode /Length {len(page.jpeg)} >>\nstream\n".encode()
            + page.jpeg
            + b"\nendstream"
        )
        ref = self.add(
            f"<< /Type /Page /Parent {pages_ref} 0 R /MediaBox [0 0 {page_w:.2f} {page_h:.2f}] "
            f"/Resources << /Font << /F1 {self.font_refs['regular']} 0 R /F2 {self.font_refs['bold']} 0 R >> "
            f"/XObject << /Im0 {image} 0 R >> >> /Contents {content} 0 R >>".encode()
        )
        return ref, round(page_h)

    def embed(self, key: str, font: Font) -> int:
        """Шрифт целиком (Type0, Identity-H) с таблицей перевода в Unicode."""
        k = 1000 / font.units
        file = self.stream(f"/Length1 {len(font.data)}", font.data)
        descriptor = self.add(
            f"<< /Type /FontDescriptor /FontName /{font.name} /Flags 32 "
            f"/FontBBox [{' '.join(str(round(v * k)) for v in font.bbox)}] /ItalicAngle 0 "
            f"/Ascent {round(font.ascent * k)} /Descent {round(font.descent * k)} /CapHeight {round(font.cap * k)} "
            f"/StemV 80 /FontFile2 {file} 0 R >>".encode()
        )
        widths = " ".join(f"{gid} [{round(font.advances[gid] * k)}]" for gid in sorted(font.used))
        cid = self.add(
            f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{font.name} "
            f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            f"/FontDescriptor {descriptor} 0 R /DW 1000 /W [{widths}] /CIDToGIDMap /Identity >>".encode()
        )
        pairs = sorted(font.used.items())
        chunks = []
        for i in range(0, len(pairs), 100):
            part = pairs[i : i + 100]
            body = "\n".join(f"<{gid:04X}> <{ch.encode('utf-16-be').hex().upper()}>" for gid, ch in part)
            chunks.append(f"{len(part)} beginbfchar\n{body}\nendbfchar")
        cmap = (
            "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
            "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
            + "\n".join(chunks)
            + "\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend"
        )
        unicode = self.stream("", cmap.encode())
        return self.put(
            self.font_refs[key],
            f"<< /Type /Font /Subtype /Type0 /BaseFont /{font.name} /Encoding /Identity-H "
            f"/DescendantFonts [{cid} 0 R] /ToUnicode {unicode} 0 R >>".encode(),
        )

    def build(self, title: str, pages: list[Page]) -> tuple[bytes, list[int]]:
        """Файл целиком; возвращает байты и высоты страниц — для проверки."""
        catalog = self.reserve()
        pages_ref = self.reserve()
        outlines = self.reserve()
        self.font_refs = {"regular": self.reserve(), "bold": self.reserve()}
        refs: list[int] = []
        heights: list[int] = []
        for page in pages:
            ref, height = self.page(pages_ref, page)
            refs.append(ref)
            heights.append(height)
        for key, font in self.fonts.items():
            self.embed(key, font)

        # закладки: строка на страницу — номер, адрес, ширина, состояние, окно
        items = [self.reserve() for _ in pages]
        for i, (page, item) in enumerate(zip(pages, items, strict=True)):
            links = f"/Parent {outlines} 0 R"
            if i > 0:
                links += f" /Prev {items[i - 1]} 0 R"
            if i < len(items) - 1:
                links += f" /Next {items[i + 1]} 0 R"
            self.put(item, b"<< /Title " + pdf_text(page.outline) + f" {links} /Dest [{refs[i]} 0 R /Fit] >>".encode())
        if items:
            self.put(
                outlines,
                f"<< /Type /Outlines /First {items[0]} 0 R /Last {items[-1]} 0 R /Count {len(items)} >>".encode(),
            )
        else:
            self.put(outlines, b"<< /Type /Outlines /Count 0 >>")
        self.put(
            pages_ref, f"<< /Type /Pages /Kids [{' '.join(f'{r} 0 R' for r in refs)}] /Count {len(refs)} >>".encode()
        )
        self.put(
            catalog,
            f"<< /Type /Catalog /Pages {pages_ref} 0 R /Outlines {outlines} 0 R /PageMode /UseOutlines >>".encode(),
        )
        info = self.add(b"<< /Title " + pdf_text(title) + b" /Producer (build_screen_catalog.py) >>")

        out = io.BytesIO()
        out.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for number, body in enumerate(self.objects, 1):
            assert body is not None, f"объект {number} не записан"
            offsets.append(out.tell())
            out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
        xref = out.tell()
        out.write(f"xref\n0 {len(self.objects) + 1}\n0000000000 65535 f \n".encode())
        for offset in offsets:
            out.write(f"{offset:010d} 00000 n \n".encode())
        out.write(
            f"trailer\n<< /Size {len(self.objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n".encode()
        )
        return out.getvalue(), heights


# ── проверка готового файла ───────────────────────────────────────────────


def verify(pdf: bytes, expected: int) -> list[str]:
    """Прочитать файл по таблице смещений и проверить каждую страницу.

    Страниц столько, сколько снимков; на каждой ровно одна картинка JPEG;
    картинка целиком ниже полосы заголовка и внутри страницы; весь текст —
    в полосе.
    """
    problems: list[str] = []
    start = int(re.search(rb"startxref\s+(\d+)", pdf[-64:]).group(1))
    table = pdf[start:].split(b"trailer", 1)[0].split(b"\n")
    count = int(table[1].split()[1])
    offsets = {n: int(table[2 + n].split()[0]) for n in range(1, count)}

    def obj(number: int) -> tuple[bytes, bytes]:
        at = offsets[number]
        head_end = pdf.index(b"obj", at) + 3
        stream_at = pdf.find(b"stream\n", head_end)
        end_at = pdf.find(b"endobj", head_end)
        if stream_at == -1 or stream_at > end_at:
            return pdf[head_end:end_at], b""
        head = pdf[head_end:stream_at]
        length = int(re.search(rb"/Length (\d+)", head).group(1))
        data = pdf[stream_at + 7 : stream_at + 7 + length]
        if not pdf[stream_at + 7 + length :].startswith(b"\nendstream"):
            problems.append(f"объект {number}: длина потока не сходится")
        if b"/FlateDecode" in head:
            data = zlib.decompress(data)
        return head, data

    pages = [n for n in offsets if re.search(rb"/Type /Page\b(?!s)", obj(n)[0])]
    if len(pages) != expected:
        problems.append(f"страниц {len(pages)}, снимков {expected}")
    for index, number in enumerate(pages, 1):
        head, _ = obj(number)
        box = [float(v) for v in re.search(rb"/MediaBox \[([^\]]+)\]", head).group(1).split()]
        images = re.findall(rb"/XObject << ((?:/\w+ \d+ 0 R ?)+) >>", head)
        refs = re.findall(rb"/\w+ (\d+) 0 R", images[0]) if images else []
        if len(refs) != 1:
            problems.append(f"страница {index}: картинок {len(refs)}")
            continue
        image_head, image = obj(int(refs[0]))
        if (
            b"/Subtype /Image" not in image_head
            or not image.startswith(b"\xff\xd8")
            or not image.rstrip().endswith(b"\xff\xd9")
        ):
            problems.append(f"страница {index}: картинка пустая или битая")
        content = obj(int(re.search(rb"/Contents (\d+) 0 R", head).group(1)))[1].decode()
        draws = re.findall(r"q ([\d.]+) 0 0 ([\d.]+) ([\d.]+) ([\d.]+) cm /Im0 Do Q", content)
        if len(draws) != 1:
            problems.append(f"страница {index}: картинка нарисована {len(draws)} раз")
            continue
        w, h, x, y = (float(v) for v in draws[0])
        band_y = float(re.search(r"^[\d. ]+ rg 0 ([\d.]+) [\d.]+ [\d.]+ re f", content, re.M).group(1))
        if y + h > band_y + 0.01:
            problems.append(f"страница {index}: снимок заходит на полосу заголовка")
        if x < 0 or y < 0 or x + w > box[2] + 0.01 or y + h > box[3] + 0.01:
            problems.append(f"страница {index}: снимок не вписан в страницу")
        for ty in re.findall(r"Tf [\d.]+ ([\d.]+) Td", content):
            if float(ty) < band_y:
                problems.append(f"страница {index}: текст заголовка ниже полосы")
                break
    return problems


# ── сборка ─────────────────────────────────────────────────────────────────


@dataclass
class Entry:
    """Снимок каталога и всё, что пишется в заголовок и оглавление."""

    number: int
    role: str
    route: str
    url: str
    width: int
    state: str
    kind: str
    png: Path
    title: str = ""
    opener: str = ""
    capped: bool = False
    file: str = ""
    page: int = 0


def load(state: str) -> list[dict]:
    path = SHOTS / state / "catalog.json"
    return json.loads(path.read_text("utf-8")) if path.exists() else []


def jpeg(png: Path) -> tuple[bytes, tuple[int, int]]:
    """Снимок в JPEG: ширина до 1400 точек, качество 75, без прогрессии.

    Сторона JPEG не больше 65 535 точек, а журнал куратора на телефоне
    выходит в 111 000: такой снимок уменьшается целиком, а не режется.
    Телефон снят с плотностью 2; сверхвысокий снимок телефона ложится
    в натуральную величину экрана (390 точек) — текст читается, а весит
    вчетверо меньше: три снимка архива иначе занимали 11 МБ из 20.
    """
    with Image.open(png) as source:
        image = source.convert("RGB")
    scale = min(1.0, MAX_WIDTH / image.width, MAX_SIDE / image.height)
    if image.width <= 2 * 390 and image.height > TALL:
        scale = min(scale, 0.5)
    if scale < 1:
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=QUALITY, optimize=True)
    return out.getvalue(), image.size


def header(entry: Entry) -> list[tuple[str, str, float, tuple[int, int, int]]]:
    """Полоса заголовка: номер, роль, адрес; ширина и школа; окно и кнопка."""
    lines = [
        (f"{entry.number}. {ROLE_TITLES[entry.role]} · {entry.route}", "bold", 13.0, GRAPHITE),
        (
            f"{entry.width} px · школа {STATES[entry.state]} · адрес при съёмке {entry.url}",
            "regular",
            9.5,
            MUTED,
        ),
    ]
    if entry.kind == "окно":
        title = f"«{entry.title}»" if entry.title else "без заголовка"
        lines.append((f"Открытое окно {title} — открыто кнопкой «{entry.opener}»", "regular", 10.5, ACCENT))
    elif entry.kind == "форма":
        lines.append((f"Форма, раскрытая на месте кнопкой «{entry.opener}»", "regular", 10.5, ACCENT))
    if entry.capped:
        lines.append(("Высота окна упёрлась в предел съёмки — низ экрана может быть не виден", "regular", 9.5, ACCENT))
    return lines


def outline(entry: Entry) -> str:
    text = f"{entry.number}. {entry.route} · {entry.width} · {STATES[entry.state]}"
    if entry.kind == "окно":
        text += f" · окно «{entry.title or entry.opener}»"
    elif entry.kind == "форма":
        text += f" · форма «{entry.opener}»"
    return text


def main() -> None:
    routes = read_routes()
    manifests = {state: load(state) for state in STATES}
    if not any(manifests.values()):
        sys.exit(f"нет манифестов каталога в {SHOTS}: сначала съёмка (см. шапку tests/screen-walk.spec.ts)")

    by_key = {
        (row["role"], row["route"], row["width"], state): row for state, rows in manifests.items() for row in rows
    }

    # порядок: роль → ширина → адрес по списку → школа наполненная, пустая → экран, окна
    entries: dict[str, list[Entry]] = {}
    missing: list[tuple[str, str, int, str, str]] = []
    number = 0
    for role, role_routes in routes.items():
        entries[role] = []
        for width in WIDTHS:
            for route in role_routes:
                for state in STATES:
                    row = by_key.get((role, route, width, state))
                    if row is None:
                        reason = (
                            "съёмки этого состояния не было" if not manifests[state] else "адрес не дошёл до съёмки"
                        )
                        missing.append((role, route, width, state, reason))
                        continue
                    if row["error"]:
                        missing.append((role, route, width, state, row["error"]))
                        continue
                    for shot in row["shots"]:
                        png = SHOTS / state / shot["file"]
                        if not png.exists():
                            missing.append((role, route, width, state, f"нет файла снимка {shot['file']}"))
                            continue
                        number += 1
                        # окно упёрлось в предел, но на телефоне страница прокручивается
                        # сама, и снимок во всю страницу забрал низ целиком: обрезан он,
                        # только если картинка не вышла за высоту окна
                        with Image.open(png) as image:
                            css_height = image.height / (2 if width <= 640 else 1)
                        cut = bool(shot.get("capped")) and css_height <= shot["height"] + 1
                        entries[role].append(
                            Entry(
                                number=number,
                                role=role,
                                route=route,
                                url=row["url"],
                                width=width,
                                state=state,
                                kind=shot["kind"],
                                png=png,
                                title=shot.get("title") or "",
                                opener=shot.get("opener") or "",
                                capped=cut,
                            )
                        )

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.pdf"):
        old.unlink()

    problems: list[str] = []
    files: list[tuple[str, int, int]] = []
    cache: dict[Path, tuple[bytes, tuple[int, int]]] = {}

    def write(name: str, title: str, chunk: list[Entry]) -> int:
        fonts = {"regular": Font.load(FONTS["regular"]), "bold": Font.load(FONTS["bold"])}
        pages = []
        for page_no, entry in enumerate(chunk, 1):
            if entry.png not in cache:
                cache[entry.png] = jpeg(entry.png)
            data, pixels = cache[entry.png]
            entry.file, entry.page = name, page_no
            pages.append(Page(entry.number, header(entry), outline(entry), data, pixels))
        pdf, _ = Writer(fonts).build(title, pages)
        (OUT / name).write_bytes(pdf)
        for problem in verify(pdf, len(chunk)):
            problems.append(f"{name}: {problem}")
        return len(pdf)

    for role, chunk in entries.items():
        if not chunk:
            continue
        base = ROLE_FILES[role]
        title = f"Каталог экранов — {ROLE_TITLES[role]}"
        size = write(f"{base}.pdf", title, chunk)
        if size <= LIMIT_BYTES:
            files.append((f"{base}.pdf", len(chunk), size))
            continue
        # роль не влезла — режем по ширинам, ширина не влезла — ещё и по школе
        (OUT / f"{base}.pdf").unlink()
        for width in WIDTHS:
            part = [e for e in chunk if e.width == width]
            if not part:
                continue
            name = f"{base}-{width}.pdf"
            size = write(name, f"{title}, {width} px", part)
            if size <= LIMIT_BYTES:
                files.append((name, len(part), size))
                continue
            (OUT / name).unlink()
            for state, state_title in STATES.items():
                piece = [e for e in part if e.state == state]
                if not piece:
                    continue
                name = f"{base}-{width}-{STATE_FILES[state]}.pdf"
                size = write(name, f"{title}, {width} px, школа {state_title}", piece)
                files.append((name, len(piece), size))
                if size > LIMIT_BYTES:
                    problems.append(f"{name}: {size / 1048576:.1f} МБ — больше 20 МБ и после разреза")

    # ── оглавление ──
    all_entries = [e for chunk in entries.values() for e in chunk]
    shot_keys = {(e.role, e.route) for e in all_entries}
    total_routes = sum(len(v) for v in routes.values())
    variants = {(r, u): 0 for r, us in routes.items() for u in us}
    for e in all_entries:
        if e.kind == "экран":
            variants[(e.role, e.route)] += 1
    full = sum(1 for n in variants.values() if n == len(WIDTHS) * len(STATES))
    partial = sum(1 for n in variants.values() if 0 < n < len(WIDTHS) * len(STATES))
    none = sum(1 for n in variants.values() if n == 0)

    lines = [
        "# Каталог экранов",
        "",
        "Все адреса из `e2e/helpers/routes.ts` под своей ролью: ширины 1440 и 390,",
        "школа наполненная (обычный посев) и пустая (заведён один ученик). Экран снят",
        "целиком, за ним — открытые формы и окна. Одна страница — один снимок, заголовок",
        "над снимком. Собрано `e2e/build_screen_catalog.py` из снимков",
        "`e2e/shots/catalog/<состояние>/`.",
        "",
        "## Файлы",
        "",
        "| Файл | Страниц | Размер |",
        "| --- | --- | --- |",
    ]
    for name, count, size in files:
        lines.append(f"| `{name}` | {count} | {size / 1048576:.1f} МБ |")
    lines += [
        "",
        "## Страницы",
        "",
        "| № | Роль | Адрес | Ширина | Состояние | Снимок | Файл | Страница |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for role, role_routes in routes.items():
        for route in role_routes:
            rows = [e for e in entries.get(role, []) if e.route == route]
            rows.sort(key=lambda e: e.number)
            for e in rows:
                what = {
                    "экран": "экран",
                    "окно": f"окно «{e.title or '—'}» ← «{e.opener}»",
                    "форма": f"форма ← «{e.opener}»",
                }[e.kind]
                lines.append(
                    f"| {e.number} | {ROLE_TITLES[role]} | `{route}` | {e.width} | {STATES[e.state]} | "
                    f"{what.replace('|', '/')} | `{e.file}` | {e.page} |"
                )
            for m_role, m_route, width, state, reason in missing:
                if (m_role, m_route) == (role, route):
                    lines.append(
                        f"| — | {ROLE_TITLES[role]} | `{route}` | {width} | {STATES[state]} | "
                        f"не снялся: {reason.replace('|', '/')} | — | — |"
                    )

    reasons: dict[str, int] = {}
    for *_, reason in missing:
        reasons[reason] = reasons.get(reason, 0) + 1
    kinds = {k: sum(1 for e in all_entries if e.kind == k) for k in ("экран", "окно", "форма")}
    lines += [
        "",
        f"Адресов в списке: {total_routes}. Сняты во всех четырёх вариантах (две ширины × две школы): "
        f"{full}; частично: {partial}; не сняты вовсе: {none}. "
        f"Вариантов, которые не снялись: {len(missing)}"
        + (": " + "; ".join(f"{r} — {n}" for r, n in sorted(reasons.items(), key=lambda x: -x[1])) if missing else "")
        + ". "
        f"Страниц всего: {len(all_entries)} — экранов {kinds['экран']}, окон {kinds['окно']}, форм {kinds['форма']}.",
        "",
    ]
    index = "\n".join(lines)
    (OUT / "index.md").write_text(index, "utf-8")

    # каждый адрес из списка — в оглавлении: снимком или строкой с причиной
    for role, role_routes in routes.items():
        for route in role_routes:
            if (role, route) not in shot_keys and not any((r, u) == (role, route) for r, u, *_ in missing):
                problems.append(f"адреса {role} {route} нет в оглавлении")
            if f"| {ROLE_TITLES[role]} | `{route}` |" not in index:
                problems.append(f"адреса {role} {route} нет в таблице index.md")
    if any(p.stat().st_size == 0 for p in OUT.glob("*.pdf")):
        problems.append("есть пустой файл PDF")

    for name, count, size in files:
        print(f"{name}: страниц {count}, {size / 1048576:.1f} МБ")
    print(f"адресов {total_routes}, страниц {len(all_entries)}, не снялось вариантов {len(missing)}")
    if problems:
        print("ПРОВЕРКА НЕ ПРОШЛА:")
        for problem in problems:
            print(" -", problem)
        sys.exit(1)
    print(
        "проверка: страниц столько же, сколько снимков; пустых страниц нет; "
        "заголовки над снимками; все адреса в оглавлении"
    )


if __name__ == "__main__":
    main()
