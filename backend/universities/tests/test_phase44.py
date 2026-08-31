"""Фаза 44: стипендии.

Проверяем то, из-за чего раздел мог бы соврать ученику:

* справочник ведёт директор по поступлению, чужой директор получает 403;
* загруженная файлом запись приходит неподтверждённой (инвариант №14);
* подбор не может назвать стипендию мимо справочника (инвариант №10);
* дедлайн живёт у стипендии: он же в календаре, он же срок задачи
  (инвариант №4) — копии даты нигде нет.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from roadmap.models import Task
from students.calendar_feed import events_for
from universities.import_scholarships import import_scholarships
from universities.models import CatalogSource, SavedScholarship, Scholarship, University


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.fixture
def scholarship(db) -> Scholarship:
    return Scholarship.objects.create(
        name="Global Excellence Award",
        organizer="Test Foundation",
        country="Канада",
        level="bachelor",
        funding_type="full",
        amount_min=10000,
        amount_max=25000,
        currency="USD",
        for_international=True,
        deadline=timezone.localdate() + dt.timedelta(days=10),
        requirements="GPA не ниже 4.5",
    )


# --- Справочник -----------------------------------------------------------


@pytest.mark.django_db
def test_admission_director_keeps_the_directory(api, make_user):
    """Заводит, правит и убирает стипендии директор по поступлению."""
    api.force_authenticate(make_user("director_admission"))
    made = api.post(
        "/api/scholarships/",
        {"name": "Bolashak", "funding_type": "full", "country": "Казахстан"},
        format="json",
    )
    assert made.status_code == 201, made.data

    changed = api.patch(f"/api/scholarships/{made.data['id']}/", {"organizer": "Фонд"}, format="json")
    assert changed.status_code == 200, changed.data

    gone = api.delete(f"/api/scholarships/{made.data['id']}/")
    assert gone.status_code == 200, gone.data
    assert not Scholarship.objects.filter(pk=made.data["id"]).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["director_sport", "director_exam", "director_talent", "admin"])
def test_others_cannot_touch_the_directory(api, make_user, scholarship, role):
    """Чужой директор и администратор справочник не ведут — только читают."""
    api.force_authenticate(make_user(role))
    assert api.get("/api/scholarships/").status_code == 200
    made = api.post("/api/scholarships/", {"name": "X", "funding_type": "full"}, format="json")
    assert made.status_code == 403, made.data
    changed = api.patch(f"/api/scholarships/{scholarship.pk}/", {"country": "Иное"}, format="json")
    assert changed.status_code == 403, changed.data


@pytest.mark.django_db
def test_student_reads_but_does_not_write(api, student_user, scholarship):
    api.force_authenticate(student_user)
    listing = api.get("/api/scholarships/")
    assert listing.status_code == 200
    assert listing.data["results"][0]["name"] == scholarship.name
    assert api.post("/api/scholarships/", {"name": "X", "funding_type": "full"}, format="json").status_code == 403


@pytest.mark.django_db
def test_hidden_scholarship_is_invisible_to_the_student(api, student_user, scholarship):
    """Снятая с показа запись у ученика не появляется, у директора остаётся."""
    scholarship.is_active = False
    scholarship.save(update_fields=["is_active"])
    api.force_authenticate(student_user)
    assert api.get("/api/scholarships/").data["count"] == 0


# --- Каталог и фильтры ------------------------------------------------------


@pytest.mark.django_db
def test_filters_narrow_the_catalogue(api, student_user, scholarship):
    Scholarship.objects.create(name="Merit Grant", country="США", funding_type="partial", for_merit=True)
    api.force_authenticate(student_user)
    assert api.get("/api/scholarships/?country=Канада").data["count"] == 1
    assert api.get("/api/scholarships/?basis=merit").data["count"] == 1
    assert api.get("/api/scholarships/?funding_type=full").data["count"] == 1
    assert api.get("/api/scholarships/?q=Merit").data["count"] == 1


@pytest.mark.django_db
def test_overview_counts_and_keeps_currencies_apart(api, student_user, scholarship):
    """Суммы не складываются между валютами: курса мы не выдумываем."""
    Scholarship.objects.create(name="Euro Grant", funding_type="partial", amount_max=5000, currency="EUR")
    api.force_authenticate(student_user)
    data = api.get("/api/scholarship-overview/").data
    assert data["total"] == 2
    assert data["soon"] == 1
    currencies = {row["currency"]: row["amount"] for row in data["funding"]}
    assert currencies == {"USD": 25000, "EUR": 5000}


@pytest.mark.django_db
def test_deadline_reads_in_words(api, student_user, scholarship):
    """«дедлайн сегодня», «остался 1 день», «через N дней» — считает сервер."""
    api.force_authenticate(student_user)
    today = timezone.localdate()
    for days, expected in ((0, "дедлайн сегодня"), (1, "остался 1 день"), (5, "через 5 дней"), (-1, "срок прошёл")):
        scholarship.deadline = today + dt.timedelta(days=days)
        scholarship.save(update_fields=["deadline"])
        row = api.get("/api/scholarships/").data["results"][0]
        assert row["deadline_state"] == expected


# --- Сохранённые ------------------------------------------------------------


@pytest.mark.django_db
def test_student_saves_and_removes(api, student_user, student, scholarship):
    api.force_authenticate(student_user)
    saved = api.post(f"/api/scholarships-saved/{scholarship.pk}/")
    assert saved.status_code == 201, saved.data
    assert SavedScholarship.objects.filter(student=student).count() == 1
    assert api.get("/api/scholarships-saved/").data["count"] == 1
    assert api.get("/api/scholarships/").data["results"][0]["is_saved"] is True

    gone = api.delete(f"/api/scholarships-saved/{scholarship.pk}/")
    assert gone.status_code == 200
    assert SavedScholarship.objects.filter(student=student).count() == 0


@pytest.mark.django_db
def test_saved_deadline_shows_up_in_the_calendar(student, scholarship):
    """Событие календаря берётся из стипендии, а не копируется в базу."""
    SavedScholarship.objects.create(student=student, scholarship=scholarship)
    events = events_for(student)
    ours = [event for event in events if event["kind"] == "scholarship"]
    assert len(ours) == 1
    assert ours[0]["date"] == scholarship.deadline.isoformat()
    assert ours[0]["link"] == "/scholarships"


@pytest.mark.django_db
def test_reminder_and_task_appear_before_the_deadline(student, student_user, scholarship, settings):
    """За N дней приходит напоминание и появляется задача роадмапа."""
    from core.models import Notification
    from roadmap.reminders import run_daily

    settings.REMIND_SCHOLARSHIP_DAYS = 10
    SavedScholarship.objects.create(student=student, scholarship=scholarship)

    result = run_daily()
    assert result["scholarship_tasks_created"] == 1
    task = Task.objects.get(student=student, scholarship=scholarship)
    # срок не скопирован: он берётся из самой стипендии (инвариант №4)
    assert task.due_date is None
    assert task.effective_due_date == scholarship.deadline
    assert Notification.objects.filter(recipient=student_user, link="/scholarships").exists()

    # повторный прогон в тот же день не заводит вторую задачу и не шлёт второе письмо
    again = run_daily()
    assert again["scholarship_tasks_created"] == 0
    assert Task.objects.filter(student=student, scholarship=scholarship).count() == 1


@pytest.mark.django_db
def test_moving_the_deadline_moves_the_task(student, scholarship):
    """Сдвинули дедлайн в справочнике — сдвинулся срок задачи у всех."""
    SavedScholarship.objects.create(student=student, scholarship=scholarship)
    task = Task.objects.create(student=student, title="Подать", category="finance", scholarship=scholarship)
    scholarship.deadline = scholarship.deadline + dt.timedelta(days=30)
    scholarship.save(update_fields=["deadline"])
    task.refresh_from_db()
    assert task.effective_due_date == scholarship.deadline


# --- Подбор -----------------------------------------------------------------


@pytest.mark.django_db
def test_pick_says_the_directory_is_empty(api, student_user):
    """Пустой справочник — так и говорится, а не достраивается по памяти."""
    api.force_authenticate(student_user)
    data = api.post("/api/scholarships-pick/").data
    assert data["picks"] == []
    assert "пуст" in data["note"]


@pytest.mark.django_db
def test_pick_names_only_records_from_the_directory(api, student_user, student, scholarship):
    """Инвариант №10: в подборе только стипендии справочника."""
    student.admission.target_country = "Канада"
    student.admission.target_level = "bachelor"
    student.admission.save()
    api.force_authenticate(student_user)
    data = api.post("/api/scholarships-pick/").data
    known = set(Scholarship.objects.values_list("id", flat=True))
    assert data["picks"]
    assert all(row["id"] in known for row in data["picks"])
    assert all(row["name"] == scholarship.name for row in data["picks"])


@pytest.mark.django_db
def test_pick_skips_the_wrong_country(api, student_user, student, scholarship):
    student.admission.target_country = "Германия"
    student.admission.save()
    api.force_authenticate(student_user)
    data = api.post("/api/scholarships-pick/").data
    assert data["picks"] == []
    assert "профиль" in data["note"] or "не нашлось" in data["note"]


@pytest.mark.django_db
def test_pick_is_a_student_screen(api, make_user, scholarship):
    api.force_authenticate(make_user("director_admission"))
    assert api.post("/api/scholarships-pick/").status_code == 403


# --- Загрузка файлом --------------------------------------------------------


HEADER = ["Название стипендии", "Организатор", "Страна", "Дедлайн подачи", "Сумма до", "Тип финансирования"]
MAPPING = {
    "Название стипендии": "name",
    "Организатор": "organizer",
    "Страна": "country",
    "Дедлайн подачи": "deadline",
    "Сумма до": "amount_max",
    "Тип финансирования": "funding_type",
}


@pytest.mark.django_db
def test_import_marks_rows_unverified(db):
    """Инвариант №14: загруженная запись живёт с плашкой, пока её не сверят."""
    rows = [["Chevening", "UK Government", "Великобритания", "01.11.2026", "30000", "полное"]]
    report = import_scholarships(header=HEADER, rows=rows, mapping=MAPPING, dry_run=False)
    assert report.created == 1, report.errors
    row = Scholarship.objects.get(name="Chevening")
    assert row.is_verified is False
    assert row.data_source == CatalogSource.IMPORT
    assert row.deadline == dt.date(2026, 11, 1)
    assert row.funding_type == "full"


@pytest.mark.django_db
def test_import_does_not_duplicate_the_same_file(db):
    rows = [["Chevening", "UK Government", "Великобритания", "01.11.2026", "30000", "полное"]]
    import_scholarships(header=HEADER, rows=rows, mapping=MAPPING, dry_run=False)
    again = import_scholarships(header=HEADER, rows=rows, mapping=MAPPING, dry_run=False)
    assert again.unchanged == 1
    assert Scholarship.objects.filter(name="Chevening").count() == 1


@pytest.mark.django_db
def test_import_names_the_broken_cell_and_keeps_the_rest(db):
    """Одна опечатка не отменяет работу за день: строка названа по номеру."""
    rows = [
        ["Good One", "Fund", "Канада", "01.11.2026", "1000", "полное"],
        ["Bad One", "Fund", "Канада", "вчера", "1000", "полное"],
    ]
    report = import_scholarships(header=HEADER, rows=rows, mapping=MAPPING, dry_run=False)
    assert report.created == 1
    assert len(report.errors) == 1
    assert "строка 3" in report.errors[0]
    assert "Дедлайн" in report.errors[0]


@pytest.mark.django_db
def test_dry_run_writes_nothing(db):
    rows = [["Chevening", "UK Government", "Великобритания", "01.11.2026", "30000", "полное"]]
    report = import_scholarships(header=HEADER, rows=rows, mapping=MAPPING, dry_run=True)
    assert report.created == 1
    assert not Scholarship.objects.exists()


@pytest.mark.django_db
def test_import_refuses_an_unknown_university(db):
    """Вуз не выдумывается: неизвестное название отклоняет строку."""
    header = [*HEADER, "Название вуза"]
    mapping = {**MAPPING, "Название вуза": "university"}
    rows = [["Uni Grant", "Fund", "Канада", "01.11.2026", "1000", "полное", "Неизвестный вуз"]]
    report = import_scholarships(header=header, rows=rows, mapping=mapping, dry_run=False)
    assert report.created == 0
    assert "нет в справочнике" in report.errors[0]

    University.objects.create(name="Неизвестный вуз", country="Канада")
    ok = import_scholarships(header=header, rows=rows, mapping=mapping, dry_run=False)
    assert ok.created == 1


@pytest.mark.django_db
def test_only_the_administrator_uploads_the_file(api, make_user):
    """Файлы грузит администратор (фаза 35) — директору 403 и подсказка."""
    api.force_authenticate(make_user("director_admission"))
    answer = api.post("/api/scholarships-import/", {}, format="multipart")
    assert answer.status_code == 403
    assert "администратор" in answer.data["detail"]


# --- Сводка директору -------------------------------------------------------


@pytest.mark.django_db
def test_attention_shows_who_saved_and_who_did_not(api, make_user, student, scholarship):
    SavedScholarship.objects.create(student=student, scholarship=scholarship)
    api.force_authenticate(make_user("director_admission"))
    data = api.get("/api/scholarships-attention/").data
    assert data["total_scholarships"] == 1
    assert data["saved_by"][0]["saved"] == 1
    assert data["deadline_this_week"] == [] or data["deadline_this_week"][0]["student"] == student.pk
    assert data["without_saved"] == []


@pytest.mark.django_db
def test_attention_is_closed_to_other_directors(api, make_user):
    api.force_authenticate(make_user("director_sport"))
    assert api.get("/api/scholarships-attention/").status_code == 403


# --- Реестр -----------------------------------------------------------------


def test_registry_owns_the_scholarship_fields():
    """Поля стипендии принадлежат домену «Поступление», и это не дубль."""
    from core.domains import can_delete, can_write, can_write_for, domain_of_model

    assert domain_of_model("universities.Scholarship").code == "admission"
    assert can_write("director_admission", "universities.Scholarship", "deadline")
    assert not can_write("director_exam", "universities.Scholarship", "deadline")
    # администратор пишет за домен только через загрузку файла
    assert not can_write("admin", "universities.Scholarship", "deadline")
    assert can_write_for("admin", "admission", "universities.Scholarship", "deadline")
    assert can_delete("director_admission", "universities.Scholarship")
