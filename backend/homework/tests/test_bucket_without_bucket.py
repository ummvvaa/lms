"""Бой с бакетом против разработки с диском — что проверяется без бакета (06.10.2026).

Бакета в разработке нет, поэтому клиент S3 здесь подменён: проверяется, что
план загрузки (одним куском до 64 МБ, частями выше), сборка из частей,
ссылки, отличие «объекта нет» от «бакет не ответил» и путь `complete`
ведут себя так, как ждёт экран, — и что сбой хранилища не удаляет
загруженный файл.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from academics.tests.conftest import login
from homework import services
from homework.files import refine, sniff
from homework.models import FileState, HomeworkFile, LatePolicy
from homework.storage import PART_SIZE, SINGLE_MAX, S3Storage, StorageError, backend
from homework.tests.test_homework_submission import PDF, due_in

pytestmark = pytest.mark.django_db

KZ = {
    "BUCKET": "lms-hw",
    "ENDPOINT": "https://storage.yandexcloud.kz",
    "REGION": "kz1",
    "ACCESS_KEY": "k",
    "SECRET_KEY": "s",
}


class S3Error(Exception):
    """Как ошибка botocore: код и статус в `response`."""

    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.response = {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}}


class FakeClient:
    """Бакет в памяти: ровно те вызовы, что делает хранилище."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.multipart: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.down = False

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.calls.append(("presign", operation, Params.get("PartNumber"), ExpiresIn))
        extra = (
            "&response-content-disposition=" + Params["ResponseContentDisposition"]
            if "ResponseContentDisposition" in Params
            else ""
        )
        part = Params.get("PartNumber", "")
        return f"https://storage.yandexcloud.kz/{Params['Bucket']}/{Params['Key']}?op={operation}&part={part}&X-Amz-Expires={ExpiresIn}{extra}"

    def create_multipart_upload(self, Bucket, Key):
        self.multipart[Key] = {"id": "mpu-1", "parts": {}}
        return {"UploadId": "mpu-1"}

    def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload):
        self.calls.append(("complete", Key, UploadId, MultipartUpload["Parts"]))
        if any(not p["ETag"] for p in MultipartUpload["Parts"]):
            raise S3Error("InvalidPart", 400)
        self.objects[Key] = b"".join(
            self.multipart[Key]["parts"].get(p["PartNumber"], b"") for p in MultipartUpload["Parts"]
        )

    def abort_multipart_upload(self, Bucket, Key, UploadId):
        self.calls.append(("abort", Key, UploadId))
        self.multipart.pop(Key, None)

    def head_object(self, Bucket, Key):
        if self.down:
            raise S3Error("AccessDenied", 403)
        if Key not in self.objects:
            raise S3Error("404", 404)
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key, Range=None):
        if self.down:
            raise S3Error("ServiceUnavailable", 503)
        if Key not in self.objects:
            raise S3Error("NoSuchKey", 404)
        data = self.objects[Key]
        if Range:
            end = int(Range.split("-")[1])
            data = data[: end + 1]

        class Body:
            def read(self_inner):
                return data

        return {"Body": Body()}

    def put_object(self, Bucket, Key, Body):
        self.objects[Key] = Body

    def delete_object(self, Bucket, Key):
        self.calls.append(("delete", Key))
        self.objects.pop(Key, None)


@pytest.fixture
def bucket(settings, monkeypatch):
    """Бакет настроен, клиент подменён: `backend()` отдаёт S3Storage поверх FakeClient."""
    settings.HOMEWORK_S3 = KZ
    fake = FakeClient()
    monkeypatch.setattr(
        S3Storage, "__init__", lambda self: setattr(self, "bucket", KZ["BUCKET"]) or setattr(self, "client", fake)
    )
    return fake


@pytest.fixture
def algebra(lesson, teacher):
    services.save_assignment(
        lesson, requires_submission=True, due_at=due_in(24), late_policy=LatePolicy.ACCEPT, actor=teacher
    )
    return services.assignment_of(lesson)


def test_small_file_goes_in_one_piece_and_big_in_parts(bucket):
    store = backend()
    assert isinstance(store, S3Storage) and store.direct
    one = store.start_upload("homework/student/a", SINGLE_MAX)
    assert one["method"] == "single" and "op=put_object" in one["url"]
    many = store.start_upload("homework/student/b", 500 * 1024 * 1024)
    assert many["method"] == "multipart" and many["part_size"] == PART_SIZE
    assert [p["number"] for p in many["parts"]] == list(range(1, 33)), "500 МБ — 32 части по 16 МБ"
    assert all("X-Amz-Expires=3600" in p["url"] for p in many["parts"]), "ссылки на загрузку живут час"


