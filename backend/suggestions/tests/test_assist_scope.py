"""Объяснение подбора и вопросы по эссе — только про видимых учеников.

Обе ручки проверяли принадлежность лишь у ученика; сотрудник с границей
видимости получал доступ к любому ученику школы по id. Куратору эти
ручки закрывает шлюз, поэтому сама проверка области видимости прогоняется
через вьюху напрямую, без промежуточного слоя: так проверяется правило,
которое достанется следующей роли с границей.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from accounts.curators import assign
from accounts.tests.test_curator_role_matrix import _student
from roadmap.models import Essay
from students.models import StudyGroup
from suggestions import views
from universities.models import Program, University

MONTH_AGO = dt.timedelta(days=30)


@pytest.fixture
def world(make_user):
    """Куратор со своим учеником, чужой ученик, по эссе у каждого, одна программа."""
    admin = make_user("admin", "admin-assist@example.kz")
    curator = make_user("curator", "curator-assist@example.kz", full_name="Куратор Границы")
    own_group = StudyGroup.objects.create(code="OWN", grade=11)
    own = _student("own-assist@example.kz", own_group, "Свой")
    assign(group=own_group, curator=curator, since=timezone.localdate() - MONTH_AGO, actor=admin)
    alien = _student("alien-assist@example.kz", StudyGroup.objects.create(code="ALIEN", grade=11), "Чужой")
    university = University.objects.create(name="Тестовый университет", country="Казахстан")
    program = Program.objects.create(university=university, name="Информатика")
    return SimpleNamespace(
        curator=curator,
        own=own,
        alien=alien,
        program=program,
        own_essay=Essay.objects.create(student=own, title="Своё эссе"),
        alien_essay=Essay.objects.create(student=alien, title="Чужое эссе"),
    )


@pytest.fixture
def no_background(monkeypatch):
    """Фоновые задачи не запускаются: проверяется граница, а не модель."""
    stub = lambda **kwargs: SimpleNamespace(id="task-stub")  # noqa: E731
    monkeypatch.setattr(views.background.explain_match, "delay", stub)
    monkeypatch.setattr(views.background.essay_questions, "delay", stub)


def _call(view, user, path: str, body: dict):
    request = APIRequestFactory().post(path, body, format="json")
    force_authenticate(request, user=user)
    return view(request)


def _explain(user, student, program):
    body = {"student": student.pk, "program": program.pk}
    return _call(views.explain_match, user, "/api/commands/explain-match/", body)


@pytest.mark.django_db
def test_explain_match_respects_the_curator_boundary(world, no_background):
    assert _explain(world.curator, world.own, world.program).status_code == 202
    assert _explain(world.curator, world.alien, world.program).status_code == 404


@pytest.mark.django_db
def test_essay_questions_respect_the_curator_boundary(world, no_background):
    body = {"essay": world.own_essay.pk, "prompt": "О чём спросить?"}
    assert _call(views.essay_questions, world.curator, "/api/commands/essay-questions/", body).status_code == 202
    body = {"essay": world.alien_essay.pk, "prompt": "О чём спросить?"}
    assert _call(views.essay_questions, world.curator, "/api/commands/essay-questions/", body).status_code == 404


@pytest.mark.django_db
def test_the_gate_still_closes_both_commands_to_the_curator(world):
    client = APIClient()
    client.force_login(world.curator)
    body = {"student": world.own.pk, "program": world.program.pk}
    assert client.post("/api/commands/explain-match/", body, format="json").status_code == 403
    body = {"essay": world.own_essay.pk, "prompt": "?"}
    assert client.post("/api/commands/essay-questions/", body, format="json").status_code == 403


@pytest.mark.django_db
def test_director_reaches_any_student(world, no_background, make_user):
    director = make_user("director_admission", "asem-assist@example.kz")
    assert _explain(director, world.alien, world.program).status_code == 202
