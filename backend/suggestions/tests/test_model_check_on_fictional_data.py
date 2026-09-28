"""Картинка для модели, пустые ответы и проверка `check_llm` без живых учеников.

Настоящего провайдера нет — подменяется HTTP-слой, как в
`test_openai_provider.py`. Проверяем три вещи, сломавшиеся на проде:

1. картинка уходит в Responses API настоящей: тип — по байтам, data-URL
   раскрывается обратно в тот же файл, битый файл до модели не доходит;
2. пустой ответ рассуждающей модели — отказ с причиной, а операция,
   которой нечего спросить, не пишет «модель не ответила»;
3. `check_llm` гоняет модель только на своём вымышленном ученике и стирает
   за собой всё, что завела.
"""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from io import BytesIO, StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from PIL import Image, ImageDraw

from accounts.models import Role
from suggestions.llm import NOT_AN_IMAGE, InvalidImage, image_from_bytes
from suggestions.providers import OpenAIProvider

LIVE = {
    "PROVIDER": "openai",
    "API_KEY": "test-key",
    "BASE_URL": "https://api.example",
    "MODEL": "gpt-6-sol",
    "TIMEOUT": 5,
    "RETRIES": 0,
    "RETRY_DELAY": 0,
    "NO_RETENTION": True,
    "SEARCH": True,
    "SEARCH_MAX_USES": 5,
    "REASONING_EFFORT": "low",
    "REASONING_RESERVE": 25000,
}

#: PNG из прежней `check_llm`: контрольная сумма блока IDAT не сходится,
#: конец файла сдвинут. Провайдер отвечал на него 400 «not a valid image»
BROKEN_PIXEL = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000100ffff03000006000557bfabd4"
    "0000000049454e44ae426082"
)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload, self.status_code, self.headers = payload, status_code, {}

    def json(self) -> dict:
        return self.payload


