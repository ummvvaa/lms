"""Сдача ДЗ: кому задано, до и после срока, замена, проверка, журнал, четвертная, выполнение, права, файлы."""

from __future__ import annotations

import datetime as dt
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from academics.schedule import create_once
from academics.tests.conftest import days, login, school_day
from core.models import SchoolRule
from homework import services
from homework.models import Assignment, HomeworkFile, LatePolicy, Submission

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n" + b"0" * 200


@pytest.fixture(autouse=True)
def local_storage(settings, tmp_path):
    """Без бакета — локальный диск во временной папке: тесты не трогают ни облако, ни диск разработки."""
    settings.HOMEWORK_S3 = {"BUCKET": "", "ENDPOINT": "", "REGION": "", "ACCESS_KEY": "", "SECRET_KEY": ""}
    settings.PRIVATE_MEDIA_ROOT = tmp_path


def due_in(hours: float) -> dt.datetime:
    return timezone.now() + dt.timedelta(hours=hours)


@pytest.fixture
def algebra(lesson, teacher):
    """Урок алгебры BOSTON с ДЗ со сдачей, срок через сутки."""
    services.save_assignment(
        lesson, requires_submission=True, due_at=due_in(24), late_policy=LatePolicy.ACCEPT, actor=teacher
    )
    return Assignment.objects.get(lesson=lesson)


@pytest.fixture
def english(eng_lesson, other_teacher):
    """Урок первой подгруппы английского: ДЗ получают только её ученики."""
    services.save_assignment(
        eng_lesson, requires_submission=True, due_at=due_in(24), late_policy=LatePolicy.CLOSE, actor=other_teacher
    )
    return Assignment.objects.get(lesson=eng_lesson)


def upload(client, target: dict, data: bytes = PDF, name: str = "работа.pdf") -> dict:
    """Весь путь файла: ссылка → PUT на подписанный адрес → «загружено»."""
    start = client.post("/api/homework/uploads/", {**target, "name": name, "size": len(data)}, format="json")
    assert start.status_code == 200, start.content
    plan = start.json()
    put = client.generic("PUT", plan["url"], data, content_type="application/octet-stream")
    assert put.status_code == 200, put.content
    done = client.post(f"/api/homework/files/{plan['file']}/complete/", {"parts": []}, format="json")
    return {"status": done.status_code, "body": done.json(), "file": plan["file"]}


# --- Кому задано ------------------------------------------------------------------


def test_group_homework_reaches_the_whole_group(algebra, pupils):
    body = login(pupils["aliya"].user).get("/api/homework/my/").json()
    assert [item["id"] for item in body["items"]] == [algebra.pk] and body["counts"]["todo"] == 1
    assert services.is_recipient(pupils["nurai"].pk, algebra.lesson)
    assert not services.is_recipient(pupils["stranger"].pk, algebra.lesson), "чужая группа"


def test_subgroup_homework_reaches_only_the_subgroup(english, pupils, make_user):
    ids = set(services.recipients(english.lesson))
    assert pupils["aliya"].pk in ids and pupils["damir"].pk in ids
    assert pupils["nurai"].pk not in ids, "вторая подгруппа задания не получает"
    nurai = make_user("student", "nurai.user@example.kz")
    pupils["nurai"].user = nurai
    pupils["nurai"].save(update_fields=["user"])
    assert login(nurai).get("/api/homework/my/").json()["items"] == []
    assert login(nurai).get(f"/api/homework/my/{english.pk}/").status_code == 404


# --- Сдача до и после срока ---------------------------------------------------------


def test_submit_before_due_and_replace_before_due(algebra, pupils):
    client = login(pupils["aliya"].user)
    first = upload(client, {"assignment": algebra.pk})
    assert first["status"] == 200 and first["body"]["kind"] == "pdf" and first["body"]["state"] == "ready"
    done = client.post(f"/api/homework/my/{algebra.pk}/submit/", {"comment": "не понял № 217"}, format="json")
    assert done.status_code == 200, done.content
    body = done.json()
    assert body["state"] == "review" and body["submission"]["late_minutes"] is None
    # до срока работу можно заменить: убрать файл и сдать заново текстом
    assert client.delete(f"/api/homework/files/{first['file']}/").status_code == 200
    again = client.post(f"/api/homework/my/{algebra.pk}/submit/", {"text": "Ответ: x = 3"}, format="json")
    assert again.status_code == 200 and again.json()["submission"]["text"] == "Ответ: x = 3"


