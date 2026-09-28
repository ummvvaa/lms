"""Банк заданий: форма по секции, пассаж, аудио и открытый ответ.

Форма у Кымбат была одна на всё — четыре варианта и верный ответ: для Listening
не было аудио, для Reading — текста, а у Writing и Speaking вариантов не бывает
вовсе. Сервер теперь держит состав задания по секции — то же, что умеет файл
массовой загрузки (`guides/QUESTION_BANK.md`):

* Listening — без аудио не сохраняется; mp3/m4a до 20 МБ; отдаётся после входа;
* Reading — пассаж один, вопросов несколько; в тренировке они приходят вместе;
* Writing, Speaking — без вариантов: задание, критерии, предел; ответ ученика
  открытый, сохраняется и ждёт проверки Кымбат — оценка и комментарий руками;
* SAT и остальное — варианты, как раньше.
"""

# ruff: noqa: F811 — фикстура ученика импортирована по имени
from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from prep import services
from prep.models import PassageKind, PracticeAnswer, Question, QuestionPassage, QuestionType, Section
from prep.tests.test_prep import student  # noqa: F401 — ученик с профилем экзаменов

pytestmark = pytest.mark.django_db

OPTIONS = [
    {"letter": "A", "text": "Первый", "is_correct": False},
    {"letter": "B", "text": "Второй", "is_correct": True},
]


def mp3(name: str = "lecture.mp3", size: int = 2048) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"ID3" + b"\x00" * size, content_type="audio/mpeg")


