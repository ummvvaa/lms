"""Проверка загружаемых файлов: тип по содержимому, размер, количество.

Расширению верить нельзя: `.pdf` дописывается к чему угодно за секунду.
Смотрим первые байты — по ним видно, что это на самом деле. Файл, который
не опознался, не принимается: хранить у школы неизвестно что не надо.

Пределы задаются настройками, чтобы школа меняла их без выката.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.conf import settings
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.phrasing import tn

#: Сигнатуры разрешённых форматов: первые байты → (тип, расширение).
#: JPEG и PNG начинаются жёстко, PDF — с «%PDF-».
SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
)

HUMAN_FORMATS = gettext_lazy("PDF, JPG или PNG")


class FileRejected(ValueError):
    """Файл не подходит. Текст пригоден для показа человеку."""


@dataclass(frozen=True)
class Inspected:
    """Что мы поняли про файл: настоящий тип, размер, контрольная сумма."""

    content_type: str
    extension: str
    size: int
    checksum: str


def max_file_bytes() -> int:
    return int(getattr(settings, "MATERIAL_MAX_FILE_MB", 15)) * 1024 * 1024


def max_files() -> int:
    return int(getattr(settings, "MATERIAL_MAX_FILES", 10))


def limits() -> dict:
    """Пределы для подсказки в интерфейсе — теми же числами, что проверка."""
    return {
        "max_file_mb": int(getattr(settings, "MATERIAL_MAX_FILE_MB", 15)),
        "max_files": max_files(),
        "formats": str(HUMAN_FORMATS),
        "hint": tn(
            max_files(),
            "{formats}, до {size} МБ на файл, не больше {n} файла в материале|"
            "{formats}, до {size} МБ на файл, не больше {n} файлов в материале|"
            "{formats}, до {size} МБ на файл, не больше {n} файлов в материале",
            formats=HUMAN_FORMATS,
            size=int(getattr(settings, "MATERIAL_MAX_FILE_MB", 15)),
        ),
    }


def _megabytes(value: int) -> str:
    return f"{value / (1024 * 1024):.1f}".replace(".0", "")


def inspect(upload) -> Inspected:
    """Прочитать файл и убедиться, что он такой, каким назвался."""
    size = getattr(upload, "size", 0) or 0
    if size == 0:
        raise FileRejected(_("Файл «{name}» пустой — проверьте, что выгрузилось").format(name=upload.name))
    if size > max_file_bytes():
        raise FileRejected(
            _("Файл «{name}» весит {size} МБ, а можно до {limit} МБ. Сожмите его или разбейте на части").format(
                name=upload.name, size=_megabytes(size), limit=int(getattr(settings, "MATERIAL_MAX_FILE_MB", 15))
            )
        )

    digest = hashlib.sha256()
    head = b""
    upload.seek(0)
    for chunk in upload.chunks():
        if not head:
            head = chunk[:16]
        digest.update(chunk)
    upload.seek(0)

    for prefix, content_type, extension in SIGNATURES:
        if head.startswith(prefix):
            return Inspected(content_type=content_type, extension=extension, size=size, checksum=digest.hexdigest())

    raise FileRejected(
        _(
            "«{name}» не похож на {formats}: имя файла ни о чём не говорит, "
            "а внутри оказалось что-то другое. Пересохраните файл в нужном формате"
        ).format(name=upload.name, formats=HUMAN_FORMATS)
    )


def check_count(existing: int, adding: int) -> None:
    """Не больше `MATERIAL_MAX_FILES` файлов в одном материале."""
    total = existing + adding
    if total > max_files():
        raise FileRejected(
            tn(
                existing,
                "В материале уже {n} файл, добавляете ещё {adding} — вместе больше {limit}. "
                "Уберите лишние или заведите второй материал|"
                "В материале уже {n} файла, добавляете ещё {adding} — вместе больше {limit}. "
                "Уберите лишние или заведите второй материал|"
                "В материале уже {n} файлов, добавляете ещё {adding} — вместе больше {limit}. "
                "Уберите лишние или заведите второй материал",
                adding=adding,
                limit=max_files(),
            )
        )