def test_empty_work_is_refused(algebra, pupils):
    answer = login(pupils["aliya"].user).post(f"/api/homework/my/{algebra.pk}/submit/", {}, format="json")
    assert answer.status_code == 400


def test_late_submission_is_marked_when_teacher_accepts(algebra, pupils):
    Assignment.objects.filter(pk=algebra.pk).update(due_at=due_in(-3))
    client = login(pupils["aliya"].user)
    answer = client.post(
        f"/api/homework/my/{algebra.pk}/submit/", {"link": "https://docs.example.com/x"}, format="json"
    )
    assert answer.status_code == 200, answer.content
    assert 170 <= answer.json()["submission"]["late_minutes"] <= 190, "«с опозданием на 3 ч»"
    # после срока сданную работу уже не заменить
    replace = client.post(f"/api/homework/my/{algebra.pk}/submit/", {"text": "другое"}, format="json")
    assert replace.status_code == 400


def test_closed_after_due_refuses(english, pupils):
    Assignment.objects.filter(pk=english.pk).update(due_at=due_in(-1))
    client = login(pupils["aliya"].user)
    answer = client.post(f"/api/homework/my/{english.pk}/submit/", {"text": "поздно"}, format="json")
    assert answer.status_code == 400
    assert client.get("/api/homework/my/").json()["items"][0]["state"] == "missed"
    start = client.post(
        "/api/homework/uploads/", {"assignment": english.pk, "name": "a.pdf", "size": 10}, format="json"
    )
    assert start.status_code == 400, "файл после закрытого срока не принимается"


def test_xp_only_for_on_time_and_only_where_xp_is_on(algebra, pupils):
    from engagement.models import XPEvent

    login(pupils["aliya"].user).post(f"/api/homework/my/{algebra.pk}/submit/", {"text": "x"}, format="json")
    assert XPEvent.objects.filter(student=pupils["aliya"], kind="homework_on_time").count() == 1, "11 — XP есть"
    services.check(Submission.objects.get(student=pupils["aliya"]), grade=10, comment="", actor=None)
    assert XPEvent.objects.filter(student=pupils["aliya"]).count() == 1, "за оценку XP нет"


def test_no_xp_for_junior_parallel(algebra, pupils, boston):
    from engagement.models import XPEvent

    boston.parallel = 9
    boston.save()
    login(pupils["aliya"].user).post(f"/api/homework/my/{algebra.pk}/submit/", {"text": "x"}, format="json")
    assert not XPEvent.objects.filter(student=pupils["aliya"]).exists()


# --- Проверка и журнал ---------------------------------------------------------------


def submitted(assignment, student, text="ответ"):
    return services.submit(assignment, student, text=text, link="", comment="")


def test_teacher_checks_with_grade_or_without_and_journal_shows_it(algebra, pupils, teacher, as_teacher, lesson):
    aliya = submitted(algebra, pupils["aliya"])
    damir = submitted(algebra, pupils["damir"])
    detail = as_teacher.get(f"/api/homework/review/{algebra.pk}/").json()
    states = {row["student"]["id"]: row["state"] for row in detail["students"]}
    assert states[pupils["aliya"].pk] == "unchecked" and states[pupils["nurai"].pk] == "missed"
    assert (
        as_teacher.post(f"/api/homework/submissions/{aliya.pk}/check/", {"grade": 9}, format="json").status_code == 200
    )
    assert (
        as_teacher.post(f"/api/homework/submissions/{damir.pk}/check/", {"grade": None}, format="json").status_code
        == 200
    )
    assert (
        as_teacher.post(f"/api/homework/submissions/{damir.pk}/check/", {"grade": 11}, format="json").status_code == 400
    )
    journal = as_teacher.get(f"/api/acad/journals/{lesson.course_id}/").json()
    assert [col["lesson"] for col in journal["homework_columns"]] == [lesson.pk]
    cells = {row["id"]: row["homework"][0] for row in journal["rows"]}
    assert cells[pupils["aliya"].pk]["grade"] == 9
    assert cells[pupils["damir"].pk]["state"] == "checked" and cells[pupils["damir"].pk]["grade"] is None
    assert cells[pupils["nurai"].pk]["state"] == "pending", "срок не прошёл — «не сдано» ещё не ставится"


