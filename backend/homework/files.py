"""Файлы сдачи ДЗ: тип по первым байтам, пределы, вид для просмотра.

Сдавать можно файлы любых типов (решение владельца, 30.09.2026): PDF, Word,
Excel, PowerPoint, фото, аудио, видео, архивы. Имени и расширению верить
нельзя — тип определяется по первым байтам, как у материалов
(`materials.files.inspect`). Опознанный тип даёт вид для просмотра в LMS:
PDF и фото — постранично, звук и видео — плеером; остальное скачивается.
Исполняемые файлы (программы Windows, Linux, macOS) не принимаются: школе
их хранить незачем, а открыть такой файл учитель может по ошибке.

Пределы — настройки школы (`core.school_rules`): файл, видео, число файлов.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext as _

from core.phrasing import tn
from homework.models import FileKind

#: сколько первых байтов нужно, чтобы узнать тип
HEAD_BYTES = 64


class FileRejected(ValueError):
    """Файл не подходит. Текст пригоден для показа человеку."""


@dataclass(frozen=True)
class Sniffed:
    content_type: str
    kind: str


#: исполняемые файлы — не принимаются ни под каким именем
EXECUTABLE = (
    b"MZ",  # Windows: exe, dll
    b"\x7fELF",  # Linux
    b"\xca\xfe\xba\xbe",  # macOS, универсальный
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
)


def sniff(head: bytes) -> Sniffed:
    """Тип файла по первым байтам. Неизвестное — «файл», скачивается как есть."""
    if not head:
        raise FileRejected(_("Файл пустой — проверьте, что выгрузилось"))
    if any(head.startswith(prefix) for prefix in EXECUTABLE):
        raise FileRejected(_("Программы не принимаются: сдайте работу документом, фото, звуком или видео"))
    if head.startswith(b"%PDF-"):
        return Sniffed("application/pdf", FileKind.PDF)
    if head.startswith(b"\xff\xd8\xff"):
        return Sniffed("image/jpeg", FileKind.IMAGE)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Sniffed("image/png", FileKind.IMAGE)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return Sniffed("image/gif", FileKind.IMAGE)
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return Sniffed("image/webp", FileKind.IMAGE)
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return Sniffed("audio/wav", FileKind.AUDIO)
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"):
            # HEIC и HEIF (в том числе серии и видеокадры с iPhone) браузеры
            # не показывают — скачивается; камера через сайт обычно отдаёт JPEG
            return Sniffed("image/heic", FileKind.OTHER)
        if brand in (b"M4A ", b"M4B "):
            return Sniffed("audio/mp4", FileKind.AUDIO)
        if brand == b"qt  ":
            return Sniffed("video/quicktime", FileKind.VIDEO)
        return Sniffed("video/mp4", FileKind.VIDEO)
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        # WebM: запись звука в Chrome и видео — вид уточняет имя файла
        return Sniffed("video/webm", FileKind.VIDEO)
    if head.startswith(b"OggS"):
        return Sniffed("audio/ogg", FileKind.AUDIO)
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return Sniffed("audio/mpeg", FileKind.AUDIO)
    if head.startswith(b"PK\x03\x04"):
        # docx, xlsx, pptx и zip — один формат снаружи; скачивается
        return Sniffed("application/zip", FileKind.OTHER)
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return Sniffed("application/msword", FileKind.OTHER)
    return Sniffed("application/octet-stream", FileKind.OTHER)


#: тип для отдачи по расширению — только у контейнеров, которые снаружи одинаковы
OFFICE_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
    ".ppt": "application/vnd.ms-powerpoint",
}


def refine(found: Sniffed, name: str) -> Sniffed:
    """Уточнить тип по имени там, где байты одинаковы: docx и zip, webm-звук и webm-видео."""
    lower = name.lower()
    extension = lower[lower.rfind(".") :] if "." in lower else ""
    if found.content_type in ("application/zip", "application/msword") and extension in OFFICE_TYPES:
        return Sniffed(OFFICE_TYPES[extension], FileKind.OTHER)
    # запись звука в браузере экран называет «audio-…»: Chrome пишет WebM,
    # Safari — MP4, снаружи оба как видео
    if found.content_type == "video/webm" and (extension in (".weba", ".opus") or lower.startswith("audio")):
        return Sniffed("audio/webm", FileKind.AUDIO)
    if found.content_type == "video/mp4" and (extension == ".m4a" or lower.startswith("audio")):
        return Sniffed("audio/mp4", FileKind.AUDIO)
    return found


def limits() -> dict:
    """Пределы для экрана — теми же числами, что проверка.

    Без бакета файл идёт на диск сервера с пределом материалов (15 МБ):
    экран говорит действующий предел, а не «видео до 500 МБ», которое
    хранилище тут же отобьёт (06.10.2026).
    """
    from core import school_rules
    from homework import storage

    values = school_rules.values()
    file_mb = values[school_rules.HOMEWORK_FILE_MB]
    video_mb = values[school_rules.HOMEWORK_VIDEO_MB]
    if not storage.configured():
        local_mb = max(1, storage.LocalStorage().max_bytes() // (1024 * 1024))
        file_mb, video_mb = min(file_mb, local_mb), min(video_mb, local_mb)
    return {"file_mb": file_mb, "video_mb": video_mb, "max_files": values[school_rules.HOMEWORK_MAX_FILES]}


def check_size(name: str, size: int, content_type: str) -> None:
    """Размер файла против пределов школы; видео — по своему пределу."""
    if size <= 0:
        raise FileRejected(_("Файл «{name}» пустой — проверьте, что выгрузилось").format(name=name))
    caps = limits()
    video = content_type.startswith("video/")
    cap = caps["video_mb"] if video else caps["file_mb"]
    if size > cap * 1024 * 1024:
        template = (
            _("Видео «{name}» весит {size} МБ, а можно до {cap} МБ — сожмите или разбейте на части")
            if video
            else _("Файл «{name}» весит {size} МБ, а можно до {cap} МБ — сожмите или разбейте на части")
        )
        raise FileRejected(template.format(name=name, size=f"{size / 1024 / 1024:.1f}", cap=cap))


def check_count(existing: int, adding: int = 1) -> None:
    cap = limits()["max_files"]
    if existing + adding > cap:
        raise FileRejected(
            tn(
                existing,
                "В работе уже {n} файл — больше {cap} не прикладывается|"
                "В работе уже {n} файла — больше {cap} не прикладывается|"
                "В работе уже {n} файлов — больше {cap} не прикладывается",
                cap=cap,
            )
        )
