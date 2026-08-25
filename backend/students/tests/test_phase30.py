"""Фаза 30: полный набор действий, видимость данных ученику, контакты.

Проверяем то, что действительно ломается:

* права по доменам на правку и удаление — включая новую модель контактов;
* инвариант №7 с обеих сторон: ученик видит про себя всё, кроме трёх
  оценочных меток, и метки не утекают ни в одном ответе API;
* сопоставление контактов при импорте и откат загрузки.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import Role
from core.domains import DOMAINS, iter_field_specs
from students.models import ContactChannel, ContactRelation, ParentContact


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def saltanat(make_user):
    """Директор школы — владелец домена `behavior`, ведёт контакты."""
    return make_user(Role.DIRECTOR_BEHAVIOR, email="saltanat@example.kz")


@pytest.fixture
def kymbat(make_user):
    return make_user(Role.DIRECTOR_EXAM, email="kymbat@example.kz")


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, email="admin30@example.kz")


@pytest.fixture
def pupil(make_user, student):
    """Учётная запись ученика, привязанная к карточке."""
    user = make_user(Role.STUDENT, email=student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


# --- Инвариант №7: ученик видит про себя всё, кроме трёх меток ----------


#: Ровно эти три поля ученику не показываются. Список в тесте написан
#: словами, а не собран из реестра: если кто-то пометит `internal_label`
#: у обычного поля, тест должен упасть, а не согласиться с новым составом.
LABEL_FIELDS = {
    ("students.BehaviorProfile", "status"),
    ("students.AdmissionProfile", "status"),
    ("students.TalentProfile", "portfolio_status"),
}


def test_only_three_fields_are_internal_labels():
    """Реестр помечает ярлыками ровно три поля — не больше и не меньше.

    Фаза 30 началась с того, что ученику не показывали балл IELTS. Поле
    оказалось не скрыто, но проверка нужна с обеих сторон: и «ярлык
    не показан», и «обычное поле ярлыком не помечено».
    """
    marked = {(model.label, spec.name) for _, model, spec in iter_field_specs() if spec.internal_label}
    assert marked == LABEL_FIELDS


@pytest.mark.django_db
def test_student_sees_every_own_field_except_labels(api, pupil, student, kymbat):
    """Балл, внесённый директором, ученик видит. Ярлык — нет."""
    from core.audit import apply_changes
    from core.domains import Source

    apply_changes(student.exam, {"ielts_current": "6.5"}, actor=kymbat, source=Source.MANUAL)
    apply_changes(student.behavior, {"attendance_percent": 88, "status": "critical"}, actor=kymbat)

    api.force_authenticate(pupil)
    payload = api.get("/api/students/me/").json()

    assert str(payload["exam"]["ielts_current"]) == "6.5"
    assert payload["behavior"]["attendance_percent"] == 88
    assert "status" not in payload["behavior"]

    # каждое поле реестра, кроме трёх меток, обязано быть в ответе
    for domain in DOMAINS.values():
        for model in domain.models:
            if not model.label.endswith("Profile"):
                continue
            for spec in model.fields:
                hidden = (model.label, spec.name) in LABEL_FIELDS
                present = spec.name in payload[domain.code]
                assert present is not hidden, f"{domain.code}.{spec.name}: скрыто={not present}"


@pytest.mark.django_db
def test_labels_never_leak_into_any_student_response(api, pupil, student, kymbat):
    """Ни один ответ API роли `student` не содержит значений-ярлыков."""
    from core.audit import apply_changes

    apply_changes(student.behavior, {"status": "critical"}, actor=kymbat)
    apply_changes(student.admission, {"status": "C"}, actor=kymbat)
    apply_changes(student.talent, {"portfolio_status": "weak"}, actor=kymbat)

    api.force_authenticate(pupil)
    forbidden = ("needs_supervision", "can_execute", "critical", "portfolio_status")
    for path in (
        "/api/students/me/",
        f"/api/students/{student.pk}/",
        "/api/meta/domains/",
        "/api/attempts/",
        "/api/activities/",
        "/api/competitions/",
        "/api/contacts/",
    ):
        response = api.get(path)
        assert response.status_code == 200, path
        body = response.content.decode()
        for word in forbidden:
            assert word not in body, f"{path} отдал ярлык «{word}»"


# --- Задача 1: где есть «добавить», есть «изменить» и «удалить» ---------


@pytest.mark.django_db
def test_admin_edits_the_registry_card(api, admin, student):
    """Администратор правит имя, класс, группу и почту ученика."""
    api.force_authenticate(admin)
    response = api.patch(
        f"/api/students/{student.pk}/",
        {"last_name": "Исправленов", "grade": 10},
        format="json",
    )
    assert response.status_code == 200, response.content
    student.refresh_from_db()
    assert student.last_name == "Исправленов"
    assert student.grade == 10


@pytest.mark.django_db
def test_director_cannot_edit_the_registry_card(api, kymbat, student):
    """Реестровую карточку ведёт администратор, доменные поля — директор."""
    api.force_authenticate(kymbat)
    response = api.patch(f"/api/students/{student.pk}/", {"last_name": "Чужов"}, format="json")
    assert response.status_code == 403
    student.refresh_from_db()
    assert student.last_name == "Тестов"


@pytest.mark.django_db
def test_group_can_be_edited_and_only_by_admin(api, admin, kymbat, group):
    """Учебную группу правит администратор, чужой роли отказ."""
    api.force_authenticate(kymbat)
    assert api.patch(f"/api/groups/{group.pk}/", {"curator": "Чужой"}, format="json").status_code == 403

    api.force_authenticate(admin)
    response = api.patch(f"/api/groups/{group.pk}/", {"curator": "Салтанат"}, format="json")
    assert response.status_code == 200, response.content
    group.refresh_from_db()
    assert group.curator == "Салтанат"


@pytest.mark.django_db
def test_row_owner_can_create_edit_and_delete(api, kymbat, student):
    """У попытки экзамена есть все три действия, и все — у владельца домена."""
    api.force_authenticate(kymbat)
    created = api.post(
        "/api/attempts/",
        {"student": student.pk, "exam_type": "IELTS", "attempt_format": "mock", "date": "2026-03-01"},
        format="json",
    )
    assert created.status_code == 201, created.content
    attempt_id = created.json()["id"]

    edited = api.patch(f"/api/attempts/{attempt_id}/", {"total_score": "6.5"}, format="json")
    assert edited.status_code == 200, edited.content

    removed = api.delete(f"/api/attempts/{attempt_id}/")
    assert removed.status_code == 200, removed.content


@pytest.mark.django_db
def test_foreign_director_cannot_edit_a_row(api, saltanat, kymbat, student):
    """Чужую строку не поправить: право на правку то же, что на заведение."""
    from students.models import AttemptFormat, ExamAttempt, ExamType

    attempt = ExamAttempt.objects.create(
        student=student, exam_type=ExamType.IELTS, attempt_format=AttemptFormat.MOCK, date="2026-03-01"
    )
    api.force_authenticate(saltanat)
    assert api.patch(f"/api/attempts/{attempt.pk}/", {"total_score": "9"}, format="json").status_code == 403
    assert api.delete(f"/api/attempts/{attempt.pk}/").status_code == 403


@pytest.mark.django_db
def test_comment_is_edited_only_by_its_author(api, make_user, student, saltanat, kymbat):
    """Чужую реплику не переписывает никто — даже другой директор."""
    from roadmap.models import Task, TaskComment

    task = Task.objects.create(student=student, title="Собрать документы")
    comment = TaskComment.objects.create(task=task, author=saltanat, text="Проверьте сроки")

    api.force_authenticate(kymbat)
    assert api.patch(f"/api/task-comments/{comment.pk}/", {"text": "Не я писал"}, format="json").status_code == 403

    api.force_authenticate(saltanat)
    response = api.patch(f"/api/task-comments/{comment.pk}/", {"text": "Уточнил"}, format="json")
    assert response.status_code == 200, response.content
    comment.refresh_from_db()
    assert comment.text == "Уточнил"


# --- Задача 4: контакты родителей --------------------------------------


@pytest.mark.django_db
def test_contacts_belong_to_the_school_director(api, saltanat, kymbat, student):
    """Контакты ведёт домен `behavior`: остальные их видят, но не правят."""
    api.force_authenticate(kymbat)
    denied = api.post(
        "/api/contacts/",
        {"student": student.pk, "full_name": "Чужая мама", "relation": ContactRelation.MOTHER, "phone": "+7"},
        format="json",
    )
    assert denied.status_code == 403

    api.force_authenticate(saltanat)
    created = api.post(
        "/api/contacts/",
        {
            "student": student.pk,
            "full_name": "Ахметова Гульнара",
            "relation": ContactRelation.MOTHER,
            "phone": "+7 701 000 00 01",
            "preferred_channel": ContactChannel.WHATSAPP,
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    contact_id = created.json()["id"]

    edited = api.patch(f"/api/contacts/{contact_id}/", {"phone": "+7 701 000 00 02"}, format="json")
    assert edited.status_code == 200, edited.content

    removed = api.delete(f"/api/contacts/{contact_id}/")
    assert removed.status_code == 200, removed.content
    # инвариант №13: у контакта есть история, поэтому он уходит в архив
    assert ParentContact.objects.filter(pk=contact_id).count() == 0
    assert ParentContact.all_objects.filter(pk=contact_id).count() == 1


@pytest.mark.django_db
def test_contact_without_phone_and_email_is_refused(api, saltanat, student):
    """Контакт, по которому не связаться, заводить незачем."""
    api.force_authenticate(saltanat)
    response = api.post(
        "/api/contacts/",
        {"student": student.pk, "full_name": "Без связи", "relation": ContactRelation.OTHER},
        format="json",
    )
    assert response.status_code == 400
    assert "телефон" in response.content.decode().lower()


@pytest.mark.django_db
def test_only_one_primary_contact_per_student(student):
    """Второй «основной» снимает признак с первого, а не появляется рядом."""
    first = ParentContact.objects.create(
        student=student, full_name="Мама", relation=ContactRelation.MOTHER, phone="1", is_primary=True
    )
    second = ParentContact.objects.create(
        student=student, full_name="Папа", relation=ContactRelation.FATHER, phone="2", is_primary=True
    )
    first.refresh_from_db()
    second.refresh_from_db()
    assert not first.is_primary
    assert second.is_primary


@pytest.mark.django_db
def test_student_sees_own_contacts_and_not_others(api, pupil, student, make_user, saltanat):
    """Свои контакты ученику видны, чужие — нет."""
    from students.models import Student

    other = Student.objects.create(
        last_name="Чужов", first_name="Чужой", email="other30@example.kz", grade=11, graduation_year=2027
    )
    ParentContact.objects.create(student=student, full_name="Моя мама", relation=ContactRelation.MOTHER, phone="1")
    ParentContact.objects.create(student=other, full_name="Чужая мама", relation=ContactRelation.MOTHER, phone="2")

    api.force_authenticate(pupil)
    body = api.get("/api/contacts/").json()
    names = {row["full_name"] for row in body["results"]}
    assert names == {"Моя мама"}


@pytest.mark.django_db
def test_student_cannot_edit_own_contacts(api, pupil, student):
    """Ученик контакты читает, но не ведёт: это домен директора школы."""
    contact = ParentContact.objects.create(
        student=student, full_name="Мама", relation=ContactRelation.MOTHER, phone="1"
    )
    api.force_authenticate(pupil)
    assert api.patch(f"/api/contacts/{contact.pk}/", {"phone": "9"}, format="json").status_code == 403
    assert api.delete(f"/api/contacts/{contact.pk}/").status_code == 403


# --- Импорт контактов ---------------------------------------------------


HEADER = ["Почта ученика", "ФИО родителя", "Кем приходится", "Телефон", "Способ связи", "Основной"]


@pytest.mark.django_db
def test_contacts_import_matches_students_and_skips_duplicates(student):
    """Ученик находится по почте, повторная загрузка не плодит дублей."""
    from students.contacts_import import apply_rows, build_preview

    rows = [[student.email, "Ахметова Гульнара", "мама", "+7 701 111 22 33", "whatsapp", "да"]]
    preview = build_preview(header=HEADER, rows=rows)
    assert preview.as_dict()["will_create"] == 1
    assert preview.rows[0].relation == ContactRelation.MOTHER
    assert preview.rows[0].preferred_channel == ContactChannel.WHATSAPP
    assert preview.rows[0].is_primary is True

    apply_rows(rows=[row.as_dict() for row in preview.ready])
    assert ParentContact.objects.filter(student=student).count() == 1

    again = build_preview(header=HEADER, rows=rows)
    assert again.as_dict()["will_create"] == 0
    assert again.rows[0].status == "exists"


@pytest.mark.django_db
def test_contacts_import_names_the_unmatched_row(student):
    """Ненайденный ученик — это ошибка строки, а не молчаливый пропуск."""
    from students.contacts_import import build_preview

    preview = build_preview(header=HEADER, rows=[["нет@такого.kz", "Кто-то", "мама", "+7", "", ""]])
    assert preview.rows[0].status == "error"
    assert "нет@такого.kz" in preview.rows[0].reason


@pytest.mark.django_db
def test_reverting_a_contacts_import_removes_what_it_created(student, saltanat):
    """Откат загрузки убирает заведённые контакты, а не обнуляет их поля."""
    from core.imports import revert_batch
    from core.models import ImportBatch
    from students.contacts_import import apply_rows, build_preview

    preview = build_preview(
        header=HEADER, rows=[[student.email, "Ахметова Гульнара", "мама", "+7 701 111 22 33", "", ""]]
    )
    result = apply_rows(rows=[row.as_dict() for row in preview.ready], actor=saltanat)
    assert ParentContact.objects.filter(student=student).count() == 1

    batch = ImportBatch.objects.get(pk=result["batch"])
    report = revert_batch(batch, actor=saltanat)
    assert report["removed"] == 1
    assert ParentContact.objects.filter(student=student).count() == 0
    # запись осталась в архиве: журнал не должен ссылаться в пустоту
    assert ParentContact.all_objects.filter(student=student).count() == 1


@pytest.mark.django_db
def test_director_creates_and_edits_a_task_and_an_essay(api, kymbat, student):
    """Задачу и эссе директор заводит с карточки ученика тем же телом, что шлёт экран.

    Сквозные модели: владельца-домена у них нет, предлагать и вести их
    вправе любой директор (`SHARED_WRITERS`). До фазы 30 в интерфейсе
    не было ни заведения, ни правки — только удаление.
    """
    api.force_authenticate(kymbat)

    task = api.post(
        "/api/tasks/",
        {
            "student": student.pk,
            "title": "Собрать документы",
            "category": "documents",
            "priority": "high",
            "due_date": "2026-11-01",
            "description": "",
        },
        format="json",
    )
    assert task.status_code == 201, task.content
    edited = api.patch(f"/api/tasks/{task.json()['id']}/", {"status": "in_progress"}, format="json")
    assert edited.status_code == 200, edited.content
    assert api.delete(f"/api/tasks/{task.json()['id']}/").status_code == 200

    essay = api.post(
        "/api/essays/",
        {"student": student.pk, "title": "Personal Statement", "essay_type": "personal_statement"},
        format="json",
    )
    assert essay.status_code == 201, essay.content
    renamed = api.patch(f"/api/essays/{essay.json()['id']}/", {"status": "review"}, format="json")
    assert renamed.status_code == 200, renamed.content
    assert api.delete(f"/api/essays/{essay.json()['id']}/").status_code == 200


@pytest.mark.django_db
def test_student_moves_own_task_but_does_not_rewrite_it(api, pupil, student, kymbat):
    """Ученик двигает свою задачу по доске и только.

    Формулировку задачи ставит директор. До фазы 30 обычный PATCH был
    ученику открыт: он мог переписать чужую задачу и подменить её срок,
    а выглядело это как обычное сохранение.
    """
    from roadmap.models import Task

    task = Task.objects.create(student=student, title="Собрать документы", author=kymbat)

    api.force_authenticate(pupil)
    assert api.patch(f"/api/tasks/{task.pk}/", {"title": "Ничего не делать"}, format="json").status_code == 403
    assert api.delete(f"/api/tasks/{task.pk}/").status_code == 403
    assert api.post("/api/tasks/", {"student": student.pk, "title": "Своя"}, format="json").status_code == 403

    moved = api.post(f"/api/tasks/{task.pk}/status/", {"status": "done"}, format="json")
    assert moved.status_code == 200, moved.content
    task.refresh_from_db()
    assert task.title == "Собрать документы"
    assert task.status == "done"


@pytest.mark.django_db
def test_comment_cannot_be_written_under_a_foreign_task(api, pupil, student, kymbat):
    """Создание комментария проверяет видимость задачи, а не только чтение."""
    from roadmap.models import Task
    from students.models import Student

    other = Student.objects.create(
        last_name="Чужов", first_name="Чужой", email="foreign30@example.kz", grade=11, graduation_year=2027
    )
    foreign_task = Task.objects.create(student=other, title="Чужая задача", author=kymbat)

    api.force_authenticate(pupil)
    response = api.post("/api/task-comments/", {"task": foreign_task.pk, "text": "Привет"}, format="json")
    assert response.status_code == 403
