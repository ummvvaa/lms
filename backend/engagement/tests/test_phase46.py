"""Фаза 46, часть 2: достижения-бейджи.

Главная проверка — инвариант №12: бейдж даётся за действия. Список мер
проверяется словами, а не выборкой из самого списка: иначе проверка
согласилась бы с любой новой мерой, включая «балл IELTS».
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from engagement.models import Badge, BadgeAward, BadgeMetric


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


# --- Инвариант №12 ----------------------------------------------------------


def test_no_measure_is_about_results():
    """В наборе мер нет ни балла, ни GPA, ни статуса, ни места в рейтинге."""
    forbidden = ("ielts", "sat", "toefl", "act", "gpa", "балл", "score", "статус", "рейтинг", "место")
    for value, title in BadgeMetric.choices:
        text = f"{value} {title}".lower()
        for word in forbidden:
            assert word not in text, f"мера «{title}» ({value}) считает результат, а не действие"
    assert len(BadgeMetric.choices) >= 8, "перечень мер не разобрался — проверка ничего не значит"


@pytest.mark.django_db
def test_badge_for_an_exam_score_is_refused(api, make_user):
    """Приёмка фазы: бейдж за балл экзамена завести нельзя."""
    api.force_authenticate(make_user("director_behavior"))
    answer = api.post(
        "/api/badges/",
        {"code": "ielts_seven", "name": "IELTS 7.0", "metric": "ielts_score", "threshold": 7},
        format="json",
    )
    assert answer.status_code == 400
    assert "metric" in answer.data


# --- Справочник -------------------------------------------------------------


@pytest.mark.django_db
def test_ten_badges_are_seeded(db):
    assert Badge.objects.count() >= 10
    assert Badge.objects.filter(code="week_streak", threshold=7).exists()


@pytest.mark.django_db
def test_school_director_keeps_the_badges(api, make_user):
    api.force_authenticate(make_user("director_behavior"))
    made = api.post(
        "/api/badges/",
        {"code": "probe_badge", "name": "Проверочный", "metric": "tasks_done", "threshold": 2},
        format="json",
    )
    assert made.status_code == 201, made.data
    assert api.patch(f"/api/badges/{made.data['id']}/", {"threshold": 3}).status_code == 200
    assert api.delete(f"/api/badges/{made.data['id']}/").status_code == 204


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["director_exam", "director_talent", "admin", "student"])
def test_others_do_not_keep_the_badges(api, make_user, role):
    api.force_authenticate(make_user(role))
    assert api.get("/api/badges/").status_code == 200
    refused = api.post("/api/badges/", {"code": "x", "name": "X", "metric": "tasks_done"}, format="json")
    assert refused.status_code == 403


# --- Прогресс и выдача ------------------------------------------------------


@pytest.mark.django_db
def test_locked_badges_are_shown_with_their_condition(api, student_user):
    """Закрытые не прячутся: видно, что можно получить и сколько осталось."""
    data = api if api.force_authenticate(student_user) is None else api
    state = data.get("/api/achievements/").data
    assert state["total"] >= 10
    assert state["earned"] == 0
    locked = state["badges"][0]
    assert locked["earned"] is False
    assert locked["condition"]
    assert locked["progress"].endswith(f"из {locked['threshold']}")


@pytest.mark.django_db
def test_progress_grows_with_actions_and_the_badge_is_given(api, student_user, student):
    """Прогресс растёт по действиям, а на пороге бейдж выдаётся."""
    from engagement.models import XPKind
    from engagement.scoring import award
    from roadmap.models import Task, TaskCategory

    badge = Badge.objects.get(code="first_plan")
    badge.metric = BadgeMetric.TASKS_DONE
    badge.threshold = 2
    badge.save(update_fields=["metric", "threshold"])

    api.force_authenticate(student_user)
    for number in (1, 2):
        task = Task.objects.create(student=student, title=f"Задача {number}", category=TaskCategory.TEST)
        award(student, kind=XPKind.TASK_DONE, object_label="roadmap.Task", object_id=str(task.pk))
        state = api.get("/api/achievements/").data
        row = next(item for item in state["badges"] if item["code"] == "first_plan")
        assert row["value"] == number
        assert row["progress"] == f"{number} из 2"
        assert row["earned"] is (number == 2)

    assert BadgeAward.objects.filter(student=student, badge=badge).exists()


@pytest.mark.django_db
def test_award_is_given_once(api, student_user, student):
    from engagement import badges as badge_service

    badge = Badge.objects.get(code="onboarding")
    badge.metric = BadgeMetric.TASKS_DONE
    badge.threshold = 0
    badge.save(update_fields=["metric", "threshold"])

    badge_service.refresh(student)
    badge_service.refresh(student)
    assert BadgeAward.objects.filter(student=student, badge=badge).count() == 1


@pytest.mark.django_db
def test_hidden_badge_is_not_shown_to_the_student(api, student_user):
    Badge.objects.filter(code="reader").update(is_active=False)
    api.force_authenticate(student_user)
    codes = [row["code"] for row in api.get("/api/achievements/").data["badges"]]
    assert "reader" not in codes


@pytest.mark.django_db
def test_achievements_are_a_student_screen(api, make_user):
    api.force_authenticate(make_user("director_behavior"))
    assert api.get("/api/achievements/").status_code == 403
