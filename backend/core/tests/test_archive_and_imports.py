"""Фаза 14: мягкое удаление, архив и отмена импорта целиком.

Инвариант №13 проверяется буквально: удалённый ученик исчезает из списков,
но остаётся в базе и в аудите, а из архива возвращается со всеми связями.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.passwords import set_password
from core.archive import archive, collect, preview, restore
from core.audit import apply_changes
from core.imports import revert_batch
from core.models import ArchiveEntry, AuditLog, ImportBatch
from roadmap.models import Essay, Task
from students.import_service import apply_preview
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)
from universities.models import Program, StudentUniversity, University

PASSWORD = "Архив!Проверка2026"


def make_user(email: str, role: str) -> User:
    user = User.objects.create_user(email=email, password=None, role=role)
    set_password(user, PASSWORD)
    return user


def login(user: User) -> APIClient:
    client = APIClient()
    client.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    return client


@pytest.fixture
def admin(db) -> User:
    return make_user("archive.admin@school.kz", Role.ADMIN)


@pytest.fixture
def exam_director(db) -> User:
    return make_user("archive.exam@school.kz", Role.DIRECTOR_EXAM)


@pytest.fixture
def talent_director(db) -> User:
    return make_user("archive.talent@school.kz", Role.DIRECTOR_TALENT)


@pytest.fixture
def learner(db) -> Student:
    group = StudyGroup.objects.create(code="11Z", grade=11)
    person = Student.objects.create(
        last_name="Ахметова",
        first_name="Алия",
        email="aliya@school.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=person)
    person.exam.ielts_current = Decimal("6.0")
    person.exam.save()

    university = University.objects.create(name="University of Testing", country="Канада")
    for name in ("Computer Science", "Economics"):
        program = Program.objects.create(university=university, name=name)
        StudentUniversity.objects.create(student=person, program=program)
    for title in ("Сдать IELTS", "Собрать документы", "Написать эссе"):
        Task.objects.create(student=person, title=title, category="test")
    Essay.objects.create(student=person, essay_type="personal_statement", title="Personal statement")
    return person


# --- мягкое удаление ------------------------------------------------------


@pytest.mark.django_db
def test_branch_collects_everything_that_goes_along(learner):
    branch = collect(learner)
    labels = {type(item).__name__ for item in branch}

    assert "Student" in labels
    assert {"StudentUniversity", "Task", "Essay", "ExamProfile"} <= labels


@pytest.mark.django_db
def test_preview_speaks_in_numbers_not_in_are_you_sure(learner):
    payload = preview(learner)

    assert payload["title"] == "Ахметова Алия"
    assert "Удалить" in payload["what"]
    assert payload["related_count"] >= 6
    assert "2 — вузы учеников" in payload["summary"]
    assert "3 — задачи" in payload["summary"]
    # удаление тянет чужую работу — просим набрать слово
    assert payload["confirm_word"] == "УДАЛИТЬ"


@pytest.mark.django_db
def test_archived_student_disappears_from_lists_but_stays_in_base(learner, admin):
    archive(learner, actor=admin)

    assert Student.objects.filter(pk=learner.pk).count() == 0
    assert Student.all_objects.filter(pk=learner.pk).count() == 1
    # связанное ушло вместе с ним
    assert Task.objects.filter(student=learner).count() == 0
    assert StudentUniversity.objects.filter(student=learner).count() == 0


@pytest.mark.django_db
def test_audit_survives_deletion(learner, admin):
    apply_changes(learner.exam, {"ielts_current": Decimal("7.0")}, actor=admin)
    before = AuditLog.objects.filter(student_id=learner.pk).count()
    assert before > 0

    archive(learner, actor=admin)

    assert AuditLog.objects.filter(student_id=learner.pk).count() == before


@pytest.mark.django_db
def test_restore_brings_back_the_whole_branch(learner, admin):
    entry = archive(learner, actor=admin)
    result = restore(entry, actor=admin)

    assert result["restored"] >= 7
    assert Student.objects.filter(pk=learner.pk).count() == 1
    assert Task.objects.filter(student=learner).count() == 3
    assert StudentUniversity.objects.filter(student=learner).count() == 2
    assert Essay.objects.filter(student=learner).count() == 1


@pytest.mark.django_db
def test_restore_does_not_raise_separately_deleted_records(learner, admin):
    """Задача, удалённая отдельно и раньше, не должна всплыть с учеником."""
    task = learner.tasks.first()
    archive(task, actor=admin)

    entry = archive(learner, actor=admin)
    restore(entry, actor=admin)

    assert Task.objects.filter(student=learner).count() == 2
    assert Task.all_objects.filter(pk=task.pk, archived_at__isnull=False).exists()


# --- права на удаление ----------------------------------------------------


@pytest.mark.django_db
def test_only_admin_deletes_a_student(learner, exam_director, admin):
    denied = login(exam_director).delete(f"/api/students/{learner.pk}/")
    assert denied.status_code == 403
    assert Student.objects.filter(pk=learner.pk).exists()

    allowed = login(admin).delete(f"/api/students/{learner.pk}/")
    assert allowed.status_code == 200
    assert not Student.objects.filter(pk=learner.pk).exists()


@pytest.mark.django_db
def test_director_cannot_delete_in_someone_elses_domain(learner, talent_director, exam_director):
    attempt = learner.exam_attempts.create(
        exam_type="IELTS", attempt_format="official", date=date.today(), total_score=Decimal("6.5")
    )

    denied = login(talent_director).delete(f"/api/attempts/{attempt.pk}/")
    assert denied.status_code == 403
    assert learner.exam_attempts.filter(pk=attempt.pk).exists()

    allowed = login(exam_director).delete(f"/api/attempts/{attempt.pk}/")
    assert allowed.status_code == 200
    assert not learner.exam_attempts.filter(pk=attempt.pk).exists()


@pytest.mark.django_db
def test_delete_preview_endpoint_answers_with_human_text(learner, admin):
    response = login(admin).get(f"/api/delete-preview/?model=students.Student&id={learner.pk}")

    assert response.status_code == 200
    assert response.data["title"] == "Ахметова Алия"
    assert response.data["soft"] is True
    assert any("архив" in line for line in response.data["consequences"])


@pytest.mark.django_db
def test_reference_record_held_by_students_refuses_with_reason(learner, admin):
    director = make_user("archive.admission@school.kz", Role.DIRECTOR_ADMISSION)
    program = StudentUniversity.objects.filter(student=learner).first().program

    response = login(director).delete(f"/api/programs/{program.pk}/")

    assert response.status_code == 409
    assert "Вузы учеников" in response.data["detail"]
    assert Program.objects.filter(pk=program.pk).exists()


@pytest.mark.django_db
def test_archive_screen_is_for_admin_only(learner, admin, exam_director):
    archive(learner, actor=admin)

    assert login(exam_director).get("/api/archive/").status_code == 403

    rows = login(admin).get("/api/archive/").data
    assert len(rows) == 1
    assert rows[0]["title"] == "Ахметова Алия"
    assert rows[0]["related_count"] >= 6


@pytest.mark.django_db
def test_restore_from_archive_screen(learner, admin):
    archive(learner, actor=admin)
    entry = ArchiveEntry.objects.get()

    response = login(admin).post(f"/api/archive/{entry.pk}/restore/")

    assert response.status_code == 200
    assert Student.objects.filter(pk=learner.pk).exists()
    entry.refresh_from_db()
    assert entry.is_restored


@pytest.mark.django_db
def test_deleting_a_user_switches_off_access_and_keeps_the_journal(admin):
    victim = make_user("archive.victim@school.kz", Role.DIRECTOR_SPORT)

    response = login(admin).delete(f"/api/users/{victim.pk}/")

    assert response.status_code == 200
    victim.refresh_from_db()
    assert victim.is_active is False
    assert User.objects.filter(pk=victim.pk).exists()

    entry = ArchiveEntry.objects.get(model_label="accounts.User")
    restore(entry, actor=admin)
    victim.refresh_from_db()
    assert victim.is_active is True


# --- история загрузок и отмена импорта ------------------------------------


def import_rows(learner: Student, value: str) -> list[dict]:
    return [
        {
            "student": learner.pk,
            "changes": [
                {"model": "students.ExamProfile", "field": "ielts_current", "old": "", "new": value, "raw": value}
            ],
        }
    ]


@pytest.mark.django_db
def test_import_lands_in_history_and_reverts_whole(learner, exam_director):
    result = apply_preview(
        preview_rows=import_rows(learner, "7.0"),
        role=Role.DIRECTOR_EXAM,
        actor=exam_director,
        file_name="ielts.csv",
    )
    batch = ImportBatch.objects.get(pk=result["batch"])
    assert batch.file_name == "ielts.csv"
    assert batch.audit_entries.count() == 1

    learner.exam.refresh_from_db()
    assert learner.exam.ielts_current == Decimal("7.0")

    report = revert_batch(batch, actor=exam_director)

    assert report["reverted"] == 1
    learner.exam.refresh_from_db()
    assert learner.exam.ielts_current == Decimal("6.0")
    batch.refresh_from_db()
    assert batch.status == ImportBatch.Status.REVERTED


@pytest.mark.django_db
def test_revert_leaves_alone_what_was_edited_by_hand(learner, exam_director):
    result = apply_preview(
        preview_rows=import_rows(learner, "7.0"),
        role=Role.DIRECTOR_EXAM,
        actor=exam_director,
        file_name="ielts.csv",
    )
    batch = ImportBatch.objects.get(pk=result["batch"])

    # директор поправил то же поле руками уже после загрузки
    apply_changes(learner.exam, {"ielts_current": Decimal("7.5")}, actor=exam_director)

    report = revert_batch(batch, actor=exam_director)

    assert report["reverted"] == 0
    assert len(report["skipped"]) == 1
    assert "правили руками" in report["skipped"][0]["reason"]
    learner.exam.refresh_from_db()
    assert learner.exam.ielts_current == Decimal("7.5")
    batch.refresh_from_db()
    assert batch.status == ImportBatch.Status.PARTIAL


@pytest.mark.django_db
def test_twenty_rows_revert_writes_twenty_entries_back(db, exam_director):
    people = []
    for i in range(20):
        person = Student.objects.create(
            last_name=f"Ученик{i}", first_name="Тест", email=f"s{i}@school.kz", grade=11, graduation_year=2027
        )
        ExamProfile.objects.create(student=person, ielts_current=Decimal("6.0"))
        people.append(person)

    rows = [
        {
            "student": person.pk,
            "changes": [
                {"model": "students.ExamProfile", "field": "ielts_current", "old": "6.0", "new": "7.0", "raw": "7.0"}
            ],
        }
        for person in people
    ]
    result = apply_preview(preview_rows=rows, role=Role.DIRECTOR_EXAM, actor=exam_director, file_name="двадцать.csv")
    batch = ImportBatch.objects.get(pk=result["batch"])
    assert batch.rows_updated == 20

    before = AuditLog.objects.count()
    report = revert_batch(batch, actor=exam_director)

    assert report["reverted"] == 20
    assert AuditLog.objects.count() == before + 20
    assert all(p.exam.ielts_current == Decimal("6.0") for p in Student.objects.all())


@pytest.mark.django_db
def test_import_history_is_not_open_to_a_foreign_domain(learner, exam_director, talent_director):
    result = apply_preview(
        preview_rows=import_rows(learner, "7.0"),
        role=Role.DIRECTOR_EXAM,
        actor=exam_director,
        file_name="ielts.csv",
    )
    denied = login(talent_director).post(f"/api/imports/{result['batch']}/revert/")

    assert denied.status_code == 403
    learner.exam.refresh_from_db()
    assert learner.exam.ielts_current == Decimal("7.0")


@pytest.mark.django_db
def test_second_revert_is_refused(learner, exam_director):
    result = apply_preview(
        preview_rows=import_rows(learner, "7.0"),
        role=Role.DIRECTOR_EXAM,
        actor=exam_director,
        file_name="ielts.csv",
    )
    client = login(exam_director)
    assert client.post(f"/api/imports/{result['batch']}/revert/").status_code == 200
    assert client.post(f"/api/imports/{result['batch']}/revert/").status_code == 400


# --- Фаза 29: автор загрузки и очистка истории ------------------------------


@pytest.mark.django_db
def test_new_upload_records_who_did_it(exam_director, learner):
    """В новых записях истории стоит имя автора, а не «неизвестно кто».

    Старые записи так и останутся безымянными — их автора уже не узнать,
    и врать про него нельзя.
    """
    from students.import_service import apply_preview

    result = apply_preview(
        preview_rows=[
            {
                "row": 2,
                "student": learner.pk,
                "changes": [
                    {"model": "students.ExamProfile", "field": "ielts_current", "old": "", "new": "7.0", "raw": "7.0"}
                ],
            }
        ],
        role=Role.DIRECTOR_EXAM,
        actor=exam_director,
        file_name="с-автором.csv",
    )

    batch = ImportBatch.objects.get(pk=result["batch"])
    assert batch.actor_id == exam_director.pk


@pytest.mark.django_db
def test_history_cleanup_keeps_the_journal(client, make_user, exam_director, learner):
    """Записи о загрузках уходят, а правки в журнале остаются.

    По ним читают историю изменений: без них «кто поменял этот балл»
    станет вопросом без ответа (инвариант №13).
    """
    from django.utils import timezone

    from students.import_service import apply_preview

    result = apply_preview(
        preview_rows=[
            {
                "row": 2,
                "student": learner.pk,
                "changes": [
                    {"model": "students.ExamProfile", "field": "ielts_current", "old": "", "new": "7.5", "raw": "7.5"}
                ],
            }
        ],
        role=Role.DIRECTOR_EXAM,
        actor=exam_director,
        file_name="старая.csv",
    )
    ImportBatch.objects.filter(pk=result["batch"]).update(created_at=timezone.now() - timezone.timedelta(days=400))
    entries_before = AuditLog.objects.count()

    admin = make_user(Role.ADMIN, email="admin.cleanup@example.kz")
    client.force_login(admin)

    preview = client.get("/api/imports/cleanup/?days=180").json()
    assert preview["entries"] == 1

    done = client.post("/api/imports/cleanup/", {"days": 180}, content_type="application/json").json()

    assert done["removed"] == 1
    assert not ImportBatch.objects.filter(pk=result["batch"]).exists()
    assert AuditLog.objects.count() == entries_before, "журнал изменений не должен пострадать"


@pytest.mark.django_db
def test_only_admin_cleans_the_history(client, exam_director):
    client.force_login(exam_director)
    assert client.get("/api/imports/cleanup/?days=30").status_code == 403
