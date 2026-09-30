"""Проверка хранилища файлов ДЗ: загрузка, скачивание, Range, удаление, CORS.

Проверяет ровно то, чем пользуется экран: маленький файл уходит по подписанной
ссылке, скачивается по подписанной ссылке целиком и куском (перемотка видео),
удаляется; предварительный запрос CORS с адреса школы получает разрешение
на PUT и GET и видит заголовок ETag (без него не собрать загрузку по частям).
`--multipart` — ещё загрузка из двух частей (5 МБ и хвост).

    manage.py check_storage [--origin https://<домен школы>] [--multipart]

Печатает «ок / не ок» по шагам; ничего, кроме своего пробного объекта, не трогает.
"""

from __future__ import annotations

import os

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from homework.storage import S3Storage, backend, configured, new_key


class Command(BaseCommand):
    help = "Проверить хранилище файлов ДЗ: подписанные ссылки, Range, удаление, CORS"

    def add_arguments(self, parser):
        origins = [o for o in getattr(settings, "CSRF_TRUSTED_ORIGINS", []) if o.startswith("https://")]
        parser.add_argument("--origin", default=origins[0] if origins else "", help="адрес сайта школы для CORS")
        parser.add_argument("--multipart", action="store_true", help="проверить и загрузку по частям")

    def step(self, ok: bool, text: str) -> bool:
        self.stdout.write(f"{'ок   ' if ok else 'не ок'}  {text}")
        self.failed = self.failed or not ok
        return ok

    def handle(self, *args, origin: str, multipart: bool, **options):
        self.failed = False
        if not configured():
            self.stdout.write("Хранилище не настроено (HOMEWORK_S3_*): файлы ДЗ лягут на локальный диск сервера")
            self.stdout.write("Для боя задайте бакет и ключ в deploy/.env.prod — docs/DEPLOY.md")
            return
        store: S3Storage = backend()  # type: ignore[assignment]
        self.stdout.write(
            f"Бакет {store.bucket} · {settings.HOMEWORK_S3['ENDPOINT']} · {settings.HOMEWORK_S3['REGION']}"
        )
        key = new_key("check")
        payload = b"%PDF-1.4\n" + os.urandom(1024)
        try:
            plan = store.start_upload(key, len(payload))
            put = requests.put(plan["url"], data=payload, timeout=30)
            self.step(put.status_code == 200, f"загрузка по подписанной ссылке: HTTP {put.status_code}")
            self.step(store.size(key) == len(payload), "размер на месте")
            self.step(store.head(key, 5) == b"%PDF-", "первые байты читаются (проверка типа)")
            link = store.link(key, name="проверка.pdf", content_type="application/pdf", inline=True)
            got = requests.get(link, timeout=30)
            self.step(got.status_code == 200 and got.content == payload, f"скачивание: HTTP {got.status_code}")
            part = requests.get(link, headers={"Range": "bytes=0-4"}, timeout=30)
            self.step(
                part.status_code == 206 and part.content == b"%PDF-", f"Range (перемотка): HTTP {part.status_code}"
            )
            if origin:
                self.cors(store, key, origin)
            else:
                self.step(False, "CORS не проверен: задайте --origin https://<домен школы>")
            if multipart:
                self.multipart(store)
        finally:
            store.delete(key)
        self.step(store.size(key) == 0, "пробный объект удалён")
        self.stdout.write("Итог: " + ("не ок" if self.failed else "ок"))

    def cors(self, store: S3Storage, key: str, origin: str) -> None:
        put_url = store.start_upload(new_key("check"), 10)["url"]
        answer = requests.options(
            put_url,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type",
            },
            timeout=30,
        )
        allowed = answer.headers.get("Access-Control-Allow-Origin", "")
        self.step(
            answer.status_code == 200 and allowed in (origin, "*"),
            f"CORS PUT с {origin}: HTTP {answer.status_code}, разрешён «{allowed}»",
        )
        link = store.link(key, name="проверка.pdf", content_type="application/pdf", inline=True)
        got = requests.get(link, headers={"Origin": origin, "Range": "bytes=0-4"}, timeout=30)
        exposed = got.headers.get("Access-Control-Expose-Headers", "").lower()
        self.step(got.headers.get("Access-Control-Allow-Origin", "") in (origin, "*"), f"CORS GET с {origin}: разрешён")
        self.step("etag" in exposed, f"CORS показывает ETag (нужен загрузке по частям): «{exposed}»")

    def multipart(self, store: S3Storage) -> None:
        from homework import storage as module

        key = new_key("check")
        size = module.PART_SIZE + 1024
        body = os.urandom(size)
        saved = module.SINGLE_MAX
        module.SINGLE_MAX = 0  # заставить разбить на части
        try:
            plan = store.start_upload(key, size)
            parts = []
            for part in plan["parts"]:
                start = (part["number"] - 1) * plan["part_size"]
                answer = requests.put(part["url"], data=body[start : start + plan["part_size"]], timeout=120)
                parts.append({"number": part["number"], "etag": answer.headers.get("ETag", "")})
            store.complete(key, plan["upload_id"], parts)
            self.step(store.size(key) == size, f"загрузка по частям: {len(parts)} части собраны")
        except Exception as error:
            self.step(False, f"загрузка по частям: {error}")
            store.abort(key, plan.get("upload_id", "") if "plan" in locals() else "")
        finally:
            module.SINGLE_MAX = saved
            store.delete(key)