def test_check_has_no_seven_day_window_and_keeps_absence(algebra, pupils, teacher, lesson, calendar, as_teacher):
    from academics import marks as marking
    from academics.models import Attendance, Lesson

    marking.save_attendance(
        lesson, [{"student": pupils["aliya"].pk, "mark": "absent"}], actor=teacher, calendar=calendar
    )
    work = submitted(algebra, pupils["aliya"])
    Lesson.objects.filter(pk=lesson.pk).update(date=days(-40))
    answer = as_teacher.post(f"/api/homework/submissions/{work.pk}/check/", {"grade": 7}, format="json")
    assert answer.status_code == 200, "окна в 7 дней у проверки ДЗ нет"
    assert Attendance.objects.filter(
        lesson=lesson, student=pupils["aliya"], mark="absent"
    ).exists(), "«не был» остаётся"


def test_homework_grade_is_not_in_quarter_by_default_and_is_with_the_setting(
    algebra, pupils, teacher, lesson, calendar
):
    from academics import marks as marking
    from academics.calendar import scale_of
    from academics.results import course_context

    scale = scale_of(calendar.year)
    marking.set_grade(lesson, pupils["aliya"], 6, actor=teacher, calendar=calendar, scale=scale)
    services.check(submitted(algebra, pupils["aliya"]), grade=10, comment="", actor=teacher)
    start, end = days(-30), days(0)

    def fo_avg():
        return course_context(lesson.course, start, end, scale).stats(pupils["aliya"].pk).fo_avg

    assert fo_avg() == 6, "по умолчанию оценка за ДЗ в четвертную не входит"
    SchoolRule.objects.create(code="homework_in_quarter", value=1)
    assert fo_avg() == 8, "входит как обычная ФО при весе 100 %"
    SchoolRule.objects.create(code="homework_weight", value=50)
    assert fo_avg() == pytest.approx(round((6 + 0.5 * 10) / 1.5, 1))


# --- Выполнение ДЗ, % ------------------------------------------------------------------


def test_completion_counts_on_time_over_all_due(algebra, pupils, teacher, subjects, cohorts, calendar):
    second = create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-3, calendar),
        slot=5,
        room="1",
    )
    other = services.save_assignment(
        second, requires_submission=True, due_at=due_in(48), late_policy=LatePolicy.ACCEPT, actor=teacher
    )
    submitted(algebra, pupils["aliya"])
    Submission.objects.filter(student=pupils["aliya"]).update(submitted_at=due_in(1))
    Assignment.objects.filter(pk__in=[algebra.pk, other.pk]).update(due_at=due_in(-1))
    Submission.objects.filter(student=pupils["aliya"]).update(submitted_at=due_in(-2), late_minutes=None)
    Submission.objects.create(assignment=other, student=pupils["aliya"], submitted_at=due_in(-0.5), late_minutes=30)
    stats = services.completion([pupils["aliya"].pk, pupils["nurai"].pk], days(-30), days(0))
    assert stats[pupils["aliya"].pk].as_dict() == {"total": 2, "on_time": 1, "late": 1, "missed": 0, "pct": 50}
    assert stats[pupils["nurai"].pk].pct == 0 and stats[pupils["nurai"].pk].missed == 2
    assert services.completion([pupils["stranger"].pk], days(-30), days(0))[pupils["stranger"].pk].pct is None


def test_readiness_and_risks_read_the_computed_percent(algebra, pupils, saltanat):
    from core.dashboards import behavior_dashboard

    Assignment.objects.filter(pk=algebra.pk).update(due_at=due_in(-1))
    rows = behavior_dashboard()["worst_homework"]
    assert {row["student_id"]: row["homework_percent"] for row in rows}[pupils["nurai"].pk] == 0
    assert login(saltanat).get("/api/dashboards/behavior/").status_code == 200


# --- Права ---------------------------------------------------------------------------------


def test_teacher_sees_only_own_assignments(algebra, english, other_teacher, teacher, as_teacher):
    listed = {item["id"] for item in as_teacher.get("/api/homework/review/").json()["items"]}
    assert listed == {algebra.pk}
    assert as_teacher.get(f"/api/homework/review/{english.pk}/").status_code == 404
    assert (
        login(other_teacher)
        .put(f"/api/homework/lessons/{algebra.lesson_id}/", {"requires_submission": False}, format="json")
        .status_code
        == 404
    )


