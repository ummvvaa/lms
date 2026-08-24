"""Закрытое хранилище файлов материалов.

Файлы лежат вне корня веб-сервера: `/media/` nginx отдаёт напрямую,
и всё, что туда попало, скачивается по угаданной ссылке кем угодно.
Материалы олимпиадников так отдавать нельзя — их видит только
олимпиадная группа, а до одобрения только автор и Арман.

Отдаёт файл единственная вьюха `materials.views.download`, и только
после проверки прав.
"""

from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    """Хранилище без публичного адреса.

    `url()` намеренно падает: у обычного `FileSystemStorage` пустой
    `base_url` молча подставляет `MEDIA_URL`, и ссылка на закрытый файл
    попала бы в ответ API вместе с сериализатором по умолчанию.
    Отдаёт файл только `materials.views.download`.
    """

    def url(self, name):
        raise ValueError(
            "У файла материала нет прямой ссылки: он отдаётся только через проверку прав "
            "(`/api/materials/files/<id>/`)"
        )


def private_storage() -> PrivateStorage:
    """Хранилище, до которого веб-сервер не дотягивается."""
    return PrivateStorage(location=str(settings.PRIVATE_MEDIA_ROOT))
