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

#: Сигнатуры разрешённых форматов: первые байты → (тип, расширение).
#: JPEG и PNG начинаются жёстко, PDF — с «%PDF-».
SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
)

HUMAN_FORMATS = "PDF, JPG или PNG"


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
        "formats": HUMAN_FORMATS,
        "hint": (
            f"{HUMAN_FORMATS}, до {int(getattr(settings, 'MATERIAL_MAX_FILE_MB', 15))} МБ на файл, "
            f"не больше {max_files()} файлов в материале"
        ),
    }


def _megabytes(value: int) -> str:
    return f"{value / (1024 * 1024):.1f}".replace(".0", "")


def inspect(upload) -> Inspected:
    """Прочитать файл и убедиться, что он такой, каким назвался."""
    size = getattr(upload, "size", 0) or 0
    if size == 0:
        raise FileRejected(f"Файл «{upload.name}» пустой — проверьте, что выгрузилось")
    if size > max_file_bytes():
        raise FileRejected(
            f"Файл «{upload.name}» весит {_megabytes(size)} МБ, "
            f"а можно до {int(getattr(settings, 'MATERIAL_MAX_FILE_MB', 15))} МБ. "
            f"Сожмите его или разбейте на части"
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
        f"«{upload.name}» не похож на {HUMAN_FORMATS}: имя файла ни о чём не говорит, "
        f"а внутри оказалось что-то другое. Пересохраните файл в нужном формате"
    )


def check_count(existing: int, adding: int) -> None:
    """Не больше `MATERIAL_MAX_FILES` файлов в одном материале."""
    total = existing + adding
    if total > max_files():
        raise FileRejected(
            f"В материале уже {existing} файлов, добавляете ещё {adding} — "
            f"вместе больше {max_files()}. Уберите лишние или заведите второй материал"
        )