def test_curator_sees_own_groups_only_read(algebra, pupils, curator, as_curator, kymbat):
    Assignment.objects.filter(pk=algebra.pk).update(due_at=due_in(-1))
    rows = as_curator.get("/api/homework/overview/").json()["rows"]
    assert {row["id"] for row in rows} == {pupils["aliya"].pk, pupils["damir"].pk, pupils["nurai"].pk}
    assert as_curator.get("/api/homework/overview/?group=CHICAGO").json()["rows"] == []
    # проверка — только уроков, которые куратор ведёт сам (классный час); чужих работ он не видит
    assert as_curator.get("/api/homework/review/").json()["items"] == []
    assert as_curator.get(f"/api/homework/review/{algebra.pk}/").status_code == 404
    assert login(kymbat).get("/api/homework/overview/").status_code == 200


def test_foreign_file_is_404_and_links_only_after_rights(
    algebra, pupils, teacher, as_teacher, other_teacher, make_user
):
    aliya = login(pupils["aliya"].user)
    loaded = upload(aliya, {"assignment": algebra.pk})
    assert aliya.get(f"/api/homework/files/{loaded['file']}/link/").status_code == 200
    stranger = make_user("student", "stranger.user@example.kz")
    pupils["stranger"].user = stranger
    pupils["stranger"].save(update_fields=["user"])
    assert login(stranger).get(f"/api/homework/files/{loaded['file']}/link/").status_code == 404
    assert login(other_teacher).get(f"/api/homework/files/{loaded['file']}/link/").status_code == 404
    assert as_teacher.get(f"/api/homework/files/{loaded['file']}/link/").status_code == 200
    assert login(stranger).delete(f"/api/homework/files/{loaded['file']}/").status_code == 404


def test_signed_link_is_the_only_pass(algebra, pupils, as_teacher):
    aliya = login(pupils["aliya"].user)
    loaded = upload(aliya, {"assignment": algebra.pk})
    url = as_teacher.get(f"/api/homework/files/{loaded['file']}/link/").json()["url"]
    from rest_framework.test import APIClient

    anonymous = APIClient()
    assert anonymous.get(url).status_code == 200, "подписанная ссылка отдаёт файл и без сессии"
    assert anonymous.get(url.replace("/local/", "/local/x")).status_code == 404
    with mock.patch("homework.storage.LINK_SECONDS", -1):
        assert anonymous.get(url).status_code == 404, "просроченная ссылка — 404"


# --- Файлы ------------------------------------------------------------------------------


def test_type_by_first_bytes_and_executables_refused(algebra, pupils):
    client = login(pupils["aliya"].user)
    jpg = upload(client, {"assignment": algebra.pk}, b"\xff\xd8\xff\xe0" + b"1" * 100, name="фото.pdf")
    assert jpg["body"]["kind"] == "image" and jpg["body"]["content_type"] == "image/jpeg", "имени не верим"
    exe = upload(client, {"assignment": algebra.pk}, b"MZ\x90\x00" + b"1" * 100, name="работа.pdf")
    assert exe["status"] == 400
    assert not HomeworkFile.objects.filter(pk=exe["file"]).exists()
    docx = upload(client, {"assignment": algebra.pk}, b"PK\x03\x04" + b"1" * 100, name="эссе.docx")
    assert docx["body"]["content_type"].endswith("wordprocessingml.document")


def test_size_and_count_limits(algebra, pupils):
    client = login(pupils["aliya"].user)
    SchoolRule.objects.create(code="homework_file_mb", value=1)
    big = client.post(
        "/api/homework/uploads/", {"assignment": algebra.pk, "name": "big.pdf", "size": 2 * 1024 * 1024}, format="json"
    )
    assert big.status_code == 400 and "1 МБ" in big.json()["detail"]
    video = client.post(
        "/api/homework/uploads/",
        {"assignment": algebra.pk, "name": "v.mp4", "size": 3 * 1024 * 1024, "content_type": "video/mp4"},
        format="json",
    )
    assert video.status_code == 200, "у видео свой предел — 500 МБ, предел файла 1 МБ его не касается"
    SchoolRule.objects.create(code="homework_max_files", value=2)
    HomeworkFile.objects.filter(submission__student=pupils["aliya"]).delete()
    for _ in range(2):
        upload(client, {"assignment": algebra.pk})
    third = client.post(
        "/api/homework/uploads/", {"assignment": algebra.pk, "name": "3.pdf", "size": 10}, format="json"
    )
    assert third.status_code == 400