def reply(text: str, *, status: str = "completed", reason: str = "") -> dict:
    """Ответ в том виде, в каком его отдаёт Responses API."""
    body = {
        "id": "resp_1",
        "model": "gpt-6-sol",
        "status": status,
        "output": [
            {"type": "reasoning", "id": "rs_1", "summary": []},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": 900, "output_tokens": 300, "output_tokens_details": {"reasoning_tokens": 300}},
    }
    if not text:
        body["output"] = body["output"][:1]
    if reason:
        body["incomplete_details"] = {"reason": reason}
    return body


@pytest.fixture
def provider(monkeypatch):
    """Подменить HTTP: запомнить каждый запрос и вернуть заготовленный ответ."""
    import requests

    box: dict = {"requests": []}

    def install(payload: dict, status_code: int = 200) -> dict:
        def fake(url, json=None, headers=None, timeout=None):
            box["requests"].append(json)
            return FakeResponse(payload, status_code)

        monkeypatch.setattr(requests, "post", fake)
        return box

    return install


def phone_jpeg() -> bytes:
    """Настоящий JPEG как с телефона: фото-градиент, EXIF, прогрессивная развёртка."""
    image = Image.new("RGB", (800, 600))
    draw = ImageDraw.Draw(image)
    for x in range(0, 800, 4):
        draw.rectangle((x, 0, x + 3, 600), fill=(x % 256, (x * 3) % 256, 200 - x % 200))
    draw.rectangle((100, 250, 700, 350), fill="white")
    exif = Image.Exif()
    exif[0x0112] = 1  # ориентация
    exif[0x010F] = "Phone"  # производитель
    out = BytesIO()
    image.save(out, format="JPEG", quality=85, progressive=True, exif=exif)
    return out.getvalue()


def opened(data_url: str) -> Image.Image:
    """Раскрыть data-URL так, как это делает провайдер."""
    head, _, data = data_url.partition(",")
    assert head.endswith(";base64")
    image = Image.open(BytesIO(base64.b64decode(data)))
    image.load()
    return image


# --- 1. Картинка ----------------------------------------------------------


def test_real_jpeg_goes_as_jpeg_whatever_the_client_said():
    """Тип — по байтам: браузер прислал «image/png», а файл — JPEG."""
    payload = phone_jpeg()
    attachment = image_from_bytes(payload, "image/png")
    assert attachment.media_type == "image/jpeg"
    assert base64.b64decode(attachment.data) == payload, "байты не переписываются"


@override_settings(LLM=LIVE)
def test_real_jpeg_reaches_the_responses_api_as_a_valid_data_url(provider):
    box = provider(reply('{"name": "Городская олимпиада"}'))
    OpenAIProvider().complete(
        system="s", user="что на фото", images=[image_from_bytes(phone_jpeg(), "application/octet-stream")]
    )
    url = box["requests"][0]["input"][0]["content"][0]["image_url"]
    assert url.startswith("data:image/jpeg;base64,")
    image = opened(url)
    assert (image.format, image.size) == ("JPEG", (800, 600))


def test_broken_png_never_reaches_the_model():
    with pytest.raises(InvalidImage, match="не читается"):
        image_from_bytes(BROKEN_PIXEL, "image/png")


@pytest.mark.parametrize("payload", [b"", b"just text, not a picture", phone_jpeg()[:2000]])
def test_empty_text_and_truncated_files_are_refused(payload):
    with pytest.raises(InvalidImage):
        image_from_bytes(payload, "image/jpeg")


def test_check_command_sample_is_a_real_png():
    from suggestions.management.commands.check_llm import sample_png

    attachment = image_from_bytes(sample_png(), "image/png")
    assert attachment.media_type == "image/png"
    assert opened(f"data:image/png;base64,{attachment.data}").format == "PNG"


def test_formats_the_model_does_not_take_go_as_png():
    """BMP и анимированный GIF — первым кадром в PNG, а не отказом провайдера."""
    bmp = BytesIO()
    Image.new("RGB", (20, 10), "red").save(bmp, format="BMP")
    gif = BytesIO()
    frames = [Image.new("RGB", (20, 10), color) for color in ("red", "green")]
    frames[0].save(gif, format="GIF", save_all=True, append_images=frames[1:], duration=200, loop=0)

    for raw in (bmp.getvalue(), gif.getvalue()):
        attachment = image_from_bytes(raw, "image/whatever")
        assert attachment.media_type == "image/png"
        assert opened(f"data:image/png;base64,{attachment.data}").size == (20, 10)


def test_phone_mpo_goes_as_plain_jpeg():
    """Фото с глубиной у телефонов — MPO: модель его не знает, уходит первый кадр."""
    out = BytesIO()
    first, second = Image.new("RGB", (30, 20), "blue"), Image.new("RGB", (30, 20), "green")
    first.save(out, format="MPO", save_all=True, append_images=[second])
    attachment = image_from_bytes(out.getvalue(), "image/jpeg")
    assert attachment.media_type == "image/jpeg"
    assert opened(f"data:image/jpeg;base64,{attachment.data}").format == "JPEG"


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_broken_upload_gets_a_human_answer_not_a_provider_error(provider, make_user):
    from students.models import Student
    from suggestions.tasks import parse_image

    box = provider(reply("{}"))
    sport = make_user(Role.DIRECTOR_SPORT, email="sport.image@example.kz")
    student = Student.objects.create(
        last_name="Картинкин", first_name="Тест", email="img@example.kz", graduation_year=2027
    )
    result = parse_image.delay(
        payload=BROKEN_PIXEL,
        media_type="image/png",
        kind="certificate",
        student_id=student.pk,
        actor_id=sport.pk,
        role=Role.DIRECTOR_SPORT,
    ).get()
    assert result == {"ok": False, "detail": NOT_AN_IMAGE}
    assert box["requests"] == [], "битый файл к провайдеру не уходит"


# --- 2. Пустой ответ и честная подпись -------------------------------------


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_answer_eaten_by_reasoning_is_a_failure_with_the_reason(provider):
    from suggestions.llm import LLMUnavailable, complete
    from suggestions.models import LLMCall

    provider(reply("", status="incomplete", reason="max_output_tokens"))
    with pytest.raises(LLMUnavailable, match="рассуждение"):
        complete(system="s", user="u", purpose="week_changes")
    call = LLMCall.objects.get()
    # деньги за пустой ответ потрачены — в учёте они есть, вызов помечен сбоем
    assert (call.is_ok, call.tokens_out) == (False, 300)
    assert "рассуждение" in call.error


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_operation_with_nothing_to_ask_does_not_blame_the_model(provider, make_user):
    from students.models import Student
    from suggestions import operations

    box = provider(reply("ок"))
    asem = make_user(Role.DIRECTOR_ADMISSION, email="asem.empty@example.kz")
    student = Student.objects.create(
        last_name="Пустов", first_name="Тест", email="empty@example.kz", graduation_year=2027
    )

    for outcome in (
        operations.week_changes(actor=asem, role=Role.DIRECTOR_ADMISSION),
        operations.check_balance(student_id=student.pk, actor=asem, role=Role.DIRECTOR_ADMISSION),
    ):
        payload = outcome.as_dict()
        assert payload["offline"] is True
        assert payload["detail"] == operations.NOT_ASKED
        assert "не ответила" not in payload["detail"]
    assert box["requests"] == [], "модель и не звали"


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_operation_names_the_reason_when_the_model_really_fails(provider, make_user):
    from core.audit import record_change
    from students.models import AdmissionProfile, Student
    from suggestions import operations

    asem = make_user(Role.DIRECTOR_ADMISSION, email="asem.fail@example.kz")
    student = Student.objects.create(
        last_name="Сбоев", first_name="Тест", email="fail@example.kz", graduation_year=2027
    )
    profile = AdmissionProfile.objects.create(student=student, target_country="Канада")
    record_change(instance=profile, field_name="target_country", old_value="", new_value="Канада", actor=asem)

    provider(reply("", status="incomplete", reason="max_output_tokens"))
    payload = operations.week_changes(actor=asem, role=Role.DIRECTOR_ADMISSION).as_dict()
    assert payload["offline"] is True
    assert payload["detail"] == "Собрано правилами: модель вернула пустой ответ: бюджет токенов ушёл на рассуждение"

    provider({"error": {"message": "boom"}}, status_code=500)
    payload = operations.week_changes(actor=asem, role=Role.DIRECTOR_ADMISSION).as_dict()
    assert payload["detail"] == "Собрано правилами: модель не ответила — провайдер вернул 500"


# --- 3. check_llm только на вымышленном ученике -----------------------------


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_check_command_never_sends_a_real_student_and_cleans_up(provider, make_user):
    from core.audit import record_change
    from core.models import AuditLog
    from students.models import AdmissionProfile, ExamProfile, Student
    from suggestions.models import LLMCall, Suggestion
    from universities.models import Program, StudentUniversity, University

    asem = make_user(Role.DIRECTOR_ADMISSION, email="asem.check@example.kz")
    university = University.objects.create(
        name="University of Toronto", country="Канада", website="https://www.utoronto.ca", domain="utoronto.ca"
    )
    program = Program.objects.create(university=university, name="Computer Science", level="bachelor")
    # живой ученик с приметными данными: ни одна из примет не должна уйти в модель
    real = Student.objects.create(
        last_name="Жанабаева", first_name="Настоящая", email="real.pupil@bhs.kz", graduation_year=2027
    )
    ExamProfile.objects.create(student=real, ielts_current=Decimal("8.5"), sat_current=1570)
    admission = AdmissionProfile.objects.create(student=real, target_country="Исландия", target_major="Вулканология")
    StudentUniversity.objects.create(student=real, program=program, tier="safety")
    record_change(instance=admission, field_name="target_major", old_value="", new_value="Вулканология", actor=asem)

    before = (Student.all_objects.count(), AuditLog.objects.count(), Suggestion.objects.count())
    box = provider(reply(json.dumps({"name": "Городская олимпиада", "title": "Собрать письма", "days": 14})))
    out = StringIO()
    call_command("check_llm", stdout=out)

    sent = json.dumps(box["requests"], ensure_ascii=False)
    for mark in ("Жанабаева", "Настоящая", "real.pupil", "Исландия", "Вулканология", "8.5", "1570"):
        assert mark not in sent, f"в модель ушла примета живого ученика: {mark}"
    assert "Жанабаева" not in out.getvalue()

    # модель действительно спрашивали — в том числе о неделе и балансе списка
    purposes = set(LLMCall.objects.values_list("purpose", flat=True))
    assert {"week_changes", "check_balance", "parse_certificate", "digest"} <= purposes

    # картинка ушла настоящим PNG
    images = [
        part["image_url"]
        for request in box["requests"]
        for part in request["input"][0]["content"]
        if part["type"] == "input_image"
    ]
    assert images and opened(images[0]).format == "PNG"

    # за собой убрано всё, кроме учёта денег
    assert (Student.all_objects.count(), AuditLog.objects.count(), Suggestion.objects.count()) == before
    assert not Student.all_objects.filter(is_fictional=True).exists()
    assert Student.objects.filter(pk=real.pk).exists()
