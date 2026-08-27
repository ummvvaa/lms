"""Фаза 31: массовый ввод результатов, соревнования файлом, материалы Армана.

Проверяем то, что ломается: права на новые пути записи, поведение
загрузки на кривых строках и правило «материал сотрудника не идёт
в очередь к самому себе».
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import Role
from directories.models import SportType
from students.models import Competition, ExamAttempt


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def kymbat(make_user):
    return make_user(Role.DIRECTOR_EXAM, email="kymbat31@example.kz")


@pytest.fixture
def nurlybek(make_user):
    return make_user(Role.DIRECTOR_SPORT, email="nurlybek31@example.kz")


@pytest.fixture
def arman(make_user):
    return make_user(Role.DIRECTOR_TALENT, email="arman31@example.kz")


# --- Массовый ввод результатов ------------------------------------------


@pytest.mark.django_db
def test_bulk_results_are_saved_and_audited(api, kymbat, student):
    """Пачка результатов ложится строками и попадает в журнал (инвариант №9)."""
    from core.models import AuditLog

    api.force_authenticate(kymbat)
    response = api.post(
        "/api/attempts/bulk/",
        {
            "rows": [
                {
                    "student": student.pk,
                    "exam_type": "IELTS",
                    "attempt_format": "mock",
                    "date": "2026-04-01",
                    "total_score": "6.5",
                    "listening": "7",
                }
            ]
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["created"] == 1

    attempt = ExamAttempt.objects.get(student=student)
    assert str(attempt.total_score) == "6.5"
    assert AuditLog.objects.filter(model_label="students.ExamAttempt", object_id=str(attempt.pk)).exists()


@pytest.mark.django_db
def test_one_bad_row_does_not_cancel_the_rest(api, kymbat, student):
    """Кривая строка называется по номеру, остальные применяются."""
    api.force_authenticate(kymbat)
    payload = api.post(
        "/api/attempts/bulk/",
        {
            "rows": [
                {
                    "student": student.pk,
                    "exam_type": "IELTS",
                    "attempt_format": "mock",
                    "date": "2026-04-01",
                    "total_score": "не сдавал",
                },
                {
                    "student": student.pk,
                    "exam_type": "IELTS",
                    "attempt_format": "mock",
                    "date": "2026-04-02",
                    "total_score": "7.0",
                },
            ]
        },
        format="json",
    ).json()

    assert payload["created"] == 1
    assert len(payload["rejected"]) == 1
    # отказ называет ученика и поле человеческим языком, а не кодом колонки
    assert payload["rejected"][0]["student"] == student.full_name
    assert "Общий балл" in payload["rejected"][0]["reason"]
    assert ExamAttempt.objects.filter(student=student).count() == 1


@pytest.mark.django_db
def test_only_the_exam_director_enters_results_in_bulk(api, nurlybek, student):
    """Массовый ввод — тот же домен, что и одиночный (инвариант №1)."""
    api.force_authenticate(nurlybek)
    response = api.post(
        "/api/attempts/bulk/",
        {"rows": [{"student": student.pk, "exam_type": "IELTS", "date": "2026-04-01", "total_score": "6"}]},
        format="json",
    )
    assert response.status_code == 403
    assert ExamAttempt.objects.count() == 0


# --- Соревнования файлом -------------------------------------------------


HEADER = ["Почта ученика", "Соревнование", "Вид спорта", "Уровень", "Дата", "Результат", "Сертификат"]


@pytest.mark.django_db
def test_competitions_import_matches_students_and_skips_duplicates(student):
    """Ученик находится по почте, повторная загрузка не плодит дублей."""
    from students.competitions_import import apply_rows, build_preview

    SportType.objects.create(name="Футбол")
    rows = [[student.email, "Кубок города", "Футбол", "городской", "2026-03-01", "2 место", "да"]]

    preview = build_preview(header=HEADER, rows=rows)
    assert preview.as_dict()["will_create"] == 1
    assert preview.rows[0].level == "city"
    assert preview.rows[0].sport_type_name == "Футбол"

    apply_rows(rows=[row.as_dict() for row in preview.ready])
    assert Competition.objects.filter(student=student).count() == 1

    again = build_preview(header=HEADER, rows=rows)
    assert again.as_dict()["will_create"] == 0
    assert again.rows[0].status == "exists"


@pytest.mark.django_db
def test_unknown_sport_is_refused_and_directory_is_not_grown(student):
    """Импорт не заводит записей справочника: опечатка отклоняет строку."""
    from students.competitions_import import build_preview

    preview = build_preview(header=HEADER, rows=[[student.email, "Кубок города", "Футбол", "", "", "", ""]])
    assert preview.rows[0].status == "error"
    assert "справочник" in preview.rows[0].reason
    assert SportType.objects.count() == 0


@pytest.mark.django_db
def test_reverting_a_competitions_import_removes_what_it_created(student, nurlybek):
    """Откат убирает заведённые выступления в архив, а не обнуляет поля."""
    from core.imports import revert_batch
    from core.models import ImportBatch
    from students.competitions_import import apply_rows, build_preview

    preview = build_preview(
        header=HEADER, rows=[[student.email, "Кубок города", "", "городской", "2026-03-01", "2 место", ""]]
    )
    result = apply_rows(rows=[row.as_dict() for row in preview.ready], actor=nurlybek)
    assert Competition.objects.filter(student=student).count() == 1

    report = revert_batch(ImportBatch.objects.get(pk=result["batch"]), actor=nurlybek)
    assert report["removed"] == 1
    assert Competition.objects.filter(student=student).count() == 0
    assert Competition.all_objects.filter(student=student).count() == 1


@pytest.mark.django_db
def test_directors_do_not_upload_competitions(api, kymbat, nurlybek):
    """Файл выступлений принимается только от администратора (фаза 35) — владелец домена тоже получает отказ."""
    for user in (kymbat, nurlybek):
        api.force_authenticate(user)
        assert api.post("/api/competitions/import/preview/", {}, format="multipart").status_code == 403


# --- Материалы: выкладывает и директор талантов --------------------------


@pytest.mark.django_db
def test_curator_material_goes_straight_to_the_library(api, arman, db):
    """Материал Армана не встаёт в очередь к самому себе.

    Он и есть проверка: отправлять его материал себе на модерацию —
    ритуал ради ритуала. Автора-ученика у такой записи нет, поэтому
    ни XP, ни записи в портфолио она не создаёт (инвариант №12).
    """
    from directories.models import OlympiadSubject
    from engagement.models import XPEvent
    from materials.models import MaterialStatus, StudyMaterial

    subject = OlympiadSubject.objects.create(name="Физика")
    api.force_authenticate(arman)
    response = api.post(
        "/api/materials/",
        {
            "subject": subject.pk,
            "topic": "Термодинамика",
            "title": "Разбор второго начала",
            "source_kind": "own_analysis",
            "rights_confirmed": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.content

    material = StudyMaterial.objects.get(pk=response.json()["id"])
    assert material.status == MaterialStatus.APPROVED
    assert material.author_id is None
    assert material.staff_author_id == arman.pk
    assert material.author_title == arman.full_name or material.author_title == arman.email
    assert not XPEvent.objects.exists()


@pytest.mark.django_db
def test_outsider_still_cannot_upload(api, make_user):
    """Раздел закрыт: сотрудник не из домена талантов туда не пишет."""
    from accounts.models import Role as R

    api.force_authenticate(make_user(R.DIRECTOR_ADMISSION, email="asem31@example.kz"))
    response = api.post("/api/materials/", {"title": "Чужое"}, format="json")
    assert response.status_code == 404


@pytest.mark.django_db
def test_curator_sees_only_own_materials_under_mine(api, arman, db):
    """«Мои материалы» у Армана — его собственные, а не вся библиотека."""
    from directories.models import OlympiadSubject
    from materials.models import MaterialStatus, StudyMaterial
    from students.models import Student

    subject = OlympiadSubject.objects.create(name="Физика")
    pupil = Student.objects.create(
        last_name="Ученикова",
        first_name="Аруна",
        email="pupil31@example.kz",
        grade=11,
        graduation_year=2027,
        in_olympiad_group=True,
    )
    StudyMaterial.objects.create(
        author=pupil, subject=subject, topic="Оптика", title="Чужой разбор", status=MaterialStatus.APPROVED
    )
    mine = StudyMaterial.objects.create(
        staff_author=arman, subject=subject, topic="Механика", title="Мой разбор", status=MaterialStatus.APPROVED
    )

    api.force_authenticate(arman)
    payload = api.get("/api/materials/?mine=true").json()
    assert [row["id"] for row in payload["results"]] == [mine.pk]
