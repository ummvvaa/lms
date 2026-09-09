"""Фаза 64: готовность к живым ученикам.

Дефекты, которые увидел бы живой ученик: 500 вместо текста на повторе
(D24, D35) и шкала балла, не зависящая от экзамена (D4, D17). Плюс
предполётная проверка, чистка вымышленных и импорт живых.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from directories.models import ExamKind
from roadmap.models import Task, TaskTemplate
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamGoal,
    ExamProfile,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)

TODAY = timezone.localdate()


def days(n: int) -> dt.date:
    return TODAY + dt.timedelta(days=n)


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def group(db) -> StudyGroup:
    return StudyGroup.objects.create(code="CHICAGO", grade=11)


@pytest.fixture
def pupil(group, make_user):
    student = Student.objects.create(
        last_name="Сериков",
        first_name="Данияр",
        email="serikov64@example.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=student)
    user = make_user("student", "serikov64@example.kz", full_name="Сериков Данияр")
    student.user = user
    student.save(update_fields=["user"])
    return student, user


@pytest.fixture
def kymbat(make_user) -> User:
    return make_user("director_exam", "kymbat64@example.kz", full_name="Кымбат")


@pytest.fixture
def saltanat(make_user) -> User:
    return make_user("director_behavior", "saltanat64@example.kz", full_name="Салтанат")


@pytest.fixture
def ielts(db) -> ExamKind:
    kind, _ = ExamKind.objects.get_or_create(name="IELTS")
    return kind


# --- D24: вторая цель по тому же экзамену --------------------------------------------


@pytest.mark.django_db
def test_second_goal_for_the_same_exam_is_refused_with_words(pupil, kymbat, ielts):
    """Через ручку: 400 с причиной, а не 500 из базы."""
    student, _ = pupil
    client = login(kymbat)
    first = client.post(
        "/api/exam-goals/", {"student": student.pk, "exam": ielts.pk, "target_score": "7.0"}, format="json"
    )
    assert first.status_code == 201, first.content
    second = client.post(
        "/api/exam-goals/", {"student": student.pk, "exam": ielts.pk, "target_score": "7.5"}, format="json"
    )
    assert second.status_code == 400, second.content
    assert "уже есть" in str(second.json())
    assert ExamGoal.objects.filter(student=student).count() == 1

    # правка существующей цели проходит — она не сталкивается сама с собой
    goal = ExamGoal.objects.get(student=student)
    patched = client.patch(f"/api/exam-goals/{goal.pk}/", {"target_score": "8.0"}, format="json")
    assert patched.status_code == 200, patched.content

    # архивная цель дорогу новой не закрывает
    goal.archived_at = timezone.now()
    goal.save(update_fields=["archived_at"])
    again = client.post(
        "/api/exam-goals/", {"student": student.pk, "exam": ielts.pk, "target_score": "7.0"}, format="json"
    )
    assert again.status_code == 201, again.content


@pytest.mark.django_db
def test_second_goal_through_a_student_proposal_is_rejected_not_crashed(pupil, kymbat, ielts):
    """Тот же путь через предложение ученика: строка отклоняется с причиной."""
    student, user = pupil
    ExamGoal.objects.create(student=student, exam=ielts, target_score=7)

    made = login(user).post(
        "/api/suggestions/propose/",
        {
            "rows": [
                {"model": "students.ExamGoal", "field": "exam", "value": "IELTS", "new_object_key": "g"},
                {"model": "students.ExamGoal", "field": "target_score", "value": "7.5", "new_object_key": "g"},
            ]
        },
        format="json",
    )
    assert made.status_code == 201, made.content
    suggestion = made.json()["suggestions"][0]

    decided = login(kymbat).post(f"/api/suggestions/{suggestion}/review/", {"decision": "confirm"}, format="json")
    assert decided.status_code == 200, decided.content
    body = decided.json()
    rejected = body.get("rejected") or body.get("result", {}).get("rejected") or []
    assert any("уже есть" in row.get("reason", "") for row in rejected), body
    assert ExamGoal.objects.filter(student=student).count() == 1


# --- D35: повтор задачи ---------------------------------------------------------------


@pytest.mark.django_db
def test_repeated_task_by_template_is_refused_with_words(pupil, saltanat):
    """Задача по тому же шаблону второй раз — 400 с причиной; без шаблона — сколько угодно."""
    student, _ = pupil
    template = TaskTemplate.objects.create(title="Собрать портфолио", category="portfolio")
    client = login(saltanat)
    body = {
        "student": student.pk,
        "title": "Собрать портфолио",
        "category": "portfolio",
        "template": template.pk,
        "due_date": str(days(7)),
    }
    assert client.post("/api/tasks/", body, format="json").status_code == 201
    repeat = client.post("/api/tasks/", body, format="json")
    assert repeat.status_code == 400, repeat.content
    assert "уже есть" in str(repeat.json())

    # обычная задача без шаблона и раунда заводится сколько угодно раз
    plain = {"student": student.pk, "title": "Позвонить в приёмную", "category": "university", "due_date": str(days(7))}
    assert client.post("/api/tasks/", plain, format="json").status_code == 201
    assert client.post("/api/tasks/", plain, format="json").status_code == 201
    assert Task.objects.filter(student=student).count() == 3


@pytest.mark.django_db
def test_student_endpoints_never_answer_500_on_repeat(pupil, kymbat, ielts):
    """Повтор и конфликт на ручках ученика — только 2xx или 4xx."""
    student, user = pupil
    client = login(user)
    rows = [
        {"model": "students.ExamGoal", "field": "exam", "value": "IELTS", "new_object_key": "g"},
        {"model": "students.ExamGoal", "field": "target_score", "value": "7.5", "new_object_key": "g"},
    ]
    for _ in range(2):
        response = client.post("/api/suggestions/propose/", {"rows": rows}, format="json")
        assert response.status_code < 500, response.content
    boss = login(kymbat)
    from suggestions.models import Suggestion

    for suggestion in Suggestion.objects.filter(author=user):
        response = boss.post(f"/api/suggestions/{suggestion.pk}/review/", {"decision": "confirm"}, format="json")
        assert response.status_code < 500, response.content
    assert ExamGoal.objects.filter(student=student).count() == 1


# --- D4, D17: шкала зависит от экзамена и живёт в реестре -----------------------------


@pytest.mark.django_db
def test_scale_is_read_from_the_registry():
    """Одно место: IELTS 0–9 шаг 0.5, SAT 400–1600 шаг 10, секции SAT 200–800."""
    from core.domains import scale_of

    assert (
        scale_of("IELTS").holds("6.5") and not scale_of("IELTS").holds("6.25") and not scale_of("IELTS").holds("12.5")
    )
    assert scale_of("IELTS", section=True).holds("9") and not scale_of("IELTS", section=True).holds("9.5")
    assert scale_of("SAT").holds("1310") and not scale_of("SAT").holds("1315") and not scale_of("SAT").holds("1700")
    assert scale_of("SAT", section=True).holds("800") and not scale_of("SAT", section=True).holds("850")
    assert scale_of("TOEFL") is None, "скрытые экзамены остаются на общей границе поля"


@pytest.mark.django_db
def test_no_value_outside_the_scale_passes_any_door(pupil, kymbat, ielts):
    """Карточка, массовый ввод, цель, профиль, предложение — везде отказ словами."""
    from directories.models import ExamKind
    from students.models import ExamAttempt

    student, user = pupil
    boss = login(kymbat)
    sat, _ = ExamKind.objects.get_or_create(name="SAT")

    # попытка через ручку: общий балл и секции
    for payload in (
        {"exam_type": "IELTS", "total_score": "12.5"},
        {"exam_type": "IELTS", "total_score": "6.5", "listening": "6.3"},
        {"exam_type": "SAT", "total_score": "1315"},
        {"exam_type": "SAT", "total_score": "1300", "math": "850"},
    ):
        response = boss.post(
            "/api/attempts/",
            {"student": student.pk, "attempt_format": "official", "date": str(TODAY), **payload},
            format="json",
        )
        assert response.status_code == 400, (payload, response.content)
        assert "шагом" in str(response.json()), response.content
    assert ExamAttempt.objects.filter(student=student).count() == 0
    fine = boss.post(
        "/api/attempts/",
        {
            "student": student.pk,
            "attempt_format": "official",
            "date": str(TODAY),
            "exam_type": "IELTS",
            "total_score": "7.5",
        },
        format="json",
    )
    assert fine.status_code == 201, fine.content

    # массовый ввод: кривая строка называется, остальные ложатся
    bulk = boss.post(
        "/api/attempts/bulk/",
        {
            "rows": [
                {
                    "student": student.pk,
                    "exam_type": "IELTS",
                    "attempt_format": "mock",
                    "date": str(days(-1)),
                    "total_score": "12.5",
                },
            ]
        },
        format="json",
    )
    assert bulk.status_code == 200, bulk.content
    assert "шагом" in str(bulk.json())
    assert ExamAttempt.objects.filter(student=student, total_score=12.5).count() == 0

    # цель: IELTS 1200 — тот самый D17
    goal = boss.post(
        "/api/exam-goals/", {"student": student.pk, "exam": ielts.pk, "target_score": "1200"}, format="json"
    )
    assert goal.status_code == 400, goal.content
    sat_goal = boss.post(
        "/api/exam-goals/", {"student": student.pk, "exam": sat.pk, "target_score": "7.5"}, format="json"
    )
    assert sat_goal.status_code == 400, sat_goal.content

    # профиль: текущий IELTS 12.5 — тот самый D4
    profile = boss.patch(f"/api/profiles/exam/{student.pk}/", {"ielts_current": "12.5"}, format="json")
    assert profile.status_code == 400, profile.content
    assert boss.patch(f"/api/profiles/exam/{student.pk}/", {"sat_current": "1315"}, format="json").status_code == 400
    assert boss.patch(f"/api/profiles/exam/{student.pk}/", {"ielts_current": "7.5"}, format="json").status_code == 200

    # предложение ученика: отказ при подаче, а не при решении
    proposed = login(user).post(
        "/api/suggestions/propose/",
        {
            "rows": [
                {"model": "students.ExamProfile", "field": "ielts_current", "value": "12.5"},
                {"model": "students.ExamProfile", "field": "sat_current", "value": "1315"},
                {"model": "students.ExamGoal", "field": "exam", "value": "IELTS", "new_object_key": "g"},
                {"model": "students.ExamGoal", "field": "target_score", "value": "1200", "new_object_key": "g"},
            ]
        },
        format="json",
    )
    rejected = {row["field"] for row in proposed.json()["rejected"]}
    assert {"ielts_current", "sat_current", "target_score"} <= rejected, proposed.content


# --- Вымышленные ученики: пометить, проверить, вычистить -------------------------------


@pytest.mark.django_db
def test_mark_fictional_by_emails_and_domain(pupil, group, make_user):
    """Признак ставится явно — по почтам и по домену, не угадывается."""
    from students import fictional

    student, _ = pupil
    probe = Student.objects.create(
        last_name="Прогон",
        first_name="Айгерим",
        email="student@probe.local",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    assert not student.is_fictional and not probe.is_fictional

    fictional.mark(domain="probe.local")
    probe.refresh_from_db()
    student.refresh_from_db()
    assert probe.is_fictional and not student.is_fictional, "домен помечает только свои"

    fictional.mark(emails=[student.email.upper()])
    student.refresh_from_db()
    assert student.is_fictional


@pytest.mark.django_db
def test_purge_fictional_removes_students_and_keeps_staff(
    pupil, group, kymbat, saltanat, make_user, tmp_path, settings
):
    """После чистки — ноль вымышленных, директора и кураторы на месте, справочники целы."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.core.management import call_command

    from accounts.curators import assign
    from directories.models import ExamKind
    from roadmap.models import Task
    from students import fictional
    from students.models import ExamAttempt, StudentDocument

    settings.DEBUG = True
    student, user = pupil
    admin = make_user("admin", "admin64b@example.kz", full_name="Администратор")
    curator = make_user("curator", "curator64@example.kz", full_name="Асель")
    assign(group=group, curator=curator, since=days(-10), actor=admin)
    ExamKind.objects.get_or_create(name="IELTS")
    ExamAttempt.objects.create(student=student, exam_type="IELTS", attempt_format="mock", date=TODAY, total_score=6)
    Task.objects.create(student=student, title="Задача", category="documents", due_date=days(3))
    document = StudentDocument.objects.create(
        student=student,
        doc_type="passport",
        file=SimpleUploadedFile("scan.pdf", b"%PDF-1.4 test", "application/pdf"),
        content_type="application/pdf",
        size=13,
    )
    stored = document.file.path
    kept = Student.objects.create(
        last_name="Настоящий",
        first_name="Ученик",
        email="real64@example.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )

    fictional.mark(emails=[student.email])
    outcome = fictional.purge()
    assert outcome.students == 1 and outcome.related["Попытки экзаменов"] == 1

    assert not Student.all_objects.filter(pk=student.pk).exists()
    assert not User.objects.filter(pk=user.pk).exists(), "учётная запись ученика ушла вместе с ним"
    assert Student.objects.filter(pk=kept.pk).exists(), "настоящий ученик остался"
    assert User.objects.filter(pk__in=[kymbat.pk, saltanat.pk, curator.pk, admin.pk]).count() == 4
    assert StudyGroup.objects.filter(pk=group.pk).exists()
    assert ExamKind.objects.filter(name="IELTS").exists()
    import os

    assert not os.path.exists(stored), "файл документа удалён с диска"

    # команда: без --yes отказывает, с DEBUG=0 требует --production
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("purge_fictional")
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("purge_fictional", "--yes")


@pytest.mark.django_db
def test_preflight_names_every_check(pupil, group, settings, capsys):
    """Предполётная проверка печатает полный список и падает, пока не всё ок."""
    from django.core.management import call_command

    settings.DEBUG = True
    with pytest.raises(SystemExit):
        call_command("preflight")
    out = capsys.readouterr().out
    for title in (
        "DEBUG выключен",
        "SECRET_KEY свой",
        "ALLOWED_HOSTS",
        "LOGIN_TRUSTED_NETWORKS",
        "Почта: сервер отвечает",
        "Бэкап: переменные бакета",
        "Бэкап: последний дамп",
        "Probe-аккаунты",
        "Вымышленных учеников нет",
        "У всех групп есть куратор",
        "ЕНТ в архиве",
        "Миграции применены",
        "check --deploy",
    ):
        assert title in out, title
    assert "НЕ ОК" in out and "К живым ученикам не готово" in out


@pytest.mark.django_db
def test_enroll_students_command_mirrors_the_screen(group, tmp_path, make_user):
    """Команда заводит учеников тем же кодом, что экран, и не дублирует при повторе."""
    from django.core.management import call_command

    admin = make_user("admin", "admin64c@example.kz", full_name="Администратор")
    curator = make_user("curator", "curator64c@example.kz", full_name="Асель")
    from accounts.curators import assign

    assign(group=group, curator=curator, since=days(-10), actor=admin)

    source = tmp_path / "live.csv"
    source.write_text(
        "ФИО,Почта,Класс,Группа\n"
        "Ахметова Аружан,live01@example.kz,11,CHICAGO\n"
        "Бекова Малика,live02@example.kz,11,CHICAGO\n",
        encoding="utf-8",
    )
    out = tmp_path / "passwords.csv"
    call_command("enroll_students", str(source), "--out", str(out), "--no-mail")

    rows = Student.objects.filter(email__startswith="live0")
    assert rows.count() == 2
    assert all(row.group_id == group.pk for row in rows), "привязаны к группе с куратором"
    assert all(row.user_id for row in rows), "у каждого учётная запись"
    assert all(not row.is_fictional for row in rows), "живые не помечены вымышленными"
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("ФИО") and len(lines) == 3, "пароли выданы файлом"

    # повтор ничего не дублирует
    call_command("enroll_students", str(source), "--no-mail")
    assert Student.objects.filter(email__startswith="live0").count() == 2
    assert User.objects.filter(email__startswith="live0").count() == 2