def test_teacher_attaches_files_and_students_read_them(lesson, teacher, as_teacher, pupils):
    loaded = upload(as_teacher, {"lesson": lesson.pk}, name="Задачи.pdf")
    assert loaded["status"] == 200
    payload = as_teacher.get(f"/api/homework/lessons/{lesson.pk}/").json()
    assert [f["name"] for f in payload["files"]] == ["Задачи.pdf"] and payload["requires_submission"] is False
    assert login(pupils["aliya"].user).get(f"/api/homework/files/{loaded['file']}/link/").status_code == 200


def test_purge_drops_the_stored_object(algebra, pupils, settings):
    from pathlib import Path

    from core.purge import drop_stored

    loaded = upload(login(pupils["aliya"].user), {"assignment": algebra.pk})
    row = HomeworkFile.objects.get(pk=loaded["file"])
    path = Path(settings.PRIVATE_MEDIA_ROOT) / row.key
    assert path.is_file()
    assert drop_stored(row) == 1 and not path.exists()


# --- Задание урока ---------------------------------------------------------------------


def test_default_due_is_next_lesson_start(lesson, teacher, subjects, cohorts, calendar, as_teacher):
    following = create_once(
        subject=subjects["alg"], teacher=teacher, cohort=cohorts["boston"], date=days(5), slot=1, room="1"
    )
    options = as_teacher.get(f"/api/homework/lessons/{lesson.pk}/").json()["options"]
    start = services.lesson_start(following)
    assert options["next_lesson"].startswith(timezone.localtime(start).strftime("%Y-%m-%dT%H:%M"))
    saved = as_teacher.put(
        f"/api/homework/lessons/{lesson.pk}/", {"requires_submission": True, "late_policy": "close"}, format="json"
    ).json()
    assert saved["requires_submission"] is True and saved["late_policy"] == "close"
    assert Assignment.objects.get(lesson=lesson).due_at == start


def test_student_never_sees_other_students_counts(algebra, pupils):
    body = login(pupils["aliya"].user).get("/api/homework/my/").json()
    assert "submitted" not in str(body["items"][0].keys()) and "total" not in body["items"][0]


def test_check_storage_without_bucket_says_so(capsys):
    call_command("check_storage")
    assert "не настроено" in capsys.readouterr().out


KZ = {
    "BUCKET": "b",
    "ENDPOINT": "https://storage.yandexcloud.kz",
    "REGION": "kz1",
    "ACCESS_KEY": "k",
    "SECRET_KEY": "s",
}


@override_settings(HOMEWORK_S3=KZ)
def test_s3_links_are_presigned_for_kz_region():
    from homework.storage import S3Storage, backend

    store = backend()
    assert isinstance(store, S3Storage)
    url = store.link("homework/x/1", name="работа.pdf", content_type="application/pdf", inline=True)
    assert url.startswith("https://storage.yandexcloud.kz/b/homework/x/1?")
    assert "kz1" in url and "X-Amz-Expires=300" in url and "response-content-disposition=inline" in url
    plan = store.start_upload("homework/x/2", 10)
    assert plan["method"] == "single" and "X-Amz-Signature" in plan["url"]


def test_stale_uploads_are_dropped(algebra, pupils):
    from homework.tasks import drop_stale_uploads

    client = login(pupils["aliya"].user)
    start = client.post(
        "/api/homework/uploads/", {"assignment": algebra.pk, "name": "a.pdf", "size": 10}, format="json"
    )
    HomeworkFile.objects.filter(pk=start.json()["file"]).update(created_at=timezone.now() - dt.timedelta(days=2))
    assert drop_stale_uploads() == 1
    assert not HomeworkFile.objects.filter(pk=start.json()["file"]).exists()


def test_recorded_audio_is_audio_in_chrome_and_safari():
    from homework.files import refine, sniff

    webm = refine(sniff(b"\x1a\x45\xdf\xa3" + b"0" * 60), "audio-2026-09-30.webm")
    safari = refine(sniff(b"\x00\x00\x00\x1cftypisom" + b"0" * 60), "audio-2026-09-30.m4a")
    video = refine(sniff(b"\x00\x00\x00\x1cftypisom" + b"0" * 60), "IMG_0001.mp4")
    assert (webm.kind, safari.kind, video.kind) == ("audio", "audio", "video")