@pytest.fixture
def kymbat(make_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(make_user("director_exam", "kymbat-bank@example.kz", full_name="Кымбат"))
    return client


def listening_passage(client) -> dict:
    answer = client.post(
        "/api/prep/passages/",
        {"exam_type": "IELTS", "section": "listening", "kind": "listening", "title": "Лекция", "audio": mp3()},
        format="multipart",
    )
    assert answer.status_code == 201, answer.content
    return answer.data


def reading_passage(client) -> dict:
    answer = client.post(
        "/api/prep/passages/",
        {"exam_type": "IELTS", "section": "reading", "kind": "reading", "title": "Bees", "body": "Bees dance."},
        format="json",
    )
    assert answer.status_code == 201, answer.content
    return answer.data


def question(client, **fields):
    body = {"exam_type": "IELTS", "topic": "Тема", "text": "Вопрос?", "difficulty": "medium", **fields}
    return client.post("/api/prep/questions/", body, format="json")


# --- Listening ------------------------------------------------------------------------


def test_listening_is_not_saved_without_audio(kymbat):
    refused = kymbat.post(
        "/api/prep/passages/",
        {"exam_type": "IELTS", "section": "listening", "kind": "listening", "title": "Без звука"},
        format="multipart",
    )
    assert refused.status_code == 400 and "audio" in refused.data
    # и задание на аудирование без источника с аудио — тоже
    no_source = question(kymbat, section="listening", options=OPTIONS)
    assert no_source.status_code == 400 and "аудио" in str(no_source.data["passage"])
    assert not Question.objects.exists() and not QuestionPassage.objects.exists()


@pytest.mark.parametrize(
    ("upload", "word"),
    [(mp3("lecture.wav"), "mp3"), (mp3("big.mp3", size=21 * 1024 * 1024), "20 МБ")],
)
def test_audio_is_mp3_or_m4a_up_to_twenty_megabytes(kymbat, upload, word):
    refused = kymbat.post(
        "/api/prep/passages/",
        {"exam_type": "IELTS", "section": "listening", "kind": "listening", "audio": upload},
        format="multipart",
    )
    assert refused.status_code == 400 and word in str(refused.data["audio"])


def test_listening_with_audio_reaches_the_student_inside_the_practice(kymbat, student, make_user):
    passage = listening_passage(kymbat)
    assert passage["has_audio"] and passage["audio_url"].endswith(f"/prep/passages/{passage['id']}/audio/")
    made = question(kymbat, section="listening", passage=passage["id"], options=OPTIONS)
    assert made.status_code == 201, made.data

    pupil = APIClient()
    pupil.force_authenticate(student.user)
    # вне тренировки аудио ученику не отдаётся — как несуществующее
    assert pupil.get(passage["audio_url"]).status_code == 404

    session = pupil.post("/api/prep/practice/start/", {"exam_type": "IELTS", "section": "listening"}, format="json")
    assert session.status_code == 201, session.data
    source = session.data["passages"][0]
    assert source["kind"] == "listening" and source["audio_url"] == passage["audio_url"]
    assert session.data["questions"][0]["passage"] == passage["id"]
    heard = pupil.get(passage["audio_url"])
    assert heard.status_code == 200 and heard["Content-Type"] == "audio/mpeg"

    # без входа аудио не отдаётся вовсе
    assert APIClient().get(passage["audio_url"]).status_code in (401, 403)


def test_the_transcript_of_the_audio_is_shown_only_in_the_review(kymbat, student):
    passage = listening_passage(kymbat)
    kymbat.patch(f"/api/prep/passages/{passage['id']}/", {"body": "Расшифровка лекции"}, format="json")
    question(kymbat, section="listening", passage=passage["id"], options=OPTIONS)

    session = services.start_practice(student, exam_type="IELTS", section="listening")
    assert services.session_payload(session)["passages"][0]["body"] == ""
    assert services.finish_practice(session)["passages"][0]["body"] == "Расшифровка лекции"


# --- Reading: пассаж и его вопросы ---------------------------------------------------


def test_reading_question_needs_a_passage(kymbat):
    refused = question(kymbat, section="reading", options=OPTIONS)
    assert refused.status_code == 400 and "пассаж" in str(refused.data["passage"])


def test_a_passage_comes_to_the_practice_with_all_its_questions(kymbat, student):
    passage = reading_passage(kymbat)
    for number in range(4):
        made = question(kymbat, section="reading", passage=passage["id"], text=f"Вопрос {number}", options=OPTIONS)
        assert made.status_code == 201, made.data
    assert kymbat.get(f"/api/prep/passages/{passage['id']}/").data["questions_count"] == 4

    # заказали два задания — пассаж всё равно пришёл целиком: половина вопросов
    # к тексту была бы другим текстом
    session = services.start_practice(student, exam_type="IELTS", section="reading", size=2)
    payload = services.session_payload(session)
    assert [item["text"] for item in payload["questions"]] == [f"Вопрос {n}" for n in range(4)]
    assert payload["passages"] == [
        {
            "id": passage["id"],
            "kind": PassageKind.READING,
            "title": "Bees",
            "body": "Bees dance.",
            "audio_url": "",
            "audio_start": None,
            "audio_end": None,
        }
    ]


def test_a_source_of_another_section_is_refused(kymbat):
    passage = reading_passage(kymbat)
    refused = question(kymbat, section="math", exam_type="SAT", passage=passage["id"], options=OPTIONS)
    assert refused.status_code == 400 and "passage" in refused.data


# --- Writing и Speaking: открытый ответ ------------------------------------------------


@pytest.mark.parametrize(("section", "kind"), [("writing", QuestionType.WRITING), ("speaking", QuestionType.SPEAKING)])
def test_open_sections_have_no_options(kymbat, section, kind):
    with_options = question(kymbat, section=section, options=OPTIONS)
    assert with_options.status_code == 400 and "вариантов" in str(with_options.data["options"])

    made = question(
        kymbat,
        section=section,
        text="Describe the chart.",
        criteria="Task response, coherence",
        word_limit=150,
        minute_limit=2,
    )
    assert made.status_code == 201, made.data
    row = Question.objects.get(pk=made.data["id"])
    assert row.question_type == kind and row.is_open and not row.options.exists()
    assert (row.word_limit, row.minute_limit, row.criteria) == (150, 2, "Task response, coherence")


def test_the_open_answer_is_kept_and_waits_for_the_director(kymbat, student):
    question(kymbat, section="writing", text="Describe the chart.", criteria="Task response", word_limit=150)
    pupil = APIClient()
    pupil.force_authenticate(student.user)
    session = pupil.post("/api/prep/practice/start/", {"exam_type": "IELTS", "section": "writing"}, format="json").data
    task = session["questions"][0]
    assert task["is_open"] and task["options"] == [] and task["word_limit"] == 150
    # критерии — текст для разбора: до сдачи их нет
    assert "criteria" not in task

    essay = "The chart shows a steady rise. " * 10
    saved = pupil.post(
        f"/api/prep/practice/{session['id']}/answer/", {"answer_id": task["answer_id"], "text": essay}, format="json"
    )
    assert saved.status_code == 200 and saved.data["answered"] is True
    review = pupil.post(f"/api/prep/practice/{session['id']}/finish/", {}, format="json").data
    assert review["open_waiting"] == 1 and review["checked_by_machine"] == 0
    # эссе не считается ошибкой: процента по машинной проверке нет, слабых тем тоже
    assert review["percent"] == 0 and review["weak_topics"] == []
    item = review["questions"][0]
    assert item["answer_text"] == essay.strip() and item["criteria"] == "Task response" and item["review"] is None

    queue = kymbat.get("/api/prep/open-answers/").data
    assert queue["waiting"] == 1
    row = queue["results"][0]
    assert (row["student"], row["answer"], row["words"]) == (student.full_name, essay.strip(), 60)

    # оценка по шкале экзамена: 6.3 у IELTS не бывает
    assert (
        kymbat.post(f"/api/prep/open-answers/{row['id']}/review/", {"score": "6.3"}, format="json").status_code == 400
    )
    assert kymbat.post(f"/api/prep/open-answers/{row['id']}/review/", {}, format="json").status_code == 400
    done = kymbat.post(
        f"/api/prep/open-answers/{row['id']}/review/", {"score": "6.5", "comment": "Нет обзора"}, format="json"
    )
    assert done.status_code == 200 and done.data["reviewed"] is True
    assert kymbat.get("/api/prep/open-answers/").data["waiting"] == 0
    assert kymbat.get("/api/prep/open-answers/?state=reviewed").data["results"][0]["score"] == 6.5

    # ученик видит оценку и слова — и не видит, кто проверял
    seen = pupil.get(f"/api/prep/practice/{session['id']}/").data["questions"][0]["review"]
    assert (seen["score"], seen["comment"]) == (6.5, "Нет обзора")
    assert "Кымбат" not in str(pupil.get(f"/api/prep/practice/{session['id']}/").data)
    answer = PracticeAnswer.objects.get(pk=row["id"])
    assert answer.reviewed_by is not None and answer.is_correct is False


def test_open_answers_are_closed_to_everyone_but_the_exam_director(kymbat, student, make_user):
    question(kymbat, section="speaking", text="Describe your town.", minute_limit=2)
    for who in (student.user, make_user("director_sport", "sport-bank@example.kz")):
        client = APIClient()
        client.force_authenticate(who)
        assert client.get("/api/prep/open-answers/").status_code == 403
        assert client.post("/api/prep/open-answers/1/review/", {"score": "6"}, format="json").status_code == 403


def test_open_questions_stay_out_of_the_machine_scored_mock(kymbat):
    question(kymbat, section="writing", text="Essay")
    assert not services.available_questions(exam_type="IELTS", section=Section.WRITING).exists()
    assert services.practice_pool(exam_type="IELTS", section=Section.WRITING).count() == 1


# --- SAT и остальное — как было ---------------------------------------------------------


def test_sat_keeps_options_and_may_have_a_passage(kymbat):
    plain = question(kymbat, exam_type="SAT", section="math", options=OPTIONS)
    assert plain.status_code == 201, plain.data
    no_correct = question(
        kymbat, exam_type="SAT", section="math", options=[{**OPTIONS[0]}, {**OPTIONS[0], "letter": "B"}]
    )
    assert no_correct.status_code == 400 and "ровно один" in str(no_correct.data["options"])

    passage = kymbat.post(
        "/api/prep/passages/",
        {"exam_type": "SAT", "section": "verbal", "kind": "reading", "title": "Essay", "body": "Text."},
        format="json",
    ).data
    assert (
        question(kymbat, exam_type="SAT", section="verbal", passage=passage["id"], options=OPTIONS).status_code == 201
    )


def test_a_foreign_director_is_refused_before_the_form_is_read(make_user):
    client = APIClient()
    client.force_authenticate(make_user("director_sport", "sport-form@example.kz"))
    assert client.post("/api/prep/questions/", {"section": "writing"}, format="json").status_code == 403
    assert client.post("/api/prep/passages/", {"kind": "reading"}, format="json").status_code == 403
