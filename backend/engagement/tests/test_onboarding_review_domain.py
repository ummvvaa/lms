"""Ответ анкеты первого входа подтверждает директор своего домена или куратор.

`onboarding_review` отбивала только ученика: директор любого домена
подтверждал или правил ответ, который ляжет в поле чужого домена, а куратор
видел список ответов всей школы. Инвариант №1: у поля один владелец —
он и решает; администратор решает за любой домен с пометкой в журнале.
Ответы по экзаменам подтверждает куратор группы (Кымбат ученические правки
не разбирает, решение владельца 25.10.2026) — только у своих учеников.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.curators import assign
from engagement import onboarding
from students.models import Student, StudyGroup


@pytest.fixture
def answers(student):
    """Два ответа одного ученика: в домен поступления и в домен экзаменов."""
    onboarding.answer(student, code="target_country", value="Казахстан")
    onboarding.answer(student, code="gpa", value="3.6")
    by_code = {row["question"]: row["id"] for row in onboarding.pending_for("admin")}
    return by_code["target_country"], by_code["gpa"]


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_a_director_reviews_only_answers_of_own_domain(make_user, answers):
    admission_answer, exam_answer = answers
    asem = _client(make_user("director_admission", "asem-review@example.kz"))
    kymbat = _client(make_user("director_exam", "kymbat-review@example.kz"))
    confirm = {"decision": "confirm"}

    assert kymbat.post(f"/api/onboarding/pending/{admission_answer}/", confirm, format="json").status_code == 403
    assert asem.post(f"/api/onboarding/pending/{exam_answer}/", confirm, format="json").status_code == 403
    assert asem.post(f"/api/onboarding/pending/{admission_answer}/", confirm, format="json").status_code == 200
    assert kymbat.post(f"/api/onboarding/pending/{exam_answer}/", confirm, format="json").status_code == 200


@pytest.mark.django_db
def test_admin_reviews_any_domain(make_user, answers):
    admission_answer, exam_answer = answers
    admin = _client(make_user("admin", "admin-review@example.kz"))
    for pk in (admission_answer, exam_answer):
        assert admin.post(f"/api/onboarding/pending/{pk}/", {"decision": "decline"}, format="json").status_code == 200


@pytest.mark.django_db
def test_pending_list_is_by_domain_and_empty_for_roles_without_one(make_user, answers):
    admission_answer, exam_answer = answers
    assert [row["id"] for row in onboarding.pending_for("director_admission")] == [admission_answer]
    assert [row["id"] for row in onboarding.pending_for("director_exam")] == [exam_answer]
    assert onboarding.pending_for("curator") == []
    assert {row["id"] for row in onboarding.pending_for("admin")} == {admission_answer, exam_answer}


def _curator_of(make_user, group, email: str):
    admin = make_user("admin", f"admin-{email}")
    user = make_user("curator", email)
    assign(group=group, curator=user, since=timezone.localdate() - dt.timedelta(days=30), actor=admin)
    return user


@pytest.mark.django_db
def test_curator_sees_and_reviews_exam_answers_of_own_group_only(make_user, student, answers):
    admission_answer, exam_answer = answers
    own = _curator_of(make_user, student.group, "own-curator@example.kz")
    stranger = _curator_of(make_user, StudyGroup.objects.create(code="G02", parallel=11), "other-curator@example.kz")

    assert [row["id"] for row in onboarding.pending_for("curator", own)] == [exam_answer]
    assert onboarding.pending_for("curator", stranger) == []

    confirm = {"decision": "confirm"}
    # ученик чужой группы куратору не виден — 404; домен без поручения — 403
    assert _client(stranger).post(f"/api/onboarding/pending/{exam_answer}/", confirm, format="json").status_code == 404
    assert _client(own).post(f"/api/onboarding/pending/{admission_answer}/", confirm, format="json").status_code == 403
    assert _client(own).get("/api/onboarding/pending/").json()[0]["id"] == exam_answer
    assert _client(own).post(f"/api/onboarding/pending/{exam_answer}/", confirm, format="json").status_code == 200
    assert onboarding.pending_for("curator", own) == []
    assert Student.objects.get(pk=student.pk).exam.gpa is not None
