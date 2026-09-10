"""Фаза 67: правка учётной записи и удаление навсегда.

Три места, где ошибка стоит дорого.

**Почта — это логин.** Смена почты меняет вход, поэтому занятая почта
должна отвечать словами, а не пятисоткой из базы, и человек должен
узнать, что прежняя ссылка больше не придёт.

**Числа предпросмотра.** Модалка обещает, сколько будет потеряно.
Обещание проверяется единственным честным способом: посчитать до,
удалить, посчитать после. Если список последствий пишется текстом
в коде, он разойдётся с делом в первую же новую таблицу — поэтому
считается обходом настоящих связей.

**Журнал переживает удаление.** Это и есть цена, за которую удаление
вообще разрешили: ни одна строка не теряется, автор становится текстом.
"""

from __future__ import annotations

import pytest

from accounts.models import Role, User
from core import purge as erasing
from core.archive import archive, purge
from core.audit import apply_changes
from core.models import ArchiveEntry, AuditLog
from students.models import (
    AdmissionProfile,
    AttendanceDay,
    BehaviorProfile,
    BehaviorRemark,
    CuratorNote,
    ExamProfile,
    SportProfile,
    Student,
    StudentCredential,
    StudyGroup,
    TalentProfile,
)


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, email="admin.phase67@example.kz")


@pytest.fixture
def group(db):
    return StudyGroup.objects.create(code="CHICAGO", grade=11)


def make_student(group, last_name, first_name, email) -> Student:
    student = Student.objects.create(
        last_name=last_name,
        first_name=first_name,
        email=email,
        grade=11,
        group=group,
        graduation_year=2027,
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=student)
    return student


@pytest.fixture
def learner(group):
    return make_student(group, "Сериков", "Данияр", "serikov.phase67@school.kz")


def login(client, user):
    client.force_login(user)
    return client


# --- Правка учётной записи ---------------------------------------------------