def test_parts_are_assembled_in_order_and_without_etag_refused(bucket):
    store = backend()
    store.start_upload("homework/student/v", 80 * 1024 * 1024)
    bucket.multipart["homework/student/v"]["parts"] = {1: b"a" * 3, 2: b"b" * 2, 3: b"c"}
    store.complete(
        "homework/student/v",
        "mpu-1",
        [{"number": 3, "etag": "e3"}, {"number": 1, "etag": "e1"}, {"number": 2, "etag": "e2"}],
    )
    assert bucket.objects["homework/student/v"] == b"aaabbc", "части собираются по номерам, а не в порядке прихода"
    store.start_upload("homework/student/w", 80 * 1024 * 1024)
    with pytest.raises(StorageError):
        store.complete("homework/student/w", "mpu-1", [])
    with pytest.raises(S3Error):
        store.complete("homework/student/w", "mpu-1", [{"number": 1, "etag": ""}])


def test_missing_object_is_empty_but_storage_failure_is_an_error(bucket):
    store = backend()
    assert store.size("homework/student/none") == 0 and store.head("homework/student/none", 64) == b""
    bucket.objects["homework/student/x"] = PDF
    assert store.size("homework/student/x") == len(PDF) and store.head("homework/student/x", 5) == b"%PDF-"
    bucket.down = True
    with pytest.raises(StorageError):
        store.size("homework/student/x")
    with pytest.raises(StorageError):
        store.head("homework/student/x", 5)


def test_storage_failure_at_complete_keeps_the_file_for_a_retry(bucket, algebra, pupils):
    client = login(pupils["aliya"].user)
    start = client.post(
        "/api/homework/uploads/", {"assignment": algebra.pk, "name": "работа.pdf", "size": len(PDF)}, format="json"
    )
    assert start.status_code == 200, start.content
    plan = start.json()
    assert plan["method"] == "single" and plan["url"].startswith(
        "https://storage.yandexcloud.kz/lms-hw/homework/student/"
    )
    key = HomeworkFile.objects.get(pk=plan["file"]).key
    bucket.objects[key] = PDF  # телефон положил файл прямо в бакет
    bucket.down = True
    refused = client.post(f"/api/homework/files/{plan['file']}/complete/", {"parts": []}, format="json")
    assert refused.status_code == 400 and "не ответило" in refused.json()["detail"]
    assert key in bucket.objects and HomeworkFile.objects.get(pk=plan["file"]).state == FileState.UPLOADING
    assert ("delete", key) not in bucket.calls, "сбой бакета — не повод удалять загруженное"
    bucket.down = False
    done = client.post(f"/api/homework/files/{plan['file']}/complete/", {"parts": []}, format="json")
    assert done.status_code == 200 and done.json()["kind"] == "pdf" and done.json()["size"] == len(PDF)
    link = client.get(f"/api/homework/files/{plan['file']}/link/").json()
    assert "response-content-disposition" in link["url"] and "X-Amz-Expires=300" in link["url"]


def test_lost_object_at_complete_is_an_empty_file(bucket, algebra, pupils):
    client = login(pupils["aliya"].user)
    plan = client.post(
        "/api/homework/uploads/", {"assignment": algebra.pk, "name": "работа.pdf", "size": 10}, format="json"
    ).json()
    done = client.post(f"/api/homework/files/{plan['file']}/complete/", {"parts": []}, format="json")
    assert done.status_code == 400 and "пустой" in done.json()["detail"]
    assert not HomeworkFile.objects.filter(pk=plan["file"]).exists()


def test_heic_and_heif_brands_are_photos_for_download():
    for brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"):
        found = refine(sniff(b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 60), "IMG_0001.HEIC")
        assert (found.content_type, found.kind) == ("image/heic", "other"), brand
    assert refine(sniff(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 60), "IMG_0002.MOV").kind == "video"


@override_settings(HOMEWORK_S3=KZ)
def test_video_limit_applies_on_the_bucket_and_file_limit_on_the_disk(settings, tmp_path):
    from homework.files import limits

    caps = limits()
    assert (
        caps["video_mb"] >= caps["file_mb"] and caps["video_mb"] >= 100
    ), "с бакетом экран обещает настоящие пределы школы"
    settings.HOMEWORK_S3 = {"BUCKET": "", "ENDPOINT": "", "REGION": "", "ACCESS_KEY": "", "SECRET_KEY": ""}
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    local = backend()
    assert not local.direct
    bare = limits()
    local_mb = local.max_bytes() // (1024 * 1024)
    assert (
        bare["file_mb"] == min(caps["file_mb"], local_mb) and bare["video_mb"] == local_mb
    ), "без бакета экран не обещает 500 МБ"
    with pytest.raises(StorageError) as refused:
        local.start_upload("homework/student/v", local.max_bytes() + 1)
    assert "не настроено" in str(refused.value), "без бакета видео в 500 МБ не влезет — экран должен сказать об этом"
