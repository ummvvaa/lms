"""Хранилище файлов ДЗ: Yandex Object Storage в регионе Казахстан или локальный диск.

Бой — отдельный закрытый бакет в регионе kz (данные не покидают Казахстан),
свой сервисный аккаунт с доступом только к нему (`docs/DEPLOY.md`). Файл идёт
с устройства прямо в бакет по подписанной ссылке, мимо сервера: большой файл —
по частям. Отдаётся тоже короткой подписанной ссылкой и только после проверки
прав (`homework.views`); перемотка видео работает — бакет отвечает на Range.

Хранилище не настроено (разработка) — локальный диск в `PRIVATE_MEDIA_ROOT`
через те же подписанные адреса, но на сервер и одним куском; предел — как
у материалов (настройка школы «Предел файла материала»).

Настройки — окружение: `HOMEWORK_S3_BUCKET`, `HOMEWORK_S3_ENDPOINT`,
`HOMEWORK_S3_REGION`, `HOMEWORK_S3_ACCESS_KEY`, `HOMEWORK_S3_SECRET_KEY`.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.utils.translation import gettext as _

#: сколько живёт ссылка на скачивание и на загрузку
LINK_SECONDS = 5 * 60
UPLOAD_SECONDS = 60 * 60
#: до этого размера — одним куском, больше — по частям
SINGLE_MAX = 64 * 1024 * 1024
PART_SIZE = 16 * 1024 * 1024

LOCAL_SALT = "homework.local"


class StorageError(RuntimeError):
    """Хранилище не ответило как надо. Текст пригоден для показа человеку."""


def new_key(prefix: str) -> str:
    """Ключ объекта без имени человека: имя файла и ученика знает только база."""
    return f"homework/{prefix}/{uuid.uuid4().hex}"


class LocalStorage:
    """Диск сервера: разработка и хранилище, которое ещё не настроили."""

    name = "local"
    direct = False

    def __init__(self) -> None:
        self.root = Path(settings.PRIVATE_MEDIA_ROOT)

    def path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if self.root.resolve() not in target.parents:
            raise StorageError(_("Неверный ключ файла"))
        return target

    def max_bytes(self) -> int:
        from materials.files import max_file_bytes

        return max_file_bytes()

    def _token(self, key: str, action: str) -> str:
        return signing.dumps({"k": key, "a": action}, salt=LOCAL_SALT)

    @staticmethod
    def read_token(token: str, action: str, max_age: int) -> str:
        data = signing.loads(token, salt=LOCAL_SALT, max_age=max_age)
        if data.get("a") != action:
            raise signing.BadSignature("не то действие")  # i18n-skip: внутренняя ошибка подписи, людям не показывается
        return data["k"]

    def start_upload(self, key: str, size: int) -> dict:
        if size > self.max_bytes():
            mb = self.max_bytes() // (1024 * 1024)
            raise StorageError(_("Хранилище не настроено: без него файл до {limit} МБ").format(limit=mb))
        return {"method": "single", "url": f"/api/homework/local/{self._token(key, 'put')}/", "upload_id": ""}

    def complete(self, key: str, upload_id: str, parts: list[dict]) -> None:
        return None

    def abort(self, key: str, upload_id: str) -> None:
        self.delete(key)

    def size(self, key: str) -> int:
        target = self.path(key)
        return target.stat().st_size if target.is_file() else 0

    def head(self, key: str, count: int) -> bytes:
        target = self.path(key)
        if not target.is_file():
            return b""
        with target.open("rb") as handle:
            return handle.read(count)

    def write(self, key: str, chunks) -> int:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with target.open("wb") as handle:
            for chunk in chunks:
                written += len(chunk)
                if written > self.max_bytes():
                    handle.close()
                    target.unlink(missing_ok=True)
                    raise StorageError(_("Файл больше предела"))
                handle.write(chunk)
        return written

    def link(self, key: str, *, name: str, content_type: str, inline: bool) -> str:
        token = signing.dumps({"k": key, "a": "get", "n": name, "t": content_type, "i": inline}, salt=LOCAL_SALT)
        return f"/api/homework/local/{token}/"

    def open(self, key: str):
        return self.path(key).open("rb")

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


class S3Storage:
    """Yandex Object Storage по протоколу S3: подписанные ссылки, загрузка по частям."""

    name = "s3"
    direct = True

    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = settings.HOMEWORK_S3["BUCKET"]
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.HOMEWORK_S3["ENDPOINT"],
            region_name=settings.HOMEWORK_S3["REGION"],
            aws_access_key_id=settings.HOMEWORK_S3["ACCESS_KEY"],
            aws_secret_access_key=settings.HOMEWORK_S3["SECRET_KEY"],
            # регион Казахстана — только kz1 и подпись v4; контрольные суммы —
            # только где их требует протокол: принимает ли их Яндекс, не сказано
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def max_bytes(self) -> int:
        return 5 * 1024 * 1024 * 1024

    def start_upload(self, key: str, size: int) -> dict:
        if size <= SINGLE_MAX:
            url = self.client.generate_presigned_url(
                "put_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=UPLOAD_SECONDS
            )
            return {"method": "single", "url": url, "upload_id": ""}
        created = self.client.create_multipart_upload(Bucket=self.bucket, Key=key)
        upload_id = created["UploadId"]
        count = -(-size // PART_SIZE)
        parts = [
            {
                "number": number,
                "url": self.client.generate_presigned_url(
                    "upload_part",
                    Params={"Bucket": self.bucket, "Key": key, "UploadId": upload_id, "PartNumber": number},
                    ExpiresIn=UPLOAD_SECONDS,
                ),
            }
            for number in range(1, count + 1)
        ]
        return {"method": "multipart", "upload_id": upload_id, "part_size": PART_SIZE, "parts": parts}

    def complete(self, key: str, upload_id: str, parts: list[dict]) -> None:
        if not upload_id:
            return
        ordered = sorted(
            ({"PartNumber": int(p["number"]), "ETag": str(p["etag"])} for p in parts), key=lambda p: p["PartNumber"]
        )
        if not ordered:
            raise StorageError(_("Загрузка по частям пришла без частей"))
        self.client.complete_multipart_upload(
            Bucket=self.bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": ordered}
        )

    def abort(self, key: str, upload_id: str) -> None:
        if upload_id:
            try:
                self.client.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
            except Exception:  # уже завершена или отменена — не повод падать
                pass
        self.delete(key)

    def size(self, key: str) -> int:
        try:
            return int(self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"])
        except Exception:
            return 0

    def head(self, key: str, count: int) -> bytes:
        try:
            answer = self.client.get_object(Bucket=self.bucket, Key=key, Range=f"bytes=0-{count - 1}")
        except Exception:
            return b""
        return answer["Body"].read()

    def link(self, key: str, *, name: str, content_type: str, inline: bool) -> str:
        from core.exports import _disposition

        disposition = _disposition(name, content_type)
        if inline:
            disposition = disposition.replace("attachment", "inline", 1)
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": disposition,
                "ResponseContentType": content_type or "application/octet-stream",
            },
            ExpiresIn=LINK_SECONDS,
        )

    def open(self, key: str):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def write(self, key: str, chunks) -> int:
        data = b"".join(chunks)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return len(data)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def configured() -> bool:
    conf = getattr(settings, "HOMEWORK_S3", {}) or {}
    return all(conf.get(name) for name in ("BUCKET", "ENDPOINT", "ACCESS_KEY", "SECRET_KEY"))


def backend() -> LocalStorage | S3Storage:
    """Хранилище по настройкам: бакет задан — он, иначе локальный диск."""
    return S3Storage() if configured() else LocalStorage()
