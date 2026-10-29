"""Стипендии: загрузка файлом и дедлайн в одном месте.

Экрана справочника и раздела ученика нет (ручки сняты 29.10.2026), данные
остались. Проверяем то, из-за чего они могли бы соврать ученику:

* загруженная файлом запись приходит неподтверждённой (инвариант №14);
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


# --- Дедлайн в календаре и задачах ---------------------------------------


@pytest.mark.django_db
def test_saved_deadline_shows_up_in_the_calendar(student, scholarship, scholarships_on_screen):
    """Событие календаря берётся из стипендии, а не копируется в базу."""
    SavedScholarship.objects.create(student=student, scholarship=scholarship)
    events = events_for(student)
    ours = [event for event in events if event["kind"] == "scholarship"]
    assert len(ours) == 1
    assert ours[0]["date"] == scholarship.deadline.isoformat()
    assert ours[0]["link"] == "/scholarships"


@pytest.mark.django_db
def test_reminder_and_task_appear_before_the_deadline(student, student_user, scholarship, scholarships_on_screen):
    """За N дней приходит напоминание и появляется задача роадмапа."""
    from core.models import Notification, SchoolRule
    from roadmap.reminders import run_daily

    SchoolRule.objects.create(code="remind_scholarship_days", value=10)
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


@pytest.fixture
def scholarships_on_screen(monkeypatch):
    """Стипендии снова на экране ученика: механизм дедлайнов цел и включится вместе с разделом."""
    from core import parallels

    monkeypatch.setattr(parallels, "HIDDEN_PATHS", parallels.HIDDEN_PATHS - {"/scholarships"})


@pytest.mark.django_db
def test_hidden_scholarships_give_no_events_tasks_or_reminders(student, student_user, scholarship):
    """Стипендий у ученика нет (решение владельца, 07.10.2026): ни события, ни задачи, ни письма в никуда."""
    from core.models import Notification, SchoolRule
    from roadmap.reminders import run_daily

    SchoolRule.objects.create(code="remind_scholarship_days", value=10)
    SavedScholarship.objects.create(student=student, scholarship=scholarship)
    assert [event for event in events_for(student) if event["kind"] == "scholarship"] == []
    assert run_daily()["scholarship_tasks_created"] == 0
    assert not Task.objects.filter(student=student, scholarship=scholarship).exists()
    assert not Notification.objects.filter(recipient=student_user, link="/scholarships").exists()


@pytest.mark.django_db
def test_moving_the_deadline_moves_the_task(student, scholarship):
    """Сдвинули дедлайн в справочнике — сдвинулся срок задачи у всех."""
    SavedScholarship.objects.create(student=student, scholarship=scholarship)
    task = Task.objects.create(student=student, title="Подать", category="finance", scholarship=scholarship)
    scholarship.deadline = scholarship.deadline + dt.timedelta(days=30)
    scholarship.save(update_fields=["deadline"])
    task.refresh_from_db()
    assert task.effective_due_date == scholarship.deadline


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


# --- Реестр -----------------------------------------------------------------


def test_registry_owns_the_scholarship_fields():
    """Поля стипендии принадлежат домену «Поступление», и это не дубль."""
    from core.domains import can_delete, can_write, can_write_for, domain_of_model

    assert domain_of_model("universities.Scholarship").code == "admission"
    assert can_write("director_admission", "universities.Scholarship", "deadline")
    assert not can_write("director_exam", "universities.Scholarship", "deadline")
    # администратор пишет во все домены (фаза 68); загрузка «за домен»
    # по-прежнему не выходит за выбранный домен
    assert can_write("admin", "universities.Scholarship", "deadline")
    assert can_write_for("admin", "admission", "universities.Scholarship", "deadline")
    assert not can_write_for("admin", "exam", "universities.Scholarship", "deadline")
    assert can_delete("director_admission", "universities.Scholarship")


def test_deadline_tone_follows_the_school_setting():
    """Цвет чипа дедлайна считает сервер: сегодня — красный, в окне «срок горит» — жёлтый."""
    import datetime as dt

    from universities.scholarships import deadline_tone

    today = dt.date(2026, 10, 5)
    assert deadline_tone(None, 7, today) == "neutral"
    assert deadline_tone(today - dt.timedelta(days=1), 7, today) == "neutral"
    assert deadline_tone(today, 7, today) == "bad"
    assert deadline_tone(today + dt.timedelta(days=7), 7, today) == "warn"
    assert deadline_tone(today + dt.timedelta(days=8), 7, today) == "neutral"
    assert deadline_tone(today + dt.timedelta(days=8), 10, today) == "warn", "порог поменяли — окно шире"