@pytest.mark.django_db
def test_full_name_is_editable(client, admin, make_user):
    """Та самая дыра: в ФИО вписали почту, и починить это было нечем."""
    user = make_user(Role.DIRECTOR_SPORT, email="nurlybek.phase67@example.kz", full_name="Старое Имя")
    login(client, admin)

    response = client.patch(
        f"/api/users/{user.pk}/",
        {"full_name": "Нурлыбек Сериков"},
        content_type="application/json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.full_name == "Нурлыбек Сериков"


@pytest.mark.django_db
def test_email_change_moves_the_login_and_says_so(client, admin, make_user):
    """Смена почты меняет вход — и об этом говорится прямо."""
    user = make_user(Role.DIRECTOR_SPORT, email="was.phase67@example.kz", full_name="Нурлыбек Сериков")
    login(client, admin)

    body = client.patch(
        f"/api/users/{user.pk}/",
        {"email": "now.phase67@example.kz"},
        content_type="application/json",
    ).json()

    user.refresh_from_db()
    assert user.email == "now.phase67@example.kz"
    assert body["login_changed"]["was"] == "was.phase67@example.kz"
    assert "вышлите приглашение заново" in body["login_changed"]["detail"]


@pytest.mark.django_db
def test_taken_email_is_refused_with_words(client, admin, make_user):
    """Занятая почта — отказ словами, а не пятисотка из базы."""
    make_user(Role.DIRECTOR_EXAM, email="taken.phase67@example.kz")
    user = make_user(Role.DIRECTOR_SPORT, email="mine.phase67@example.kz")
    login(client, admin)

    response = client.patch(
        f"/api/users/{user.pk}/",
        {"email": "taken.phase67@example.kz"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "занята" in response.json()["detail"]
    user.refresh_from_db()
    assert user.email == "mine.phase67@example.kz"


@pytest.mark.django_db
def test_edit_lands_in_the_journal(client, admin, make_user):
    """Правка видна в журнале: кто, что было, что стало."""
    user = make_user(Role.DIRECTOR_SPORT, email="journal.phase67@example.kz", full_name="Было Имя")
    login(client, admin)

    client.patch(f"/api/users/{user.pk}/", {"full_name": "Стало Имя"}, content_type="application/json")

    row = AuditLog.objects.filter(model_label="accounts.User", field_name="full_name").latest("id")
    assert row.old_value == "Было Имя"
    assert row.new_value == "Стало Имя"
    assert row.actor_id == admin.pk


@pytest.mark.django_db
def test_own_role_cannot_be_changed(client, admin):
    """Понизив себя по ошибке, вернуть роль было бы некому."""
    response = login(client, admin).patch(
        f"/api/users/{admin.pk}/",
        {"role": Role.STUDENT},
        content_type="application/json",
    )

    assert response.status_code == 400
    admin.refresh_from_db()
    assert admin.role == Role.ADMIN


@pytest.mark.django_db
def test_own_name_is_editable(client, admin):
    """Себя править можно — нельзя только менять себе роль."""
    response = login(client, admin).patch(
        f"/api/users/{admin.pk}/",
        {"full_name": "Мухаммед Тунгышбай"},
        content_type="application/json",
    )

    assert response.status_code == 200
    admin.refresh_from_db()
    assert admin.full_name == "Мухаммед Тунгышбай"


@pytest.mark.django_db
def test_only_admin_edits_users(client, make_user):
    director = make_user(Role.DIRECTOR_EXAM, email="kymbat.phase67@example.kz")
    victim = make_user(Role.DIRECTOR_SPORT, email="victim2.phase67@example.kz")

    response = login(client, director).patch(
        f"/api/users/{victim.pk}/", {"full_name": "Чужая Правка"}, content_type="application/json"
    )

    assert response.status_code == 403


# --- Предпросмотр удаления ------------------------------------------------------


@pytest.mark.django_db
def test_preview_numbers_match_what_is_really_erased(learner, admin, group):
    """Единственная честная проверка обещания: посчитать до и после.

    Модалка говорит числами, что уйдёт. Если предпросмотр расходится
    с делом, человек подтверждает не то, что видел.
    """
    apply_changes(learner.exam, {"ielts_current": "7.0"}, actor=admin)
    StudentCredential.objects.create(student=learner, kind="email", ciphertext="x")
    AttendanceDay.objects.create(student=learner, date="2026-09-01", present=False)
    BehaviorRemark.objects.create(student=learner, date="2026-09-01", text="Опоздал")
    CuratorNote.objects.create(student=learner, author=admin, author_role="curator", text="Заметка")

    before = {
        "credentials": StudentCredential.objects.count(),
        "attendance": AttendanceDay.objects.count(),
        "remarks": BehaviorRemark.objects.count(),
        "notes": CuratorNote.objects.count(),
    }

    numbers = erasing.preview(learner)
    promised = {row["title"]: row["count"] for row in numbers["erased"]}

    entry = archive(learner, actor=admin)
    purge(entry, actor=admin)

    assert StudentCredential.objects.count() == before["credentials"] - promised["Пароли учеников"]
    assert AttendanceDay.objects.count() == before["attendance"] - promised["Дни посещаемости"]
    assert BehaviorRemark.objects.count() == before["remarks"] - promised["Замечания"]
    assert CuratorNote.objects.count() == before["notes"] - promised["Заметки куратора"]
    assert not Student.all_objects.filter(pk=learner.pk).exists()


@pytest.mark.django_db
def test_preview_shows_the_effect_on_neighbours(learner, group, admin):
    """«В группе станет 19 учеников» — последствие видно тому, кто её откроет."""
    make_student(group, "Ержанова", "Малика", "erzhanova.phase67@school.kz")
    make_student(group, "Оспанов", "Тимур", "ospanov.phase67@school.kz")

    numbers = erasing.preview(learner)

    # склонение считает сервер: «станет 1 учеников» читалось бы как сбой
    assert any("В группе CHICAGO станет 2 ученика" in line for line in numbers["impact"])


@pytest.mark.django_db
def test_preview_counts_files_with_their_size(learner, admin):
    """Файлы считаются штуками и мегабайтами: их удаление необратимо."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from students.models import StudentDocument

    StudentDocument.objects.create(
        student=learner,
        doc_type="passport",
        file=SimpleUploadedFile("passport.pdf", b"x" * 2048, content_type="application/pdf"),
        size=2048,
    )

    numbers = erasing.preview(learner)
    files = next(row for row in numbers["erased"] if row["title"] == "Файлы на диске")

    assert files["count"] == 1
    assert numbers["bytes"] >= 2048


@pytest.mark.django_db
def test_preview_of_a_user_says_what_survives(admin, make_user, learner):
    """У учётной записи главное — сколько строк переживёт удаление."""
    author = make_user(Role.DIRECTOR_EXAM, email="author.phase67@example.kz", full_name="Кымбат Автор")
    apply_changes(learner.exam, {"ielts_current": "6.0"}, actor=author)

    numbers = erasing.preview(author)

    assert numbers["email"] == "author.phase67@example.kz"
    assert any(row["count"] >= 1 for row in numbers["kept"])
    assert "резервной копии" in numbers["warning"]


@pytest.mark.django_db
def test_preview_does_not_leak_passwords_or_note_text(client, learner, admin):
    """Предпросмотр отдаёт числа, а не содержимое: это не место для секретов."""
    StudentCredential.objects.create(student=learner, kind="email", ciphertext="секретный-шифртекст")
    CuratorNote.objects.create(student=learner, author=admin, author_role="curator", text="Тайная заметка")
    entry = archive(learner, actor=admin)

    body = login(client, admin).get(f"/api/archive/{entry.pk}/purge/").content.decode()

    assert "секретный-шифртекст" not in body
    assert "Тайная заметка" not in body
    assert "Пароли учеников" in body


# --- Само удаление ---------------------------------------------------------------


@pytest.mark.django_db
def test_journal_keeps_every_row_and_the_author_becomes_text(admin, make_user, learner):
    """Ни одна строка не теряется, автор перестаёт быть ссылкой."""
    author = make_user(Role.DIRECTOR_EXAM, email="kymbat.gone@example.kz", full_name="Кымбат Ушедшая")
    apply_changes(learner.exam, {"ielts_current": "7.5"}, actor=author)
    note = CuratorNote.objects.create(student=learner, author=author, author_role="curator", text="Заметка")

    rows_before = AuditLog.objects.count()
    entry = ArchiveEntry.objects.create(
        model_label="accounts.User", object_id=str(author.pk), title=author.email, kind_title="Учётная запись"
    )
    purge(entry, actor=admin)

    # строк не убыло: к журналу только добавилась запись о самом удалении
    assert AuditLog.objects.count() >= rows_before
    row = AuditLog.objects.filter(field_name="ielts_current").latest("id")
    assert row.actor_id is None
    assert "Кымбат Ушедшая" in row.actor_title
    assert "kymbat.gone@example.kz" in row.actor_title

    note.refresh_from_db()
    assert note.author_id is None
    assert "Кымбат Ушедшая" in note.author_title


@pytest.mark.django_db
def test_erasure_itself_is_recorded_forever(admin, make_user):
    """Кто удалил, кого, когда и что было удалено — остаётся навсегда."""
    victim = make_user(Role.DIRECTOR_SPORT, email="erased.phase67@example.kz", full_name="Стёртый Человек")
    entry = ArchiveEntry.objects.create(
        model_label="accounts.User", object_id=str(victim.pk), title=victim.email, kind_title="Учётная запись"
    )

    purge(entry, actor=admin)

    row = AuditLog.objects.filter(model_label="core.Erasure").latest("id")
    assert row.actor_id == admin.pk
    assert "Стёртый Человек" in row.new_value
    assert "erased.phase67@example.kz" in row.new_value


@pytest.mark.django_db
def test_student_data_is_gone_physically(learner, admin):
    """У ученика удаляется всё: карточка, пароли, посещаемость, замечания."""
    StudentCredential.objects.create(student=learner, kind="email", ciphertext="x")
    AttendanceDay.objects.create(student=learner, date="2026-09-02", present=False)
    BehaviorRemark.objects.create(student=learner, date="2026-09-02", text="Замечание")

    entry = archive(learner, actor=admin)
    purge(entry, actor=admin)

    assert not Student.all_objects.filter(pk=learner.pk).exists()
    assert not StudentCredential.objects.filter(student_id=learner.pk).exists()
    assert not AttendanceDay.objects.filter(student_id=learner.pk).exists()
    assert not BehaviorRemark.all_objects.filter(student_id=learner.pk).exists()
    assert not ExamProfile.all_objects.filter(student_id=learner.pk).exists()


@pytest.mark.django_db
def test_last_admin_is_refused(admin, make_user):
    """Без администратора не завести людей и не вернуть данные из архива."""
    someone = make_user(Role.DIRECTOR_EXAM, email="asker.phase67@example.kz")

    reason = erasing.refusal_for_user(admin, actor=someone)
    assert "последний администратор" in reason.lower()

    # появился второй — первого удалить уже можно
    User.objects.create_user(email="second.phase67@example.kz", password=None, role=Role.ADMIN)
    assert erasing.refusal_for_user(admin, actor=someone) == ""


@pytest.mark.django_db
def test_self_is_refused(admin, make_user):
    """Себя удалить нельзя — войти после этого будет некому."""
    User.objects.create_user(email="backup.phase67@example.kz", password=None, role=Role.ADMIN)

    reason = erasing.refusal_for_user(admin, actor=admin)

    assert "себя" in reason.lower()


@pytest.mark.django_db
def test_api_refuses_before_asking_for_the_email(client, admin):
    """Отказ виден на предпросмотре, а не после того, как почту набрали."""
    entry = ArchiveEntry.objects.create(
        model_label="accounts.User", object_id=str(admin.pk), title=admin.email, kind_title="Учётная запись"
    )

    body = login(client, admin).get(f"/api/archive/{entry.pk}/purge/").json()
    assert body["refusal"]

    refused = client.post(f"/api/archive/{entry.pk}/purge/", {"confirm": admin.email}, content_type="application/json")
    assert refused.status_code == 400
    assert User.objects.filter(pk=admin.pk).exists()


@pytest.mark.django_db
def test_only_admin_erases(client, make_user, learner):
    director = make_user(Role.DIRECTOR_EXAM, email="notadmin.phase67@example.kz")
    entry = ArchiveEntry.objects.create(
        model_label="students.Student", object_id=str(learner.pk), title=learner.full_name, kind_title="Ученик"
    )

    response = login(client, director).post(
        f"/api/archive/{entry.pk}/purge/", {"confirm": learner.email}, content_type="application/json"
    )

    assert response.status_code == 403
    assert Student.all_objects.filter(pk=learner.pk).exists()


# --- Чистка вымышленных после объединения -------------------------------------


@pytest.mark.django_db
def test_purge_fictional_still_works(group, admin):
    """Команда 64-й фазы после объединения кода делает то же самое."""
    from students import fictional

    student = make_student(group, "Вымышленный", "Ученик", "fake.phase67@probe.local")
    student.is_fictional = True
    student.save(update_fields=["is_fictional"])
    StudentCredential.objects.create(student=student, kind="email", ciphertext="x")
    real = make_student(group, "Настоящий", "Ученик", "real.phase67@school.kz")

    outcome = fictional.purge(actor=admin)

    assert outcome.students == 1
    assert not Student.all_objects.filter(pk=student.pk).exists()
    assert Student.all_objects.filter(pk=real.pk).exists()
    assert not StudentCredential.objects.filter(student_id=student.pk).exists()


@pytest.mark.django_db
def test_author_trails_registry_matches_the_models(db):
    """Реестр следов не должен разойтись с моделями: поля обязаны быть."""
    from django.apps import apps

    for label, link, title_field in erasing.AUTHOR_TRAILS:
        model = apps.get_model(label)
        names = {field.name for field in model._meta.get_fields()}
        assert link in names, f"{label}: нет поля {link}"
        assert title_field in names, f"{label}: нет поля {title_field}"
