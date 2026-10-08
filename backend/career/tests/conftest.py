"""Маленькая школа для проверок профтеста.

Предмет профориентации, учитель с журналом в BOSTON (11), второй учитель
без профориентации, куратор BOSTON, Асем, Кымбат, администратор; ученики
BOSTON и один в RIGA (9) — все с учётными записями.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from academics.cohorts import group_cohort
from academics.models import Course, Scheme, Subject, TeacherProfile
from accounts.curators import assign
from accounts.models import Role, User
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)
from suggestions.providers import Completion, LLMUnavailable, Usage

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "guides" / "examples" / "karta_interesov.xlsx"


class FakeProvider:
    """Провайдер, отвечающий заранее заданным разбором."""

    name = "fake"

    def __init__(self, parsed=None, *, fail: bool = False) -> None:
        self.parsed, self.fail = parsed, fail
        self.calls: list[dict] = []

    def is_configured(self) -> bool:
        return True

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise LLMUnavailable("провайдер вернул 503")
        return Completion(
            content="",
            parsed=self.parsed,
            model="fake-1",
            external_id="msg_1",
            usage=Usage(100, 50),
            raw={"id": "msg_1"},
        )


@pytest.fixture
def fake(monkeypatch):
    def install(provider):
        monkeypatch.setattr("suggestions.providers.get_provider", lambda: provider)
        monkeypatch.setattr("suggestions.llm.get_provider", lambda: provider)
        return provider

    return install


def make_student(group, last, first, email, make_user) -> Student:
    student = Student.objects.create(last_name=last, first_name=first, email=email, group=group, graduation_year=2027)
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=student)
    student.user = make_user("student", email, full_name=f"{last} {first}")
    student.save(update_fields=["user"])
    return student


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def career_subject(db) -> Subject:
    return Subject.objects.create(
        code="career", title="Профориентация", short_title="Профор.", scheme=Scheme.FO, in_lms=True, is_career=True
    )


@pytest.fixture
def boston(db) -> StudyGroup:
    return StudyGroup.objects.create(code="BOSTON", parallel=11)


@pytest.fixture
def riga(db) -> StudyGroup:
    return StudyGroup.objects.create(code="RIGA", parallel=9)


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin", "admin.career@example.kz", full_name="Администратор", is_staff=True)


@pytest.fixture
def asem(make_user) -> User:
    return make_user("director_admission", "asem.career@example.kz", full_name="Асем")


@pytest.fixture
def kymbat(make_user) -> User:
    return make_user("director_exam", "kymbat.career@example.kz", full_name="Кымбат")


@pytest.fixture
def curator(make_user, boston, admin) -> User:
    user = make_user("curator", "curator.career@example.kz", full_name="Асель Куратор")
    assign(group=boston, curator=user, since=timezone.localdate() - dt.timedelta(days=70), actor=admin)
    return user


@pytest.fixture
def teacher(make_user, career_subject, boston, riga) -> User:
    """Учитель профориентации: журналы в BOSTON и RIGA."""
    user = make_user(Role.TEACHER, "career.teacher@example.kz", full_name="Жанар Профориентатор")
    profile = TeacherProfile.objects.create(user=user, room="101")
    profile.subjects.set([career_subject])
    Course.objects.create(subject=career_subject, teacher=user, cohort=group_cohort(boston))
    Course.objects.create(subject=career_subject, teacher=user, cohort=group_cohort(riga))
    return user


@pytest.fixture
def other_teacher(make_user, boston) -> User:
    user = make_user(Role.TEACHER, "other.teacher@example.kz", full_name="Сапарова Гульнара")
    subject = Subject.objects.create(code="alg", title="Алгебра", short_title="Алгебра")
    TeacherProfile.objects.create(user=user, room="204").subjects.set([subject])
    Course.objects.create(subject=subject, teacher=user, cohort=group_cohort(boston))
    return user


@pytest.fixture
def pupils(boston, riga, make_user) -> dict[str, Student]:
    return {
        "aliya": make_student(boston, "Ахметова", "Алия", "aliya.career@example.kz", make_user),
        "damir": make_student(boston, "Сериков", "Дамир", "damir.career@example.kz", make_user),
        "nurai": make_student(riga, "Абдрахман", "Нурай", "nurai.career@example.kz", make_user),
    }


@pytest.fixture
def example_bytes() -> bytes:
    return EXAMPLE.read_bytes()


@pytest.fixture
def karta(teacher, example_bytes):
    """«Карта интересов», загруженная учителем через API."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    client = login(teacher)
    upload = SimpleUploadedFile("karta.xlsx", example_bytes)
    response = client.post("/api/career/tests/", {"file": upload}, format="multipart")
    assert response.status_code == 201, response.content
    from career.models import CareerTest

    return CareerTest.objects.get(pk=response.data["id"])


def activate(test, groups: list[dict], *, by) -> None:
    client = login(by)
    assert client.patch(f"/api/career/tests/{test.pk}/", {"is_active": True}, format="json").status_code == 200
    response = client.put(f"/api/career/tests/{test.pk}/assignments/", {"groups": groups}, format="json")
    assert response.status_code == 200, response.content


def answer_all(client, attempt: int, pick) -> dict:
    """Ответить на все вопросы: `pick(number) → подпись варианта`."""
    payload = client.get(f"/api/career/my/attempts/{attempt}/").data
    by_label = {o["label"]: o["id"] for o in payload["options"]}
    answers = [{"item": item["id"], "option": by_label[pick(item["number"])]} for item in payload["items"]]
    response = client.post(f"/api/career/my/attempts/{attempt}/answers/", {"answers": answers}, format="json")
    assert response.status_code == 200, response.content
    return response.data
