"""Фаза 47: фоновые операции одним механизмом и замки вместо пустоты.

Проверяем то, ради чего это сведено вместе:

* долгая операция видна плашкой, а её конец приходит уведомлением — даже
  если человек ушёл с экрана, на котором её запустил;
* сорвавшаяся операция говорит, что не получилось, и повторяется тем же
  вызовом, а не «запустите заново и вспомните, что вы там вводили»;
* закрытый разделу ученика раздел объясняется словами, а чужой домен —
  по-прежнему без объяснений (инвариант №7 не смягчается).
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core import jobs
from core.models import BackgroundJob, Notification


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


# --- Плашка операций --------------------------------------------------------


@pytest.mark.django_db
def test_job_shows_stages_and_percent(api, make_user):
    """Этапы, которые называет операция, становятся процентом на плашке."""
    user = make_user("director_exam")
    job = jobs.start(user=user, kind="parse_file", title="Разбор файла «11a.csv»", task_id="task-1")
    assert job.percent == 0

    jobs.step("task-1", "Читаю файл")
    jobs.step("task-1", "Разбираю строки")
    job.refresh_from_db()
    assert job.stage == "Разбираю строки"
    assert 0 < job.percent < 100, "до конца сотни не бывает"

    api.force_authenticate(user)
    rows = api.get("/api/jobs/").data["results"]
    assert rows[0]["title"] == "Разбор файла «11a.csv»"
    assert rows[0]["percent"] == job.percent


@pytest.mark.django_db
def test_finished_job_leaves_the_panel_and_rings_the_bell(api, make_user):
    """Конец операции — уведомление в колокольчик, а не только плашка."""
    user = make_user("director_exam")
    jobs.start(user=user, kind="paste", title="Разбор вставленного текста", task_id="task-2")
    jobs.complete("task-2", link="/suggestions/7")

    api.force_authenticate(user)
    assert api.get("/api/jobs/").data["results"] == [], "готовое из плашки уходит само"
    note = Notification.objects.filter(recipient=user, kind=Notification.Kind.JOB_DONE).first()
    assert note is not None
    assert "готово" in note.text
    assert note.link == "/suggestions/7"


@pytest.mark.django_db
def test_failed_job_says_why_and_can_be_retried(api, make_user):
    """Сбой объясняется словами, и его можно повторить тем же вызовом."""
    user = make_user("director_exam")
    jobs.start(
        user=user,
        kind="operation",
        title="Проверка баланса списка вузов",
        task_id="task-3",
        retry_task="suggestions.run_operation",
        retry_payload={"code": "check_balance", "actor_id": user.pk, "role": user.role, "payload": {}},
    )
    jobs.fail("task-3", "модель вернула 503")

    api.force_authenticate(user)
    row = api.get("/api/jobs/").data["results"][0]
    assert row["status"] == "failed"
    assert row["error"] == "модель вернула 503"
    assert row["can_retry"] is True
    assert Notification.objects.filter(recipient=user, kind=Notification.Kind.JOB_FAILED).exists()

    again = api.post(f"/api/jobs/{row['id']}/retry/")
    assert again.status_code == 200, again.data
    assert BackgroundJob.objects.filter(owner=user).count() == 2


@pytest.mark.django_db
def test_retry_without_a_recipe_says_so(api, make_user):
    """Распознавание картинки повторить нечем: файл живёт один запрос."""
    user = make_user("director_talent")
    jobs.start(user=user, kind="parse_image", title="Распознавание изображения", task_id="task-4")
    jobs.fail("task-4", "не удалось разобрать")

    api.force_authenticate(user)
    row = api.get("/api/jobs/").data["results"][0]
    assert row["can_retry"] is False
    answer = api.post(f"/api/jobs/{row['id']}/retry/")
    assert answer.status_code == 400
    assert "запустите её заново" in answer.data["detail"]


@pytest.mark.django_db
def test_dismiss_hides_the_row_but_not_the_work(api, make_user):
    user = make_user("director_exam")
    job = jobs.start(user=user, kind="paste", title="Разбор текста", task_id="task-5")
    api.force_authenticate(user)
    assert api.post(f"/api/jobs/{job.pk}/dismiss/").status_code == 200
    assert api.get("/api/jobs/").data["results"] == []
    job.refresh_from_db()
    assert job.status == BackgroundJob.Status.RUNNING, "операция продолжается"


@pytest.mark.django_db
def test_jobs_are_personal(api, make_user):
    """Чужие операции в списке не появляются."""
    mine = make_user("director_exam")
    other = make_user("director_sport")
    jobs.start(user=other, kind="paste", title="Чужой разбор", task_id="task-6")

    api.force_authenticate(mine)
    assert api.get("/api/jobs/").data["results"] == []
    assert api.post("/api/jobs/1/dismiss/").status_code == 404


@pytest.mark.django_db
def test_every_background_operation_opens_a_job(api, make_user, student, monkeypatch):
    """Каждая долгая операция заводит плашку — иначе человек ждёт вслепую."""
    from suggestions import views as suggestion_views

    class FakeTask:
        id = "fake-task"

    user = make_user("director_exam")
    api.force_authenticate(user)
    monkeypatch.setattr(suggestion_views.background.parse_paste, "delay", lambda **_kwargs: FakeTask())
    answer = api.post("/api/commands/paste/", {"text": "IELTS 7.0", "command": "paste_as_is"}, format="json")
    assert answer.status_code == 202
    job = BackgroundJob.objects.get(task_id="fake-task")
    assert job.kind == "paste"
    assert job.retry_task == "suggestions.parse_paste"


# --- Замки ------------------------------------------------------------------


@pytest.mark.django_db
def test_locked_sections_explain_themselves(api, student_user, student):
    """Закрытый раздел объясняется словами и говорит, что сделать."""
    api.force_authenticate(student_user)
    locks = {row["path"]: row for row in api.get("/api/journey/locks/").data["locks"]}
    assert locks["/selection"]["locked"] is True
    assert "внесёте баллы" in locks["/selection"]["reason"]
    assert locks["/plan"]["locked"] is True
    assert locks["/plan"]["reason"] == "Откроется, когда выберете вузы"
    assert locks["/plan"]["to"] == "/selection"


@pytest.mark.django_db
def test_lock_lifts_as_soon_as_the_step_is_done(api, student_user, student):
    """Шаг сделан — замок снят: без второй кнопки и без перезахода."""
    student.exam.ielts_current = 6.5
    student.exam.save(update_fields=["ielts_current"])

    api.force_authenticate(student_user)
    locks = {row["path"]: row for row in api.get("/api/journey/locks/").data["locks"]}
    assert locks["/selection"]["locked"] is False
    assert locks["/plan"]["locked"] is True, "план ждёт своего шага — выбора вузов"

    from universities.models import Program, StudentUniversity, University

    university = University.objects.create(name="Lock University", country="Канада")
    program = Program.objects.create(university=university, name="CS", level="bachelor")
    StudentUniversity.objects.create(student=student, program=program)

    locks = {row["path"]: row for row in api.get("/api/journey/locks/").data["locks"]}
    assert locks["/plan"]["locked"] is False


@pytest.mark.django_db
def test_staff_has_no_locks(api, make_user):
    """У сотрудника замков нет: у него разделы закрыты доменом, а не шагом."""
    api.force_authenticate(make_user("director_exam"))
    assert api.get("/api/journey/locks/").data["locks"] == []


def test_foreign_domain_is_still_refused_without_explanation():
    """Инвариант №7 не смягчается: чужой раздел закрыт, а не «объяснён».

    Проверяем по исходникам: разделы чужой роли по-прежнему уводят
    на дашборд, а не показывают замок с причиной.
    """
    import re
    from pathlib import Path

    root = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
    app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "DOMAIN_ONLY[location.pathname] !== undefined" in app
    assert re.search(r"if \(forbidden\) return <Navigate to=\"/dashboard\" replace />", app)
    shell = (root / "frontend" / "src" / "layout" / "Shell.tsx").read_text(encoding="utf-8")
    # замок показывается только по ответу сервера про шаги ученика
    assert "currentLock ? (" in shell and "<LockedScreen lock={currentLock}>" in shell
